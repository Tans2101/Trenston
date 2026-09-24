"""Canonical integration definitions — user-facing connectable services only.

Platform infrastructure (Anthropic, R2, Resend, Paddle) is configured by the Trenston
host and must not appear as end-user "integrations".
"""
from __future__ import annotations

from typing import Any

import credential_crypto as cred_crypto
import google_oauth

# One Google grant powers every Google feature; a missing fragment means reconsent.
GOOGLE_REQUIRED_SCOPE_FRAGMENTS = (
    "calendar.events",
    "gmail.readonly",
    "gmail.compose",
    "spreadsheets",
    "drive.file",
)

# kind: oauth | credentials | coming_soon
USER_INTEGRATIONS: list[dict[str, Any]] = [
    {
        "id": "google",
        "name": "Google Workspace",
        "category": "Calendar & Email",
        "provider": "google",
        "kind": "oauth",
        "oauth": True,
        "pro": True,
        "description": "Connect your Google account once to bring your Calendar, important Gmail threads, Gmail draft replies, Sheets export and Drive bill import into Trenston. Personal to you — teammates never see your Google data.",
        "value": "Your schedule and important email in your morning briefing, with no tab switching.",
        "cta_route": "/app",
        "cta_label": "Open briefing",
        "connect_label": "Connect Google",
    },
    {
        "id": "quickbooks",
        "name": "QuickBooks",
        "category": "Finance",
        "provider": "quickbooks",
        "kind": "oauth",
        "oauth": True,
        "pro": True,
        "description": "Pull purchases and invoices from your QuickBooks company into Financials. Use QuickBooks or Xero; you typically connect one accounting system.",
        "value": "Real burn, runway, and expense categories, synced from the books you already use.",
        "cta_route": "/app/financials",
        "cta_label": "View financials",
        "connect_label": "Connect QuickBooks",
        "sync_action": True,
    },
    {
        "id": "xero",
        "name": "Xero",
        "category": "Finance",
        "provider": "xero",
        "kind": "oauth",
        "oauth": True,
        "pro": True,
        "description": "Pull invoices and bills from Xero into Financials, the global alternative to QuickBooks (UK, AU, NZ, and beyond).",
        "value": "Same Financials, Decision Engine, and reports pipeline as QuickBooks. Pick the ledger you already run.",
        "cta_route": "/app/financials",
        "cta_label": "View financials",
        "connect_label": "Connect Xero",
        "sync_action": True,
    },
    {
        "id": "sap_b1",
        "name": "SAP Business One",
        "category": "Finance",
        "provider": "sap_b1",
        "kind": "credentials",
        "oauth": False,
        "pro": True,
        "description": "Pull A/R invoices and A/P purchase invoices from SAP Business One Service Layer into Financials.",
        "value": "ERP invoices land in the same burn, runway, and Decision Engine pipeline as QuickBooks and Xero.",
        "cta_route": "/app/financials",
        "cta_label": "View financials",
        "connect_label": "Connect SAP B1",
        "sync_action": True,
    },
    {
        "id": "github",
        "name": "GitHub",
        "category": "Engineering",
        "provider": "github",
        "kind": "coming_soon",
        "oauth": False,
        "pro": True,
        "description": "Track PR velocity, releases, and engineering delivery in Telemetry.",
        "value": "Connect your repos to see shipping pace alongside business KPIs.",
        "coming_soon": True,
    },
    # Slack Incoming Webhook alerts are configured on the Integrations page UI
    # (not listed here) — do not re-add a coming_soon Slack OAuth card.
    {
        "id": "hubspot",
        "name": "HubSpot",
        "category": "Sales",
        "provider": "hubspot",
        "kind": "oauth",
        "oauth": True,
        "pro": True,
        "description": "Pull HubSpot CRM deals into Trenston Pipeline and Telemetry, built for SMB and mid-market teams.",
        "value": "Open pipeline, stage, and win/loss land in the same board as deals you create manually.",
        "cta_route": "/app/sales",
        "cta_label": "Open pipeline",
        "connect_label": "Connect HubSpot",
        "sync_action": True,
    },
]

# Back-compat alias for any code still importing INTEGRATION_CATALOG
INTEGRATION_CATALOG = USER_INTEGRATIONS


def _token_scope(tokens: dict | None) -> str:
    scope = (tokens or {}).get("scope") or ""
    if isinstance(scope, (list, tuple)):
        return " ".join(str(item) for item in scope)
    return str(scope)


