#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-/mnt/c/project2026/claradocpharma}"
API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
START_TUNNEL="${START_TUNNEL:-false}"
TUNNEL_URL="${TUNNEL_URL:-http://localhost:8000}"

if [ ! -d "$REPO_DIR" ]; then
  echo "Repo directory not found: $REPO_DIR"
  echo "Set REPO_DIR to your actual path and retry."
  exit 1
fi

cd "$REPO_DIR"

echo "Starting Docker services..."
docker compose up -d

echo "Current containers:"
docker compose ps

echo "Checking API health..."
if curl -fsS "$API_BASE_URL/health" >/dev/null; then
  echo "API health check passed at $API_BASE_URL/health"
else
  echo "API health check failed. Showing recent logs."
  docker compose logs api --tail=80 || true
  docker compose logs worker --tail=80 || true
  exit 1
fi

echo "Seeding demo data..."
curl -fsS -X POST "$API_BASE_URL/seed" >/dev/null
echo "Seed complete."

cat <<EOF

Local app is up.
- Web:  http://localhost:5173
- API:  $API_BASE_URL/docs

Cloudflared reminder:
Run this in another terminal and keep it open:
  cloudflared tunnel --url $TUNNEL_URL

If tunnel URL changes, update PUBLIC_API_BASE_URL in .env and run:
  cd $REPO_DIR
  docker compose up -d --force-recreate api
EOF

if [ "$START_TUNNEL" = "true" ]; then
  echo
  echo "Starting cloudflared in this terminal..."
  exec cloudflared tunnel --url "$TUNNEL_URL"
fi

