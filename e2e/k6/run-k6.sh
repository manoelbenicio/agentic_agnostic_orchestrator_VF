#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

API_BASE="${API_BASE:-http://127.0.0.1:8095}"
UI_BASE="${UI_BASE:-http://127.0.0.1:13000}"
AOP_K6_PROFILE="${AOP_K6_PROFILE:-${K6_PROFILE:-smoke}}"
AOP_K6_VUS="${AOP_K6_VUS:-${K6_VUS:-3}}"
AOP_K6_DURATION="${AOP_K6_DURATION:-${K6_DURATION:-20s}}"
K6_SUMMARY_PATH="${K6_SUMMARY_PATH:-${ROOT_DIR}/e2e/k6/last-summary.json}"

export API_BASE UI_BASE AOP_K6_PROFILE AOP_K6_VUS AOP_K6_DURATION K6_SUMMARY_PATH

curl -fsS "${API_BASE%/}/health/ready" >/dev/null
curl -fsS "${UI_BASE%/}/" >/dev/null

if command -v k6 >/dev/null 2>&1; then
  exec k6 run "${SCRIPT_DIR}/aop-stress.js"
fi

if command -v docker >/dev/null 2>&1; then
  mkdir -p "$(dirname "${K6_SUMMARY_PATH}")"
  exec docker run --rm --network host \
    -e API_BASE -e UI_BASE -e AOP_K6_PROFILE -e AOP_K6_VUS -e AOP_K6_DURATION -e K6_SUMMARY_PATH="/work/e2e/k6/last-summary.json" \
    -e K6_ERROR_RATE_MAX="${K6_ERROR_RATE_MAX:-0.05}" \
    -e K6_P95_MS="${K6_P95_MS:-750}" \
    -e K6_READY_P95_MS="${K6_READY_P95_MS:-500}" \
    -e K6_WRITE_P95_MS="${K6_WRITE_P95_MS:-1000}" \
    -e K6_SLEEP_S="${K6_SLEEP_S:-0.2}" \
    -v "${ROOT_DIR}:/work" \
    -w /work \
    grafana/k6:latest run /work/e2e/k6/aop-stress.js
fi

echo "k6 is not installed and docker is unavailable; install k6 or enable docker to run e2e/k6/aop-stress.js" >&2
exit 127
