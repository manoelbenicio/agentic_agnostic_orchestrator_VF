#!/usr/bin/env sh
set -eu

compose_files="-f docker-compose.yml"

case "${EXPOSE_DB_PORTS:-false}" in
  true|TRUE|True|1|yes|YES|Yes|on|ON|On)
    compose_files="$compose_files -f docker-compose.db-ports.yml"
    ;;
esac

# shellcheck disable=SC2086
exec docker compose $compose_files "$@"
