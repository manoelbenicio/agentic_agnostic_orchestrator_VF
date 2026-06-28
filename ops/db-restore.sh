#!/usr/bin/env bash
#
# db-restore.sh — Restore an AOP Postgres backup created by db-backup.sh.
#
# Usage:
#   bash AOP/ops/db-restore.sh <path-to-.dump> [target_db]
#
# Restores a custom-format dump into the target database (default: aop).
# By default it restores into the EXISTING database (objects use CREATE ... IF NOT EXISTS
# semantics via --clean --if-exists). Review before running against production data.
#
set -Eeuo pipefail

PG_CONTAINER="${PG_CONTAINER:-deploy-postgres-1}"
PG_USER="${PG_USER:-aop_dev}"
PG_DB="${PG_DB:-aop}"
DUMP="${1:?usage: db-restore.sh <path-to-.dump> [target_db]}"
TARGET_DB="${2:-aop}"

[ -s "$DUMP" ] || { echo "dump not found or empty: $DUMP" >&2; exit 1; }

echo ">> Verifying archive integrity..."
docker exec -i "$PG_CONTAINER" pg_restore --list < "$DUMP" >/dev/null

echo ">> Restoring ${DUMP} into database '${TARGET_DB}' on ${PG_CONTAINER}"
echo ">> (--clean --if-exists: existing objects will be dropped and recreated)"
docker exec -i "$PG_CONTAINER" pg_restore -U "$PG_USER" -d "$TARGET_DB" \
  --clean --if-exists --no-owner --no-privileges < "$DUMP"

echo ">> Restore complete."
