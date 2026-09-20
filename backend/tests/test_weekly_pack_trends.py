"""Weekly CEO Pack context + report trend snapshot behavior."""
import os
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pymongo
import requests

from conftest import set_workspace_plan

os.environ.setdefault("DB_NAME", os.environ.get("DB_NAME", "test_database"))
os.environ.setdefault("MONGO_URL", os.environ.get("MONGO_URL", "mongodb://localhost:27017"))

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
OWNER_TOKEN = "test_session_kalun_123"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


def _sess(token):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    return s


@pytest.fixture
def owner():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not set")
    s = _sess(OWNER_TOKEN)
    set_workspace_plan(s, BASE_URL, "pro")
    return s


@pytest.fixture
def mongo():
    client = pymongo.MongoClient(MONGO_URL, serverSelectionTimeoutMS=2000)
    try:
        client.admin.command("ping")
    except Exception:
        pytest.skip("MongoDB not available")
    return client[DB_NAME]


@pytest.fixture
def ws_id(owner):
    return owner.get(f"{BASE_URL}/api/auth/me").json()["workspace_id"]


def test_build_weekly_pack_context_includes_manual_reports_not_legacy():
    """Acceptance: LLM context reads manual_reports, not the always-empty c['reports']."""
    from server import _build_weekly_pack_context

    fin = {"mrr": "$1K", "arr": "$12K", "runway_months": 10, "burn": "$2K",
           "mrr_value": 1000, "burn_value": 2000}
    c = {
        "name": "Acme",
        "telemetry": {"kpis": []},
        "reports": [],  # legacy — empty in real usage
        "manual_reports": [
            {"title": "Sales Recap", "summary": "Closed 3 deals this week."},
        ],
    }
    ctx = _build_weekly_pack_context(c, fin, [], [], 3, prior=None)
    assert ctx["reports"] == [{"title": "Sales Recap", "summary": "Closed 3 deals this week."}]
    assert len(ctx["weekly_comparison"]["cards"]) == 3
    assert {t["title"] for t in ctx["weekly_comparison"]["cards"]} == {
        "Money check-in", "Team check-in", "Work completed",
    }


def test_signed_delta_and_first_vs_prior_cards():
    from server import _signed_delta, _shipped_in_window, _computed_report_cards

    assert "first week" in _signed_delta(10, None)
    assert _signed_delta(12, 10).startswith("+2")
    assert "flat" in _signed_delta(10, 10)

    now = datetime(2026, 9, 4, tzinfo=timezone.utc)
    items = [
        {"column": "done", "done_at": (now - timedelta(days=2)).isoformat()},
        {"column": "done", "done_at": (now - timedelta(days=10)).isoformat()},
        {"column": "done"},
        {"column": "backlog"},
    ]
    assert _shipped_in_window(items, now=now, days=7) == 1

    fin = {"mrr": "$10K", "arr": "$120K", "runway_months": 12, "burn": "$5K",
           "mrr_value": 10000, "burn_value": 5000, "mrr_known": True, "burn_known": True}
    cards = _computed_report_cards({}, fin, items, [], 5, prior=None)
    assert all("first weekly baseline" in c["summary"] for c in cards)
    assert cards[0]["metrics"][0] == {
        "label": "Monthly recurring revenue",
        "value": "$10K",
        "change": "No comparison yet",
    }

    prior = {"mrr": 9000, "runway_months": 11, "burn": 4000, "headcount": 4,
             "updates_count": 1, "blocked_count": 0, "shipped_week": 0}
    cards2 = _computed_report_cards({}, fin, items, [{"blocker": True}], 5, prior=prior)
    assert cards2[0]["period"] == "Compared with last check-in"
    assert cards2[0]["metrics"][0]["value"] == "$10K"
    assert cards2[0]["metrics"][0]["change"] == "Up $1K from last week"
    assert "monthly recurring revenue" in cards2[0]["summary"].lower()


@pytest.mark.asyncio
async def test_snapshot_rotation_keeps_previous_baseline_for_pack_and_cards():
    from server import _apply_report_snapshot

    old = {
        "taken_at": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),
        "mrr": 100,
    }
    current = {"taken_at": datetime.now(timezone.utc).isoformat(), "mrr": 120}
    mock_db = MagicMock()
    mock_db.workspaces.update_one = AsyncMock()

    with patch("server.get_ws", new=AsyncMock(return_value={"report_snapshot": old})), \
         patch("server.db", mock_db):
        rotated_baseline = await _apply_report_snapshot("ws_1", current)

    update = mock_db.workspaces.update_one.await_args.args[1]["$set"]
    assert rotated_baseline == old
    assert update["report_snapshot"] == current
    assert update["report_previous_snapshot"] == old

    with patch(
        "server.get_ws",
        new=AsyncMock(return_value={
            "report_snapshot": current,
            "report_previous_snapshot": old,
        }),
    ):
        pack_baseline = await _apply_report_snapshot("ws_1", current)
    assert pack_baseline == old


