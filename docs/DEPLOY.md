# What you must do to launch Trenston (I cannot do these for you)

## Before first customer

Production is already on **MongoDB Atlas** (`/api/health` → `"mongo_source": "atlas"`). Clerk’s secret is already on Vercel. OAuth tokens are sealed automatically on API boot when `INTEGRATION_ENCRYPTION_KEY` is set. Do not add Redis, extra workers, Sentry, or SOC 2 yet.

Only dashboard clicks I cannot do from here:

1. **Render** → if a private service named `helm-mongo` still exists, delete it. The API is not using it.
2. **MongoDB Atlas** → cluster → Backup: turn on whatever your tier includes (or take a snapshot).
3. **Public email** `contact@trenston.com` is on the site/legal pages. Still set it in **Clerk** (support email) and **Paddle** (seller/customer email).
4. **DMARC** (Namecheap TXT, Host `_dmarc`): `v=DMARC1; p=none; rua=mailto:contact@trenston.com`
5. **Resend**: add domain `send.trenston.com` (not the root — Workspace already owns MX on `@`). Paste Resend’s DNS, then set Render `SENDER_EMAIL` to `Trenston <contact@trenston.com>`. Do **not** add a second SPF on `@`.

---

The code on **`main`** is set up for **your** stack:
Render (API) + Vercel (frontend/domain) + MongoDB Atlas + Clerk + Anthropic + Paddle.

Do these steps in order. After each step, check the “Done when” line.

> **Repo / branch:** connect Render and Vercel to **`Tans2101/Trenston`** on branch **`main`** (same as `render.yaml` and `.github/workflows/deploy-render.yml`). If a Render service still points at the old `tansherd21` fork or the pre-rename `Helm---Company-Cockpit` URL, see [RENDER_SETUP.md](./RENDER_SETUP.md) (“After repo transfer to Tans2101”).

---

## Start here

1. **MongoDB Atlas** — database (do this first)
2. **Clerk** — sign-in (Google SSO is configured inside Clerk; do not use DIY Google OAuth for login)
3. **Render** — API (see below)
4. **Vercel** — frontend + domain
5. **Anthropic** + **Cloudflare R2** + **Paddle** keys on Render
   - R2: [docs/R2_SETUP.md](R2_SETUP.md) (required for Financials bill uploads)

When `CLERK_SECRET_KEY` + `CLERK_JWKS_URL` are set on Render and
`REACT_APP_CLERK_PUBLISHABLE_KEY` + `CLERK_SECRET_KEY` are set as protected
Vercel environment variables, Trenston uses **Clerk for login** automatically.
The secret must be configured independently on each host; the API never
returns it to the frontend deployment.

