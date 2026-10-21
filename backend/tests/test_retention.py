"""Trial-ending and inactivity retention emails — no live Resend required."""
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_retention")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import retention  # noqa: E402
import server  # noqa: E402


NOW = datetime(2026, 9, 8, 13, 0, tzinfo=timezone.utc)


def _ws(**kwargs):
    base = {
        "workspace_id": "ws_ret",
        "name": "Northwind",
        "subscription_status": "trialing",
        "trial_ends_at": (NOW + timedelta(days=2)).isoformat(),
        "trial_reminder_sent": False,
        "onboarding_done": True,
        "last_active_at": (NOW - timedelta(days=6)).isoformat(),
        "decisions": [
            {"id": "d1", "title": "Approve infra reservation", "status": "pending"},
        ],
        "tasks": {"items": [
            {"id": "t1", "title": "Security questionnaire", "column": "in_progress", "due": "2026-09-01"},
        ]},
    }
    base.update(kwargs)
    return base


def test_trial_due_two_days_out():
    assert retention.trial_reminder_due(_ws(), now=NOW, trial_days=7) is True


def test_trial_not_due_when_already_sent():
    assert retention.trial_reminder_due(_ws(trial_reminder_sent=True), now=NOW, trial_days=7) is False


def test_trial_not_due_when_five_days_remain():
    ws = _ws(trial_ends_at=(NOW + timedelta(days=5)).isoformat())
    assert retention.trial_reminder_due(ws, now=NOW, trial_days=7) is False


def test_trial_not_due_after_conversion():
    ws = _ws(subscription_status="active")
    assert retention.trial_reminder_due(ws, now=NOW, trial_days=7) is False


def test_inactivity_due_after_five_days():
    assert retention.inactivity_nudge_due(_ws(), now=NOW) is True


def test_inactivity_once_per_window():
    ws = _ws(inactivity_nudge_sent_at=(NOW - timedelta(days=1)).isoformat())
    assert retention.inactivity_nudge_due(ws, now=NOW) is False


def test_inactivity_skipped_while_browsing_pre_setup_demo():
    # Sample-data bullets would be about a made-up company.
    assert retention.inactivity_nudge_due(_ws(demo_mode=True), now=NOW) is False


def test_inactivity_can_fire_again_after_return():
    last = NOW - timedelta(days=6)
    ws = _ws(
        last_active_at=last.isoformat(),
        inactivity_nudge_sent_at=(last - timedelta(days=2)).isoformat(),
    )
    assert retention.inactivity_nudge_due(ws, now=NOW) is True


def test_empty_workspace_has_no_bullets():
    ws = _ws(decisions=[], tasks={"items": []}, decision_suggestions=[])
    assert retention.collect_change_bullets(ws, deals=[], activities=[], now=NOW) == []


def test_bullets_are_specific():
    bullets = retention.collect_change_bullets(
        _ws(),
        deals=[{"name": "Acme renewal", "stage": "proposal"}],
        activities=[],
        now=NOW,
    )
    assert any("Approve infra reservation" in b for b in bullets)
    assert any("Security questionnaire" in b for b in bullets)
    assert any("Acme renewal" in b for b in bullets)


def test_trial_email_links_to_app_briefing():
    html = retention.trial_email_html(
        workspace_name="Northwind",
        bullets=["Open decision: Hire GTM"],
        briefing_url="https://www.trenston.com/app",
    )
    assert "https://www.trenston.com/app" in html
    assert "card" in html.lower() or "charged" in html.lower()
    assert "Hire GTM" in html


def test_paddle_next_billed_at():
    iso = retention.trial_end_from_paddle_payload({
        "next_billed_at": "2026-09-10T15:00:00Z",
        "current_billing_period": {"ends_at": "2026-10-10T15:00:00Z"},
    })
    assert iso.startswith("2026-09-10")


