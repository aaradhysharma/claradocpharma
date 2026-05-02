#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-clara-voiceops}"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic clara-secrets -n "${NAMESPACE}" \
  --from-literal=GEMINI_API_KEY="${GEMINI_API_KEY:-}" \
  --from-literal=ELEVENLABS_API_KEY="${ELEVENLABS_API_KEY:-}" \
  --from-literal=DOCTOR_ELEVENLABS_VOICE_ID="${DOCTOR_ELEVENLABS_VOICE_ID:-}" \
  --from-literal=PHARMACIST_ELEVENLABS_VOICE_ID="${PHARMACIST_ELEVENLABS_VOICE_ID:-}" \
  --from-literal=TWILIO_ACCOUNT_SID="${TWILIO_ACCOUNT_SID:-}" \
  --from-literal=TWILIO_AUTH_TOKEN="${TWILIO_AUTH_TOKEN:-}" \
  --from-literal=TWILIO_FROM_NUMBER="${TWILIO_FROM_NUMBER:-}" \
  --from-literal=PUBLIC_AUDIO_BASE_URL="${PUBLIC_AUDIO_BASE_URL:-}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Applied clara-secrets in namespace ${NAMESPACE}."
