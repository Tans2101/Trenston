"""In-process tests for insights generation, rate limits, and briefing wiring."""
import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pymongo

os.environ.setdefault("DB_NAME", "test_database")
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


@pytest.fixture
def mongo():
    return pymongo.MongoClient(MONGO_URL)[DB_NAME]


@pytest.mark.asyncio
async def test_briefing_schedules_insights_without_awaiting_them():
    """Stale insights must not block /briefing (was causing multi-second freezes)."""
    import time
    import server as srv

    ws = {
        "workspace_id": "ws_speed",
        "briefing": {"headline": "Hello", "what_changed": []},
        "insights_generated_at": None,
        "decisions": [],
        "decision_suggestions": [],
        "delegate_suggestions": [],
    }
    principal = {"workspace_id": "ws_speed", "user_id": "u1", "role": "owner", "pack": "owner"}

    scheduled = {"n": 0}

    def fake_schedule(ws_id):
        scheduled["n"] += 1

    empty_cursor = MagicMock()
    empty_cursor.sort.return_value = empty_cursor
    empty_cursor.to_list = AsyncMock(return_value=[])

    with patch.object(srv, "get_ws", AsyncMock(return_value=ws)), \
         patch.object(srv.db.workspaces, "update_one", AsyncMock()), \
         patch.object(srv, "compute_financials", AsyncMock(return_value={
             "mrr": 0, "mrr_known": False, "mrr_delta": 0,
             "runway_months": None, "burn": 0, "burn_known": False, "burn_tone": "neutral",
         })), \
         patch.object(srv, "db") as mock_db, \
         patch.object(srv, "workspace_is_pro", return_value=False), \
         patch.object(srv, "_insights_stale", return_value=True), \
         patch.object(srv, "_schedule_insights_refresh", side_effect=fake_schedule):
        mock_db.workspaces.update_one = AsyncMock()
        mock_db.activities.find.return_value = empty_cursor
        mock_db.updates.find.return_value = empty_cursor
        t0 = time.monotonic()
        result = await srv.briefing(principal)
        elapsed = time.monotonic() - t0

    assert elapsed < 1.0, f"briefing blocked on insights ({elapsed:.2f}s)"
    assert scheduled["n"] == 1
    assert result.get("headline") == "Hello" or result.get("metrics") is not None


@pytest.mark.asyncio
async def test_schedule_insights_refresh_is_background():
    """_schedule_insights_refresh must return immediately while generate runs."""
    import time
    import server as srv

    finished = asyncio.Event()

    async def slow_generate(ws_id, raise_on_rate_limit=False):
        await asyncio.sleep(0.4)
        finished.set()
        return {"ok": True}

    with patch.object(srv, "_generate_insights", side_effect=slow_generate), \
         patch.object(srv.helm_llm, "anthropic_configured", return_value=True):
        srv._insights_refresh_inflight.clear()
        t0 = time.monotonic()
        srv._schedule_insights_refresh("ws_bg")
        elapsed = time.monotonic() - t0
        assert elapsed < 0.2, f"schedule blocked ({elapsed:.2f}s)"
        assert not finished.is_set()
        await asyncio.wait_for(finished.wait(), timeout=2.0)


@pytest.mark.asyncio
async def test_briefing_builders_use_live_decisions_and_suggestions():
    from server import _briefing_what_to_decide, _briefing_what_to_delegate

    c = {
        "decisions": [
            {"id": "d1", "title": "Manual hire", "status": "pending", "impact": "High",
             "recommendation": "Hire now", "description": "", "due": "2026-09-10", "source": "manual"},
            {"id": "d2", "title": "Resolved", "status": "approved", "impact": "High"},
        ],
        "decision_suggestions": [
            {"id": "sug1", "title": "AI runway call", "status": "suggested", "impact": "High",
             "recommendation": "Cut burn", "confidence": 80, "source": "ai_suggested"},
        ],
        "delegate_suggestions": [
            {"id": "del1", "title": "Unblock Maya", "detail": "Help", "status": "suggested",
             "suggested_owner_name": "Maya", "suggested_owner_user_id": "u1"},
        ],
    }
    decide = _briefing_what_to_decide(c)
    assert len(decide) == 2
    sources = {x["source"] for x in decide}
    assert "manual" in sources and "ai_suggested" in sources
    assert all(x.get("urgency") for x in decide)

    delegate = _briefing_what_to_delegate(c)
    assert len(delegate) == 1
    assert delegate[0]["owner"] == "Maya"
    assert delegate[0]["id"] == "del1"


