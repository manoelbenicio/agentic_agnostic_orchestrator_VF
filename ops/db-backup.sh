#!/usr/bin/env bash
#
# db-backup.sh — Automated Postgres backups for the AOP stack.
#
#   full   : weekly full logical backup (globals/roles + full custom-format dump)
#   hourly : hourly snapshot (self-contained custom-format dump, independently restorable)
#
# Each dump is verified with `pg_restore --list` before being kept. Old dumps are
# pruned by retention policy. Designed to run via cron (see ops/install-backup-cron.sh).
#
# Restore:  bash AOP/ops/db-restore.sh <path-to-.dump>
#
set -Eeuo pipefail

# ---- config (override via env) ------------------------------------------------
# Resolve paths relative to this script so the default works regardless of where
# the AOP repo is checked out (no hard-coded project root).
OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AOP_DIR="$(cd "${OPS_DIR}/.." && pwd)"
PG_CONTAINER="${PG_CONTAINER:-deploy-postgres-1}"
PG_USER="${PG_USER:-aop_dev}"
PG_DB="${PG_DB:-aop}"
BACKUP_ROOT="${BACKUP_ROOT:-${AOP_DIR}/deploy/backups}"
RETAIN_FULL="${RETAIN_FULL:-8}"      # keep last 8 weekly fulls (~2 months)
RETAIN_HOURLY="${RETAIN_HOURLY:-48}" # keep last 48 hourly snapshots (~2 days)
LOCK_TIMEOUT_SECONDS="${LOCK_TIMEOUT_SECONDS:-5}"

LOG="${BACKUP_ROOT}/backup.log"
TS="$(date -u +%Y%m%dT%H%M%SZ)"

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) [$1] ${2}" | tee -a "$LOG" >&2; }
die() { log ERROR "$1"; exit 1; }

mode="${1:-hourly}"
mkdir -p "${BACKUP_ROOT}/full" "${BACKUP_ROOT}/hourly" "${BACKUP_ROOT}/globals"
LOCK_FILE="${BACKUP_ROOT}/.backup.lock"
exec 9>"${LOCK_FILE}"
if ! flock -w "${LOCK_TIMEOUT_SECONDS}" 9; then
  die "another backup is already running (lock: ${LOCK_FILE})"
fi
log INFO "lock acquired: ${LOCK_FILE}"

# Ensure the DB container is up
docker inspect -f '{{.State.Running}}' "$PG_CONTAINER" 2>/dev/null | grep -q true \
  || die "container ${PG_CONTAINER} is not running"

dump_db() { # $1 = output file on host
  local out="$1"
  # -Fc custom format (compressed, selective restore), pipe container stdout -> host file
  docker exec "$PG_CONTAINER" pg_dump -U "$PG_USER" -d "$PG_DB" -Fc --no-owner --no-privileges \
    > "$out" 2>>"$LOG"
}

verify_dump() { # $1 = dump file
  local f="$1"
  [ -s "$f" ] || return 1
  # custom-format dumps are restorable with pg_restore; --list validates the archive TOC
  docker exec -i "$PG_CONTAINER" pg_restore --list < "$f" >/dev/null 2>>"$LOG"
}

prune() { # $1 = dir, $2 = glob, $3 = keep N
  local dir="$1" glob="$2" keep="$3"
  ls -1t "${dir}"/${glob} 2>/dev/null | tail -n +$((keep + 1)) | while read -r old; do
    rm -f -- "$old" && log INFO "pruned $(basename "$old")"
  done
}

case "$mode" in
  full)
    out="${BACKUP_ROOT}/full/aop_full_${TS}.dump"
    globals="${BACKUP_ROOT}/globals/globals_${TS}.sql"
    log INFO "starting FULL backup -> ${out}"
    docker exec "$PG_CONTAINER" pg_dumpall -U "$PG_USER" --globals-only > "$globals" 2>>"$LOG" \
      || die "pg_dumpall (globals) failed"
    dump_db "$out" || die "pg_dump failed"
    verify_dump "$out" || die "integrity check FAILED for ${out}"
    sz=$(du -h "$out" | cut -f1)
    log INFO "FULL backup OK (${sz}) verified: ${out}"
    prune "${BACKUP_ROOT}/full" "aop_full_*.dump" "$RETAIN_FULL"
    prune "${BACKUP_ROOT}/globals" "globals_*.sql" "$RETAIN_FULL"
    ;;
  hourly|incr|incremental)
    out="${BACKUP_ROOT}/hourly/aop_hourly_${TS}.dump"
    log INFO "starting HOURLY snapshot -> ${out}"
    dump_db "$out" || die "pg_dump failed"
    verify_dump "$out" || die "integrity check FAILED for ${out}"
    sz=$(du -h "$out" | cut -f1)
    log INFO "HOURLY snapshot OK (${sz}) verified: ${out}"
    prune "${BACKUP_ROOT}/hourly" "aop_hourly_*.dump" "$RETAIN_HOURLY"
    ;;
  *)
    die "unknown mode '${mode}' (use: full | hourly)"
    ;;
esac

log INFO "done (${mode})"
