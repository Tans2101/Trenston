# Render deploy — if build fails, use these exact settings

## Web Service settings

| Field | Value |
|-------|--------|
| **Repository** | `Tans2101/Helm---Company-Cockpit` |
| **Branch** | `main` |
| **Root Directory** | `backend` |
| **Runtime** | Python 3 |
| **Build Command** | `pip install -r requirements-prod.txt` |
| **Start Command** | `uvicorn server:app --host 0.0.0.0 --port $PORT` |
| **Health Check Path** | `/api/health` |

These match `render.yaml` and `.github/workflows/deploy-render.yml`. Prefer Blueprint deploy from `render.yaml` so cron jobs are created automatically.

## After repo transfer to Tans2101

Render may still point at the old `tansherd21` repo. That was a known past mistake — do **not** reconnect `tansherd21/Helm---Company-Cockpit` or any feature branch such as `cursor/helm-production-ready-*`. Fix:

1. Render Dashboard → your service → **Settings**
2. **Build & Deploy** → **Repository** → **Connect** / change to `Tans2101/Helm---Company-Cockpit`
3. Or: Account → **GitHub** → configure access for **Tans2101** org/user
4. Confirm **Branch** = `main`
5. **Manual Deploy** → Deploy latest commit

## "Build upload failed"

Usually **not** your code — upload to Render’s builders failed. Try in order:

1. **Manual Deploy** again (transient network blip)
2. Reconnect **GitHub** on Render (especially after transfer to Tans2101)
3. Confirm **Root Directory** = `backend` (not empty, not `frontend`)
4. Confirm branch = `main`
5. Check https://status.render.com

## Minimum env vars before first deploy

**Recommended:** deploy via **Blueprint** (`render.yaml`) with Atlas as the only database (`MONGO_URL` + `USE_ATLAS_MONGO=true`). Do not run a second Mongo on Render.

| Key | Required for build? | Required for run? |
|-----|---------------------|-------------------|
| `MONGO_URL` (Atlas) | No | **Yes** |
| `DB_NAME` | No | Yes (`trenston`) |
| `SESSION_SECRET` | No | Yes |
| `CLERK_SECRET_KEY` + `CLERK_JWKS_URL` | No | Yes (for login) |
| `ANTHROPIC_MODEL` | No | Optional (`claude-sonnet-5` in `render.yaml`) |

Check with the protected setup endpoint:

```bash
curl -H "X-Setup-Secret: YOUR_SETUP_SECRET" \
  https://helm-company-cockpit.onrender.com/api/setup/status
```

`mongo_probes` shows which URLs were tried.

Full launch checklist: [DEPLOY.md](./DEPLOY.md).
