# Get App Working

This is the restart checklist for **your machine** (WSL terminal + Docker Desktop backend) after shutdown/reboot, especially when the cloudflared tunnel crashes.

## 0) Open terminals (recommended layout)

Use 3 terminals so long-running commands do not block each other:

- **Terminal A**: app stack (docker compose)
- **Terminal B**: cloudflared tunnel
- **Terminal C**: quick checks / curl / troubleshooting

## 1) Start Docker Desktop first (from Windows)

1. Launch Docker Desktop from Start Menu.
2. Wait until Docker shows as running.
3. In WSL Terminal C:

```bash
docker version
```

If this fails, wait for Docker Desktop to finish starting and run again.

## 2) Start the app containers

In **Terminal A**:

```bash
cd /mnt/c/project2026/claradocpharma
docker compose up -d --build
docker compose ps
```

Expected: `api`, `worker`, `web`, `postgres`, `redis` are up.

## 3) Verify local API is healthy

In **Terminal C**:

```bash
curl http://localhost:8000/health
```

If health is not OK:

```bash
cd /mnt/c/project2026/claradocpharma
docker compose logs api --tail=100
docker compose logs worker --tail=100
```

## 4) Restart cloudflared tunnel (critical after reboot)

In **Terminal B**:

```bash
cloudflared tunnel --url http://localhost:8000
```

Keep this terminal open.  
Copy the generated `https://...trycloudflare.com` URL.

## 5) Update webhook base URL after tunnel changes

If cloudflared gave a new URL, update your `.env`:

- `PUBLIC_API_BASE_URL=https://<new-cloudflared-url>`
- Optionally keep `PUBLIC_AUDIO_BASE_URL` unset (the app derives it from `PUBLIC_API_BASE_URL`) unless you intentionally override it.

Then recreate API so new env is loaded.

In **Terminal A**:

```bash
cd /mnt/c/project2026/claradocpharma
docker compose up -d --force-recreate api
```

## 6) Seed demo data (safe to rerun)

In **Terminal C**:

```bash
curl -X POST http://localhost:8000/seed
```

## 7) Open UI and test

- Web: `http://localhost:5173`
- API docs: `http://localhost:8000/docs`

Quick call flow check:

1. Open dashboard.
2. Expand provider.
3. Click **Call** on a patient.
4. Confirm logs move in:
   - Terminal A: `docker compose logs -f api`
   - Terminal A: `docker compose logs -f worker`

## Cloudflared crash recovery (fast path)

If calls suddenly stop working, usually tunnel died or URL changed.

1. Stop old tunnel terminal (`Ctrl+C`).
2. Start again:

```bash
cloudflared tunnel --url http://localhost:8000
```

3. If URL changed, update `.env` `PUBLIC_API_BASE_URL`.
4. Recreate API:

```bash
cd /mnt/c/project2026/claradocpharma
docker compose up -d --force-recreate api
```

5. Re-test:

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/seed
```

## Full clean restart (when things feel weird)

```bash
cd /mnt/c/project2026/claradocpharma
docker compose down
docker compose up -d --build
curl http://localhost:8000/health
```

Then run tunnel again and update `.env` if URL changed.

## Optional daily shortcut sequence

Run these in order after each reboot:

```bash
# Terminal A
cd /mnt/c/project2026/claradocpharma
docker compose up -d

# Terminal B
cloudflared tunnel --url http://localhost:8000

# Terminal C
curl http://localhost:8000/health
```

If tunnel URL changed, update `.env` and run:

```bash
cd /mnt/c/project2026/claradocpharma
docker compose up -d --force-recreate api
```

## WSL path sanity check (run once)

If `/mnt/c/project2026/claradocpharma` does not exist in your distro, find the repo path and use that in commands above:

```bash
pwd
ls /mnt/c/project2026
```

