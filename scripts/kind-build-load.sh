#!/usr/bin/env bash
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-clara}"
APP_VERSION="${APP_VERSION:-0.0.1}"

docker build -t "clara-api:${APP_VERSION}" apps/api
docker build -t "clara-worker:${APP_VERSION}" apps/worker
docker build -t "clara-web:${APP_VERSION}" apps/web

kind load docker-image "clara-api:${APP_VERSION}" --name "${CLUSTER_NAME}"
kind load docker-image "clara-worker:${APP_VERSION}" --name "${CLUSTER_NAME}"
kind load docker-image "clara-web:${APP_VERSION}" --name "${CLUSTER_NAME}"

echo "Loaded Clara VoiceOps images into kind cluster ${CLUSTER_NAME}."
