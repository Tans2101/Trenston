"""Integration catalog merge and status tests."""
from __future__ import annotations

import integrations_catalog as cat


def test_merge_oauth_google_not_connected():
    ws = {"workspace_id": "ws1", "quickbooks_tokens": None, "plan": "free"}
    ints = cat.merge_integrations(ws, google_configured=True, qb_configured=True)
    gcal = next(i for i in ints if i["id"] == "google")
    assert gcal["status"] == "not_connected"
    assert gcal["configured"] is True


def test_merge_oauth_unavailable_when_not_configured():
    ws = {"workspace_id": "ws1", "plan": "free"}
    ints = cat.merge_integrations(ws, google_configured=False, qb_configured=False)
    gcal = next(i for i in ints if i["id"] == "google")
    qb = next(i for i in ints if i["id"] == "quickbooks")
    assert gcal["status"] == "unavailable"
    assert qb["status"] == "unavailable"


def test_merge_oauth_connected():
    scope = "https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/gmail.readonly"
    ws = {
        "workspace_id": "ws1",
        "quickbooks_tokens": {"access_token": "y"},
        "xero_tokens": {"access_token": "z", "tenant_id": "tenant-1", "tenant_name": "Demo"},
    }
    user_google = {"access_token": "x", "scope": scope}
    ints = cat.merge_integrations(
        ws,
        google_configured=True,
        qb_configured=True,
        xero_configured=True,
        user_google_tokens=user_google,
    )
    gcal = next(i for i in ints if i["id"] == "google")
    qb = next(i for i in ints if i["id"] == "quickbooks")
    xero = next(i for i in ints if i["id"] == "xero")
    assert gcal["status"] == "connected"
    assert gcal["capabilities"]["gmail"] is True
    assert qb["status"] == "connected"
    assert xero["status"] == "connected"
    assert xero["tenant_name"] == "Demo"


def test_xero_needs_tenant_select():
    ws = {
        "workspace_id": "ws1",
        "xero_tokens": {
            "access_token": "z",
            "pending_tenants": [{"tenant_id": "a", "tenant_name": "A"}, {"tenant_id": "b", "tenant_name": "B"}],
        },
        "plan": "free",
    }
    ints = cat.merge_integrations(ws, google_configured=True, qb_configured=True, xero_configured=True)
    xero = next(i for i in ints if i["id"] == "xero")
    assert xero["status"] == "not_connected"
    assert xero.get("needs_tenant_select") is True
    assert xero["connected"] is False


def test_google_needs_reconsent_when_calendar_only():
    ws = {"workspace_id": "ws1", "plan": "free"}
    user_google = {
        "access_token": "x",
        "scope": "https://www.googleapis.com/auth/calendar.readonly",
    }
    ints = cat.merge_integrations(
        ws, google_configured=True, qb_configured=True, user_google_tokens=user_google,
    )
    google = next(i for i in ints if i["id"] == "google")
    assert google["status"] == "connected"
    assert google.get("needs_reconsent") is True
    assert google["connect_label"] == "Reconnect Google"
    assert google["capabilities"]["gmail"] is False


FULL_SCOPE = " ".join(
    f"https://www.googleapis.com/auth/{frag}"
    for frag in ("calendar.events", "gmail.readonly", "gmail.compose", "spreadsheets", "drive.file")
)


def test_catalog_has_exactly_one_google_entry():
    ids = [i["id"] for i in cat.USER_INTEGRATIONS]
    assert ids.count("google") == 1
    assert "google_calendar" not in ids
    assert "gmail" not in ids
    google = next(i for i in cat.USER_INTEGRATIONS if i["id"] == "google")
    assert google["name"] == "Google Workspace"
    assert google["category"] == "Calendar & Email"
    assert google["connect_label"] == "Connect Google"
    assert google["cta_route"] == "/app"