def merge_integrations(
    workspace: dict,
    *,
    google_configured: bool,
    qb_configured: bool,
    xero_configured: bool = False,
    hubspot_configured: bool = False,
    user_google_tokens: Any = None,
    **_kwargs,
) -> list[dict]:
    """Build user integration cards with live connection status.

    Google Workspace (Calendar + Gmail + Sheets + Drive) status comes from ``user_google_tokens`` (the calling
    user's sealed or plaintext blob), not from the workspace document. Company
    ledgers (QuickBooks, Xero, HubSpot, SAP) remain workspace-scoped.
    """
    google_connected = cred_crypto.credentials_present(user_google_tokens)
    qb_connected = cred_crypto.credentials_present(workspace.get("quickbooks_tokens"))
    qb_last_synced = workspace.get("qb_last_synced_at")
    xero_tokens = None
    if cred_crypto.credentials_present(workspace.get("xero_tokens")):
        try:
            xero_tokens = cred_crypto.unseal_credentials(workspace.get("xero_tokens"))
        except cred_crypto.CredentialCryptoError:
            xero_tokens = None
    xero_connected = bool(xero_tokens and xero_tokens.get("tenant_id"))
    xero_pending = bool(xero_tokens and not xero_tokens.get("tenant_id") and xero_tokens.get("pending_tenants"))
    xero_last_synced = workspace.get("xero_last_synced_at")
    hubspot_connected = cred_crypto.credentials_present(workspace.get("hubspot_tokens"))
    hubspot_last_synced = workspace.get("hubspot_last_synced_at")
    sap_creds = None
    if cred_crypto.credentials_present(workspace.get("sap_b1_credentials")):
        try:
            sap_creds = cred_crypto.unseal_credentials(workspace.get("sap_b1_credentials"))
        except cred_crypto.CredentialCryptoError:
            sap_creds = None
    sap_connected = bool(sap_creds and sap_creds.get("service_layer_url") and sap_creds.get("company_db"))
    sap_last_synced = workspace.get("sap_b1_last_synced_at")
    google_tokens = None
    if google_connected:
        try:
            google_tokens = cred_crypto.unseal_credentials(user_google_tokens)
        except cred_crypto.CredentialCryptoError:
            google_tokens = None
    google_scope = _token_scope(google_tokens)

    oauth_configured = {
        "google": google_configured,
        "quickbooks": qb_configured,
        "xero": xero_configured,
        "hubspot": hubspot_configured,
    }

    out: list[dict] = []
    for spec in USER_INTEGRATIONS:
        item = dict(spec)
        item.setdefault("connected", False)
        kind = item.get("kind")

        if kind == "oauth":
            provider = item.get("provider")
            item["configured"] = oauth_configured.get(provider, False)
            if provider == "google":
                item["connected"] = google_connected
                missing = [frag for frag in GOOGLE_REQUIRED_SCOPE_FRAGMENTS if frag not in google_scope]
                if google_connected and missing:
                    item["needs_reconsent"] = True
                    item["connect_label"] = "Reconnect Google"
                item["capabilities"] = google_oauth.google_capabilities(
                    {"scope": google_scope} if google_tokens else None,
                )
            elif provider == "quickbooks":
                item["connected"] = qb_connected
                item["last_synced_at"] = qb_last_synced
            elif provider == "xero":
                item["connected"] = xero_connected
                item["last_synced_at"] = xero_last_synced
                item["needs_tenant_select"] = xero_pending
                if xero_tokens and xero_tokens.get("tenant_name"):
                    item["tenant_name"] = xero_tokens.get("tenant_name")
            elif provider == "hubspot":
                item["connected"] = hubspot_connected
                item["last_synced_at"] = hubspot_last_synced
        elif kind == "credentials":
            # Per-workspace secrets (e.g. SAP B1) — no host OAuth app required.
            item["configured"] = True
            if item.get("provider") == "sap_b1":
                item["connected"] = sap_connected
                item["last_synced_at"] = sap_last_synced
                if sap_creds and sap_creds.get("company_db"):
                    item["tenant_name"] = sap_creds.get("company_db")
        elif kind == "coming_soon":
            item["configured"] = False
            item["connected"] = False
        else:
            item["configured"] = True

        if item.get("coming_soon"):
            item["status"] = "coming_soon"
        elif item.get("oauth"):
            if item.get("connected"):
                item["status"] = "connected"
            elif item.get("needs_tenant_select"):
                item["status"] = "not_connected"
            elif not item.get("configured"):
                item["status"] = "unavailable"
            else:
                item["status"] = "not_connected"
        elif kind == "credentials":
            item["status"] = "connected" if item.get("connected") else "not_connected"
        else:
            item["status"] = "not_connected"

        out.append(item)
    return out
