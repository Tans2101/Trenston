# Helm — CEO Operating System

Helm is a multi-tenant executive cockpit: morning briefing, decisions, financials, pipeline, team pulse, and Ask Helm AI.

## Ownership model (production)

Helm is designed to run on **your** infrastructure — not Emergent:

| Concern | Production choice |
|---------|-------------------|
| Frontend | Vercel (+ your domain) |
| API | Render (`render.yaml`) |
| Database | **MongoDB Atlas** (persistent) |
| Auth | **Your** Google Cloud OAuth client |
| AI | **Your** `ANTHROPIC_API_KEY` |
| Billing | Paddle |

### Why Kalun felt like “new account every Google login”

That was almost never “Google is broken.” Typical causes:

1. **Ephemeral / wiped Mongo** on Emergent previews — users and memberships disappeared between redeploys, so login correctly created a *new* DB user and empty workspace gate.
2. **Unstable email matching** — mixed-case emails and no `google_sub` key meant lookups could miss.
3. **Workspace ≠ user** — even with the same user row, missing memberships sends you through “create/join company” again, which feels like a brand-new account.

Production fix in this codebase:

- Upsert by `google_sub`, then normalized `email.lower()`
- Sparse unique indexes on `email` and `google_sub`
- **Atlas** (or other durable Mongo) — required on Render
- Sessions issued by Helm (not Emergent)

## Deploy (Render + Vercel)

Use this checklist plus [INTEGRATIONS.md](./INTEGRATIONS.md) and [GOOGLE_WORKSPACE_AND_CLOUD.txt](./GOOGLE_WORKSPACE_AND_CLOUD.txt) for Google/Workspace setup.

### 1. MongoDB Atlas

Create a cluster, database user, and network access (allow Render IPs or `0.0.0.0/0` carefully). Copy the `mongodb+srv://…` URI.

### 2. Google Cloud OAuth

Create an OAuth 2.0 Web client. Add authorized redirect URI:

`https://<your-helm-api>.onrender.com/api/auth/google/callback`

Add authorized JavaScript origins for your Vercel domain if prompted.

### 3. Render API

- Connect this repo and use `render.yaml`, or create a Python Web Service with root `backend/`
- Start: `uvicorn server:app --host 0.0.0.0 --port $PORT`
- Health: `/api/health`
- Set env vars from `backend/.env.example` (especially `MONGO_URL`, `ANTHROPIC_API_KEY`, Google, Paddle, `FRONTEND_URL` / `CORS_ORIGINS` / `APP_URL`)

### 4. Vercel frontend

- Root directory: `frontend`
- Build: `yarn build` (or `npm run build`)
- Env: leave `REACT_APP_BACKEND_URL` **empty** if using rewrites (recommended)
- Edit `frontend/vercel.json` and replace `REPLACE_WITH_YOUR_RENDER_SERVICE` with your Render hostname
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
4. Google login twice → **same** `user_id` and workspace (not a fresh onboarding every time)
5. Anthropic key set; Ask Helm / briefing work
6. Paddle checkout + portal
7. `/privacy` and `/terms` placeholders replaced with your company details

## Local development

```bash
# Backend
cd backend
cp .env.example .env   # set MONGO_URL, ANTHROPIC_API_KEY, GOOGLE_*, FRONTEND_URL=http://localhost:3000
# Google redirect URI for local: http://localhost:8001/api/auth/google/callback
pip install -r requirements.txt
uvicorn server:app --reload --port 8001

# Frontend
cd frontend
echo 'REACT_APP_BACKEND_URL=http://localhost:8001' > .env
yarn install
yarn start
```

Open http://localhost:3000/login → Continue with Google.
