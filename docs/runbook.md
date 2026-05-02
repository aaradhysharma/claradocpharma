# Clara VoiceOps Runbook

For the clean local Kubernetes demo with Argo CD, port cleanup, browser URLs, and presenter talking points, use `docs/argocd-demo.md`.
For reboot/restart commands on your WSL setup (including cloudflared recovery), use `docs/get-app-working.md`.

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

The demo database maps each patient to an assigned provider and each provider to a default ElevenLabs voice cloned from the repo samples:

- Doctors (Dr. Aadi) -> `DOCTOR_ELEVENLABS_VOICE_ID` or baked-in Aadi clone id `VrD3EIr2SqyhWLakvrMt`
- Pharmacists (Bunny Patel) -> `PHARMACIST_ELEVENLABS_VOICE_ID` or baked-in Bunny clone id `fw4xyJhgrfgP0Y1OuCBb`

There is no generic premade ElevenLabs library voice in the loop anymore — only those two clone IDs (overridable via env).

To update a provider voice in a GitOps demo:

1. Update the relevant voice ID in `infra/k8s/configmap.yaml` or your secret management layer.
2. Commit and push the change.
3. Let ArgoCD sync the deployment.
4. Restart or resync the app, then run `POST /seed` once to update the demo DB row without duplicating patients/providers.

## Local Kubernetes And GitOps Demo

One-command local setup:

```bash
bash scripts/deploy-local-gitops.sh
```

Manual steps are below if you want to narrate each DevOps layer.

Create a local cluster:

```bash
kind create cluster --name clara
```

Build images and load them into kind:

```bash
bash scripts/kind-build-load.sh
```

Create the runtime secret from your local `.env`:

```bash
bash scripts/apply-k8s-secrets.sh
```

Apply the app manifests:

```bash
kubectl apply -k infra/k8s
kubectl get pods -n clara-voiceops
```

Install ArgoCD for the GitOps story:

```bash
kubectl create namespace argocd
bash scripts/install-argocd.sh
kubectl port-forward svc/argocd-server -n argocd 8443:443
```

Then apply the ArgoCD app:

```bash
kubectl apply -f infra/k8s/argocd-application.yaml
argocd app get clara-voiceops
argocd app sync clara-voiceops
```

The ArgoCD app points to `https://github.com/aaradhysharma/claradocpharma.git`. ArgoCD can only deploy changes after they are committed and pushed to that repo. For uncommitted local testing, use `kubectl apply -k infra/k8s`.

Access the deployed app:

```bash
kubectl port-forward svc/clara-web -n clara-voiceops 8080:80
kubectl port-forward svc/clara-api -n clara-voiceops 8000:8000
```

Open `http://localhost:8080`.

## Monday Interview Demo Script

1. Show the repo layout: `apps`, `infra/k8s`, `infra/terraform`, `.github/workflows`.
2. Run `docker compose ps` to show local containers.
3. Run `kubectl get pods -n clara-voiceops` to show Kubernetes workloads.
4. Open ArgoCD and show the `clara-voiceops` app health/sync.
5. Open the webapp, seed demo data, select a patient-provider relationship, and queue a reminder.
6. Show the generated Gemini script and play the ElevenLabs MP3.
7. Run `kubectl logs deployment/clara-worker -n clara-voiceops --tail=30`.
8. Run `kubectl scale deployment clara-worker --replicas=2 -n clara-voiceops`.
9. Explain that GitHub Actions publishes to ECR and ArgoCD deploys from Git.

## ECR Publishing

Do not publish to Docker Hub for this project by default. The AWS path uses ECR because it better matches the Systems Engineer JD.

See `docs/dockerhub-cicd.md` for required GitHub secrets and image tagging.

## Troubleshoot Worker Failures

```bash
kubectl logs deployment/clara-worker -n clara-voiceops
kubectl describe deployment clara-worker -n clara-voiceops
kubectl get events -n clara-voiceops --sort-by=.lastTimestamp
```

Common causes:

- Missing `ELEVENLABS_API_KEY`.
- Wrong `DOCTOR_ELEVENLABS_VOICE_ID` / `PHARMACIST_ELEVENLABS_VOICE_ID` (or missing ElevenLabs API key).
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
