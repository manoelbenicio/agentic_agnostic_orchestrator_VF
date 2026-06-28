#!/usr/bin/env bash
#
# install-backup-cron.sh — Schedule AOP Postgres backups via cron (idempotent).
#
#   hourly snapshot : every hour at :05
#   weekly full     : Sundays at 03:00
#
# Re-running replaces the AOP backup cron block without touching other cron entries.
#
set -Eeuo pipefail

OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AOP_DIR="$(cd "${OPS_DIR}/.." && pwd)"
BACKUP_SH="${OPS_DIR}/db-backup.sh"
BACKUP_ROOT="${BACKUP_ROOT:-${AOP_DIR}/deploy/backups}"
PG_CONTAINER="${PG_CONTAINER:-deploy-postgres-1}"
PG_USER="${PG_USER:-aop_dev}"
PG_DB="${PG_DB:-aop}"
RETAIN_FULL="${RETAIN_FULL:-8}"
RETAIN_HOURLY="${RETAIN_HOURLY:-48}"
MARKER_BEGIN="# >>> AOP db-backup (managed) >>>"
MARKER_END="# <<< AOP db-backup (managed) <<<"

chmod +x "${OPS_DIR}/db-backup.sh" "${OPS_DIR}/db-restore.sh" 2>/dev/null || true

# Ensure cron daemon is running (WSL: needs manual start; harmless if already up)
if command -v service >/dev/null 2>&1; then
  sudo service cron start >/dev/null 2>&1 || service cron start >/dev/null 2>&1 || true
fi

block="$(cat <<EOF
${MARKER_BEGIN}
5 * * * * BACKUP_ROOT=${BACKUP_ROOT} PG_CONTAINER=${PG_CONTAINER} PG_USER=${PG_USER} PG_DB=${PG_DB} RETAIN_HOURLY=${RETAIN_HOURLY} /usr/bin/env bash ${BACKUP_SH} hourly >> ${BACKUP_ROOT}/cron.log 2>&1
0 3 * * 0 BACKUP_ROOT=${BACKUP_ROOT} PG_CONTAINER=${PG_CONTAINER} PG_USER=${PG_USER} PG_DB=${PG_DB} RETAIN_FULL=${RETAIN_FULL} /usr/bin/env bash ${BACKUP_SH} full >> ${BACKUP_ROOT}/cron.log 2>&1
${MARKER_END}
EOF
)"

current="$(crontab -l 2>/dev/null || true)"
# strip any previous managed block
cleaned="$(printf '%s\n' "$current" | sed "/${MARKER_BEGIN}/,/${MARKER_END}/d")"
printf '%s\n%s\n' "$cleaned" "$block" | sed '/^$/N;/^\n$/D' | crontab -

echo "Installed AOP backup cron:"
crontab -l | sed -n "/${MARKER_BEGIN}/,/${MARKER_END}/p"
