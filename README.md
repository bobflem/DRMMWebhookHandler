# Datto RMM Webhook Quickjob Service

Receives Datto RMM monitor webhooks when software is detected or cleared, and runs Datto RMM quick jobs on affected devices every 15 minutes while any monitor still reports detection. Multiple monitors can use **different webhook secrets** mapped to **different components** via a profiles config file.

### One quick job per device

Before starting another quick job (only when the device is due per `QUICKJOB_INTERVAL_MINUTES`), the service checks the last job via `GET /v2/job/{jobUid}/results/{deviceUid}`. A new quick job is **not** created while `jobDeploymentStatus` is `null`, `Pending`, or `Running`—regardless of which component/profile would run next.

### Multiple monitors (refcount)

- Each **detect** adds a `(device, profile)` row; scheduling starts on first detect for that device.
- **First detect** sets `primary_profile_id`; recurring quick jobs use that profile’s component until the device is fully cleared.
- Each **cleared** removes only that profile’s detection; scheduling stops only when **all** profiles have cleared for the device.

---

## Profiles config

Copy [`config/profiles.example.yaml`](config/profiles.example.yaml) to `config/profiles.yaml` and edit secrets and component UIDs:

```yaml
profiles:
  - id: unwanted-software-a
    secret: "your-secret-for-monitor-a"
    component_uid: "component-uid-from-datto"
    job_name: "Remediate software A"
    variables: []
```

| Field | Description |
|-------|-------------|
| `id` | Internal key (stored in DB) |
| `secret` | Webhook `?secret=` or `X-Webhook-Secret` value |
| `component_uid` | Datto component for quick jobs |
| `job_name` | Quick job display name |
| `variables` | Component variables (optional) |

Set `PROFILES_CONFIG_PATH` if not using the default `/config/profiles.yaml`.

**Legacy fallback:** If the profiles file is missing, a single profile is built from `WEBHOOK_SECRET`, `DATTO_COMPONENT_UID`, `DATTO_JOB_NAME`, and `DATTO_JOB_VARIABLES_JSON` in `.env`.

---

## Workflow: Docker host

1. Copy `.env.example` to `.env` and fill in Datto API keys.
2. Copy `config/profiles.example.yaml` to `config/profiles.yaml` and configure profiles.
3. Run:

```bash
mkdir -p data
docker compose up -d --build
```

4. Datto monitor webhook URL (one per profile secret):

`https://your-public-host/webhook/datto?secret=<profile-secret>`

5. Health checks:

```bash
curl http://localhost:8080/health
curl http://localhost:8080/ready
```

---

## Datto monitor payloads

**Alert raised:**

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

**Alert resolved:**

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

Enable **When Alert is Resolved**. Use `application/json`.

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATTO_API_KEY` | Yes | Setup → Users → Generate API Keys |
| `DATTO_API_SECRET` | Yes | Same |
| `DATTO_API_BASE_URL` | Yes | e.g. `https://zinfandel-api.centrastage.net` |
| `PROFILES_CONFIG_PATH` | No | Default: `/config/profiles.yaml` |
| `QUICKJOB_INTERVAL_MINUTES` | No | Default: `15` |
| `RUN_ON_DETECT` | No | Default: `true` |
| `DATA_DIR` | No | Default: `/data` |

Legacy (only if profiles file absent): `WEBHOOK_SECRET`, `DATTO_COMPONENT_UID`, `DATTO_JOB_NAME`, `DATTO_JOB_VARIABLES_JSON`.

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness |
| GET | `/ready` | Readiness (DB + Datto API token) |
| POST | `/webhook/datto` | Datto webhook (`?secret=` or `X-Webhook-Secret`) |

---

## Persistence

SQLite at `DATA_DIR/active_devices.db` with `device_detections` and `device_schedule` tables. Mount `./data:/data`.

---

## Docker image (GHCR)

Published on push to `main`, `dev`, or version tags `v*`.

| Branch / tag | Image tags |
|--------------|------------|
| `main` | `latest`, `main`, `sha-<commit>` |
| `dev` | `dev`, `sha-<commit>` (no `latest`) |
| `v1.2.3` | `1.2.3`, `1.2`, `1`, `sha-<commit>` |

Example: `ghcr.io/<owner>/<repo>:dev` for the dev branch.

For production compose, mount `config/profiles.yaml` the same way as in [`docker-compose.yml`](docker-compose.yml).
