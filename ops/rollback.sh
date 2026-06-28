#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

require_cmd docker

if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <image_name> <target_tag>"
    echo "Example: $0 aop-web v1.0.0"
    exit 1
fi

IMAGE_NAME=$1
TARGET_TAG=$2
REGISTRY="127.0.0.1:5000"

log "Rolling back ${IMAGE_NAME} to tag ${TARGET_TAG} on local registry..."

docker pull "${REGISTRY}/${IMAGE_NAME}:${TARGET_TAG}"
docker tag "${REGISTRY}/${IMAGE_NAME}:${TARGET_TAG}" "${REGISTRY}/${IMAGE_NAME}:latest"
docker push "${REGISTRY}/${IMAGE_NAME}:latest"

log "Rollback completed. Tag 'latest' for ${IMAGE_NAME} now points to '${TARGET_TAG}'."