@pytest.mark.asyncio
async def test_generate_insights_keeps_prior_on_total_draft_failure():
    """If every AI draft fails, do not wipe suggestions or stamp insights_generated_at."""
    import server as srv

    ws_id = "ws_draft_fail"
    ws = {
        "workspace_id": ws_id,
        "name": "Fail Co",
        "plan": "pro",
        "tasks": {"items": [
            {"id": "t1", "title": "Overdue", "column": "backlog", "due": "2020-01-01",
             "assignee": "Maya", "assignee_user_id": "u_maya"},
        ], "columns": []},
        "decisions": [],
        "decision_suggestions": [{"id": "sug_keep", "status": "suggested", "title": "Keep me"}],
        "delegate_suggestions": [{"id": "del_keep", "status": "suggested", "title": "Keep"}],
        "financial_settings": {"cash": 40000, "gross_margin": 70, "currency": "usd"},
        "briefing": {},
        "insights_generated_at": None,
    }

    async def boom(*_a, **_k):
        raise RuntimeError("anthropic down")

    empty = MagicMock()
    empty.to_list = AsyncMock(return_value=[])
    signal_type = next(iter(srv.decision_engine.DECISION_SIGNAL_TYPES))

    mock_db = MagicMock()
    mock_db.financial_entries.find.return_value = empty
    mock_db.deals.find.return_value = empty
    mock_db.workspaces.update_one = AsyncMock()

    with patch.object(srv, "db", mock_db), \
         patch.object(srv, "get_ws", AsyncMock(return_value=ws)), \
         patch.object(srv, "compute_financials", AsyncMock(return_value={
             "mrr": 0, "mrr_known": False, "currency": "usd",
         })), \
         patch.object(srv, "_recent_updates", AsyncMock(return_value=[])), \
         patch.object(srv, "_department_signal_inputs", AsyncMock(return_value=[])), \
         patch.object(srv.decision_engine, "collect_signals", return_value=[
             {"type": signal_type, "severity": "high"},
         ]), \
         patch.object(srv, "company_context_for_synthesis", return_value={}), \
         patch.object(srv.helm_llm, "anthropic_configured", return_value=True), \
         patch.object(srv.helm_llm, "draft_decision", new=AsyncMock(side_effect=boom)), \
         patch.object(srv.helm_llm, "draft_delegate", new=AsyncMock(side_effect=boom)), \
         patch.object(srv.doc_rate_limit, "insights_over_limit", AsyncMock(return_value=False)), \
         patch.object(srv.doc_rate_limit, "acquire_insights_slot", AsyncMock(return_value=True)) as acquire:
        result = await srv._generate_insights(ws_id, raise_on_rate_limit=False)

    assert result.get("skipped") == "draft_failed"
    acquire.assert_not_called()
    mock_db.workspaces.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_generate_insights_partial_draft_failure_keeps_high_severity():
    """One failed draft must not erase that signal when others succeed."""
    import server as srv

    ws_id = "ws_partial_draft"
    runway_sig = {
        "type": "runway_risk",
        "severity": "high",
        "summary": "Runway under 6 months",
        "detail": "Cash covers 3.2 months of burn.",
        "related_id": None,
        "runway_months": 3.2,
    }
    other_sigs = [
        {
            "type": "stalled_deal",
            "severity": "medium",
            "summary": f"Deal {i}",
            "detail": f"stalled {i}",
            "related_id": f"deal_{i}",
            "value": 1000,
            "idle_days": 20,
        }
        for i in range(9)
    ]
    signals = [runway_sig] + other_sigs

    prior_runway = {
        "id": "sug_prior_runway",
        "status": "suggested",
        "source": "ai_suggested",
        "signal_type": "runway_risk",
        "signal": dict(runway_sig),
        "severity": "high",
        "title": "Prior runway draft",
        "description": "Keep this text if draft fails",
        "recommendation": "Cut burn",
        "confidence": 70,
        "confidence_unavailable": False,
        "category": "Finance",
        "impact": "High",
        "due": "",
        "owner": None,
    }

    ws = {
        "workspace_id": ws_id,
        "name": "Partial Co",
        "plan": "pro",
        "tasks": {"items": [], "columns": []},
        "decisions": [],
        "decision_suggestions": [prior_runway],
        "delegate_suggestions": [],
        "financial_settings": {"cash": 40000, "gross_margin": 70, "currency": "usd"},
        "briefing": {},
        "insights_generated_at": None,
        "notified_signal_ids": [],
    }

    async def draft_decision(sig, *_a, **_k):
        if sig.get("type") == "runway_risk":
            raise RuntimeError("transient model failure on highest-severity")
        return {
            "title": f"Draft {sig.get('related_id')}",
            "description": sig.get("detail") or "",
            "recommendation": "Follow up",
            "confidence": 60,
            "confidence_unavailable": False,
            "category": "Sales",
            "impact": "Medium",
        }

    empty = MagicMock()
    empty.to_list = AsyncMock(return_value=[])
    mock_db = MagicMock()
    mock_db.financial_entries.find.return_value = empty
    mock_db.deals.find.return_value = empty
    mock_db.workspaces.update_one = AsyncMock()

    with patch.object(srv, "db", mock_db), \
         patch.object(srv, "get_ws", AsyncMock(return_value=ws)), \
         patch.object(srv, "compute_financials", AsyncMock(return_value={
             "mrr": 0, "mrr_known": False, "currency": "usd",
         })), \
         patch.object(srv, "_recent_updates", AsyncMock(return_value=[])), \
         patch.object(srv, "_department_signal_inputs", AsyncMock(return_value=[])), \
         patch.object(srv.decision_engine, "collect_signals", return_value=signals), \
         patch.object(srv, "company_context_for_synthesis", return_value={}), \
         patch.object(srv, "_notify_high_severity_alerts", AsyncMock(return_value={
             "emailed": False, "slack": False, "new_alerts": 0,
         })), \
         patch.object(srv.helm_llm, "anthropic_configured", return_value=True), \
         patch.object(srv.helm_llm, "draft_decision", new=AsyncMock(side_effect=draft_decision)), \
         patch.object(srv.helm_llm, "draft_delegate", new=AsyncMock()), \
         patch.object(srv.doc_rate_limit, "insights_over_limit", AsyncMock(return_value=False)), \
         patch.object(srv.doc_rate_limit, "acquire_insights_slot", AsyncMock(return_value=True)):
        result = await srv._generate_insights(ws_id, raise_on_rate_limit=False)

    assert result.get("ok") is True
    assert result["decision_suggestions"] == 10
    mock_db.workspaces.update_one.assert_called_once()
    stored = mock_db.workspaces.update_one.call_args[0][1]["$set"]["decision_suggestions"]
    runway_cards = [s for s in stored if s.get("signal_type") == "runway_risk"]
    assert len(runway_cards) == 1
    assert runway_cards[0]["title"] == "Prior runway draft"
    assert runway_cards[0].get("draft_reused") is True
    assert runway_cards[0]["severity"] == "high"


