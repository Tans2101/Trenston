"""Proactive daily alerts + weekly digest cron runners and internal endpoints."""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DB_NAME", "test_proactive_cron")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

import server


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    async def to_list(self, _n):
        return list(self._rows)


def test_daily_alerts_endpoint_requires_cron_secret():
    with patch.object(server, "INTERNAL_CRON_SECRET", "cron-secret-test"):
        client = TestClient(server.app)
        assert client.post("/api/internal/run-daily-alerts").status_code == 401
        assert client.post(
            "/api/internal/run-daily-alerts",
            headers={"X-Trenston-Cron-Secret": "wrong"},
        ).status_code == 401


def test_daily_alerts_endpoint_runs_with_cron_header():
    with (
        patch.object(server, "INTERNAL_CRON_SECRET", "cron-secret-test"),
        patch.object(
            server,
            "run_daily_alerts_cron",
            new=AsyncMock(return_value={"workspaces_scanned": 0, "ok": 0, "skipped": 0, "errors": 0, "new_alerts": 0}),
        ),
    ):
        client = TestClient(server.app)
        res = client.post(
            "/api/internal/run-daily-alerts",
            headers={"X-Trenston-Cron-Secret": "cron-secret-test"},
        )
    assert res.status_code == 200
    assert res.json()["workspaces_scanned"] == 0


def test_weekly_digest_endpoint_requires_cron_secret():
    with patch.object(server, "INTERNAL_CRON_SECRET", "cron-secret-test"):
        client = TestClient(server.app)
        assert client.post("/api/internal/run-weekly-digest").status_code == 401
        assert client.post(
            "/api/internal/run-weekly-digest",
            headers={"X-Trenston-Cron-Secret": "wrong"},
        ).status_code == 401


def test_weekly_digest_endpoint_runs_with_cron_header():
    with (
        patch.object(server, "INTERNAL_CRON_SECRET", "cron-secret-test"),
        patch.object(
            server,
            "run_weekly_digest_cron",
            new=AsyncMock(return_value={"workspaces_scanned": 0, "sent": 0, "week": "2026-W38"}),
        ),
    ):
        client = TestClient(server.app)
        res = client.post(
            "/api/internal/run-weekly-digest",
            headers={"X-Trenston-Cron-Secret": "cron-secret-test"},
        )
    assert res.status_code == 200
    assert res.json()["sent"] == 0


def test_run_daily_alerts_isolates_workspace_failures():
    rows = [
        {"workspace_id": "ws_ok", "name": "Ok Co"},
        {"workspace_id": "ws_bad", "name": "Bad Co"},
        {"workspace_id": "ws_skip", "name": "Skip Co"},
    ]
    fake_db = MagicMock()
    fake_db.workspaces.find = MagicMock(return_value=_Cursor(rows))

    async def fake_generate(wid, *, raise_on_rate_limit=False):
        assert raise_on_rate_limit is False
        if wid == "ws_bad":
            raise RuntimeError("boom")
        if wid == "ws_skip":
            return {"skipped": "rate_limited"}
        return {
            "ok": True,
            "notifications": {"new_alerts": 2, "emailed": True, "slack": False},
        }

    with (
        patch.object(server, "db", fake_db),
        patch.object(server, "_generate_insights", side_effect=fake_generate),
    ):
        stats = asyncio.run(server.run_daily_alerts_cron())

    assert stats["workspaces_scanned"] == 3
    assert stats["ok"] == 1
    assert stats["skipped"] == 1
    assert stats["errors"] == 1
    assert stats["new_alerts"] == 2


# Monday 19 Oct 2026, 08:00 in Manila (UTC+8).
MONDAY_MORNING_MANILA = datetime(2026, 10, 19, 0, 0, tzinfo=timezone.utc)

_FIN = {
    "cash": "₱500K", "cash_entered": True,
    "burn": "₱120K", "burn_known": True, "burn_value": 120000,
    "runway_months": 4.2, "runway_no_burn": False, "runway_basis": "Based on the last 3 full months.",
}


def _ws(wid, **extra):
    doc = {
        "workspace_id": wid, "name": f"{wid} Co", "plan": "growth", "timezone": "Asia/Manila",
        "decisions": [{"id": "d1", "title": "Hire a plant manager", "status": "pending"}],
        "tasks": {"items": [{"id": "t1", "title": "Send report", "assignee": "Sarah",
                             "column": "doing", "due": "2026-10-03"}]},
    }
    doc.update(extra)
    return doc