def test_google_needs_reconsent_when_gmail_compose_missing():
    scope = FULL_SCOPE.replace("https://www.googleapis.com/auth/gmail.compose", "")
    ints = cat.merge_integrations(
        {"workspace_id": "ws1"}, google_configured=True, qb_configured=True,
        user_google_tokens={"access_token": "x", "scope": scope},
    )
    google = next(i for i in ints if i["id"] == "google")
    assert google["connected"] is True
    assert google["needs_reconsent"] is True
    assert google["connect_label"] == "Reconnect Google"
    assert google["capabilities"]["gmail_compose"] is False


def test_google_full_grant_no_reconsent():
    ints = cat.merge_integrations(
        {"workspace_id": "ws1"}, google_configured=True, qb_configured=True,
        user_google_tokens={"access_token": "x", "scope": FULL_SCOPE},
    )
    google = next(i for i in ints if i["id"] == "google")
    assert google["connected"] is True
    assert not google.get("needs_reconsent")
    assert google["connect_label"] == "Connect Google"
    caps = google["capabilities"]
    assert all(caps[k] for k in ("gmail", "gmail_compose", "calendar_write", "sheets", "drive_file"))


def test_merge_oauth_connected_when_sealed():
    sealed = {"_helm_enc": "v1", "payload": "gAAAAABnot-a-real-token-but-present"}
    ws = {"workspace_id": "ws1", "quickbooks_tokens": sealed, "plan": "free"}
    ints = cat.merge_integrations(
        ws, google_configured=True, qb_configured=True, user_google_tokens=sealed,
    )
    gcal = next(i for i in ints if i["id"] == "google")
    qb = next(i for i in ints if i["id"] == "quickbooks")
    # Sealed blob counts as present even if payload cannot be unsealed here.
    assert gcal["connected"] is True
    assert qb["connected"] is True


def test_workspace_google_tokens_ignored_without_user_blob():
    """Legacy workspace-level google_tokens must not mark the user as connected."""
    ws = {
        "workspace_id": "ws1",
        "google_tokens": {"access_token": "legacy", "scope": "gmail.readonly"},
        "plan": "free",
    }
    ints = cat.merge_integrations(ws, google_configured=True, qb_configured=True)
    gcal = next(i for i in ints if i["id"] == "google")
    assert gcal["status"] == "not_connected"


def test_coming_soon_integrations():
    ws = {"workspace_id": "ws1", "plan": "pro"}
    ints = cat.merge_integrations(ws, google_configured=True, qb_configured=True)
    github = next(i for i in ints if i["id"] == "github")
    assert github["coming_soon"] is True
    assert github["status"] == "coming_soon"
    google = next(i for i in ints if i["id"] == "google")
    assert google.get("coming_soon") is not True
    assert google["kind"] == "oauth"
    assert google["provider"] == "google"
    hubspot = next(i for i in ints if i["id"] == "hubspot")
    assert hubspot["kind"] == "oauth"
    assert hubspot["provider"] == "hubspot"
    assert hubspot.get("sync_action") is True
    sap = next(i for i in ints if i["id"] == "sap_b1")
    assert sap["kind"] == "credentials"
    assert sap["provider"] == "sap_b1"
    assert sap.get("sync_action") is True
    assert sap["status"] == "not_connected"
    assert not any(i["id"] == "salesforce" for i in ints)
    assert not any(i["id"] == "slack" for i in ints)


def test_hubspot_connected_when_tokens_present():
    ws = {
        "workspace_id": "ws1",
        "hubspot_tokens": {"access_token": "hs", "refresh_token": "r"},
        "hubspot_last_synced_at": "2026-09-01T00:00:00+00:00",
        "plan": "free",
    }
    ints = cat.merge_integrations(
        ws, google_configured=True, qb_configured=True, hubspot_configured=True,
    )
    hubspot = next(i for i in ints if i["id"] == "hubspot")
    assert hubspot["status"] == "connected"
    assert hubspot["last_synced_at"] == "2026-09-01T00:00:00+00:00"
