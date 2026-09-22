# Trenston — CEO & Founder Operating System

Trenston is a multi-tenant executive cockpit: morning briefing, decisions, financials, pipeline, team pulse, and Ask Trenston AI.

## Ownership model (production)

Trenston is designed to run on **your** infrastructure — not Emergent:

| Concern | Production choice |
|---------|-------------------|
| Frontend | Vercel (+ your domain) |
| API | Render (`render.yaml`) |
| Database | **MongoDB Atlas** (persistent) |
| Auth | **Clerk** (Google SSO via Clerk) |
| AI | **Your** `ANTHROPIC_API_KEY` |
| Billing | Paddle |

### Why Kalun felt like “new account every Google login”

That was almost never “Google is broken.” Typical causes:

1. **Ephemeral / wiped Mongo** on Emergent previews — users and memberships disappeared between redeploys, so login correctly created a *new* DB user and empty workspace gate.
2. **Unstable email matching** — mixed-case emails and no `google_sub` key meant lookups could miss.
3. **Workspace ≠ user** — even with the same user row, missing memberships sends you through “create/join company” again, which feels like a brand-new account.

Production fix in this codebase:

- **Clerk** for sign-in (stable identity across sessions)
- Upsert by Clerk/`google_sub`, then normalized `email.lower()` where applicable
- Sparse unique indexes on `email` and `google_sub`
- **Atlas** (or other durable Mongo) — required on Render

> Google Cloud OAuth (`GOOGLE_CLIENT_*`) is **integration-only** (Calendar / Gmail / Sheets / Drive). It is not the login path.

## Deploy (Render + Vercel)

Use this checklist plus [docs/DEPLOY.md](./docs/DEPLOY.md), [docs/RENDER_SETUP.md](./docs/RENDER_SETUP.md), [docs/INTEGRATIONS.md](./docs/INTEGRATIONS.md), and [docs/GOOGLE_WORKSPACE_AND_CLOUD.txt](./docs/GOOGLE_WORKSPACE_AND_CLOUD.txt).

Connect Render/Vercel to **`Tans2101/Helm---Company-Cockpit`** on branch **`main`** (see `render.yaml`). If Render still points at `tansherd21`, fix it per [RENDER_SETUP.md](./docs/RENDER_SETUP.md).

Quick pointers:

Create a cluster, database user, and network access (allow Render IPs or `0.0.0.0/0` carefully). Copy the `mongodb+srv://…` URI.

### 2. Clerk (sign-in)

Configure Clerk for production (`CLERK_SECRET_KEY`, `CLERK_JWKS_URL` on Render; publishable key on Vercel). Google SSO for login is enabled in the Clerk dashboard — not via the Google Cloud OAuth client used for Workspace integrations.

### 3. Render API

- Connect this repo and use `render.yaml`, or create a Python Web Service with root `backend/`
- Start: `uvicorn server:app --host 0.0.0.0 --port $PORT`
- Health: `/api/health`
- Set env vars from `backend/.env.example` (especially `MONGO_URL`, `DB_NAME=trenston`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL=claude-sonnet-5`, Clerk, Paddle, `FRONTEND_URL` / `CORS_ORIGINS` / `APP_URL`)

### 4. Vercel frontend

- Root directory: `frontend`
- Build: `yarn build` (or `npm run build`)
- Env: leave `REACT_APP_BACKEND_URL` **empty** if using rewrites (recommended)
- Confirm the `/api/*` rewrite in `frontend/vercel.json` points at your **actual Render hostname** (today: `https://helm-company-cockpit.onrender.com`)
- With rewrites, set Render `COOKIE_SAMESITE=lax` (same-origin `/api`)

If you skip rewrites and call Render directly from the browser, set:

- `REACT_APP_BACKEND_URL=https://<api>.onrender.com`
- `COOKIE_SAMESITE=none` and `COOKIE_SECURE=true` on Render

### 5. Paddle webhook

Point Paddle to `https://<api>.onrender.com/api/webhook/paddle`.

## Go-live checklist

1. Strong `SESSION_SECRET` / `OAUTH_STATE_SECRET`
2. `ALLOW_DEMO_LOGIN=false`, `DEMO_RESET_ENABLED=false`, `COOKIE_SECURE=true`
3. Atlas Mongo + `/api/health` → `mongo: true`
4. Clerk sign-in twice → **same** `user_id` and workspace (not a fresh onboarding every time). Google Cloud OAuth is for Integrations only, not this smoke test.
5. Anthropic key set; Ask Trenston / briefing work
6. Paddle checkout + portal
7. `/privacy` and `/terms` placeholders replaced with your company details

## Local development

```bash
# Backend
cd backend
cp .env.example .env   # set MONGO_URL, ANTHROPIC_API_KEY, Clerk, FRONTEND_URL=http://localhost:3000
pip install -r requirements.txt
uvicorn server:app --reload --port 8001

# Frontend
cd frontend
echo 'REACT_APP_BACKEND_URL=http://localhost:8001' > .env
yarn install
yarn start
```

Open http://localhost:3000/login → sign in with Clerk.

## Pricing source of truth

Public plan names and dollar amounts live in **`frontend/src/lib/marketingCopy.js`** (`PLANS`). Keep `backend/plans.py` seats/prices aligned with that list. Do not paste prices into `memory/`, READMEs, or other docs — they drift (an old single-tier Pro claim once misled crawlers). After changing `PLANS`, run `cd frontend && yarn sync-llms` (also runs during `yarn build`) and `yarn check-pricing-drift`. Canonical crawlable page: `/pricing`; machine readers: `/llms.txt`.

## Changelog (manual only)

Public `/changelog` is driven solely by **`frontend/src/lib/changelog.json`**. Edit that file by hand to publish an entry — nothing in CI, deploy, or git history writes to it automatically.