@pytest.mark.asyncio
async def test_generate_insights_partial_draft_failure_raw_fallback_without_prior():
    """Failed draft with no prior card still surfaces as a raw-signal suggestion."""
    import server as srv

    ws_id = "ws_raw_fallback"
    runway_sig = {
        "type": "runway_risk",
        "severity": "high",
        "summary": "Runway under 6 months",
        "detail": "Cash covers 2 months of burn.",
        "related_id": None,
    }
    ok_sig = {
        "type": "stalled_deal",
        "severity": "medium",
        "summary": "Small deal",
        "detail": "idle",
        "related_id": "deal_1",
    }
    ws = {
        "workspace_id": ws_id,
        "name": "Raw Co",
        "plan": "pro",
        "tasks": {"items": [], "columns": []},
        "decisions": [],
        "decision_suggestions": [],
        "delegate_suggestions": [],
        "financial_settings": {"cash": 10000, "gross_margin": 70, "currency": "usd"},
        "briefing": {},
        "notified_signal_ids": [],
    }

    async def draft_decision(sig, *_a, **_k):
        if sig.get("type") == "runway_risk":
            raise RuntimeError("boom")
        return {
            "title": "Ok draft",
            "description": "ok",
            "recommendation": "Follow up",
            "confidence": 55,
            "confidence_unavailable": False,
            "category": "Sales",
            "impact": "Medium",
        }

    empty = MagicMock()
    empty.to_list = AsyncMock(return_value=[])
    mock_db = MagicMock()
    mock_db.financial_entries.find.return_value = empty
    mock_db.deals.find.return_value = empty
    mock_db.workspaces.update_one = AsyncMock()

    with patch.object(srv, "db", mock_db), \
         patch.object(srv, "get_ws", AsyncMock(return_value=ws)), \
         patch.object(srv, "compute_financials", AsyncMock(return_value={
             "mrr": 0, "mrr_known": False, "currency": "usd",
         })), \
         patch.object(srv, "_recent_updates", AsyncMock(return_value=[])), \
         patch.object(srv, "_department_signal_inputs", AsyncMock(return_value=[])), \
         patch.object(srv.decision_engine, "collect_signals", return_value=[runway_sig, ok_sig]), \
         patch.object(srv, "company_context_for_synthesis", return_value={}), \
         patch.object(srv, "_notify_high_severity_alerts", AsyncMock(return_value={
             "emailed": False, "slack": False, "new_alerts": 0,
         })), \
         patch.object(srv.helm_llm, "anthropic_configured", return_value=True), \
         patch.object(srv.helm_llm, "draft_decision", new=AsyncMock(side_effect=draft_decision)), \
         patch.object(srv.doc_rate_limit, "insights_over_limit", AsyncMock(return_value=False)), \
         patch.object(srv.doc_rate_limit, "acquire_insights_slot", AsyncMock(return_value=True)):
        result = await srv._generate_insights(ws_id, raise_on_rate_limit=False)

    assert result.get("ok") is True
    stored = mock_db.workspaces.update_one.call_args[0][1]["$set"]["decision_suggestions"]
    runway = next(s for s in stored if s.get("signal_type") == "runway_risk")
    assert runway["source"] == "signal_fallback"
    assert runway.get("draft_failed") is True
    assert runway["title"] == "Runway under 6 months"
    assert runway["severity"] == "high"
    assert any(s.get("signal_type") == "stalled_deal" for s in stored)
