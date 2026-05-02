#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"

curl -fsS -X POST "$API_BASE_URL/seed"
echo
curl -fsS "$API_BASE_URL/patients"
echo
curl -fsS "$API_BASE_URL/providers"
echo
