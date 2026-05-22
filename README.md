# Datto RMM Webhook Quickjob Service

Receives Datto RMM monitor webhooks when software is detected or cleared, and runs a configured Datto RMM quick job on affected devices every 15 minutes while detection is active. State is stored in SQLite so scheduling resumes after container restarts.

### Overlap prevention

Before starting another quick job (only when the device is due per `QUICKJOB_INTERVAL_MINUTES`), the service checks the last job via `GET /v2/job/{jobUid}/results/{deviceUid}`. A new quick job is **not** created while `jobDeploymentStatus` is `null`, `Pending`, or `Running`. If skipped for that reason, the interval timer is reset and the status is checked again on the next scheduled run—not on every 60-second scheduler tick.

---

## Workflow: Docker host

### On your Docker host (Linux recommended)

1. Install Docker Engine and Docker Compose plugin.
2. Create a deploy folder and add:
   - `.env` (same values as on Windows)
   - `docker-compose.prod.yml` (edit `OWNER/REPO` to match your GitHub repo, lowercase)
3. Create a persistent data directory:

```bash
mkdir -p data
```

4. Log in to GHCR once (if the package is private):

```bash
echo $GITHUB_TOKEN | docker login ghcr.io -u YOUR_GITHUB_USER --password-stdin
```

5. Pull and run:

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

6. Check health:

```bash
curl http://localhost:8080/health
curl http://localhost:8080/ready
```

7. Put **HTTPS** in front of port 8080 (Caddy, nginx, Traefik, or your reverse proxy). Datto must reach:

`https://your-public-host/webhook/datto?secret=<WEBHOOK_SECRET>`

---

## Build on the Docker host without GHCR

Copy the project to the host, then:

```bash
docker compose up -d --build
```

This uses `docker-compose.yml` and builds the image locally (pip runs inside the build, not on your Windows machine).

---

## Optional: test on Windows with Docker Desktop

If you have [Docker Desktop](https://www.docker.com/products/docker-desktop/):

```powershell
cd path\to\dattowebhooktest
copy .env.example .env
# Edit .env with your values
docker compose up --build
```

Test webhook (PowerShell):

```powershell
$body = '{"event":"detected","device_uid":"test-device-uid","hostname":"TEST-PC"}'
Invoke-RestMethod -Method POST -Uri "http://localhost:8080/webhook/datto?secret=YOUR_WEBHOOK_SECRET" -ContentType "application/json" -Body $body
```

---

## Datto monitor configuration

In the monitor **Response → Send a Webhook**, use **application/json**.

**Alert raised (software detected):**

```json
{
  "event": "detected",
  "device_uid": "[device_uid]",
  "device_id": "[device_id]",
  "hostname": "[device_hostname]",
  "site_name": "[site_name]",
  "alert_uid": "[alert_uid]"
}
```

**Alert resolved (software cleared):**

```json
{
  "event": "cleared",
  "device_uid": "[device_uid]",
  "device_id": "[device_id]",
  "hostname": "[device_hostname]",
  "site_name": "[site_name]",
  "alert_uid": "[alert_uid]"
}
```

Enable **When Alert is Resolved**. Both payloads use the same URL.

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATTO_API_KEY` | Yes | Setup → Users → Generate API Keys |
| `DATTO_API_SECRET` | Yes | Same |
| `DATTO_API_BASE_URL` | Yes | e.g. `https://zinfandel-api.centrastage.net` |
| `DATTO_COMPONENT_UID` | Yes | Component UID for the quick job |
| `DATTO_JOB_NAME` | No | Default: `Webhook remediation` |
| `DATTO_JOB_VARIABLES_JSON` | No | Default: `[]` |
| `WEBHOOK_SECRET` | Yes | Shared secret for inbound webhooks |
| `QUICKJOB_INTERVAL_MINUTES` | No | Default: `15` |
| `RUN_ON_DETECT` | No | Default: `true` |
| `DATA_DIR` | No | Default: `/data` (mount `./data:/data`) |

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness |
| GET | `/ready` | Readiness (DB + Datto API token) |
| POST | `/webhook/datto` | Datto webhook (`?secret=` or `X-Webhook-Secret`) |

---

## Persistence

Active devices are stored in `DATA_DIR/active_devices.db` (default `/data`). Mount a volume so restarts keep tracking:

```yaml
volumes:
  - ./data:/data
```

---

## Docker image (GHCR)

Published on push to `main` or tags `v*`. Image: `ghcr.io/<owner>/<repo>:latest`.
