#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/common.sh"

require_cmd docker
require_cmd find
load_aop_env

log "running full stop before flush"
"${OPS_DIR}/stop.sh"

log "flushing logs and generated caches"
rm -rf "${LOG_DIR:?}/"* 2>/dev/null || true
rm -f "${HERDMASTER_PID_FILE}" "${AOP_API_PID_FILE}" "${AOP_WEB_PID_FILE}" 2>/dev/null || true
rm -rf "${AOP_DIR}/web/.next/cache" 2>/dev/null || true
rm -rf "${AOP_DIR}/control-plane/.pytest_cache" "${ROOT_DIR}/.pytest_cache" 2>/dev/null || true
find "${AOP_DIR}/control-plane" "${AOP_DIR}/e2e" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
find "${AOP_DIR}/control-plane" "${AOP_DIR}/e2e" -type f -name "*.pyc" -delete 2>/dev/null || true
rm -rf "${RUNTIME_DIR}/herdmaster/prompts" 2>/dev/null || true
find "${RUNTIME_DIR}" -type f \( -name "*.prompt" -o -name "*.prompt.txt" -o -name "prompt-*.txt" \) -delete 2>/dev/null || true

printf 'Type CONFIRMO to reset AOP Postgres schemas and Redis; anything else preserves DB/Redis: '
read -r confirmation || confirmation=""
if [[ "${confirmation}" == "CONFIRMO" ]]; then
  log "confirmed destructive reset for AOP Postgres schemas and Redis"
  docker_compose_aop up -d postgres redis
  wait_until "postgres" 60 2 docker_compose_aop exec -T postgres pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"
  wait_until "redis" 60 2 docker_compose_aop exec -T redis redis-cli -a "${REDIS_PASSWORD}" ping

  docker_compose_aop exec -T postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 <<'SQL'
DO $$
DECLARE
  schema_name text;
BEGIN
  FOR schema_name IN
    SELECT nspname
    FROM pg_namespace
    WHERE nspname LIKE 'aop\_%' ESCAPE '\'
  LOOP
    EXECUTE format('DROP SCHEMA IF EXISTS %I CASCADE', schema_name);
  END LOOP;
END $$;
SQL
  docker_compose_aop exec -T redis redis-cli -a "${REDIS_PASSWORD}" FLUSHALL >/dev/null
  docker_compose_aop exec -T postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 <<'SQL'
DO $$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'messages',
    'tasks',
    'projects',
    'agents',
    'health_events',
    'message_deliveries'
  ]
  LOOP
    EXECUTE format('DROP TABLE IF EXISTS public.%I CASCADE', table_name);
  END LOOP;
END $$;
SQL
  log "AOP Postgres schemas, HerdMaster runtime tables, and Redis FLUSHALL completed"
  docker_compose_aop down
else
  log "DB/Redis reset not confirmed; preserving persisted data"
fi

log "starting full stack after flush"
"${OPS_DIR}/start.sh"