@pytest.mark.asyncio
async def test_run_sends_each_email_once_then_skips():
    ws = _ws()
    stored = [ws]
    sent = []

    async def fake_send(to, subject, body, headers=None):
        sent.append({"to": to, "subject": subject, "body": body, "headers": headers})
        return {"sent": True}

    async def fake_recipients(_wid):
        return ["ceo@northwind.test"]

    mock_db = MagicMock()

    async def find_to_list(_limit=400):
        return list(stored)

    mock_find = MagicMock()
    mock_find.to_list = find_to_list
    mock_db.workspaces.find = MagicMock(return_value=mock_find)
    mock_db.workspaces.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    mock_db.deals.find = MagicMock(return_value=MagicMock(
        sort=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[]))),
    ))
    mock_db.activities.find = MagicMock(return_value=MagicMock(
        sort=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[]))),
    ))
    mock_db.email_suppressions.find_one = AsyncMock(return_value=None)

    stats = await retention.run_retention_checks(
        mock_db,
        now=NOW,
        trial_days=7,
        app_base_url="https://www.trenston.com",
        send_email=fake_send,
        recipient_emails=fake_recipients,
        signing_secret="retention-test-secret",
        api_base_url="https://www.trenston.com",
    )
    assert stats["trial_sent"] == 1
    assert stats["inactivity_sent"] == 1
    assert len(sent) == 2
    assert "/app" in sent[0]["body"]
    assert "Unsubscribe" in sent[0]["body"]
    assert "BGC, Taguig, Philippines" in sent[0]["body"]
    assert sent[0]["headers"] and "List-Unsubscribe" in sent[0]["headers"]
    assert mock_db.workspaces.update_one.await_count == 2
    # Claim filters must refuse a second writer once trial_reminder_sent is set.
    trial_claim = mock_db.workspaces.update_one.await_args_list[0].args[0]
    assert trial_claim.get("trial_reminder_sent") == {"$ne": True}

    # Same window: flags set on the in-memory workspace as the runner would persist
    stored[0]["trial_reminder_sent"] = True
    stored[0]["inactivity_nudge_sent_at"] = NOW.isoformat()
    sent.clear()
    stats2 = await retention.run_retention_checks(
        mock_db,
        now=NOW + timedelta(hours=20),
        trial_days=7,
        app_base_url="https://www.trenston.com",
        send_email=fake_send,
        recipient_emails=fake_recipients,
        signing_secret="retention-test-secret",
        api_base_url="https://www.trenston.com",
    )
    assert stats2["trial_sent"] == 0
    assert stats2["inactivity_sent"] == 0
    assert sent == []


@pytest.mark.asyncio
async def test_run_skips_empty_workspace():
    sent = []

    async def fake_send(*_a, **_k):
        sent.append(1)
        return {"sent": True}

    mock_db = MagicMock()
    empty = _ws(decisions=[], tasks={"items": []}, decision_suggestions=[])
    mock_find = MagicMock()
    mock_find.to_list = AsyncMock(return_value=[empty])
    mock_db.workspaces.find = MagicMock(return_value=mock_find)
    mock_db.workspaces.update_one = AsyncMock()
    mock_db.deals.find = MagicMock(return_value=MagicMock(
        sort=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[]))),
    ))
    mock_db.activities.find = MagicMock(return_value=MagicMock(
        sort=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[]))),
    ))
    stats = await retention.run_retention_checks(
        mock_db,
        now=NOW,
        trial_days=7,
        app_base_url="https://www.trenston.com",
        send_email=fake_send,
        recipient_emails=AsyncMock(return_value=["ceo@x.test"]),
    )
    assert sent == []
    assert stats["trial_skipped"] == 1
    assert stats["inactivity_skipped"] == 1
    mock_db.workspaces.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_lost_claim_skips_send_without_email():
    """Overlapping cron: first writer claimed the flag; second must not mail."""
    ws = _ws()
    sent = []

    async def fake_send(*_a, **_k):
        sent.append(1)
        return {"sent": True}

    mock_db = MagicMock()
    mock_find = MagicMock()
    mock_find.to_list = AsyncMock(return_value=[ws])
    mock_db.workspaces.find = MagicMock(return_value=mock_find)
    mock_db.workspaces.update_one = AsyncMock(return_value=MagicMock(matched_count=0))
    mock_db.deals.find = MagicMock(return_value=MagicMock(
        sort=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[]))),
    ))
    mock_db.activities.find = MagicMock(return_value=MagicMock(
        sort=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[]))),
    ))
    mock_db.email_suppressions.find_one = AsyncMock(return_value=None)

    stats = await retention.run_retention_checks(
        mock_db,
        now=NOW,
        trial_days=7,
        app_base_url="https://www.trenston.com",
        send_email=fake_send,
        recipient_emails=AsyncMock(return_value=["ceo@northwind.test"]),
        signing_secret="retention-test-secret",
        api_base_url="https://www.trenston.com",
    )
    assert sent == []
    assert stats["trial_sent"] == 0
    assert stats["inactivity_sent"] == 0
    assert stats["trial_skipped"] >= 1
    assert stats["inactivity_skipped"] >= 1