def _run_weekly(monkeypatch, docs, *, now=MONDAY_MORNING_MANILA, fin_readers=("ceo@x.test",),
                everyone=("ceo@x.test", "coo@x.test"), pack_raises=None):
    from mongomock_motor import AsyncMongoMockClient

    db = AsyncMongoMockClient()["weekly"]
    sent = []

    async def fake_send(*, to, subject, html, attachments=None, headers=None):
        sent.append({"to": to, "subject": subject, "html": html, "attachments": attachments, "headers": headers})
        return {"sent": True, "id": "e1"}

    async def recipients(wid, financial=False, **_kw):
        return list(fin_readers if financial else everyone)

    async def pack(wid):
        if pack_raises:
            raise pack_raises
        return {"content": "# Pack\n\nQuiet week.", "workspace_name": f"{wid} Co", "workspace_id": wid}

    async def stale(_db, _wid, **_kw):
        return []

    async def fin(_wid, *a, **k):
        return dict(_FIN)

    async def go():
        if docs:
            await db.workspaces.insert_many([dict(d) for d in docs])
        with (
            patch.object(server, "db", db),
            patch.object(server, "BILLING_ENFORCED", True),
            patch.object(server, "SESSION_SECRET", "weekly-digest-test-secret"),
            patch.object(server, "_alert_recipient_emails", side_effect=recipients),
            patch.object(server, "_generate_weekly_pack_content", side_effect=pack),
            patch.object(server, "compute_financials", side_effect=fin),
            patch.object(server.helm_freshness, "stale_department_alerts", side_effect=stale),
            patch.object(server, "send_resend_email", side_effect=fake_send),
            patch("weekly_pack_export.render_weekly_pack_pdf", return_value=b"%PDF-1.4 fake"),
            patch("weekly_pack_export.pdf_filename", return_value="Pack.pdf"),
        ):
            stats = await server.run_weekly_digest_cron(now=now)
            again = await server.run_weekly_digest_cron(now=now)
        marks = {d["workspace_id"]: d.get("weekly_digest_emailed_week")
                 async for d in db.workspaces.find({}, {"_id": 0, "workspace_id": 1, "weekly_digest_emailed_week": 1})}
        return stats, again, marks

    stats, again, marks = asyncio.run(go())
    return stats, again, marks, sent


def test_weekly_digest_sends_inline_summary_and_debounces(monkeypatch):
    stats, again, marks, sent = _run_weekly(monkeypatch, [_ws("ws_a")])
    assert stats["sent"] == 1 and stats["errors"] == 0
    assert marks["ws_a"] == "2026-W43"
    # The second run the same Monday sends nothing.
    assert again["sent"] == 0 and again["skipped_already"] == 1
    assert len(sent) == 2
    by_to = {m["to"][0]: m for m in sent}
    ceo, coo = by_to["ceo@x.test"], by_to["coo@x.test"]
    # Inline content, subject names what needs attention, compliance footer present.
    assert "ws_a Co" in ceo["subject"] and "1 decision waiting" in ceo["subject"]
    assert "Hire a plant manager" in ceo["html"] and "Send report" in ceo["html"]
    assert "Unsubscribe" in ceo["html"] and "List-Unsubscribe" in ceo["headers"]
    # Money and the PDF go only to the person with Financials access.
    assert "₱500K" in ceo["html"] and ceo["attachments"][0]["filename"] == "Pack.pdf"
    assert "₱500K" not in coo["html"] and coo["attachments"] is None
    assert stats["pdf_attached"] == 1


def test_weekly_digest_waits_for_monday_morning_in_the_workspaces_own_timezone(monkeypatch):
    docs = [
        _ws("ws_manila"),
        _ws("ws_ny", timezone="America/New_York"),  # still Sunday evening there
    ]
    stats, _again, marks, sent = _run_weekly(monkeypatch, docs)
    assert stats["sent"] == 1 and stats["skipped_not_due"] == 1
    assert marks["ws_manila"] == "2026-W43" and marks["ws_ny"] is None
    assert {m["subject"].split(":")[0] for m in sent} == {"ws_manila Co"}
    # Before 07:00 Monday in Manila nothing goes out either.
    early = datetime(2026, 10, 18, 20, 0, tzinfo=timezone.utc)  # Manila Monday 04:00
    stats, _a, _m, sent = _run_weekly(monkeypatch, [_ws("ws_early")], now=early)
    assert stats["skipped_not_due"] == 1 and sent == []


