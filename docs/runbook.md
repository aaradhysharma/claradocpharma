# Clara VoiceOps Runbook

## Check Service Health

```bash
curl http://localhost:8000/health
kubectl get pods -n clara-voiceops
kubectl get svc -n clara-voiceops
```

## Seed Demo Data

```bash
curl -X POST http://localhost:8000/seed
```

## Queue A Reminder

Use the web dashboard or API docs at `http://localhost:8000/docs`.

## Local Docker Demo

```bash
docker compose up --build -d
curl http://localhost:8000/health
```

Open the dashboard at `http://localhost:5173`, seed demo data, queue a reminder, then refresh until the call attempt shows a generated script and playable MP3.

If `GEMINI_API_KEY` is set, the worker generates a short AI reminder script before sending text to ElevenLabs. If it is missing, the worker uses the original reminder message.

## Provider Voice Mapping

The demo database maps each patient to an assigned provider and each provider to a default ElevenLabs voice:

- Maria Johnson -> Dr. Maya Chen -> `DOCTOR_ELEVENLABS_VOICE_ID`
- Robert Wilson -> Bunny Patel, PharmD -> `PHARMACIST_ELEVENLABS_VOICE_ID`

If `DOCTOR_ELEVENLABS_VOICE_ID` is empty, the seed endpoint uses a generic ElevenLabs premade voice for the doctor. If `PHARMACIST_ELEVENLABS_VOICE_ID` is empty, it falls back to `ELEVENLABS_VOICE_ID`, which is useful for your cloned pharmacy voice.

To update a provider voice in a GitOps demo:

1. Update the relevant voice ID in `infra/k8s/configmap.yaml` or your secret management layer.
2. Commit and push the change.
3. Let ArgoCD sync the deployment.
4. Restart or resync the app, then run `POST /seed` once to update the demo DB row without duplicating patients/providers.

## Local Kubernetes And GitOps Demo

Create a local cluster:

```bash
kind create cluster --name clara
```

Build images and load them into kind:

```bash
docker build -t clara-api:0.0.1 apps/api
docker build -t clara-worker:0.0.1 apps/worker
docker build -t clara-web:0.0.1 apps/web
kind load docker-image clara-api:0.0.1 --name clara
kind load docker-image clara-worker:0.0.1 --name clara
kind load docker-image clara-web:0.0.1 --name clara
```

Create the runtime secret from your local `.env`:

```bash
kubectl create namespace clara-voiceops --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic clara-secrets -n clara-voiceops \
  --from-literal=GEMINI_API_KEY="$GEMINI_API_KEY" \
  --from-literal=ELEVENLABS_API_KEY="$ELEVENLABS_API_KEY" \
  --from-literal=ELEVENLABS_VOICE_ID="$ELEVENLABS_VOICE_ID" \
  --from-literal=TWILIO_ACCOUNT_SID="$TWILIO_ACCOUNT_SID" \
  --from-literal=TWILIO_AUTH_TOKEN="$TWILIO_AUTH_TOKEN" \
  --from-literal=TWILIO_FROM_NUMBER="$TWILIO_FROM_NUMBER" \
  --from-literal=PUBLIC_AUDIO_BASE_URL="$PUBLIC_AUDIO_BASE_URL" \
  --dry-run=client -o yaml | kubectl apply -f -
```

Apply the app manifests:

```bash
kubectl apply -k infra/k8s
kubectl get pods -n clara-voiceops
kubectl port-forward svc/clara-web -n clara-voiceops 8080:80
```

Install ArgoCD for the GitOps story:

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl get pods -n argocd
kubectl port-forward svc/argocd-server -n argocd 8443:443
```

Then update `infra/k8s/argocd-application.yaml` with your GitHub repo URL and apply it:

```bash
kubectl apply -f infra/k8s/argocd-application.yaml
argocd app get clara-voiceops
argocd app sync clara-voiceops
```

## Troubleshoot Worker Failures

```bash
kubectl logs deployment/clara-worker -n clara-voiceops
kubectl describe deployment clara-worker -n clara-voiceops
kubectl get events -n clara-voiceops --sort-by=.lastTimestamp
```

Common causes:

- Missing `ELEVENLABS_API_KEY`.
- Wrong `ELEVENLABS_VOICE_ID`.
- Missing `GEMINI_API_KEY` if AI scripting is expected.
- Redis service unavailable.
- Postgres service unavailable.
- Twilio credentials missing or `PUBLIC_AUDIO_BASE_URL` is not reachable by Twilio.

## Scale Workers

```bash
kubectl scale deployment clara-worker --replicas=2 -n clara-voiceops
kubectl rollout status deployment/clara-worker -n clara-voiceops
```

## GitOps Recovery

```bash
argocd app get clara-voiceops
argocd app sync clara-voiceops
```

If live state drifts from Git, ArgoCD self-healing should restore the desired state.