@pytest.mark.asyncio
async def test_weekly_pack_llm_user_prompt_contains_manual_report(mongo):
    """In-process: mock LLM and assert the prompt includes the manual report text."""
    from server import weekly_pack, helm_llm

    ws_id = "ws_pack_ctx_test"
    title = f"TEST_PACK_{uuid.uuid4().hex[:6]}"
    summary = "Unique manual report body for LLM context."
    mongo.workspaces.delete_many({"workspace_id": ws_id})
    mongo.workspaces.insert_one({
        "workspace_id": ws_id,
        "name": "Pack Co",
        "plan": "pro",
        "telemetry": {"kpis": []},
        "tasks": {"items": [], "columns": []},
        "people": {"people": []},
        "employees": 2,
        "manual_reports": [{"id": "rep_x", "title": title, "summary": summary}],
        "reports": [],
        "report_snapshot": None,
    })
    captured = {}

    async def fake_complete(system, user, **kwargs):
        captured["system"] = system
        captured["user"] = user
        return "# ok"

    principal = {"workspace_id": ws_id, "user_id": "u1", "pack": "owner", "name": "Owner", "email": "o@x.com"}
    with patch.object(helm_llm, "anthropic_configured", return_value=True), \
         patch.object(helm_llm, "complete", new=AsyncMock(side_effect=fake_complete)):
        # Call the route function directly
        result = await weekly_pack(principal=principal)
    assert result["content"] == "# ok"
    assert title in captured["user"]
    assert summary in captured["user"]
    assert '"weekly_comparison"' in captured["user"]
    assert "instructions_for_missing_data" in captured["user"]
    assert "revenue_series" not in captured["user"]
    assert "board-ready" not in captured["system"].lower()
    assert "board" not in captured["system"].lower()
    assert "plain English" in captured["system"]
    assert "350 words" in captured["system"]
    assert "monetization signal" in captured["system"]
    assert "Structure follows" in captured["system"] or "structure follow" in captured["system"].lower()
    assert "**Label:**" in captured["system"] or "bold-label" in captured["system"].lower()
    assert "em dash" in captured["system"].lower() or "em dashes" in captured["system"].lower()
    assert "Output this exact markdown structure" not in captured["system"]
    assert "## What happened" not in captured["system"] or "Never default" in captured["system"] or "always-on" in captured["system"].lower()


class TestReportSnapshotsHTTP:
    def test_first_run_stores_snapshot_and_shows_first_week(self, owner, mongo, ws_id):
        mongo.workspaces.update_one(
            {"workspace_id": ws_id},
            {"$unset": {"report_snapshot": "", "report_previous_snapshot": ""}},
        )
        r = owner.get(f"{BASE_URL}/api/reports")
        assert r.status_code == 200
        j = r.json()
        assert len(j["auto_reports"]) == 3
        for card in j["auto_reports"]:
            assert "first week" in card["summary"].lower() or card["period"] == "First week"
        snap = mongo.workspaces.find_one({"workspace_id": ws_id}, {"report_snapshot": 1})
        assert snap and snap.get("report_snapshot") and snap["report_snapshot"].get("taken_at")

    def test_week_old_snapshot_diffs_and_rotates(self, owner, mongo, ws_id):
        old = {
            "taken_at": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),
            "mrr": 1,
            "arr": 12,
            "runway_months": 1,
            "burn": 1,
            "headcount": 1,
            "updates_count": 0,
            "blocked_count": 0,
            "shipped_week": 0,
            "open_tasks": 0,
            "in_progress": 0,
        }
        mongo.workspaces.update_one({"workspace_id": ws_id}, {"$set": {"report_snapshot": old}})
        r = owner.get(f"{BASE_URL}/api/reports")
        assert r.status_code == 200
        j = r.json()
        for card in j["auto_reports"]:
            assert card["period"].startswith("Compared with ")
            assert "first week" not in card["summary"].lower()
        snap = mongo.workspaces.find_one({"workspace_id": ws_id}, {"report_snapshot": 1})["report_snapshot"]
        assert snap["taken_at"] != old["taken_at"]
        taken = datetime.fromisoformat(snap["taken_at"].replace("Z", "+00:00"))
        assert (datetime.now(timezone.utc) - taken).total_seconds() < 120
        previous = mongo.workspaces.find_one(
            {"workspace_id": ws_id}, {"report_previous_snapshot": 1},
        )["report_previous_snapshot"]
        assert previous["taken_at"] == old["taken_at"]