**Google Cloud OAuth** (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`) is for **Calendar / Gmail / Sheets / Drive integrations only** — not the login path. Login is Clerk.

---

## 1. MongoDB Atlas

Create a cluster, database user, and network access (allow Render IPs or `0.0.0.0/0` carefully). Copy the `mongodb+srv://…` URI.

**Done when:** you have a URI that works from your laptop (`mongosh` or Compass).

> This is what fixed Kalun’s “new account every login” — Emergent’s DB was not durable.

---

## 2. Clerk (sign-in)

Configure the Clerk application for `clerk.trenston.com` (or your Clerk domain). Copy `pk_…`, `sk_…`, and the JWKS URL.

**Done when:** you have `pk_...`, `sk_...`, and JWKS URL saved.

---

## 3. Anthropic API key

1. https://console.anthropic.com → API keys → create key
2. Keep it for Render env as `ANTHROPIC_API_KEY`

**Done when:** you have a `sk-ant-...` key.

---

## 3b. Cloudflare R2 (bill / receipt uploads)

Full walkthrough: **[docs/R2_SETUP.md](R2_SETUP.md)**.

1. Cloudflare → R2 → create private bucket (e.g. `helm-documents`)
2. Create R2 API token (Object Read & Write) → copy Access Key ID + Secret
3. On Render set `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME` (`R2_ENDPOINT` optional if account id is set)
4. Redeploy → verify with `/api/setup/status` (`r2.ok: true`) or upload a bill in Financials

**Done when:** setup status shows R2 configured and ok, or a PDF upload reaches extraction.

---

## 4. Deploy API on Render

1. https://dashboard.render.com → New → Blueprint (or Web Service)
2. Connect GitHub repo **`Tans2101/Trenston`** (not `tansherd21/…` — see [RENDER_SETUP.md](./RENDER_SETUP.md))
3. Branch: **`main`**
4. If not using Blueprint:
   - Root directory: `backend`
   - Build: `pip install -r requirements-prod.txt`
   - Start: `uvicorn server:app --host 0.0.0.0 --port $PORT`
   - Health: `/api/health`
5. Set environment variables (copy from `backend/.env.example` / `render.yaml`):

| Key | Value |
|-----|--------|
| `MONGO_URL` | Atlas URI from step 1 |
| `DB_NAME` | `trenston` |
| `SESSION_SECRET` | long random string |
| `INTEGRATION_ENCRYPTION_KEY` | Fernet key — `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` — **required in production**; never commit |
| `OAUTH_STATE_SECRET` | long random string |
| `FRONTEND_URL` | `https://YOUR-VERCEL-DOMAIN` (set after step 5, then update) |
| `APP_URL` | same as `FRONTEND_URL` |
| `CORS_ORIGINS` | same as `FRONTEND_URL` (comma-separated if multiple) |
| `COOKIE_SECURE` | `true` |
| `COOKIE_SAMESITE` | `lax` if using Vercel `/api` rewrite; `none` if browser calls Render directly |
| `ALLOW_DEMO_LOGIN` | `false` |
| `DEMO_RESET_ENABLED` | `false` |
| `CLERK_SECRET_KEY` | Clerk secret key |
| `CLERK_JWKS_URL` | Clerk JWKS URL |
| `GOOGLE_CLIENT_ID` | Google **integration** OAuth client (Calendar/Gmail/Sheets/Drive) — not login |
| `GOOGLE_CLIENT_SECRET` | matching secret |
| `ANTHROPIC_API_KEY` | from step 3 |
| `ANTHROPIC_MODEL` | `claude-sonnet-5` |
| `PADDLE_API_KEY` | Paddle API key |
| `PADDLE_CLIENT_TOKEN` | Paddle.js client token |
| `PADDLE_PRICE_ID_STARTER` | Paddle price ID for Starter — create with 7-day trial |
| `PADDLE_PRICE_ID_GROWTH` | Paddle price ID for Growth — create with 7-day trial |
| `PADDLE_PRICE_ID_BUSINESS` | Paddle price ID for Business — create with 7-day trial |
| `PADDLE_WEBHOOK_SECRET` | Webhook secret |
| `PADDLE_ENV` | `production` or `sandbox` |
| `BILLING_ENFORCED` | `true` when ready to gate Free vs paid features |
| `RESEND_API_KEY` / `SENDER_EMAIL` | optional until invites |
| `SETUP_SECRET` | random string (admin/setup routes + orphan-doc cron) |
| `INTERNAL_CRON_SECRET` | dedicated random string for `/api/internal/*` crons (do not reuse `SETUP_SECRET`) |

**Removed / do not use:** single `PADDLE_PRICE_ID` and flat `PRO_PRICE` as the source of truth.
Tier amounts live in `backend/plans.py`.

### Plan migration (read this)

Existing workspaces with `plan: "pro"` are **migrated to Starter** on first API access (`get_ws` write-through).
That is a **conscious choice**: Starter is the closest paid tier to the old single Pro product.
If you want legacy Pro customers on Growth or Business instead, update those workspace documents in Mongo **before** enabling `BILLING_ENFORCED`, or after deploy with a one-off script.

6. Deploy → open `https://YOUR-API.onrender.com/api/health`

**Done when:** health returns `{"status":"ok","mongo":true}`.

### Encrypt existing Google / QuickBooks tokens (one-time)

After `INTEGRATION_ENCRYPTION_KEY` is set on Render (and the API has redeployed), seal any legacy plaintext token blobs:

```bash
cd backend
INTEGRATION_ENCRYPTION_KEY=... MONGO_URL=... DB_NAME=trenston \
  python scripts/migrate_encrypt_integration_tokens.py
```

Safe to re-run. New OAuth connections are encrypted automatically; this only migrates older workspace documents.

---

## 5. Deploy frontend on Vercel + domain

1. https://vercel.com → Import the same GitHub repo (`Tans2101/Trenston`, branch `main`)
2. Root directory: `frontend`
3. Framework: Create React App / leave defaults (`yarn build` / `npm run build`)
4. Environment:
   - Leave `REACT_APP_BACKEND_URL` **empty** if using rewrite (recommended)
   - Set Clerk publishable key (and secret if your Vercel setup requires it)
5. Confirm the `/api/*` rewrite in `frontend/vercel.json` points at your **actual Render hostname** (currently `https://helm-company-cockpit.onrender.com/api/:path*` — change it if your Render service name differs)
6. Redeploy
7. Domains → Add your domain purchased/managed in Vercel

**Done when:** `https://your-domain/` loads the Trenston landing page.

Then go back to Render and set `FRONTEND_URL`, `APP_URL`, `CORS_ORIGINS` to that domain and redeploy API.

---

## 6. Paddle webhook + multi-tier prices

1. In Paddle, create **three** products/prices (Starter / Growth / Business), each with a **7-day free trial**.
2. Copy each price ID into Render env vars listed above.
3. Set webhook URL to:

`https://YOUR-API.onrender.com/api/webhook/paddle`

**Done when:** checkout for a tier completes and the workspace `plan` becomes `starter` / `growth` / `business` (not `pro`).

### Downgrades

In-app downgrades are scheduled for the **end of the current billing period** (no mid-cycle refunds). Upgrades open Paddle checkout immediately.

---

## 7. Cron jobs (defined in `render.yaml`)

These run as Render **Cron** services on the same repo/branch as the API. Sync the matching secrets from the web service:

| Cron service | Schedule | Hits |
|--------------|----------|------|
| `helm-retention-checks` | daily | `POST /api/internal/run-retention-checks` (`INTERNAL_CRON_SECRET`) |
| `helm-accounting-sync` | hourly | `POST /api/internal/run-accounting-sync` (`INTERNAL_CRON_SECRET`) |
| `helm-daily-alerts` | daily | `POST /api/internal/run-daily-alerts` (`INTERNAL_CRON_SECRET`) |
| `helm-weekly-digest` | weekly | `POST /api/internal/run-weekly-digest` (`INTERNAL_CRON_SECRET`) |
| `helm-daily-briefing` | daily | `POST /api/internal/run-daily-briefing` (`INTERNAL_CRON_SECRET`) |
| `helm-orphan-doc-cleanup` | daily | `POST /api/admin/cleanup-orphaned-documents` (`SETUP_SECRET` / `X-Setup-Secret`) |

Bill/receipt uploads that are never saved as a financial entry (`linked_entry_id` stays empty) are purged after **7 days** (`DOC_ORPHAN_RETENTION_DAYS`, default `7`) by `helm-orphan-doc-cleanup`.

**Done when:** Blueprint deploy creates all six cron services and a manual curl to each endpoint with the correct secret returns 200.

---

## 7b. Retention emails (trial ending + inactivity)

`helm-retention-checks` hits once a day:

`POST https://www.trenston.com/api/internal/run-retention-checks`

```bash
curl -sf -X POST "https://www.trenston.com/api/internal/run-retention-checks" \
  -H "X-Trenston-Cron-Secret: YOUR_INTERNAL_CRON_SECRET"
```

Set `INTERNAL_CRON_SECRET` on the web service and each `INTERNAL_CRON_SECRET`-gated cron to the same dedicated random value. Do not reuse `SETUP_SECRET`.

- Trial reminder: workspaces with `subscription_status=trialing` whose trial ends within ~2 days, once per trial (`trial_reminder_sent`).
- Inactivity nudge: no Briefing visit (`last_active_at`) for 5+ days, once per inactivity window (`inactivity_nudge_sent_at`).
- Both skip empty workspaces (no pending decisions, overdue tasks, pipeline moves, or recent activity).

---

## 7c. Accounting auto-sync (QuickBooks + Xero)

`helm-accounting-sync` runs hourly:

`POST https://www.trenston.com/api/internal/run-accounting-sync`

```bash
curl -sf -X POST "https://www.trenston.com/api/internal/run-accounting-sync" \
  -H "X-Trenston-Cron-Secret: YOUR_INTERNAL_CRON_SECRET"
```

Uses the same `INTERNAL_CRON_SECRET` as retention. For each workspace with a live
QuickBooks or Xero connection it refreshes tokens, pulls new transactions since
`qb_last_synced_at` / `xero_last_synced_at`, and upserts into Financials.
Expired grants are cleared so owners can reconnect in Integrations. Manual
**Sync** on the Integrations page still works anytime.

---

## 8. Smoke test (must pass before you tell anyone)

1. Open your domain → **Sign in with Clerk** (Google SSO via Clerk is fine)
2. Sign in → create a company once
3. Sign out → sign in again with the **same Clerk account**
4. Confirm you land in the **same** company (not empty onboarding)
5. Ask Trenston / briefing (needs Anthropic)
6. Billing page loads (needs Paddle)

**Done when:** login #2 restores the same workspace.

> **Not the login path:** Google Cloud OAuth (`GOOGLE_CLIENT_*`) only powers Calendar / Gmail / Sheets / Drive under Integrations. Do not treat “Continue with Google” on the login page as that OAuth client — that button is Clerk.

---

## What I already did in the repo

- Clerk as production login; Google Workspace OAuth scoped to integrations
- Anthropic client (`backend/llm.py`)
- Legal pages, GDPR export/delete, Paddle-only billing, security defaults
- `render.yaml` (web + six crons), `frontend/vercel.json`, `backend/.env.example`, this file

### Department disable / re-enable (Sept 2026)

Disabling a department now soft-disables (`enabled: false`) instead of deleting the
Mongo row. Re-enable reuses the same `department_id`, so deals and financial entries
created before the disable stay linked. Workspaces that already deleted a department
(pre-fix) and re-created it may have orphaned `department_id` values on old deals —
those are rare; only repair if a customer reports missing history after a disable/re-enable
cycle that happened before this change.

---

## What I cannot do from here

- Log into your Atlas / Clerk / Render / Vercel / Anthropic / Paddle accounts
- Buy or attach your domain
- Paste your live secrets into those dashboards
- Click Deploy on your behalf

Those are the only remaining blockers.
