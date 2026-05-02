# Clara VoiceOps Argo CD Demo Guide

This guide is the clean local demo path for showing Clara VoiceOps running from Kubernetes with Argo CD watching the Git repo.

## What You Are Demonstrating

- The app is packaged into three images: `clara-api`, `clara-worker`, and `clara-web`.
- Kubernetes runs the full stack: web UI, FastAPI, worker, Postgres, Redis, PVCs, ConfigMaps, Secrets, and CronJob.
- Argo CD owns the desired state from `infra/k8s`.
- A Git change to a manifest, such as `infra/k8s/demo-banner.yaml`, is reconciled into the cluster.

## Prerequisites

Run these commands from WSL, not normal PowerShell, unless your Windows shell already has Linux-style tooling configured.

```bash
cd /mnt/c/project2026/claradocpharma
bash scripts/verify-tools.sh
```

You need Docker Desktop with WSL integration enabled, plus `kind`, `kubectl`, and Git.

For live phone calls, create `.env` and fill the real API keys:

```bash
cp .env.example .env
```

Minimum keys for the full voice demo:

- `GEMINI_API_KEY`
- `ELEVENLABS_API_KEY`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_NUMBER`
- `PUBLIC_API_BASE_URL`, only when Twilio must call back into your API

Without Twilio/public tunnel values, the Kubernetes app still runs and the dashboard still opens, but real outbound calls will not complete.

## Start Fresh On Port 5173

If an older demo is still using `http://localhost:5173`, clear it from Windows PowerShell:

```powershell
$pids = Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique
$pids | ForEach-Object { Stop-Process -Id $_ -Force }
```

Verify the port is free:

```powershell
Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue
```

No output means the port is clear.

## One-Command GitOps Setup

From WSL:

```bash
cd /mnt/c/project2026/claradocpharma
bash scripts/deploy-local-gitops.sh
```

What this does:

- Creates the `clara` kind cluster if it does not exist.
- Builds `clara-api:0.0.1`, `clara-worker:0.0.1`, and `clara-web:0.0.1`.
- Loads those local images into kind.
- Creates the `clara-secrets` Kubernetes secret from `.env`.
- Installs Argo CD into the cluster.
- Applies `infra/k8s/argocd-application.yaml`.
- Waits for the Clara workloads to become available.

## Confirm Kubernetes Is Running

```bash
kubectl get pods -n clara-voiceops
kubectl rollout status deployment/clara-api -n clara-voiceops
kubectl rollout status deployment/clara-web -n clara-voiceops
kubectl rollout status deployment/clara-worker -n clara-voiceops
```

Expected healthy services:

- `clara-api`: FastAPI backend and Twilio webhooks
- `clara-web`: React dashboard served by Nginx
- `clara-worker`: background reminder worker
- `postgres`: app database
- `redis`: worker queue

## Open The Clara App

Start the web port-forward from WSL:

```bash
kubectl port-forward --address 0.0.0.0 -n clara-voiceops svc/clara-web 5173:80
```

Open this in Windows:

```text
http://localhost:5173
```

If Windows cannot reach `localhost:5173`, use the WSL IP instead:

```bash
hostname -I | awk '{print $1}'
```

Then open:

```text
http://<wsl-ip>:5173
```

In a second WSL terminal, expose the API:

```bash
kubectl port-forward --address 0.0.0.0 -n clara-voiceops svc/clara-api 8000:8000
```

Check the API:

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/seed
```

After seeding, refresh the dashboard and use:

1. `Provider Directory` to show Dr. Aadi and Bunny Patel.
2. `Use This Match` to select a patient/provider relationship.
3. `Talk to AI (Live Call)` if Twilio and public callback URLs are configured.
4. `Reminder Message` for the one-way reminder workflow.

## Open Argo CD

Start the Argo CD port-forward:

```bash
kubectl port-forward --address 0.0.0.0 -n argocd svc/argocd-server 8443:443
```

Open:

```text
https://localhost:8443
```

Login:

- Username: `admin`
- Password:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
```

Click the `clara-voiceops` application. It should show `Healthy` and `Synced` after reconciliation finishes.

## Demo Script To Narrate

Use this sequence during the demo:

1. Show `infra/k8s/argocd-application.yaml`.
   Explain that Argo CD is pointed at the GitHub repo, branch `main`, path `infra/k8s`.

2. Show `infra/k8s/kustomization.yaml`.
   Explain that this is the app bundle Argo CD reconciles: namespace, config, API, worker, web, Postgres, Redis, storage, and scheduled jobs.

3. Show the Argo CD UI.
   Explain `Synced` means live cluster state matches Git, and `Healthy` means Kubernetes reports the workloads are available.

4. Open `http://localhost:5173`.
   Explain that the web UI is not running with Vite anymore; it is the Kubernetes `clara-web` service port-forwarded from the cluster.

5. Run:

   ```bash
   kubectl get pods -n clara-voiceops
   ```

   Explain each pod role: API for webhooks and REST, worker for async jobs, Redis for queueing, Postgres for persistence, web for the dashboard.

6. Seed demo data:

   ```bash
   curl -X POST http://localhost:8000/seed
   ```

   Explain that this creates demo patients, providers, care relationships, and voice mappings.

7. Make a visible GitOps change in `infra/k8s/demo-banner.yaml`.
   Change `BANNER_TEXT`, commit, and push to `main`.

8. Watch Argo CD.
   The app moves from `OutOfSync` to `Syncing` to `Synced`. Explain that no manual `kubectl apply` is needed after Git is updated.

## Useful Recovery Commands

Restart the web port-forward if the browser stops loading:

```bash
kubectl port-forward --address 0.0.0.0 -n clara-voiceops svc/clara-web 5173:80
```

Check why a pod is not ready:

```bash
kubectl describe pod -n clara-voiceops <pod-name>
kubectl logs -n clara-voiceops deployment/clara-api --tail=100
```

Force Argo CD to sync from the CLI:

```bash
kubectl -n argocd patch app clara-voiceops --type merge -p '{"operation":{"sync":{}}}'
```

Check Argo CD application status:

```bash
kubectl -n argocd get app clara-voiceops \
  -o jsonpath='Sync: {.status.sync.status} Health: {.status.health.status} Revision: {.status.sync.revision}{"\n"}'
```

