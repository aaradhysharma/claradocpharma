#!/usr/bin/env bash
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-clara}"

if ! kind get clusters | grep -qx "${CLUSTER_NAME}"; then
  kind create cluster --name "${CLUSTER_NAME}"
fi

bash scripts/kind-build-load.sh
bash scripts/apply-k8s-secrets.sh
bash scripts/install-argocd.sh

kubectl apply -f infra/k8s/argocd-application.yaml

echo "Waiting for ArgoCD to reconcile clara-voiceops..."
kubectl wait --for=condition=available deployment/clara-api -n clara-voiceops --timeout=300s || true
kubectl get pods -n clara-voiceops

echo "Web app: kubectl port-forward svc/clara-web -n clara-voiceops 8080:80"
echo "API: kubectl port-forward svc/clara-api -n clara-voiceops 8000:8000"
