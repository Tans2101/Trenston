"""Free-tier AI briefing must persist on GET /briefing (not stripped by is_pro)."""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_briefing_ai_summary")

import plans as helm_plans
import server


MOCK_OWNER = {
    "user_id": "u_owner",
    "email": "owner@example.com",
    "name": "Owner",
    "workspace_id": "ws_brief",
    "role": "owner",
    "pack": "owner",
}


@pytest.fixture
def client():
    app = server.app
    with TestClient(app) as c:
        app.dependency_overrides[server.get_principal] = lambda: MOCK_OWNER
        yield c
        app.dependency_overrides.pop(server.get_principal, None)


def test_free_plan_includes_ai_briefing_feature():
    assert helm_plans.plan_allows("free", helm_plans.FEATURE_AI_BRIEFING, billing_enforced=True)
    assert helm_plans.is_paid_plan("free") is False


def _get_briefing(client, briefing_extra: dict, *, fin_access: bool):
    ws = {
        "workspace_id": "ws_brief",
        "name": "Acme",
        "plan": "free",
        "subscription_status": "none",
        "briefing": {
            "headline": "Hello",
            "what_changed": [],
            **briefing_extra,
        },
        "tasks": {"items": []},
        "people": {"people": []},
        "decisions": [],
    }
    with patch.object(server, "BILLING_ENFORCED", True), \
         patch.object(server, "get_ws", new=AsyncMock(return_value=ws)), \
         patch.object(server, "can_access_financials", new=AsyncMock(return_value=fin_access)), \
         patch.object(server, "can_edit_financials", new=AsyncMock(return_value=fin_access)), \
         patch.object(server, "compute_financials", new=AsyncMock(return_value={})), \
         patch.object(server, "_briefing_finance_metrics", return_value=[]), \
         patch.object(server, "_insights_stale", return_value=False), \
         patch.object(server.helm_freshness, "resolve_workspace_data_as_of", new=AsyncMock(return_value={
             "data_as_of": "2026-09-18T10:00:00+00:00", "sources": {},
         })), \
         patch.object(server.db, "activities", MagicMock()), \
         patch.object(server.db, "updates", MagicMock()), \
         patch.object(server.db, "workspaces", MagicMock()):
        server.db.activities.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
        server.db.updates.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
        server.db.workspaces.update_one = AsyncMock(return_value=None)
        r = client.get("/api/briefing")
    assert r.status_code == 200, r.text
    return r.json()


def test_briefing_returns_ai_summary_for_free_workspace(client):
    # A note written without money figures is safe for anyone on any plan.
    body = _get_briefing(client, {
        "ai_summary": "Decide on hiring today.",
        "ai_summary_includes_financials": False,
    }, fin_access=False)
    assert body["is_pro"] is False
    assert body["ai_summary"] == "Decide on hiring today."
    assert body["can_generate_ai_summary"] is True


def test_money_note_hidden_from_people_without_financials_access(client):
    # The note is written once per company; when it was grounded on cash/runway
    # (or predates the flag) only Financials viewers may read it.
    for extra in (
        {"ai_summary": "Runway is 6 months.", "ai_summary_includes_financials": True},
        {"ai_summary": "Runway is 6 months."},  # legacy note, no flag
    ):
        assert _get_briefing(client, extra, fin_access=False)["ai_summary"] is None
        assert _get_briefing(client, extra, fin_access=True)["ai_summary"] == "Runway is 6 months."


def test_stored_nrr_and_money_headline_never_leak(client):
    body = _get_briefing(client, {
        "headline": "Revenue is ahead of plan.",
        "nrr": {"value": "118%", "delta": 2.0, "tone": "positive"},
    }, fin_access=False)
    assert "nrr" not in body
    assert "Revenue" not in body["headline"]
    assert all(m.get("label") != "NRR" for m in body["metrics"])
