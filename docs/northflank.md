# Deploy on Northflank

## Security: API keys

Never commit Northflank or Datto secrets to Git. If an API key was shared in chat or logs, **revoke it in Northflank** and create a new one.

Store the new key only as a GitHub Actions secret: `NORTHFLANK_API_KEY`.

---

## Option A — Build on Northflank (Git + Dockerfile)

1. Create a **project** and link this GitHub repository.
2. Add a **deployment** (or combined) **service**:
   - **Build:** Dockerfile at `/Dockerfile`, context `/`
   - **Branch:** `dev` or `main`
   - **Instances:** `1` (SQLite + scheduler; do not scale horizontally without shared locking)
   - **Port:** `8080` (set runtime env `PORT=8080` if needed)
   - **Health check:** HTTP `GET /health` on port 8080
3. **Runtime environment variables** (secret group):
   - `DATTO_API_KEY`, `DATTO_API_SECRET`, `DATTO_API_BASE_URL`
   - `PROFILES_CONFIG_PATH=/config/profiles.yaml`
   - `DATA_DIR=/data`
   - `QUICKJOB_INTERVAL_MINUTES=15`, `RUN_ON_DETECT=true`
4. **Secret file** (runtime):
   - Mount path: `/config/profiles.yaml`
   - Content: your profiles YAML (see `config/profiles.example.yaml`)
5. **Persistent volume:**
   - Container mount path: `/data`
6. Enable **public HTTPS** port; use the Northflank URL in Datto:

   `https://<your-northflank-host>/webhook/datto?secret=<profile-secret>`

---

## Option B — GitHub Actions builds GHCR and deploys to Northflank

### Northflank setup (once)

1. Create project + deployment service (can use external image initially).
2. **Integrations → Registries:** add GitHub Container Registry credentials (`read:packages` PAT). Note the **credentials ID**.
3. Configure the service runtime (env, secret file, volume) as in Option A.
4. Note **project ID** and **service ID** from the Northflank UI or API.

### GitHub repository secrets

| Secret | Description |
|--------|-------------|
| `NORTHFLANK_API_KEY` | Northflank API token (after rotation) |
| `NORTHFLANK_PROJECT_ID` | Project ID |
| `NORTHFLANK_SERVICE_ID` | Service ID |
| `NORTHFLANK_CREDENTIALS_ID` | GHCR registry credentials ID in Northflank |

### CI behavior

On push to `dev` or `main`, GitHub Actions:

1. Builds and pushes `ghcr.io/<owner>/<repo>:dev` or `:latest`
2. Runs `northflank/deploy-to-northflank@v1` to update the service image

CI deploy is configured in `.github/workflows/docker-publish.yml` (`deploy-northflank` job on pushes to `main` and `dev`).

---

## Dockerfile / PORT

The image should start uvicorn with:

```dockerfile
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
```

Northflank can set `PORT`; default remains `8080`.

---

## Checklist after deploy

```bash
curl https://<your-host>/health
curl https://<your-host>/ready
```

Test webhook (replace secret and host):

```bash
curl -X POST "https://<your-host>/webhook/datto?secret=<profile-secret>" \
  -H "Content-Type: application/json" \
  -d '{"event":"detected","device_uid":"test-uid","hostname":"TEST"}'
```
