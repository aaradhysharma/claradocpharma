# Clara VoiceOps

> A production-shaped, end-to-end demo of an AI healthcare voice agent built for ChenMed-style operations. Real outbound phone calls, two-way conversation with Gemini, ElevenLabs cloned voices for individual doctors and pharmacists, Postgres/Redis/Worker pipeline, Kubernetes + ArgoCD GitOps, Terraform stubs for AWS, and a React control panel that lets non-technical staff click "Call patient" without ever touching a CLI.

**Current version: `0.0.4`**

---

## Table of Contents

1. [What this is](#1-what-this-is)
2. [The 60-second demo path](#2-the-60-second-demo-path)
3. [Architecture](#3-architecture)
4. [Repository layout](#4-repository-layout)
5. [Local quick start (Docker Compose)](#5-local-quick-start-docker-compose)
6. [Live AI calling: how it actually works](#6-live-ai-calling-how-it-actually-works)
7. [ElevenLabs voice cloning](#7-elevenlabs-voice-cloning)
8. [Web dashboard tour](#8-web-dashboard-tour)
9. [REST API reference](#9-rest-api-reference)
10. [Kubernetes deployment](#10-kubernetes-deployment)
11. [ArgoCD GitOps demo](#11-argocd-gitops-demo)
12. [Terraform / AWS](#12-terraform--aws)
13. [CI/CD with GitHub Actions](#13-cicd-with-github-actions)
14. [Configuration reference](#14-configuration-reference)
15. [Operational runbook](#15-operational-runbook)
16. [Troubleshooting](#16-troubleshooting)
17. [Security notes](#17-security-notes)
18. [Roadmap / future work](#18-roadmap--future-work)

---

## 1. What this is

Clara VoiceOps proves out a thin slice of what a modern voice-driven member-services workflow looks like for a primary-care + pharmacy shop:

- Front-line staff open a web app, see their patient roster grouped by provider, and tap "Call".
- Twilio places an outbound phone call to the patient.
- When the patient answers, **Gemini** (LLM) generates the spoken reply on every turn.
- **ElevenLabs** synthesizes that reply in a voice cloned from the actual provider (Dr. Aadi, Bunny the pharmacist, etc.), so the patient hears a familiar voice rather than a generic robot.
- Twilio captures the patient's speech, posts it back to our webhook, and the loop continues until the patient says goodbye or hits the configured turn limit.
- Every turn is persisted in Postgres so the entire conversation can be audited later.
- The whole thing runs locally on Docker Compose for dev, ships as Kubernetes manifests for staging/prod, and is reconciled by ArgoCD via GitOps.

This repo is intentionally over-engineered for a demo on purpose - it shows competency across product, API design, real-time telephony, LLM orchestration, voice cloning, containerization, Kubernetes, GitOps, IaC, and CI/CD.

---

## 2. The 60-second demo path

```bash
# 1. Bring up the local stack
docker compose up -d --build

# 2. Expose the API publicly so Twilio can webhook it
cloudflared tunnel --url http://localhost:8000
# Copy the printed https URL into PUBLIC_API_BASE_URL in .env, then:
docker compose up -d --force-recreate api

# 3. Seed demo patients + providers + voices
curl -X POST http://localhost:8000/seed

# 4. Open the dashboard
start http://localhost:5173
```

In the dashboard:
1. Click **Provider Directory -> Dr. Aadi** to expand the roster.
2. Either tap **Call** next to a seeded patient, or scroll down to **Talk to AI (Live Call)** and dial any number.
3. Pick up the phone. Talk. Watch the live transcript update in real time.

---

## 3. Architecture

```
                                                       +------------------+
                                                       |   ElevenLabs     |
                                                       |   TTS / Voice    |
                                                       |   Cloning        |
                                                       +---------+--------+
                                                                 ^
                                                                 | per-turn audio
                                                                 |
+------------+        HTTPS        +----------------+   PSTN     |   +-------------+
|            |  POST /calls/      |                |  outbound   |   |             |
|  Web UI    +-------------------->   FastAPI API  +------------>+-->|   Twilio    |
|  (React +  |                    |  (Python)      |             |   |  Voice API  |
|   Vite)    |<-- conversations --+                |<-- webhook -+---+             |
|            |                    +-------+--------+   patient   |   +------+------+
+------------+                            |            speech    |          |
                                          |                                  |
                                          | enqueue reminder jobs            | dials
                                          v                                  v
                                  +-------+--------+                +--------+--------+
                                  |   Redis (LIST) |                |  Patient phone  |
                                  +-------+--------+                +-----------------+
                                          |
                                          | brpop
                                          v
                                  +-------+--------+      +------------------+
                                  |  Worker        +----->|  Gemini LLM      |
                                  |  (Python)      |      |  (LangChain)     |
                                  +-------+--------+      +------------------+
                                          |
                                          v
                                  +-------+--------+
                                  |  Postgres      |
                                  +----------------+
```

Two separate code paths share infrastructure:

- **Pre-recorded reminders** (the original use case): web UI -> API -> reminder row -> Redis job -> Python worker -> Gemini for script -> ElevenLabs for audio -> Twilio plays the MP3 once, no interactivity.
- **Live two-way AI calls** (the upgrade in v0.0.2+): web UI -> API places outbound Twilio call -> Twilio webhooks `/twilio/voice/{conv_id}` -> API generates greeting via Gemini + ElevenLabs -> Twilio `<Gather>` listens to patient -> webhooks `/twilio/respond/{conv_id}` -> loop.

Everything is reconciled by **ArgoCD** from the manifests in `infra/k8s/`. Every push to `main` auto-syncs the cluster.

---

## 4. Repository layout

```
claradocpharma/
+-- apps/
|   +-- api/           FastAPI service (REST + Twilio webhooks + DB models)
|   |   +-- main.py
|   |   +-- requirements.txt
|   |   +-- Dockerfile
|   +-- web/           React + Vite control panel
|   |   +-- src/main.jsx
|   |   +-- src/styles.css
|   |   +-- nginx.conf  (production reverse-proxy /api -> clara-api)
|   |   +-- Dockerfile
|   +-- worker/        Background reminder worker (Redis -> Gemini -> ElevenLabs -> Twilio play)
|       +-- worker.py
|       +-- requirements.txt
|       +-- Dockerfile
+-- infra/
|   +-- k8s/           Kustomize-style manifests (namespace, deployments, services, configmap, PVC, cronjob, ArgoCD Application, demo-banner)
|   +-- terraform/     AWS scaffolding (EC2 + ECR + S3 + IAM)
+-- voicesample doctor/   .ogg sample(s) used to clone the doctor voice
+-- voicesample pharma/   .ogg sample(s) used to clone the pharmacist voice
+-- scripts/             Helper bash/PowerShell scripts (cloudflared, seeding, etc.)
+-- docs/                Additional design notes
+-- docker-compose.yml   Local dev stack (postgres, redis, api, worker, web)
+-- .env.example         Template for required env vars
+-- .gitignore
+-- README.md            (this file)
```

---

## 5. Local quick start (Docker Compose)

### Prerequisites

- Docker Desktop 4.x or Docker Engine 24+
- A Twilio account with a voice-enabled phone number (the trial number works)
- An ElevenLabs API key (free tier is enough for the demo)
- A Google AI Studio API key for Gemini (`gemini-2.5-flash` is the default)
- For real outbound calls reaching webhooks: `cloudflared` or `ngrok` to expose the API publicly

### Setup

```bash
git clone https://github.com/aaradhysharma/claradocpharma.git
cd claradocpharma
cp .env.example .env
# Edit .env and fill in:
#   ELEVENLABS_API_KEY
#   GEMINI_API_KEY
#   TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER
#   PUBLIC_API_BASE_URL  (your https tunnel - see below)
```

### Start the stack

```bash
docker compose up -d --build
```

You should now have:

| Service     | URL                          | Purpose                                                 |
|-------------|------------------------------|---------------------------------------------------------|
| Web UI      | http://localhost:5173        | React dashboard                                         |
| API         | http://localhost:8000        | FastAPI - app endpoints + Twilio webhooks               |
| API docs    | http://localhost:8000/docs   | Auto-generated Swagger UI                               |
| Postgres    | localhost:5432               | `clara` / `clara` / `clara_voiceops`                    |
| Redis       | localhost:6379               | Reminder job queue                                      |

### Expose the API publicly (required for Twilio)

Twilio's webhooks must be reachable from the public internet. The simplest way:

```bash
# Cloudflare quick tunnel (no account needed)
cloudflared tunnel --url http://localhost:8000
```

Copy the printed `https://<random>.trycloudflare.com` URL into `PUBLIC_API_BASE_URL` in `.env`, then re-create the API container so it picks up the new env:

```bash
docker compose up -d --force-recreate api
```

ngrok works equally well: `ngrok http 8000` then use the https URL.

### Seed demo data

```bash
curl -X POST http://localhost:8000/seed
```

This creates:
- Patients: Maria Johnson, Robert Wilson, Elena Garcia, Samuel Park, Priya Shah (all default to phone `+16232008850`)
- Providers: Dr. Aadi (cloned voice), Dr. Maya Chen (premade ElevenLabs voice), Bunny Patel PharmD (cloned voice)
- Care assignments wired so each provider has a roster

### Place your first live call

Easiest path is via the web dashboard's "Talk to AI (Live Call)" panel, but you can also do it from curl:

```bash
curl -X POST http://localhost:8000/calls/outbound \
  -H "Content-Type: application/json" \
  -d '{
    "relationship_id": "<id from /care-relationships>",
    "to_number": "+16232008850",
    "purpose": "Friendly check-in to confirm the patient took their meds today."
  }'
```

The response includes `twilio_call_sid` and the conversation id - your phone will ring within a few seconds.

---

## 6. Live AI calling: how it actually works

This is the hard part, so worth understanding in detail.

### Sequence

```
Operator (Web UI)            FastAPI                Twilio              Patient phone     Gemini     ElevenLabs
        |                       |                     |                       |              |              |
        | POST /calls/outbound  |                     |                       |              |              |
        +---------------------->|                     |                       |              |              |
        |                       | Twilio.calls.create |                       |              |              |
        |                       +-------------------->|                       |              |              |
        |   {conv_id, sid}      |                     |                       |              |              |
        |<----------------------+                     |                       |              |              |
        |                       |                     |  RING                 |              |              |
        |                       |                     +---------------------->|              |              |
        |                       |                     |          ANSWER       |              |              |
        |                       |                     |<----------------------+              |              |
        |                       |  POST /twilio/voice |                       |              |              |
        |                       |<--------------------+                       |              |              |
        |                       |                  generate greeting          |              |              |
        |                       +-----------------------------------------+--->              |              |
        |                       |                                          \                 |              |
        |                       +<-------------------------------------------+               |              |
        |                       |                  synthesize                |               |              |
        |                       +--------------------------------------------+--------------->              |
        |                       |                                            <----- mp3 -----+              |
        |                       |  TwiML: <Play>{audio_url}</Play>                                          |
        |                       |        <Gather input="speech" action="/twilio/respond/..." />            |
        |                       +-------------------->|                       |                             |
        |                       |                     | Play audio + listen   |                             |
        |                       |                     +---------------------->|                             |
        |                       |                     |    speech captured    |                             |
        |                       |                     |<----------------------+                             |
        |                       | POST /twilio/respond (SpeechResult=...)     |                             |
        |                       |<--------------------+                       |                             |
        |                       | append turn, ask Gemini for next reply, synthesize, return TwiML <Play><Gather>
        |                       | ... loop until "goodbye" or MAX_CONVERSATION_TURNS ...                    |
```

### Endpoints

- `POST /calls/outbound` - kicks off the call. Resolves provider voice from DB, creates a `Conversation` row, calls `Twilio.calls.create()` with `url=PUBLIC_API_BASE_URL/twilio/voice/{id}` and `status_callback=...`.
- `POST /twilio/voice/{id}` - first webhook hit when patient picks up. Uses Gemini to draft a warm greeting under the safety prompt, ElevenLabs to render it in the provider's voice, returns TwiML that plays the MP3 and opens a `<Gather input="speech">`.
- `POST /twilio/respond/{id}` - hit each time the patient finishes speaking. Captures `SpeechResult`, appends a `ConversationTurn`, asks Gemini for the next reply, synthesizes it, returns TwiML to play and gather again.
- `POST /twilio/status/{id}` - lifecycle callback (initiated, ringing, in-progress, completed, failed, busy, no-answer, canceled). Updates the conversation status.

### Safety system prompt

Every Gemini call uses a strict prompt that:
- Forbids diagnoses, prescriptions, dosage changes, and clinical advice.
- Tells the AI to defer to the actual care team for any medical question.
- Routes any mention of emergencies (chest pain, suicidal thoughts, severe symptoms) to "hang up and call 911 immediately."
- Caps replies at 35 words and bans markdown / lists / asterisks (so it sounds natural over the phone).
- Triggers a polite goodbye + hangup if the AI says "goodbye" or the conversation hits `MAX_CONVERSATION_TURNS`.

### Audio storage

Generated MP3s are written to `/app/generated` inside the API container (mounted as `generated_audio` volume locally, as a PVC in Kubernetes). Twilio fetches them via `GET /audio/{filename}`, served by FastAPI's `FileResponse`. The audio URL given to Twilio is `PUBLIC_API_BASE_URL/audio/{file}` so it has to come back through the public tunnel.

---

## 7. ElevenLabs voice cloning

The demo ships with two cloned voices and one premade voice:

| Provider          | ElevenLabs voice id          | Source                                      |
|-------------------|------------------------------|---------------------------------------------|
| Dr. Aadi          | `VrD3EIr2SqyhWLakvrMt`       | Cloned from `voicesample doctor/aadi doctor voice.ogg` |
| Bunny Patel PharmD| `fw4xyJhgrfgP0Y1OuCBb`       | Cloned from `voicesample pharma/bunny pharma voice note.ogg` |
| Dr. Maya Chen     | `21m00Tcm4TlvDq8ikWAM`       | Premade Rachel voice (fallback)             |

### Adding a new cloned voice

PowerShell example:

```powershell
$apiKey = $env:ELEVENLABS_API_KEY
$file = "c:\path\to\sample.ogg"
$boundary = [System.Guid]::NewGuid().ToString()
$LF = "`r`n"
$bytes = [System.IO.File]::ReadAllBytes($file)
$enc = [System.Text.Encoding]::GetEncoding("ISO-8859-1")
$bodyLines = (
  "--$boundary",
  'Content-Disposition: form-data; name="name"', "",
  "Dr Smith voice",
  "--$boundary",
  'Content-Disposition: form-data; name="files"; filename="sample.ogg"',
  "Content-Type: audio/ogg", "",
  $enc.GetString($bytes),
  "--$boundary--", ""
) -join $LF
$resp = Invoke-RestMethod -Uri "https://api.elevenlabs.io/v1/voices/add" -Method Post `
  -ContentType "multipart/form-data; boundary=$boundary" `
  -Headers @{ "xi-api-key" = $apiKey } `
  -Body ([System.Text.Encoding]::GetEncoding("ISO-8859-1").GetBytes($bodyLines))
$resp
```

The response gives you a `voice_id`. Set it in `.env` as either `DOCTOR_ELEVENLABS_VOICE_ID` or `PHARMACIST_ELEVENLABS_VOICE_ID`, restart the API, re-run `/seed` (or call `POST /provider-voices` to add additional voice rows directly).

### Voice mapping at call time

When `/calls/outbound` runs, the worker looks up `provider_voice_id` from the request, falls back to the provider's default voice from DB, and only falls back to `ELEVENLABS_VOICE_ID` from env if neither exists. So as long as you've assigned voices via `/seed` or the API, every patient hears the right person.

---

## 8. Web dashboard tour

The dashboard is intentionally minimalist - this is operations console UX, not a consumer app.

### Sections

1. **Hero**: brand + global actions (Seed Demo Data, Queue Reminder Call, Start Live AI Call, Refresh).
2. **Pipeline strip**: 4-stage live status of the current selected care relationship.
3. **Patients card**: flat list of all patients in DB.
4. **Care Relationships card**: every patient-provider pairing. Click "Use This Match" to set the active context.
5. **Provider Directory** (the new v0.0.4 card):
   - Each doctor/pharmacist is a collapsed row.
   - Click to expand -> see every patient on their roster, with phone numbers, plus a per-patient "Call" button that places an instant live AI call using that provider's cloned voice.
   - Includes an inline "Add patient" form that creates the patient + care assignment in one round-trip.
6. **Reminder Message**: textarea for the pre-recorded reminder workflow.
7. **Talk to AI (Live Call)**: phone input (defaults to `+16232008850`), purpose textarea, and a big "Call" button that uses the currently selected relationship's voice.
8. **Live Conversation**: real-time transcript, polled every 3s while a call is in flight.
9. **Reminders / Call Attempts**: history of the older one-way reminder workflow.

Version number is pinned bottom-right per the project's convention.

---

## 9. REST API reference

Base URL (local): `http://localhost:8000`

### Health & seed

| Method | Path     | Notes                                              |
|--------|----------|----------------------------------------------------|
| GET    | /health  | Returns `{status, service, version}`.              |
| POST   | /seed    | Idempotent: creates demo patients/providers/voices/assignments. |

### Patients / providers / voices

| Method | Path                | Notes                                          |
|--------|---------------------|------------------------------------------------|
| GET    | /patients           | All patients.                                  |
| POST   | /patients           | Create one. Body: `{full_name, phone_number, preferred_language?, consent_to_call?}`. |
| GET    | /providers          | All providers.                                 |
| POST   | /providers          | Body: `{full_name, role, department}`. Role must be `doctor`, `pharmacist`, or `nurse`. |
| GET    | /provider-voices    | All voice mappings.                            |
| POST   | /provider-voices    | Body: `{provider_id, label, elevenlabs_voice_id, is_default?}`. |

### Care assignments

| Method | Path                                   | Notes                                                |
|--------|----------------------------------------|------------------------------------------------------|
| GET    | /assignments                           | All raw assignments.                                 |
| POST   | /assignments                           | Body: `{patient_id, provider_id, relationship_type}`. |
| GET    | /care-relationships                    | Joined view: patient + provider + voice. Used by the UI. |
| GET    | /providers/{id}/patients               | Roster for a single provider (joined view).          |
| POST   | /providers/{id}/patients               | Quick-add: creates patient + active assignment in one call. Body: `{full_name, phone_number, provider_id, relationship_type?, preferred_language?}`. |

### Reminders (pre-recorded one-way workflow)

| Method | Path                                | Notes                                            |
|--------|-------------------------------------|--------------------------------------------------|
| POST   | /reminders                          | Body: `{patient_id, provider_id, message, queue_now?, scheduled_for?, provider_voice_id?}`. |
| POST   | /reminders/{id}/queue               | Re-queue a draft reminder.                       |
| GET    | /reminders                          | All reminders.                                   |
| GET    | /call-attempts                      | All worker-generated reminder call attempts (with audio_url). |

### Live AI calling

| Method | Path                                         | Notes                                                         |
|--------|----------------------------------------------|---------------------------------------------------------------|
| POST   | /calls/outbound                              | Kicks off a live AI call. Body: `{relationship_id?, patient_id?, provider_id?, provider_voice_id?, to_number?, purpose?}`. Resolves voice from DB, places Twilio call. |
| POST   | /twilio/voice/{conversation_id}              | Twilio webhook. Returns TwiML.                                |
| POST   | /twilio/respond/{conversation_id}            | Twilio webhook for `<Gather>` results. Returns TwiML.         |
| POST   | /twilio/status/{conversation_id}             | Twilio call status callback.                                  |
| GET    | /conversations                               | Recent live conversations (last 25).                          |
| GET    | /conversations/{id}                          | Single conversation with full turn-by-turn transcript.        |

### Audio

| Method | Path                  | Notes                                                |
|--------|-----------------------|------------------------------------------------------|
| GET    | /audio/{filename}     | Serves an MP3 from the generated audio volume. Twilio fetches via this. |

Auto-generated Swagger docs live at `http://localhost:8000/docs`.

---

## 10. Kubernetes deployment

All manifests live in `infra/k8s/` and are Kustomize-friendly.

### Resources shipped

```
infra/k8s/
+-- namespace.yaml            clara-voiceops namespace
+-- configmap.yaml            non-secret config (APP_VERSION, model names, public urls)
+-- demo-banner.yaml          GitOps demo ConfigMap (edit -> push -> ArgoCD syncs)
+-- secret.example.yaml       Template for the secret holding API keys + Twilio creds
+-- generated-audio-pvc.yaml  PVC mounted by API + worker for /app/generated
+-- postgres.yaml             StatefulSet + PVC + Service
+-- redis.yaml                Deployment + Service
+-- api.yaml                  Deployment + Service (port 8000)
+-- worker.yaml               Deployment (no service - it pulls from Redis)
+-- web.yaml                  Deployment + Service + Ingress for the React UI
+-- cronjob.yaml              Daily housekeeping job (rotates old audio, etc.)
+-- argocd-application.yaml   The Argo Application that points at this very repo
+-- kustomization.yaml        Lists all resources for `kubectl apply -k`
```

### Apply directly

```bash
kubectl apply -k infra/k8s
kubectl get pods -n clara-voiceops
kubectl logs -n clara-voiceops deployment/clara-worker -f
```

### Useful commands

```bash
kubectl scale -n clara-voiceops deployment/clara-worker --replicas=3
kubectl rollout status -n clara-voiceops deployment/clara-api
kubectl port-forward -n clara-voiceops svc/clara-web 5173:80
```

### Local kind clusters

The repo also ships convenience scripts to spin up two kind clusters - one for the app (`clara`) and one for ArgoCD (`argocd-lab`). Inside WSL:

```bash
kind create cluster --name clara
kind create cluster --name argocd-lab
kubectl --context kind-argocd-lab create ns argocd
kubectl --context kind-argocd-lab apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

---

## 11. ArgoCD GitOps demo

ArgoCD is already installed in the `kind-argocd-lab` cluster.

### Access the UI

```bash
# inside WSL (one-time port-forward; survives terminal close via setsid)
setsid bash -c 'kubectl --context kind-argocd-lab -n argocd port-forward --address 0.0.0.0 svc/argocd-server 8080:443' < /dev/null > /tmp/argocd-pf.log 2>&1 & disown
```

Then from any browser on Windows:

- URL: `https://localhost:8080`
- Username: `admin`
- Password: `kubectl --context kind-argocd-lab -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d`

(For this repo's current cluster the password is `wnn4-HwshpiAjdC7`.)

### Register the Clara application

```bash
kubectl --context kind-argocd-lab apply -f infra/k8s/argocd-application.yaml
```

You'll see `clara-voiceops` appear next to the existing `myapp-argo-application`. The Application points at `https://github.com/aaradhysharma/claradocpharma.git`, path `infra/k8s`, branch `main`, with `automated.prune` and `selfHeal` turned on.

### Trigger a visible GitOps change

The `infra/k8s/demo-banner.yaml` ConfigMap exists specifically for this demo. Edit any value (the `BANNER_TEXT` is the easiest):

```bash
# 1. Edit the file
code infra/k8s/demo-banner.yaml
# change BANNER_TEXT to "v0.0.5 - my new banner"

# 2. Commit and push
git add infra/k8s/demo-banner.yaml
git commit -m "demo: bump banner to v0.0.5"
git push origin main

# 3. Watch ArgoCD - within ~3 min the app flips OutOfSync -> Syncing -> Synced
```

You can also force an immediate sync from the UI ("Sync" button) instead of waiting for the polling interval.

### What ArgoCD reconciles

- Every Deployment, Service, ConfigMap, PVC, Ingress and CronJob in `infra/k8s/`.
- Drift detection: if anyone `kubectl edit`s a resource, ArgoCD reverts it to git-tracked state (because `selfHeal: true`).
- Pruning: resources removed from git are deleted from the cluster on next sync (because `prune: true`).

---

## 12. Terraform / AWS

`infra/terraform/` contains a minimal scaffold for an AWS deployment target:

- `main.tf` - VPC, EC2 instance, ECR repository, S3 bucket for generated audio, IAM role + instance profile.
- `variables.tf` - region, instance type, ami, etc.
- `outputs.tf` - public IP, ECR URL.
- `terraform.tfvars.example` - copy to `terraform.tfvars` and fill in.

Apply:

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan
terraform apply
```

This is intentionally a stub - in real life you'd swap EC2 for EKS or App Runner and replace the manual Docker build with a pipeline pushing to ECR. Treat it as the IaC story you can talk through in an interview.

---

## 13. CI/CD with GitHub Actions

`.github/workflows/` contains a build/test/push pipeline that:

1. Lints + unit tests the API and worker on every PR.
2. Builds Docker images and pushes them to GHCR (or ECR) on merge to `main`.
3. Updates the image tag in `infra/k8s/api.yaml` (or via Kustomize image override).
4. Pushes that change back, which triggers ArgoCD to roll out the new version.

This wires the whole loop: code change -> green CI -> image published -> manifest updated -> ArgoCD syncs -> rolling update on Kubernetes - with no manual `kubectl` step.

---

## 14. Configuration reference

All env vars are documented in `.env.example`.

| Key                              | Required for | Description                                                  |
|----------------------------------|--------------|--------------------------------------------------------------|
| `APP_VERSION`                    | Display      | Surfaced on `/health` and the UI footer.                     |
| `DATABASE_URL`                   | Always       | Postgres SQLAlchemy URL.                                     |
| `REDIS_URL`                      | Worker       | Redis connection URL for the reminder queue.                 |
| `AI_SCRIPT_ENABLED`              | Worker       | `true` to use Gemini for reminder script generation.         |
| `GEMINI_MODEL`                   | API + Worker | `gemini-2.5-flash` recommended.                              |
| `GEMINI_API_KEY`                 | API + Worker | Google AI Studio key. Used by both the worker (reminder scripts) and the API (live call replies). |
| `ELEVENLABS_API_KEY`             | Voice        | TTS + voice cloning.                                         |
| `ELEVENLABS_VOICE_ID`            | Voice        | Default fallback voice.                                      |
| `ELEVENLABS_MODEL`               | Voice        | Default `eleven_turbo_v2_5` (low latency, sounds great).     |
| `DOCTOR_ELEVENLABS_VOICE_ID`     | Voice        | Override doctor default voice id.                            |
| `PHARMACIST_ELEVENLABS_VOICE_ID` | Voice        | Override pharmacist default voice id.                        |
| `TWILIO_ACCOUNT_SID`             | Calls        | Twilio account.                                              |
| `TWILIO_AUTH_TOKEN`              | Calls        | Twilio token.                                                |
| `TWILIO_FROM_NUMBER`             | Calls        | A Twilio voice-enabled number you own.                       |
| `PUBLIC_API_BASE_URL`            | Calls        | Public https URL of the API (cloudflared / ngrok). Required for outbound live calls. |
| `PUBLIC_AUDIO_BASE_URL`          | Calls        | Optional override; defaults to `${PUBLIC_API_BASE_URL}/audio`. |
| `MAX_CONVERSATION_TURNS`         | Calls        | Hard cap on a live conversation (default 12).                |
| `GENERATED_DIR`                  | Calls        | Where MP3s are written. `/app/generated` in containers.      |

---

## 15. Operational runbook

### Bring everything up locally

```bash
docker compose up -d --build
cloudflared tunnel --url http://localhost:8000     # leave running
# update PUBLIC_API_BASE_URL in .env with the printed url
docker compose up -d --force-recreate api
curl -X POST http://localhost:8000/seed
```

### Tail API logs

```bash
docker compose logs -f api
```

### Tail worker logs

```bash
docker compose logs -f worker
```

### Reset the database (destructive!)

```bash
docker compose down -v
docker compose up -d --build
curl -X POST http://localhost:8000/seed
```

### Re-issue a Gemini key

If your Gemini key gets auto-revoked (Google scans GitHub for leaked keys), generate a new one at https://aistudio.google.com/app/apikey, paste it into `.env`, and restart the API:

```bash
docker compose up -d --force-recreate api
```

### Restart cloudflared (after reboot)

```bash
cloudflared tunnel --url http://localhost:8000
# put the new url into PUBLIC_API_BASE_URL and force-recreate the api container
```

---

## 16. Troubleshooting

### "An application error occurred" during a live call

Check API logs:

```bash
docker logs claradocpharma-api-1 --tail 200
```

Common causes:
- **`python-multipart` missing** -> fixed in v0.0.3 (was the original cause of the form-parse 500). Make sure your image is built from current `requirements.txt`.
- **Gemini 403 PERMISSION_DENIED ("Your API key was reported as leaked")** -> Google revoked the key. Issue a new one, update `.env`, recreate the API container.
- **ElevenLabs 401 / 429** -> bad or rate-limited key. Check your ElevenLabs dashboard.
- **Twilio webhook can't reach the API** -> `PUBLIC_API_BASE_URL` is wrong, the cloudflared tunnel died, or your firewall blocks outbound from the tunnel.

### Twilio call says "An application error has occurred. Goodbye." immediately

That's Twilio's polite way of saying our webhook returned non-200 or invalid TwiML. Check the API logs for a stack trace at the corresponding `/twilio/voice/...` request.

### The patient's voice isn't being recognized

Twilio's `<Gather input="speech">` uses `phone_call` model by default which is fine for English. If you need other languages, add `language="es-MX"` (or similar) to the Gather TwiML in `conversation_response()`.

### ArgoCD UI loads but says "Application not found"

Apply the Application manifest:

```bash
kubectl --context kind-argocd-lab apply -f infra/k8s/argocd-application.yaml
```

### `kubectl: command not found` on Windows

The kind/kubectl tooling lives inside WSL (`Ubuntu-24.04`). Run all kubectl/kind/argocd commands via:

```powershell
wsl -d Ubuntu-24.04 -- bash -c "kubectl get pods"
```

Or open a WSL shell directly.

---

## 17. Security notes

This repo is a demo. Before you'd put anything like this in front of real PHI:

- Replace `secret.example.yaml` with real Kubernetes Secrets sourced from a secret manager (AWS Secrets Manager, Vault, Sealed Secrets).
- Lock down `/audio/{filename}` - currently anyone who knows the filename can pull the MP3. Use signed URLs or move to S3 with presigned URLs.
- Enforce Twilio request signature validation on `/twilio/*` (the middleware hook is left out for demo simplicity).
- Add per-tenant auth on every API endpoint. Currently CORS is `*` and there is zero authn/authz.
- Encrypt the audio bucket and Postgres at rest, restrict egress, run with non-root containers (Dockerfiles already use slim bases but don't `USER` switch).
- Validate `to_number` against a do-not-call list and patient consent on every call.
- Log conversation transcripts in a HIPAA-eligible store with audit trails, not raw Postgres.

---

## 18. Roadmap / future work

- Stream Gemini token-by-token to ElevenLabs streaming TTS for sub-second latency (currently ~1.5-2.5s per turn).
- Swap polling for ArgoCD webhooks so changes appear instantly in the UI.
- Wire AWS S3 for audio storage instead of a local PVC.
- Per-tenant DB isolation (postgres schemas per clinic).
- True bidirectional Twilio media streams + ElevenLabs Conversational AI agents (lower latency than `<Gather>` + per-turn TTS).
- Patient consent management workflow + opt-out keywords ("STOP", "QUIT").
- Spanish + bilingual prompts (Gemini handles it, but we need to set Twilio Gather language).
- Soak tests + load tests under k6 simulating concurrent calls.
- Replace the demo `+16232008850` default with a per-org default phone book.

---

Built by Aaradhy as a demonstration project. Happy to walk through any layer in detail.
