"""POST /briefing/generate must ground what_changed on live activities + real metrics."""
from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_briefing_generate_grounding")

import server  # noqa: E402


@pytest.mark.asyncio
async def test_generate_briefing_uses_live_what_changed_and_real_metrics():
    ws = {
        "workspace_id": "ws_gen",
        "name": "Acme",
        "plan": "pro",
        "briefing": {
            "headline": "Hello",
            "what_changed": [{"title": "Seed only", "detail": "stale", "tone": "neutral"}],
            "nrr": {"value": "110%", "delta": 1.0, "tone": "positive"},
        },
        "decisions": [],
        "decision_suggestions": [],
    }
    principal = {
        "user_id": "u1",
        "workspace_id": "ws_gen",
        "role": "owner",
        "pack": "owner",
    }
    acts = [
        {
            "summary": "Logged today from Production",
            "actor_name": "Sam",
            "created_at": "2026-09-23T08:00:00+00:00",
        },
    ]
    fin = {
        "mrr": 12000, "mrr_known": True, "mrr_value": 12000, "mrr_delta": 5,
        "burn": 8000, "burn_known": True, "burn_value": 8000, "burn_tone": "neutral",
        "runway_months": 9.0, "runway_no_burn": False, "cash_entered": True,
        "cash_value": 72000, "currency": "usd",
    }
    ops = [{"label": "Today's output", "value": "12 units", "tone": "positive", "section": "ops"}]
    captured = {}

    async def fake_complete(system, user_msg):
        # Company data for today:\n{json}\n\nWrite...
        payload = user_msg.split("Company data for today:\n", 1)[1]
        payload = payload.rsplit("\n\nWrite", 1)[0]
        captured["context"] = json.loads(payload)
        return "Cash is fine. Ship the release."

    empty_cursor = MagicMock()
    empty_cursor.sort.return_value = empty_cursor
    empty_cursor.to_list = AsyncMock(return_value=acts)

    with patch.object(server, "get_ws", AsyncMock(return_value=ws)), \
         patch.object(server.helm_llm, "anthropic_configured", return_value=True), \
         patch.object(server.helm_llm, "complete", side_effect=fake_complete), \
         patch.object(server, "can_access_financials", AsyncMock(return_value=True)), \
         patch.object(server, "compute_financials", AsyncMock(return_value=fin)), \
         patch.object(server, "_briefing_ops_metrics", AsyncMock(return_value=ops)), \
         patch.object(server, "_google_calendar_snapshot", AsyncMock(return_value=None)), \
         patch.object(server.helm_freshness, "resolve_workspace_data_as_of", AsyncMock(return_value={
             "data_as_of": "2026-09-23T09:00:00+00:00", "sources": {},
         })), \
         patch.object(server, "db") as mock_db:
        mock_db.activities.find.return_value = empty_cursor
        mock_db.workspaces.update_one = AsyncMock()
        result = await server.generate_briefing(principal)

    assert result["ai_summary"].startswith("Cash is fine")
    ctx = captured["context"]
    assert ctx["what_changed"][0]["title"] == "Logged today from Production"
    assert any(c["title"] == "Seed only" for c in ctx["what_changed"])
    # metrics must be KPI cards, not a duplicate of decisions
    assert ctx["decisions"] == []
    labels = [m["label"] for m in ctx["metrics"]]
    assert "MRR" in labels
    assert "Burn" in labels
    assert "Runway" in labels
    assert "Today's output" in labels
    assert "NRR" in labels