@pytest.mark.asyncio
async def test_suppressed_recipient_skips_send():
    ws = _ws()
    sent = []

    async def fake_send(to, subject, body, headers=None):
        sent.append(to)
        return {"sent": True}

    mock_db = MagicMock()
    mock_find = MagicMock()
    mock_find.to_list = AsyncMock(return_value=[ws])
    mock_db.workspaces.find = MagicMock(return_value=mock_find)
    mock_db.workspaces.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    mock_db.deals.find = MagicMock(return_value=MagicMock(
        sort=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[]))),
    ))
    mock_db.activities.find = MagicMock(return_value=MagicMock(
        sort=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[]))),
    ))
    mock_db.email_suppressions.find_one = AsyncMock(
        return_value={"email": "ceo@northwind.test", "category": "commercial"},
    )

    stats = await retention.run_retention_checks(
        mock_db,
        now=NOW,
        trial_days=7,
        app_base_url="https://www.trenston.com",
        send_email=fake_send,
        recipient_emails=AsyncMock(return_value=["ceo@northwind.test"]),
        signing_secret="retention-test-secret",
        api_base_url="https://www.trenston.com",
    )
    assert sent == []
    assert stats["suppressed_skipped"] >= 1
    assert stats["trial_sent"] == 0
    assert stats["inactivity_sent"] == 0

    async def mock_principal():
        return {"user_id": "u", "workspace_id": "ws", "pack": "owner", "role": "owner"}

    server.app.dependency_overrides[server.get_principal] = mock_principal
    with patch.object(server, "INTERNAL_CRON_SECRET", "cron-secret-test"), patch.object(
        server, "SETUP_SECRET", "setup-secret-test"
    ):
        client = TestClient(server.app)
        r = client.post("/api/internal/run-retention-checks")
        assert r.status_code == 401
        r2 = client.post("/api/internal/run-retention-checks", headers={"X-Trenston-Cron-Secret": "wrong"})
        assert r2.status_code == 401
    server.app.dependency_overrides.clear()


def test_endpoint_runs_with_cron_header():
    called = {}

    async def fake_run(*_a, **_k):
        called["ok"] = True
        return {"trial_sent": 0, "inactivity_sent": 0}

    with patch.object(server, "INTERNAL_CRON_SECRET", "cron-secret-test"), patch.object(
        server, "SETUP_SECRET", "setup-secret-test"
    ), patch.object(server.helm_retention, "run_retention_checks", new=fake_run), patch.object(
        server.helm_dept_drafts, "run_department_drafts", new=AsyncMock(return_value={"drafts_upserted": 0})
    ):
        client = TestClient(server.app)
        r = client.post(
            "/api/internal/run-retention-checks",
            headers={"X-Trenston-Cron-Secret": "cron-secret-test"},
        )
    assert r.status_code == 200, r.text
    assert called.get("ok") is True
    assert r.json()["trial_sent"] == 0
