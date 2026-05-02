# Deploy the web dashboard to Vercel

## What belongs on Vercel

Only **`apps/web`** — the React + Vite static build. That is a good fit for Vercel.

## What does not belong on Vercel (this repo)

- **`apps/api`** (FastAPI) — long-lived Python HTTP + WebSockets/streaming assumptions; host on ECS, Cloud Run, Fly.io, Railway, Render, or your Kubernetes cluster.
- **`apps/worker`**, **Postgres**, **Redis** — always-on processes / stateful services elsewhere.

Configure the browser UI to talk to your real API URL with **`VITE_API_BASE_URL`** (must be `https`, same-origin or CORS-allowed).

## Deploy from GitHub (recommended)

1. Push this repo to GitHub (already wired).
2. [Vercel](https://vercel.com/new) → Import the repo.
3. **Root Directory**: `apps/web`
4. **Framework Preset**: Vite (auto).
5. **Build Command**: `npm run build` (default).
6. **Output Directory**: `dist` (default).
7. **Environment Variables**:
   - `VITE_API_BASE_URL` = `https://<your-api-host>` (no trailing slash), e.g. your cloudflared URL or load balancer.

Redeploy after changing env vars (Vite bakes them at build time).

## CORS

The FastAPI app must allow your Vercel origin in CORS (or put the API behind the same domain via a reverse proxy). If calls fail in the browser, check Network tab and API CORS settings.

## Local check before deploy

```bash
cd apps/web
npm ci
npm run build
```

The built files are under `apps/web/dist`.

## Cursor / MCP

If you use the **Vercel MCP** in Cursor (`deploy_to_vercel`), it deploys the **current workspace**. Ensure the Vercel project’s **Root Directory** is **`apps/web`** in the dashboard, or run the Vercel CLI from `apps/web` so the build uses the right folder.
