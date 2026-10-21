"""CAN-SPAM unsubscribe + commercial email footer — no live Resend required."""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_email_compliance")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import email_compliance as ec  # noqa: E402
import retention  # noqa: E402
import server  # noqa: E402


SECRET = "test-unsubscribe-secret-not-for-prod"


def test_audit_classification_documented():
    """Keep the commercial vs transactional list discoverable in the module docstring."""
    doc = ec.__doc__ or ""
    assert "weekly digest" in doc.lower() or "weekly pack" in doc.lower()
    assert "trial" in doc.lower()
    assert "inactivity" in doc.lower() or "catch-up" in doc.lower()
    assert "invite" in doc.lower()
    assert "delegation" in doc.lower()
    assert "alert" in doc.lower()


def test_token_roundtrip():
    token = ec.make_unsubscribe_token("CEO@Example.COM", secret=SECRET)
    parsed = ec.parse_unsubscribe_token(token, secret=SECRET)
    assert parsed["email"] == "ceo@example.com"
    assert parsed["category"] == ec.CATEGORY_COMMERCIAL


def test_token_rejects_tamper_and_expiry():
    token = ec.make_unsubscribe_token("a@b.com", secret=SECRET, now=1_700_000_000)
    with pytest.raises(ValueError):
        ec.parse_unsubscribe_token(token + "x", secret=SECRET)
    with pytest.raises(ValueError):
        ec.parse_unsubscribe_token(token, secret=SECRET, now=1_700_000_000 + ec.TOKEN_TTL_SECONDS + 10)


def test_marketing_footer_has_address_and_unsubscribe():
    html = ec.marketing_footer_html(unsubscribe_url="https://www.trenston.com/unsubscribe?token=abc")
    assert ec.COMPANY_POSTAL_ADDRESS in html
    assert "Unsubscribe" in html
    assert "https://www.trenston.com/unsubscribe?token=abc" in html


def test_retention_email_includes_footer_when_url_set():
    html = retention.trial_email_html(
        workspace_name="Northwind",
        bullets=["Open decision: Hire GTM"],
        briefing_url="https://www.trenston.com/app",
        unsubscribe_url="https://www.trenston.com/unsubscribe?token=xyz",
    )
    assert "Unsubscribe" in html
    assert ec.COMPANY_POSTAL_ADDRESS in html
    assert "unsubscribe?token=xyz" in html


def test_weekly_digest_html_includes_footer():
    import weekly_summary

    html = weekly_summary.email_html(
        workspace_name="Acme",
        summary=weekly_summary.build_summary(
            workspace={"decisions": [{"title": "Hire", "status": "pending"}], "tasks": {"items": []}},
            fin=None, stale=[], today=__import__("datetime").date(2026, 10, 19),
        ),
        app_url="https://www.trenston.com",
        unsubscribe_url="https://www.trenston.com/unsubscribe?token=digest",
    )
    assert "Unsubscribe" in html
    assert ec.COMPANY_POSTAL_ADDRESS in html


def test_invite_and_alert_templates_have_no_unsubscribe():
    invite = server._invite_email_html("Ada", "Acme", "Owner", "https://www.trenston.com/app")
    assert "Unsubscribe" not in invite
    assert ec.COMPANY_POSTAL_ADDRESS not in invite
    alert = __import__("alert_notify").build_alert_email_html(
        "Acme",
        [{"title": "Cash risk", "description": "Runway low"}],
        "https://www.trenston.com",
    )
    assert "Unsubscribe" not in alert


@pytest.mark.asyncio
async def test_suppress_then_filter():
    stored = {}

    class _Cursor:
        def __init__(self, rows):
            self._rows = rows

        async def to_list(self, _n):
            return list(self._rows)

    class _Coll:
        async def find_one(self, query, _proj=None):
            key = (query.get("email"), query.get("category"))
            return stored.get(key)

        def find(self, query, _proj=None):
            emails = set((query.get("email") or {}).get("$in") or [])
            cat = query.get("category")
            rows = [
                doc for (em, c), doc in stored.items()
                if em in emails and c == cat
            ]
            return _Cursor(rows)

        async def update_one(self, query, update, upsert=False):
            key = (query["email"], query["category"])
            doc = stored.get(key, {})
            doc.update(update.get("$set") or {})
            stored[key] = doc

    db = MagicMock()
    db.email_suppressions = _Coll()
    await ec.suppress_email(db, "CEO@Acme.test", source="test")
    assert await ec.is_suppressed(db, "ceo@acme.test") is True
    assert await ec.filter_unsuppressed(db, ["ceo@acme.test", "other@acme.test", "CEO@Acme.test"]) == ["other@acme.test"]


def test_unsubscribe_post_endpoint_writes_suppression():
    token = ec.make_unsubscribe_token("optout@helm.test", secret=SECRET)
    updates = []

    class _Coll:
        async def update_one(self, query, update, upsert=False):
            updates.append({"query": query, "update": update, "upsert": upsert})

        async def find_one(self, *_a, **_k):
            return None

    fake_db = MagicMock()
    fake_db.email_suppressions = _Coll()

    with patch.object(server, "SESSION_SECRET", SECRET), patch.object(server, "db", fake_db):
        client = TestClient(server.app)
        r = client.post("/api/email/unsubscribe", json={"token": token})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["email"] == "optout@helm.test"
    assert updates and updates[0]["upsert"] is True


def test_unsubscribe_get_redirects_after_suppress():
    token = ec.make_unsubscribe_token("click@helm.test", secret=SECRET)

    class _Coll:
        async def update_one(self, *_a, **_k):
            return None

    fake_db = MagicMock()
    fake_db.email_suppressions = _Coll()

    with patch.object(server, "SESSION_SECRET", SECRET), patch.object(server, "db", fake_db), patch.object(
        server, "APP_URL", "https://www.trenston.com"
    ):
        client = TestClient(server.app, follow_redirects=False)
        r = client.get(f"/api/email/unsubscribe?token={token}")
    assert r.status_code in (302, 303)
    loc = r.headers.get("location") or ""
    assert "/unsubscribe?status=ok" in loc
