#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/common.sh"

require_cmd docker
require_cmd curl
require_cmd lsof
require_cmd ss
require_cmd npm
require_cmd setsid
load_aop_env
resolve_runtime_ports
resolve_observability_ports

log "starting AOP base services"
docker_compose_aop up -d
wait_until "postgres" 60 2 docker_compose_aop exec -T postgres pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"
wait_until "redis" 60 2 docker_compose_aop exec -T redis redis-cli -a "${REDIS_PASSWORD}" ping

log "starting HerdMaster observability stack"
write_prometheus_token
render_observability_configs
docker_compose_obs up -d --force-recreate
wait_observability_http_200 "prometheus" "http://127.0.0.1:${PROMETHEUS_PORT}/-/healthy"
wait_observability_http_200 "grafana" "http://127.0.0.1:${GRAFANA_PORT}/api/health"
wait_observability_http_200 "alertmanager" "http://127.0.0.1:${ALERTMANAGER_PORT}/-/ready"
wait_observability_http_200 "blackbox-exporter" "http://127.0.0.1:${BLACKBOX_PORT}/-/healthy"
wait_observability_http_200 "remediation-webhook" "http://127.0.0.1:${REMEDIATION_PORT}/health"

write_herdmaster_config
if [[ "$(http_code "http://127.0.0.1:${HERDMASTER_PORT}/metrics" -H "$(herdmaster_auth_header)")" == "200" ]]; then
  log "HerdMaster already healthy on :${HERDMASTER_PORT}"
  record_listener_pid "HerdMaster" "${HERDMASTER_PORT}" "${HERDMASTER_PID_FILE}"
else
  log "starting HerdMaster control plane on :${HERDMASTER_PORT}"
  (
    cd "${HERDMASTER_DIR}"
    setsid env DATABASE_URL="${DATABASE_URL}" PYTHONPATH="${HERDMASTER_DIR}/src" \
      herdmaster start --http --config "${HERDMASTER_CONFIG}" \
      >>"${LOG_DIR}/herdmaster.log" 2>&1 < /dev/null &
    printf '%s\n' "$!" > "${HERDMASTER_PID_FILE}"
  )
  wait_http_200 "HerdMaster" "http://127.0.0.1:${HERDMASTER_PORT}/metrics" -H "$(herdmaster_auth_header)"
  record_listener_pid "HerdMaster" "${HERDMASTER_PORT}" "${HERDMASTER_PID_FILE}"
fi

if [[ "$(http_code "http://127.0.0.1:${AOP_API_PORT}/health")" == "200" ]] && aop_control_plane_coupling_connected; then
  log "AOP control-plane already healthy on :${AOP_API_PORT} with HerdMaster coupling connected"
  record_listener_pid "AOP control-plane" "${AOP_API_PORT}" "${AOP_API_PID_FILE}"
else
  log "starting AOP control-plane on :${AOP_API_PORT} with HerdMaster token from runtime config"
  (
    cd "${ROOT_DIR}"
    export HERDMASTER_TOKEN
    HERDMASTER_TOKEN="$(herdmaster_token)"
    setsid env DATABASE_URL="${DATABASE_URL}" REDIS_URL="${REDIS_URL}" HERDMASTER_URL="http://127.0.0.1:${HERDMASTER_PORT}" \
      HERDMASTER_TOKEN="${HERDMASTER_TOKEN}" \
      PYTHONPATH="${AOP_DIR}/control-plane:${HERDMASTER_DIR}/src" \
      "$(uvicorn_bin)" app.main:app --host 127.0.0.1 --port "${AOP_API_PORT}" \
      >>"${LOG_DIR}/aop-control-plane.log" 2>&1 < /dev/null &
    printf '%s\n' "$!" > "${AOP_API_PID_FILE}"
  )
  wait_http_200 "AOP control-plane" "http://127.0.0.1:${AOP_API_PORT}/health"
  wait_http_200 "AOP readiness" "http://127.0.0.1:${AOP_API_PORT}/health/ready"
  record_listener_pid "AOP control-plane" "${AOP_API_PORT}" "${AOP_API_PID_FILE}"
fi

if [[ "$(http_code "http://127.0.0.1:${AOP_WEB_PORT}")" == "200" ]]; then
  log "AOP frontend already healthy on :${AOP_WEB_PORT}"
  record_listener_pid "AOP frontend" "${AOP_WEB_PORT}" "${AOP_WEB_PID_FILE}"
else
  log "starting AOP frontend on :${AOP_WEB_PORT}"
  (
    cd "${AOP_DIR}/web"
    setsid env NEXT_PUBLIC_API_URL="http://127.0.0.1:${NGINX_PORT}/api" npm run dev -- --hostname 127.0.0.1 --port "${AOP_WEB_PORT}" \
      >>"${LOG_DIR}/aop-frontend.log" 2>&1 < /dev/null &
    printf '%s\n' "$!" > "${AOP_WEB_PID_FILE}"
  )
  wait_http_200 "AOP frontend" "http://127.0.0.1:${AOP_WEB_PORT}"
  record_listener_pid "AOP frontend" "${AOP_WEB_PORT}" "${AOP_WEB_PID_FILE}"
fi

print_status_table
