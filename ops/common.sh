#!/usr/bin/env bash
set -euo pipefail

OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AOP_DIR="$(cd "${OPS_DIR}/.." && pwd)"
ROOT_DIR="$(cd "${AOP_DIR}/.." && pwd)"
HERDMASTER_DIR="${ROOT_DIR}/HerdMaster"

RUN_DIR="${AOP_OPS_RUN_DIR:-/tmp/aop-ops-run}"
LOG_DIR="${OPS_DIR}/logs"
export AOP_OPS_RUNTIME_DIR="${HOME}/.aop-runtime"
RUNTIME_DIR="${AOP_OPS_RUNTIME_DIR}"
mkdir -p "${RUN_DIR}" "${RUNTIME_DIR}/herdmaster" "${LOG_DIR}" "${RUNTIME_DIR}"
chmod 700 "${RUN_DIR}" "${RUNTIME_DIR}" 2>/dev/null || true

AOP_DEPLOY_DIR="${AOP_DIR}/deploy"
AOP_ENV_FILE="${AOP_DEPLOY_DIR}/.env"
AOP_COMPOSE="${AOP_DEPLOY_DIR}/docker-compose.yml"
OBS_DIR="${HERDMASTER_DIR}/deploy/observability"
OBS_COMPOSE="${OBS_DIR}/docker-compose.yml"

HERDMASTER_CONFIG="${RUNTIME_DIR}/herdmaster.config.toml"
HERDMASTER_TOKEN_FILE="${RUNTIME_DIR}/herdmaster.token"
# Container-readable (644) copy of the HerdMaster API token, bind-mounted into the
# Prometheus container so its credentials_file stays in sync with the live token.
PROM_TOKEN_FILE="${RUNTIME_DIR}/prometheus.token"
OBS_RUNTIME_DIR="${RUNTIME_DIR}/observability"
HERDMASTER_PID_FILE="${RUN_DIR}/herdmaster.pid"
AOP_API_PID_FILE="${RUN_DIR}/aop-control-plane.pid"
AOP_WEB_PID_FILE="${RUN_DIR}/aop-frontend.pid"

LOCAL_HOST="127.0.0.1"
RESOLVED_PORTS=()
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
REDIS_PORT="${REDIS_PORT:-6379}"
HERDMASTER_PORT="${HERDMASTER_PORT:-8080}"
AOP_API_PORT="${AOP_API_PORT:-8090}"
AOP_WEB_PORT="${AOP_WEB_PORT:-13000}"
GRAFANA_PORT="${GRAFANA_PORT:-3000}"
PROMETHEUS_PORT="${PROMETHEUS_PORT:-9090}"
ALERTMANAGER_PORT="${ALERTMANAGER_PORT:-9093}"
BLACKBOX_PORT="${BLACKBOX_PORT:-9115}"
REMEDIATION_PORT="${REMEDIATION_PORT:-9099}"

log() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

warn() {
  printf '[%s] WARN: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2
}

