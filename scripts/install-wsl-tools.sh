#!/usr/bin/env bash
set -euo pipefail

mkdir -p "$HOME/.local/bin"
export PATH="$HOME/.local/bin:$PATH"

if ! command -v helm >/dev/null 2>&1; then
  curl -fsSLo /tmp/helm.tgz https://get.helm.sh/helm-v3.20.2-linux-amd64.tar.gz
  tar -xzf /tmp/helm.tgz -C /tmp
  mv /tmp/linux-amd64/helm "$HOME/.local/bin/helm"
  chmod +x "$HOME/.local/bin/helm"
fi

if ! command -v terraform >/dev/null 2>&1; then
  ver="$(curl -fsS https://checkpoint-api.hashicorp.com/v1/check/terraform | python3 -c 'import json, sys; print(json.load(sys.stdin)["current_version"])')"
  curl -fsSLo /tmp/terraform.zip "https://releases.hashicorp.com/terraform/${ver}/terraform_${ver}_linux_amd64.zip"
  python3 -c 'import zipfile; zipfile.ZipFile("/tmp/terraform.zip").extractall("/tmp")'
  mv /tmp/terraform "$HOME/.local/bin/terraform"
  chmod +x "$HOME/.local/bin/terraform"
fi

if ! command -v kind >/dev/null 2>&1; then
  curl -fsSLo "$HOME/.local/bin/kind" https://kind.sigs.k8s.io/dl/latest/kind-linux-amd64
  chmod +x "$HOME/.local/bin/kind"
fi

echo "helm=$(helm version --short)"
echo "terraform=$(terraform version | awk 'NR==1{print}')"
echo "kind=$(kind version)"
