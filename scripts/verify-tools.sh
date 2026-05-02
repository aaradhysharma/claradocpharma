#!/usr/bin/env bash
set -euo pipefail

for tool in git python3 node npm kubectl helm terraform kind; do
  if command -v "$tool" >/dev/null 2>&1; then
    printf "%-10s %s\n" "$tool" "ok"
  else
    printf "%-10s %s\n" "$tool" "missing"
  fi
done

if command -v docker >/dev/null 2>&1; then
  docker --version
  docker compose version
else
  echo "docker     missing - enable Docker Desktop WSL integration"
fi