def test_weekly_digest_free_plan_gets_the_summary_without_the_pdf(monkeypatch):
    stats, _a, _m, sent = _run_weekly(monkeypatch, [_ws("ws_free", plan="free")])
    assert stats["sent"] == 1 and stats["pdf_attached"] == 0
    assert all(m["attachments"] is None for m in sent)
    assert any("Hire a plant manager" in m["html"] for m in sent)


def test_weekly_digest_skips_sample_workspaces_and_empty_weeks(monkeypatch):
    docs = [
        _ws("ws_sample", template="sample"),
        _ws("ws_empty", decisions=[], tasks={"items": []}),
    ]
    # Readers with no Financials access, so an empty workspace has nothing at all to say.
    stats, _a, marks, sent = _run_weekly(monkeypatch, docs, fin_readers=())
    assert stats["skipped_sample"] == 1 and stats["skipped_empty"] == 1 and stats["sent"] == 0
    assert sent == [] and marks == {"ws_sample": None, "ws_empty": None}


def test_weekly_digest_summary_still_goes_out_when_the_pdf_fails(monkeypatch):
    stats, _a, marks, sent = _run_weekly(monkeypatch, [_ws("ws_a")], pack_raises=RuntimeError("llm down"))
    assert stats["sent"] == 1 and stats["errors"] == 0
    assert marks["ws_a"] == "2026-W43"
    assert all(m["attachments"] is None for m in sent)


def test_weekly_digest_continues_after_one_workspace_fails(monkeypatch):
    # A malformed tasks value breaks that workspace only; its week is never claimed.
    bad = _ws("ws_bad", tasks="broken")
    stats, _a, marks, sent = _run_weekly(monkeypatch, [bad, _ws("ws_ok")])
    assert stats["errors"] >= 1 and stats["sent"] == 1
    assert marks["ws_ok"] == "2026-W43" and marks["ws_bad"] is None
    assert all("ws_ok" in m["subject"] for m in sent)


@pytest.mark.asyncio
async def test_weekly_pack_endpoint_uses_shared_helper():
    principal = {"workspace_id": "ws_1", "user_id": "u1", "pack": "owner"}
    with patch.object(
        server,
        "_generate_weekly_pack_content",
        new=AsyncMock(return_value={
            "content": "shared body",
            "workspace_name": "Acme",
            "data_as_of": None,
            "data_freshness_sources": {},
        }),
    ) as helper, patch.object(
        server, "db", MagicMock(workspaces=MagicMock(update_one=AsyncMock())),
    ) as fake_db:
        result = await server.weekly_pack(principal=principal)
    assert result.pop("created_at")  # stamped when the pack is saved
    assert result == {
        "content": "shared body",
        "data_as_of": None,
        "data_freshness_sources": {},
    }
    helper.assert_awaited_once_with("ws_1")
    # The pack is persisted so Reports can show the last one.
    fake_db.workspaces.update_one.assert_awaited_once()


def test_iso_week_key_format():
    key = server._iso_week_key(datetime(2026, 9, 17, tzinfo=timezone.utc))
    assert key == "2026-W38"


def test_daily_briefing_endpoint_requires_cron_secret():
    with patch.object(server, "INTERNAL_CRON_SECRET", "cron-secret-test"):
        client = TestClient(server.app)
        assert client.post("/api/internal/run-daily-briefing").status_code == 401
        assert client.post(
            "/api/internal/run-daily-briefing",
            headers={"X-Trenston-Cron-Secret": "wrong"},
        ).status_code == 401


def test_daily_briefing_endpoint_runs_with_cron_header():
    with (
        patch.object(server, "INTERNAL_CRON_SECRET", "cron-secret-test"),
        patch.object(
            server,
            "run_daily_briefing_cron",
            new=AsyncMock(return_value={"workspaces_scanned": 0, "sent": 0, "day": "2026-09-19"}),
        ),
    ):
        client = TestClient(server.app)
        res = client.post(
            "/api/internal/run-daily-briefing",
            headers={"X-Trenston-Cron-Secret": "cron-secret-test"},
        )
    assert res.status_code == 200
    assert res.json()["sent"] == 0