die() {
  printf '[%s] ERROR: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

load_aop_env() {
  [[ -f "${AOP_ENV_FILE}" ]] || die "missing ${AOP_ENV_FILE}"
  set -a
  # shellcheck disable=SC1090
  source "${AOP_ENV_FILE}"
  set +a
  POSTGRES_PORT="${POSTGRES_PORT:-5432}"
  REDIS_PORT="${REDIS_PORT:-6379}"
  HERDMASTER_PORT="${HERDMASTER_PORT:-8080}"
  AOP_API_PORT="${AOP_API_PORT:-8090}"
  AOP_WEB_PORT="${AOP_WEB_PORT:-13000}"
  GRAFANA_PORT="${GRAFANA_PORT:-3000}"
  PROMETHEUS_PORT="${PROMETHEUS_PORT:-9090}"
  ALERTMANAGER_PORT="${ALERTMANAGER_PORT:-9093}"
  BLACKBOX_PORT="${BLACKBOX_PORT:-9115}"
  REMEDIATION_PORT="${REMEDIATION_PORT:-9099}"
  export POSTGRES_PORT REDIS_PORT HERDMASTER_PORT AOP_API_PORT AOP_WEB_PORT
  export GRAFANA_PORT PROMETHEUS_PORT ALERTMANAGER_PORT BLACKBOX_PORT REMEDIATION_PORT
  : "${POSTGRES_USER:?POSTGRES_USER missing}"
  : "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD missing}"
  : "${POSTGRES_DB:?POSTGRES_DB missing}"
  : "${REDIS_PASSWORD:?REDIS_PASSWORD missing}"
  export DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${LOCAL_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
  export REDIS_URL="redis://:${REDIS_PASSWORD}@${LOCAL_HOST}:${REDIS_PORT}/0"
}

docker_compose_aop() {
  docker compose --env-file "${AOP_ENV_FILE}" -f "${AOP_COMPOSE}" "$@"
}

docker_compose_obs() {
  docker compose -f "${OBS_COMPOSE}" "$@"
}

observability_network_mode() {
  local mode
  mode="$(docker_compose_obs config 2>/dev/null | awk '
    $1 == "network_mode:" {
      gsub(/"/, "", $2)
      print $2
    }
  ' | sort -u | tr '\n' ' ')"
  if [[ "${mode}" == *host* ]]; then
    printf '%s\n' "host"
  else
    printf '%s\n' "published"
  fi
}

http_code() {
  local url="$1"
  shift || true
  curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "$@" "${url}" 2>/dev/null || true
}

wait_until() {
  local name="$1"
  local attempts="$2"
  local sleep_s="$3"
  shift 3
  local i
  for ((i = 1; i <= attempts; i++)); do
    if "$@" >/dev/null 2>&1; then
      log "${name}: healthy"
      return 0
    fi
    log "${name}: waiting (${i}/${attempts})"
    sleep "${sleep_s}"
  done
  return 1
}

wait_http_200() {
  local name="$1"
  local url="$2"
  shift 2
  local i
  local code
  for ((i = 1; i <= 60; i++)); do
    code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "$@" "${url}" 2>/dev/null || true)"
    if [[ "${code}" == "200" ]]; then
      log "${name}: healthy"
      return 0
    fi
    log "${name}: waiting (${i}/60, http=${code:-none})"
    sleep 2
  done
  return 1
}

wait_observability_http_200() {
  local name="$1"
  local url="$2"
  local mode
  mode="$(observability_network_mode)"
  log "${name}: observability probe mode=${mode} url=${url}"
  wait_http_200 "${name}" "${url}"
}

port_listening() {
  local port="$1"
  ss -ltn "sport = :${port}" 2>/dev/null | grep -q ":${port}"
}

port_reserved() {
  local port="$1"
  local reserved
  for reserved in "${RESOLVED_PORTS[@]}"; do
    [[ "${reserved}" == "${port}" ]] && return 0
  done
  return 1
}

resolve_port() {
  local label="$1"
  local native_port="$2"
  local var_name="$3"
  local candidate="${!var_name:-${native_port}}"

  if [[ "${candidate}" != "${native_port}" ]]; then
    export "${var_name}=${candidate}"
    RESOLVED_PORTS+=("${candidate}")
    log "${label}: usando porta ${candidate} via ${var_name}"
    return 0
  fi

  while port_listening "${candidate}" || port_reserved "${candidate}"; do
    candidate=$((candidate + 5))
  done

  if [[ "${candidate}" != "${native_port}" ]]; then
    log "${label}: porta nativa ${native_port} ocupada -> usando ${candidate} (politica +5)"
  else
    log "${label}: usando porta nativa ${native_port}"
  fi

  export "${var_name}=${candidate}"
  RESOLVED_PORTS+=("${candidate}")
}

resolve_runtime_ports() {
  resolve_port "Postgres" "5432" "POSTGRES_PORT"
  resolve_port "Redis" "6379" "REDIS_PORT"
  resolve_port "HerdMaster" "8080" "HERDMASTER_PORT"
  resolve_port "AOP control-plane" "8090" "AOP_API_PORT"
  resolve_port "AOP frontend" "13000" "AOP_WEB_PORT"
  resolve_port "Nginx Load Balancer" "8000" "NGINX_PORT"
  export DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${LOCAL_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
  export REDIS_URL="redis://:${REDIS_PASSWORD}@${LOCAL_HOST}:${REDIS_PORT}/0"
}

resolve_observability_ports() {
  GRAFANA_PORT="${GRAFANA_PORT:-3000}"
  if [[ "${GRAFANA_PORT}" != "3000" ]]; then
    warn "Grafana: ignorando GRAFANA_PORT=${GRAFANA_PORT}; Task P fixa Grafana em 3000"
  fi
  export GRAFANA_PORT=3000
  RESOLVED_PORTS+=("${GRAFANA_PORT}")
  log "Grafana: usando porta fixa 3000"
  resolve_port "Prometheus" "9090" "PROMETHEUS_PORT"
  resolve_port "Alertmanager" "9093" "ALERTMANAGER_PORT"
  resolve_port "Blackbox exporter" "9115" "BLACKBOX_PORT"
  resolve_port "Remediation webhook" "9099" "REMEDIATION_PORT"
}

pid_alive() {
  local pid="$1"
  [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1
}

pid_from_file() {
  local file="$1"
  [[ -f "${file}" ]] || return 1
  local pid
  pid="$(tr -dc '0-9' < "${file}")"
  [[ -n "${pid}" ]] || return 1
  printf '%s\n' "${pid}"
}

stop_pid_file() {
  local label="$1"
  local file="$2"
  local pid=""
  if pid="$(pid_from_file "${file}" 2>/dev/null)" && pid_alive "${pid}"; then
    log "stopping ${label} pid=${pid}"
    kill -TERM -- "-${pid}" >/dev/null 2>&1 || true
    kill -TERM "${pid}" >/dev/null 2>&1 || true
    local i
    for ((i = 1; i <= 20; i++)); do
      pid_alive "${pid}" || break
      sleep 1
    done
    if pid_alive "${pid}"; then
      warn "${label} did not stop after SIGTERM; sending SIGKILL"
      kill -KILL -- "-${pid}" >/dev/null 2>&1 || true
      kill -KILL "${pid}" >/dev/null 2>&1 || true
    fi
  else
    log "${label}: no managed process"
  fi
  rm -f "${file}"
}

kill_port_processes() {
  local label="$1"
  local port="$2"
  local pids
  pids="$(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]*$//' || true)"
  if [[ -z "${pids}" ]] && command -v fuser >/dev/null 2>&1; then
    pids="$(fuser -n tcp "${port}" 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]*$//' || true)"
  fi
  if [[ -n "${pids}" ]]; then
    warn "stopping unmanaged ${label} listener(s) on ${port}: ${pids}"
    # shellcheck disable=SC2086
    kill -TERM ${pids} >/dev/null 2>&1 || true
    sleep 2
    pids="$(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]*$//' || true)"
    if [[ -z "${pids}" ]] && command -v fuser >/dev/null 2>&1; then
      pids="$(fuser -n tcp "${port}" 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]*$//' || true)"
    fi
    if [[ -n "${pids}" ]]; then
      # shellcheck disable=SC2086
      kill -KILL ${pids} >/dev/null 2>&1 || true
    fi
  fi
}

record_listener_pid() {
  local label="$1"
  local port="$2"
  local file="$3"
  local pid
  pid="$(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null | head -n 1 || true)"
  if [[ -z "${pid}" ]] && command -v fuser >/dev/null 2>&1; then
    pid="$(fuser -n tcp "${port}" 2>/dev/null | tr ' ' '\n' | sed '/^$/d' | head -n 1 || true)"
  fi
  if [[ -n "${pid}" ]]; then
    printf '%s\n' "${pid}" > "${file}"
    log "${label}: recorded listener pid=${pid}"
  fi
}

ensure_herdmaster_token() {
  if [[ ! -f "${HERDMASTER_TOKEN_FILE}" ]]; then
    umask 077
    if command -v openssl >/dev/null 2>&1; then
      openssl rand -hex 24 > "${HERDMASTER_TOKEN_FILE}"
    else
      date +%s%N | sha256sum | awk '{print $1}' > "${HERDMASTER_TOKEN_FILE}"
    fi
  fi
  chmod 600 "${HERDMASTER_TOKEN_FILE}" 2>/dev/null || true
}

herdmaster_token() {
  ensure_herdmaster_token
  tr -d '\r\n' < "${HERDMASTER_TOKEN_FILE}"
}

# Writes a container-readable (644, no trailing newline) copy of the HerdMaster API
# token for Prometheus credentials_file. Prometheus runs as 'nobody' inside the
# container and cannot read the canonical 600 token file, hence this synced copy.
write_prometheus_token() {
  ensure_herdmaster_token
  printf '%s' "$(herdmaster_token)" > "${PROM_TOKEN_FILE}"
  chmod 644 "${PROM_TOKEN_FILE}" 2>/dev/null || true
}

render_observability_configs() {
  local prom_dir="${OBS_RUNTIME_DIR}/prometheus"
  local alertmanager_dir="${OBS_RUNTIME_DIR}/alertmanager"
  local grafana_datasources_dir="${OBS_RUNTIME_DIR}/grafana/datasources"
  local grafana_dashboards_dir="${OBS_RUNTIME_DIR}/grafana/dashboards"
  mkdir -p "${prom_dir}" "${alertmanager_dir}" "${grafana_datasources_dir}" "${grafana_dashboards_dir}"

  sed \
    -e "s/localhost:8080/localhost:${HERDMASTER_PORT}/g" \
    -e "s/localhost:8090/localhost:${AOP_API_PORT}/g" \
    -e "s/localhost:9090/localhost:${PROMETHEUS_PORT}/g" \
    -e "s/localhost:9093/localhost:${ALERTMANAGER_PORT}/g" \
    -e "s/localhost:9099/localhost:${REMEDIATION_PORT}/g" \
    -e "s/localhost:9115/localhost:${BLACKBOX_PORT}/g" \
    "${OBS_DIR}/prometheus/prometheus.yml" > "${prom_dir}/prometheus.yml"

  sed \
    -e "s/localhost:9099/localhost:${REMEDIATION_PORT}/g" \
    "${OBS_DIR}/alertmanager/alertmanager.yml" > "${alertmanager_dir}/alertmanager.yml"

  sed \
    -e "s/localhost:9090/localhost:${PROMETHEUS_PORT}/g" \
    "${OBS_DIR}/grafana/datasources/datasource.yml" > "${grafana_datasources_dir}/datasource.yml"

  local dashboard
  for dashboard in "${OBS_DIR}"/grafana/dashboards/*; do
    [[ -f "${dashboard}" ]] || continue
    case "${dashboard}" in
      *.json)
        sed \
          -e "s/localhost:HERDMASTER_PORT/localhost:${HERDMASTER_PORT}/g" \
          -e "s/localhost:AOP_API_PORT/localhost:${AOP_API_PORT}/g" \
          -e "s/localhost:PROMETHEUS_PORT/localhost:${PROMETHEUS_PORT}/g" \
          -e "s/localhost:ALERTMANAGER_PORT/localhost:${ALERTMANAGER_PORT}/g" \
          -e "s/localhost:REMEDIATION_PORT/localhost:${REMEDIATION_PORT}/g" \
          -e "s/localhost:BLACKBOX_PORT/localhost:${BLACKBOX_PORT}/g" \
          -e "s/localhost:8080/localhost:${HERDMASTER_PORT}/g" \
          -e "s/localhost:8090/localhost:${AOP_API_PORT}/g" \
          -e "s/localhost:9090/localhost:${PROMETHEUS_PORT}/g" \
          -e "s/localhost:9093/localhost:${ALERTMANAGER_PORT}/g" \
          -e "s/localhost:9099/localhost:${REMEDIATION_PORT}/g" \
          -e "s/localhost:9115/localhost:${BLACKBOX_PORT}/g" \
          "${dashboard}" > "${grafana_dashboards_dir}/$(basename "${dashboard}")"
        ;;
      *)
        cp "${dashboard}" "${grafana_dashboards_dir}/$(basename "${dashboard}")"
        ;;
    esac
  done
}

write_herdmaster_config() {
  ensure_herdmaster_token
  local token
  local tmp_config
  token="$(herdmaster_token)"
  tmp_config="$(mktemp "${HERDMASTER_CONFIG}.tmp.XXXXXX")"
  chmod 600 "${tmp_config}" 2>/dev/null || true
  cat > "${tmp_config}" <<EOF
[paths]
config_dir = "${RUNTIME_DIR}/herdmaster"
db = "herdmaster.db"
socket = "herdmaster.sock"
log = "herdmaster.log"

[watchdog]
soft_timeout_s = 10.0
hard_timeout_s = 30.0
poll_interval_s = 15
max_retries = 3
tertiary_hash_interval_s = 30

[bus]
socket_path = "${RUNTIME_DIR}/herdmaster/herdmaster.sock"
message_ttl_s = 300

[acl]
default_policy = "deny"

[[acl.roles]]
name = "orchestrator"
agents = ["cli"]
can_send_to = ["*"]
can_receive_from = ["*"]
can_dispatch_tasks = true
can_reassign_tasks = true

[[acl.roles]]
name = "worker"
agents = ["*"]
can_send_to = ["cli"]
can_receive_from = ["cli"]
can_dispatch_tasks = false
can_reassign_tasks = false

[api]
bind = "127.0.0.1"
port = ${HERDMASTER_PORT}
token = "${token}"

[database]
url = "${DATABASE_URL}"

[logging]
level = "INFO"
json = true
EOF
  mv "${tmp_config}" "${HERDMASTER_CONFIG}"
  chmod 600 "${HERDMASTER_CONFIG}" 2>/dev/null || true
}

herdmaster_auth_header() {
  printf 'Authorization: Bearer %s' "$(herdmaster_token)"
}

aop_control_plane_coupling_connected() {
  local payload
  payload="$(curl -sS --max-time 5 "http://${LOCAL_HOST}:${AOP_API_PORT}/health" 2>/dev/null || true)"
  [[ "${payload}" == *'"coupling":{"status":"connected"'* ]]
}

uvicorn_bin() {
  if [[ -x "/tmp/aop-control-plane-venv/bin/uvicorn" ]]; then
    printf '%s\n' "/tmp/aop-control-plane-venv/bin/uvicorn"
  elif command -v uvicorn >/dev/null 2>&1; then
    command -v uvicorn
  else
    die "uvicorn not found; install AOP control-plane dependencies first"
  fi
}

print_status_table() {
  local obs_mode
  obs_mode="$(observability_network_mode)"
  printf '\n%-24s %-10s %s\n' "Component" "Status" "URL"
  printf '%-24s %-10s %s\n' "---------" "------" "---"
  printf '%-24s %-10s %s\n' "Postgres" "$(port_listening "${POSTGRES_PORT}" && echo up || echo down)" "127.0.0.1:${POSTGRES_PORT}"
  printf '%-24s %-10s %s\n' "Redis" "$(port_listening "${REDIS_PORT}" && echo up || echo down)" "127.0.0.1:${REDIS_PORT}"
  printf '%-24s %-10s %s\n' "Prometheus" "$(http_code "http://127.0.0.1:${PROMETHEUS_PORT}/-/healthy")" "http://127.0.0.1:${PROMETHEUS_PORT} (${obs_mode})"
  printf '%-24s %-10s %s\n' "Grafana" "$(http_code "http://127.0.0.1:${GRAFANA_PORT}/api/health")" "http://127.0.0.1:${GRAFANA_PORT} (${obs_mode})"
  printf '%-24s %-10s %s\n' "Alertmanager" "$(http_code "http://127.0.0.1:${ALERTMANAGER_PORT}/-/ready")" "http://127.0.0.1:${ALERTMANAGER_PORT} (${obs_mode})"
  printf '%-24s %-10s %s\n' "Blackbox" "$(http_code "http://127.0.0.1:${BLACKBOX_PORT}/-/healthy")" "http://127.0.0.1:${BLACKBOX_PORT} (${obs_mode})"
  printf '%-24s %-10s %s\n' "Remediation Webhook" "$(http_code "http://127.0.0.1:${REMEDIATION_PORT}/health")" "http://127.0.0.1:${REMEDIATION_PORT}/health (${obs_mode})"
  printf '%-24s %-10s %s\n' "HerdMaster" "$(http_code "http://127.0.0.1:${HERDMASTER_PORT}/metrics" -H "$(herdmaster_auth_header)")" "http://127.0.0.1:${HERDMASTER_PORT}/metrics"
  printf '%-24s %-10s %s\n' "AOP API" "$(http_code "http://127.0.0.1:${AOP_API_PORT}/health")" "http://127.0.0.1:${AOP_API_PORT}"
  printf '%-24s %-10s %s\n' "AOP Frontend" "$(http_code "http://127.0.0.1:${AOP_WEB_PORT}")" "http://127.0.0.1:${AOP_WEB_PORT}"
  printf '%-24s %-10s %s\n' "Nginx LB" "$(http_code "http://127.0.0.1:${NGINX_PORT:-8000}")" "http://127.0.0.1:${NGINX_PORT:-8000}"
}
