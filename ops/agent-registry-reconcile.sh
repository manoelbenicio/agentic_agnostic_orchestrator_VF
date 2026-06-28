#!/usr/bin/env bash
#
# agent-registry-reconcile.sh — Keep the agent registry in sync with reality.
#
# The single source of truth for "which agents exist" is the LIVE herdr roster
# (the panes actually running) plus the 'cli' orchestrator. This script:
#
#   1. Derives the authoritative roster from `herdr pane list`.
#   2. Writes the canonical whitelist to a JSON file consumed by the
#      remediation webhook (so the anti-ghost purge uses CURRENT names, never
#      a stale hardcoded list).
#   3. Upserts the authoritative agents into hm_main.agents with correct
#      label/type, and PRUNES any agent not in the roster (stale/ghost).
#   4. (--flush) Wipes runtime state (tasks/audit/alerts/messages/health_events)
#      and the control-plane registry tables for a clean slate, then reseeds.
#
# Idempotent. Safe to run hourly via cron. FK rules on hm_main.agents are
# CASCADE / SET NULL, so pruning an agent never violates a constraint.
#
# Usage:
#   bash agent-registry-reconcile.sh            # reconcile (hourly)
#   bash agent-registry-reconcile.sh --flush    # full clean slate + reseed
#
set -Eeuo pipefail

PG_CONTAINER="${PG_CONTAINER:-deploy-postgres-1}"
PG_USER="${PG_USER:-aop_dev}"
PG_DB="${PG_DB:-aop}"
WHITELIST_FILE="${WHITELIST_FILE:-/home/dataops-lab/.config/herdmaster/agent_whitelist.json}"
OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="${RECONCILE_LOG:-${OPS_DIR}/../deploy/backups/reconcile.log}"

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) [$1] ${2}" | tee -a "$LOG" >&2; }
die() { log ERROR "$1"; exit 1; }

FLUSH=0
[ "${1:-}" = "--flush" ] && FLUSH=1

psql_x() { docker exec -i "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -v ON_ERROR_STOP=1 "$@"; }

# ── 1. Authoritative roster from live herdr ───────────────────────────────────
ROSTER_JSON="$(herdr pane list 2>/dev/null)" || die "herdr pane list failed"
mapfile -t ROWS < <(printf '%s' "$ROSTER_JSON" | python3 -c "
import sys,json
d=json.load(sys.stdin)
panes=d.get('result',{}).get('panes',[])
# id|label|type|role
for p in panes:
    pid=p['pane_id']
    lbl=(p.get('label') or pid).replace(chr(39),chr(39)*2)
    typ=p.get('agent') or 'unknown'
    print(f\"{pid}|{lbl}|{typ}|worker\")
print('cli|CLI Operator|system|orchestrator')
")
[ "${#ROWS[@]}" -ge 1 ] || die "empty roster"

IDS=(); VALUES=""
for r in "${ROWS[@]}"; do
  IFS='|' read -r id lbl typ role <<< "$r"
  IDS+=("$id")
  VALUES+="('${id}','${lbl}','${typ}','${role}','${id}','w8'),"
done
VALUES="${VALUES%,}"
# SQL IN-list of ids
INLIST=""; for id in "${IDS[@]}"; do INLIST+="'${id}',"; done; INLIST="${INLIST%,}"

log INFO "authoritative roster (${#IDS[@]}): ${IDS[*]}"

# ── 2. Propagate identity DYNAMICALLY: whitelist json + token + every config.toml
#       Single source of truth = AOP/ops/sync_agent_identity.py. Nothing manual.
SYNC_PY="${OPS_DIR}/sync_agent_identity.py"
[ -f "$SYNC_PY" ] || die "missing ${SYNC_PY}"
AGENT_WHITELIST_FILE="$WHITELIST_FILE" python3 "$SYNC_PY" >>"$LOG" 2>&1 \
  && log INFO "identity propagated (whitelist+token+config.toml) via sync_agent_identity.py" \
  || die "sync_agent_identity.py failed"

# ── 3. Detect control-plane registry schema (canonical, hashed name) ──────────
REG_SCHEMA="$(psql_x -t -A -c "select table_schema from information_schema.tables where table_name='registry_agents' and table_schema like 'aop_registry%' limit 1;" | tr -d '[:space:]')"

# ── 4. Reconcile ──────────────────────────────────────────────────────────────
SQL="BEGIN;"
if [ "$FLUSH" -eq 1 ]; then
  log WARN "FLUSH mode: wiping runtime state + registry"
  SQL+="
  TRUNCATE hm_main.tasks, hm_main.task_audit_log, hm_main.task_alerts, hm_main.messages, hm_main.health_events RESTART IDENTITY CASCADE;
  DELETE FROM hm_main.agents;"
  if [ -n "$REG_SCHEMA" ]; then
    SQL+="
  TRUNCATE \"${REG_SCHEMA}\".registry_pane_mappings, \"${REG_SCHEMA}\".registry_agents CASCADE;"
  fi
fi
# Upsert authoritative agents (correct names) + prune anything not in roster
SQL+="
INSERT INTO hm_main.agents (id,label,type,role,herdr_pane,herdr_ws) VALUES ${VALUES}
ON CONFLICT (id) DO UPDATE SET
  label=EXCLUDED.label, type=EXCLUDED.type, role=EXCLUDED.role,
  herdr_pane=EXCLUDED.herdr_pane, herdr_ws=EXCLUDED.herdr_ws, updated_at=now();
DELETE FROM hm_main.agents WHERE id NOT IN (${INLIST});"
# Prune stale control-plane registry rows whose pane is not in the live roster
if [ -n "$REG_SCHEMA" ] && [ "$FLUSH" -eq 0 ]; then
  SQL+="
DELETE FROM \"${REG_SCHEMA}\".registry_agents
 WHERE pane_id IS NULL OR pane_id NOT IN (${INLIST});"
fi
SQL+="
COMMIT;"

printf '%s' "$SQL" | psql_x >/dev/null 2>>"$LOG" || die "reconcile transaction failed"

# ── 5. Report integrity ───────────────────────────────────────────────────────
DBN="$(psql_x -t -A -c "select count(*) from hm_main.agents;")"
GHOST="$(psql_x -t -A -c "select count(*) from hm_main.agents where id not in (${INLIST});")"
log INFO "reconcile OK: db_agents=${DBN} roster=${#IDS[@]} ghost=${GHOST} registry_schema=${REG_SCHEMA:-none} flush=${FLUSH}"
[ "$GHOST" = "0" ] || die "post-reconcile ghost agents present: ${GHOST}"
echo "RECONCILE_OK db_agents=${DBN} ghost=${GHOST}"