def test_run_daily_briefing_emails_and_debounces():
    day = "2026-09-19"
    rows = [
        {"workspace_id": "ws_send", "name": "Send Co"},
        {
            "workspace_id": "ws_done",
            "name": "Done Co",
            "daily_briefing_emailed_date": day,
        },
        {"workspace_id": "ws_empty", "name": "Empty Co"},
    ]
    fake_db = MagicMock()
    fake_db.workspaces.find = MagicMock(return_value=_Cursor(rows))
    fake_db.workspaces.find_one_and_update = AsyncMock(
        return_value={"workspace_id": "ws_send", "daily_briefing_emailed_date": day},
    )
    fake_db.workspaces.update_one = AsyncMock()
    fake_db.email_suppressions.find_one = AsyncMock(return_value=None)

    sent = []

    async def fake_send(*, to, subject, html, attachments=None, headers=None):
        sent.append({"to": to, "subject": subject, "html": html, "headers": headers})
        return {"sent": True, "id": "email_1"}

    async def fake_recipients(wid, **_kw):
        if wid == "ws_empty":
            return ["empty@test"]
        return ["ceo@send.test"] if wid == "ws_send" else []

    async def fake_assemble(wid, workspace=None):
        if wid == "ws_empty":
            return {"has_content": False, "sections": {}, "month": "2026-09"}
        return {
            "has_content": True,
            "month": "2026-09",
            "sections": {
                "sales": {
                    "summary": {
                        "line_count": 1,
                        "confirmed_this_month": 3000,
                        "by_country_this_month": [{"country": "IN", "total_value": 3000, "count": 1}],
                        "by_product_this_month": [{"product": "Oil", "total_value": 3000, "count": 1}],
                        "forward_pipeline": [
                            {"month": "2026-09", "expected": 0, "in_negotiation": 0, "confirmed": 3000},
                            {"month": "2026-10", "expected": 500, "in_negotiation": 0, "confirmed": 0},
                            {"month": "2026-11", "expected": 0, "in_negotiation": 200, "confirmed": 0},
                        ],
                    },
                    "target_vs_actual": {
                        "target_entered": True,
                        "target": 5000,
                        "actual": 3000,
                        "gap": -2000,
                        "pct_of_target": 60.0,
                    },
                },
                "procurement": None,
                "production": None,
                "maintenance": None,
            },
        }

    with (
        patch.object(server, "db", fake_db),
        patch.object(server, "SESSION_SECRET", "daily-briefing-test-secret"),
        patch.object(server, "_alert_recipient_emails", side_effect=fake_recipients),
        patch.object(server, "assemble_ops_briefing_data", side_effect=fake_assemble),
        patch.object(server, "send_resend_email", side_effect=fake_send),
        patch.object(server, "_daily_briefing_date_key", return_value=day),
    ):
        stats = asyncio.run(server.run_daily_briefing_cron())

    assert stats["sent"] == 1
    assert stats["skipped_already"] == 1
    assert stats["skipped_empty"] == 1
    assert stats["errors"] == 0
    assert len(sent) == 1
    assert sent[0]["to"] == ["ceo@send.test"]
    assert "daily briefing" in sent[0]["subject"].lower()
    assert "Unsubscribe" in sent[0]["html"]
    assert "BGC, Taguig, Philippines" in sent[0]["html"]
    assert "Target vs actual" in sent[0]["html"]
    assert sent[0]["headers"] and "List-Unsubscribe" in sent[0]["headers"]
    # Slim projection — never load full workspace blobs for the cron sweep.
    proj = fake_db.workspaces.find.call_args_list[0].args[1]
    assert set(proj.keys()) >= {"_id", "workspace_id", "name", "daily_briefing_emailed_date"}
    fake_db.workspaces.find_one_and_update.assert_awaited_once()
    claim_filt = fake_db.workspaces.find_one_and_update.await_args.args[0]
    assert claim_filt["workspace_id"] == "ws_send"
    set_fields = fake_db.workspaces.find_one_and_update.await_args.args[1]["$set"]
    assert set_fields["daily_briefing_emailed_date"] == day
    # Successful send must not revert the claim.
    fake_db.workspaces.update_one.assert_not_called()


