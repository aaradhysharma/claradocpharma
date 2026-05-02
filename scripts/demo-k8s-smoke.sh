#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-clara-voiceops}"

kubectl get pods -n "${NAMESPACE}"
kubectl rollout status deployment/clara-api -n "${NAMESPACE}" --timeout=120s
kubectl rollout status deployment/clara-worker -n "${NAMESPACE}" --timeout=120s
kubectl rollout status deployment/clara-web -n "${NAMESPACE}" --timeout=120s

echo "Port-forward the API in another terminal:"
echo "kubectl port-forward svc/clara-api -n ${NAMESPACE} 8000:8000"
echo
echo "Then run:"
echo "curl -X POST http://localhost:8000/seed"
echo "curl http://localhost:8000/care-relationships"
