# Clara VoiceOps

Clara VoiceOps is an interview-focused healthcare reminder platform that demonstrates a full DevOps lifecycle around a small AI voice workflow.

The product flow is simple: create demo patients, assign a doctor or pharmacist, map that provider to an ElevenLabs voice, queue a reminder, and let a worker generate audio for the patient reminder.

## Stack

- FastAPI API
- Python worker
- Postgres relational data model
- Redis job queue
- React/Vite web dashboard
- ElevenLabs text-to-speech integration
- Twilio-ready call attempt tracking
- Docker Compose for local development
- Kubernetes manifests for k3s
- ArgoCD Application for GitOps
- Terraform for AWS EC2, ECR, S3, and IAM
- GitHub Actions CI/CD

## Local Quick Start

Copy the environment example:

```bash
cp .env.example .env
```

Set `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID` in `.env` when you are ready to generate real audio.

Start the stack:

```bash
docker compose up --build
```

Open:

- API docs: http://localhost:8000/docs
- Web dashboard: http://localhost:5173

Seed demo data:

```bash
curl -X POST http://localhost:8000/seed
```

## Interview Demo Commands

```bash
kubectl get pods -n clara-voiceops
kubectl logs deployment/clara-worker -n clara-voiceops
kubectl scale deployment clara-worker --replicas=2 -n clara-voiceops
kubectl rollout status deployment/clara-api -n clara-voiceops
```

## Version

Current app version: `0.0.1`
