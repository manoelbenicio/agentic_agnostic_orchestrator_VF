#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/common.sh"

require_cmd docker
require_cmd curl
require_cmd lsof
require_cmd ss
load_aop_env

log "stopping AOP frontend"
stop_pid_file "AOP frontend" "${AOP_WEB_PID_FILE}"
kill_port_processes "AOP frontend" "${AOP_WEB_PORT}"

log "stopping AOP control-plane"
stop_pid_file "AOP control-plane" "${AOP_API_PID_FILE}"
kill_port_processes "AOP control-plane" "${AOP_API_PORT}"

log "stopping HerdMaster control plane"
stop_pid_file "HerdMaster" "${HERDMASTER_PID_FILE}"
kill_port_processes "HerdMaster" "${HERDMASTER_PORT}"
rm -f "${RUNTIME_DIR}/herdmaster/herdmaster.sock" "${RUNTIME_DIR}/herdmaster/herdmaster.pid" 2>/dev/null || true

log "stopping observability containers"
docker_compose_obs down

log "stopping base containers"
docker_compose_aop stop postgres redis

print_status_table
