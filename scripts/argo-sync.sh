#!/usr/bin/env bash
set -euo pipefail
CTX=kind-argocd-lab
APP=clara-voiceops
kubectl --context "$CTX" -n argocd patch app "$APP" --type merge -p '{"operation":{"sync":{}}}'
sleep 5
kubectl --context "$CTX" -n argocd get app "$APP" -o jsonpath='Sync: {.status.sync.status}  Health: {.status.health.status}  Rev: {.status.sync.revision}
'
echo '--- resources ---'
kubectl --context "$CTX" -n argocd get app "$APP" -o jsonpath='{range .status.resources[*]}{.kind}/{.name} -> {.status} {.health.status}
{end}'
