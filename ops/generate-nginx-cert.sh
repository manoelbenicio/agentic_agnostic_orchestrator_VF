#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/common.sh"

require_cmd openssl
load_aop_env

AOP_DOMAIN="${AOP_DOMAIN:-localhost}"
CERT_DIR="${AOP_DIR}/deploy/nginx/certs"
CERT_FILE="${CERT_DIR}/aop.crt"
KEY_FILE="${CERT_DIR}/aop.key"
mkdir -p "${CERT_DIR}"

openssl req -x509 -nodes -newkey rsa:2048 -days "${AOP_TLS_CERT_DAYS:-30}" \
  -keyout "${KEY_FILE}" \
  -out "${CERT_FILE}" \
  -subj "/CN=${AOP_DOMAIN}" \
  -addext "subjectAltName=DNS:${AOP_DOMAIN},DNS:localhost,IP:127.0.0.1"

chmod 600 "${KEY_FILE}"
chmod 644 "${CERT_FILE}"
log "generated local TLS certificate: ${CERT_FILE}"
