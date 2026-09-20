# Integrations — Trenston

Trenston integrations are split into **OAuth connections** (per workspace) and **platform services** (configured once on Render). Set variables on your Render web service unless noted for Vercel.

Users never create API keys. Once you paste keys on Render, owners click **Connect** in the app.

## Paste these on Render (then redeploy)

| Service | Env vars | Where to get them |
|--------|----------|-------------------|
| **Google Calendar / Gmail** | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) → OAuth 2.0 Client (Web) |
| **QuickBooks** | `QUICKBOOKS_CLIENT_ID`, `QUICKBOOKS_CLIENT_SECRET`, `QUICKBOOKS_ENV` (`production` or `sandbox`) | [Intuit Developer](https://developer.intuit.com/) → app → Keys |
| **Xero** | `XERO_CLIENT_ID`, `XERO_CLIENT_SECRET` | [Xero Developer](https://developer.xero.com/) → My Apps → OAuth 2.0 |
| **HubSpot** | `HUBSPOT_CLIENT_ID`, `HUBSPOT_CLIENT_SECRET` | [HubSpot Developer](https://developers.hubspot.com/) → Apps → Auth |
| **Anthropic** | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | [Anthropic Console](https://console.anthropic.com/settings/keys) |
| **Cloudflare R2** | `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, plus `R2_ACCOUNT_ID` and/or `R2_ENDPOINT` | See **[docs/R2_SETUP.md](docs/R2_SETUP.md)** — Cloudflare → R2 → Manage API tokens |
| **Resend** | `RESEND_API_KEY`, `SENDER_EMAIL` | [Resend](https://resend.com/) — optional until invites |
| **Paddle** | `PADDLE_API_KEY`, `PADDLE_CLIENT_TOKEN`, `PADDLE_PRICE_ID_STARTER` / `_GROWTH` / `_BUSINESS` (or legacy `PADDLE_PRICE_ID`), `PADDLE_WEBHOOK_SECRET`, `PADDLE_ENV` | Paddle dashboard — when charging |
| **Clerk** | already on Render | Sign-in |

## OAuth redirect URIs (register exactly)

Because Vercel proxies `/api` → Render, register the **www** URLs:

**Google Cloud → Credentials → your OAuth client → Authorized redirect URIs**

```
https://www.trenston.com/api/oauth/google/callback
```

Also enable **Google Calendar API**, **Gmail API**, **Google Sheets API**, **Google Drive API**, and **Google Picker API** for the project.
Scopes requested (one Connect Google grant):

```
calendar.readonly
calendar.events
gmail.readonly
gmail.compose
spreadsheets
drive.file
```

Existing workspaces must **Reconnect Google** once after this change.

**Document AI (GCP $300 credits, optional)** — operator service account, not the user:

```
GCP_PROJECT_ID
GCP_DOCUMENT_AI_PROCESSOR_ID
GCP_DOCUMENT_AI_LOCATION=us
GCP_SERVICE_ACCOUNT_JSON
DOCUMENT_AI_GLOBAL_DAILY_LIMIT=80
DOCUMENT_AI_WORKSPACE_DAILY_LIMIT=8
```

Over those daily caps Trenston still extracts bills with Claude; it just stops calling Document AI so GCP credits are not exhausted. `0` turns Document AI off.

See `GOOGLE_WORKSPACE_AND_CLOUD.txt` for the exact Cloud Console clicks.

**Drive picker** (Financials → From Drive) also needs on Render:

```
GOOGLE_PICKER_API_KEY
GOOGLE_CLOUD_PROJECT_NUMBER
```

**Intuit Developer → your app → Keys → Redirect URI**

```
https://www.trenston.com/api/oauth/quickbooks/callback
```

Scopes needed: Accounting (`com.intuit.quickbooks.accounting`).

**Xero Developer → your app → Redirect URI**

```
https://www.trenston.com/api/oauth/xero/callback
```

Scopes needed: `offline_access`, `accounting.transactions.read` (plus openid profile email).
If the user can access multiple Xero organisations, Trenston asks them to pick one after Connect.

Workspaces typically connect **either** QuickBooks **or** Xero; both can coexist without interfering.

**SAP Business One (Service Layer)** — no platform OAuth app. Workspace owners enter:

- Service Layer URL (e.g. `https://host:50000/b1s/v1`)
- Company database name
- Username / password

Credentials are encrypted at rest (`INTEGRATION_ENCRYPTION_KEY`). After Connect, click **Sync to Financials** to pull A/R invoices and A/P purchase invoices into the same ledger shape as QuickBooks/Xero.

**HubSpot Developer → your app → Redirect URL**

```
https://www.trenston.com/api/oauth/hubspot/callback
```

Scopes needed: `oauth`, `crm.objects.deals.read`, `crm.objects.companies.read`, `crm.schemas.deals.read`.
After Connect, use **Sync to Pipeline** to pull deals into Trenston’s Sales board (same shape as manually created deals).

Verify live config with the Render `SETUP_SECRET`:

```
curl -H "X-Setup-Secret: YOUR_SETUP_SECRET" \
  https://www.trenston.com/api/setup/status
```

Look under `integrations` / `oauth_redirect_uris` — `configured: true` means the env vars are present.

## After keys are set

1. Redeploy the Render API (or wait for auto-deploy).
2. Sign in as a workspace **owner**.
3. Open **Integrations** → Connect Google / QuickBooks or Xero / SAP Business One / HubSpot.
4. If Google was connected before Gmail shipped, click **Enable Gmail** once to re-consent.
5. Accounting: after Connect (and org pick for Xero if needed), click **Sync to Financials**.
   SAP B1: enter Service Layer URL + company login in the Connect modal, then Sync.
6. HubSpot: after Connect, click **Sync to Pipeline**.
7. Financials uploads need R2 + Anthropic; Ask Trenston / briefing need Anthropic.

## Troubleshooting OAuth connect

If Intuit/Google shows Allow, then Helm toasts that it could not finish or save the connection:

1. Confirm the exact redirect URI is registered (see above) — sandbox and production Intuit apps each need their own Keys + Redirect URI.
2. On Render, set **sandbox** Development keys with `QUICKBOOKS_ENV=sandbox`, or Production keys with `QUICKBOOKS_ENV=production` (do not mix).
3. Ensure `INTEGRATION_ENCRYPTION_KEY` is a Fernet key (see `docs/DEPLOY.md`) — without it Helm cannot store tokens.
4. Check Render logs for `oauth token exchange quickbooks failed` (bad client secret / redirect) vs `oauth token store failed` (encryption/Mongo).
5. Click **Connect** again after fixing env (auth codes are single-use).

## Coming soon

GitHub stays “Coming soon” in the UI until that OAuth app is built.
Slack alerts use an Incoming Webhook on the Integrations page (not a full Slack OAuth app yet).

## Quick tester flow

1. Sign in with Clerk.
2. Set `ANTHROPIC_API_KEY` (+ R2) → generate a briefing and upload a bill.
3. Connect Google → open Calendar and check Email on the Briefing.
4. Connect QuickBooks or Xero → Sync to Financials.
5. Connect HubSpot → Sync to Pipeline.
6. Invite a teammate (Resend sends email when `RESEND_API_KEY` is set).

See also `backend/.env.example` for the full variable list.