def test_run_daily_briefing_respects_suppression():
    rows = [{"workspace_id": "ws_1", "name": "Suppressed Co"}]
    fake_db = MagicMock()
    fake_db.workspaces.find = MagicMock(return_value=_Cursor(rows))
    fake_db.workspaces.find_one_and_update = AsyncMock()
    fake_db.workspaces.update_one = AsyncMock()
    fake_db.email_suppressions.find_one = AsyncMock(
        return_value={"email": "ceo@x.test", "category": "commercial"},
    )

    with (
        patch.object(server, "db", fake_db),
        patch.object(server, "SESSION_SECRET", "daily-briefing-test-secret"),
        patch.object(server, "_alert_recipient_emails", new=AsyncMock(return_value=["ceo@x.test"])),
        patch.object(
            server,
            "assemble_ops_briefing_data",
            new=AsyncMock(return_value={"has_content": True, "sections": {"sales": {}}, "month": "2026-09"}),
        ),
        patch.object(server, "send_resend_email", new=AsyncMock()) as send_mock,
        patch.object(server, "_daily_briefing_date_key", return_value="2026-09-19"),
    ):
        stats = asyncio.run(server.run_daily_briefing_cron())

    assert stats["skipped_suppressed"] == 1
    assert stats["sent"] == 0
    send_mock.assert_not_called()
    fake_db.workspaces.find_one_and_update.assert_not_called()
    fake_db.workspaces.update_one.assert_not_called()


def test_run_daily_briefing_atomic_claim_skips_race_loser():
    """Overlapping cron: find_one_and_update returns None → skip, do not send."""
    day = "2026-09-19"
    rows = [{"workspace_id": "ws_race", "name": "Race Co"}]
    fake_db = MagicMock()
    fake_db.workspaces.find = MagicMock(return_value=_Cursor(rows))
    fake_db.workspaces.find_one_and_update = AsyncMock(return_value=None)
    fake_db.workspaces.update_one = AsyncMock()
    fake_db.email_suppressions.find_one = AsyncMock(return_value=None)

    with (
        patch.object(server, "db", fake_db),
        patch.object(server, "SESSION_SECRET", "daily-briefing-test-secret"),
        patch.object(server, "_alert_recipient_emails", new=AsyncMock(return_value=["ceo@race.test"])),
        patch.object(
            server,
            "assemble_ops_briefing_data",
            new=AsyncMock(return_value={"has_content": True, "sections": {"sales": {}}, "month": "2026-09"}),
        ),
        patch.object(server, "send_resend_email", new=AsyncMock()) as send_mock,
        patch.object(server, "_daily_briefing_date_key", return_value=day),
    ):
        stats = asyncio.run(server.run_daily_briefing_cron())

    assert stats["skipped_already"] == 1
    assert stats["sent"] == 0
    send_mock.assert_not_called()


def test_run_daily_briefing_reverts_claim_on_send_failure():
    day = "2026-09-19"
    rows = [{"workspace_id": "ws_fail", "name": "Fail Co"}]
    fake_db = MagicMock()
    fake_db.workspaces.find = MagicMock(return_value=_Cursor(rows))
    fake_db.workspaces.find_one_and_update = AsyncMock(
        return_value={"workspace_id": "ws_fail", "daily_briefing_emailed_date": day},
    )
    fake_db.workspaces.update_one = AsyncMock()
    fake_db.email_suppressions.find_one = AsyncMock(return_value=None)

    with (
        patch.object(server, "db", fake_db),
        patch.object(server, "SESSION_SECRET", "daily-briefing-test-secret"),
        patch.object(server, "_alert_recipient_emails", new=AsyncMock(return_value=["ceo@fail.test"])),
        patch.object(
            server,
            "assemble_ops_briefing_data",
            new=AsyncMock(return_value={"has_content": True, "sections": {"sales": {}}, "month": "2026-09"}),
        ),
        patch.object(server, "send_resend_email", new=AsyncMock(return_value={"sent": False})),
        patch.object(server, "_daily_briefing_date_key", return_value=day),
    ):
        stats = asyncio.run(server.run_daily_briefing_cron())

    assert stats["send_failed"] == 1
    assert stats["sent"] == 0
    unset = fake_db.workspaces.update_one.await_args.args[1]["$unset"]
    assert "daily_briefing_emailed_date" in unset


def test_daily_briefing_date_key_format():
    key = server._daily_briefing_date_key(datetime(2026, 9, 19, 3, 0, tzinfo=timezone.utc))
    assert key == "2026-09-19"


@pytest.fixture(autouse=True)
def _no_ai_rate_limit(monkeypatch):
    # The endpoints rate-limit paid AI calls through Mongo; these tests mock db.
    from unittest.mock import AsyncMock as _AM
    monkeypatch.setattr(server.doc_rate_limit, "acquire_event_slot", _AM(return_value=True))
