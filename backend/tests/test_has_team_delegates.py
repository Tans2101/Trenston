"""has_team gates delegate drafting vs personal later cards."""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_has_team_delegates")

import decision_engine  # noqa: E402
import server  # noqa: E402


def test_workspace_has_team_defaults_true_when_missing():
    assert decision_engine.workspace_has_team({}) is True
    assert decision_engine.workspace_has_team({"employees": 1}) is True
    assert decision_engine.workspace_has_team({"has_team": None}) is True


def test_workspace_has_team_respects_explicit_bool():
    assert decision_engine.workspace_has_team({"has_team": True}) is True
    assert decision_engine.workspace_has_team({"has_team": False}) is False


def test_briefing_delegate_personal_when_no_team():
    c = {
        "has_team": False,
        "delegate_suggestions": [
            {
                "id": "del1",
                "title": "Chase overdue PO",
                "detail": "Waiting on vendor",
                "status": "suggested",
                "source": "personal_later",
                "personal": True,
                "suggested_owner_name": "Maya",
                "suggested_owner_user_id": "u_maya",
            },
        ],
    }
    out = server._briefing_what_to_delegate(c)
    assert len(out) == 1
    assert out[0]["personal"] is True
    assert out[0]["owner"] is None
    assert out[0]["suggested_owner_user_id"] is None
    assert out[0]["source"] == "personal_later"


def test_briefing_delegate_team_behavior_unchanged():
    c = {
        "has_team": True,
        "delegate_suggestions": [
            {
                "id": "del1",
                "title": "Unblock Maya",
                "detail": "Help",
                "status": "suggested",
                "suggested_owner_name": "Maya",
                "suggested_owner_user_id": "u1",
            },
        ],
    }
    out = server._briefing_what_to_delegate(c)
    assert len(out) == 1
    assert out[0]["personal"] is False
    assert out[0]["owner"] == "Maya"
    assert out[0]["suggested_owner_user_id"] == "u1"
    assert out[0]["source"] == "ai_suggested"


def test_briefing_delegate_legacy_missing_has_team_keeps_handoffs():
    c = {
        "delegate_suggestions": [
            {
                "id": "del1",
                "title": "Unblock Maya",
                "detail": "Help",
                "status": "suggested",
                "suggested_owner_name": "Maya",
                "suggested_owner_user_id": "u1",
            },
        ],
    }
    out = server._briefing_what_to_delegate(c)
    assert out[0]["personal"] is False
    assert out[0]["owner"] == "Maya"


@pytest.mark.asyncio
async def test_generate_insights_solo_skips_draft_delegate():
    ws = {
        "workspace_id": "ws_solo",
        "name": "Solo Co",
        "has_team": False,
        "plan": "pro",
        "decision_suggestions": [],
        "delegate_suggestions": [],
        "tasks": {"items": []},
        "financial_settings": {"cash": 100000, "cash_entered": True, "currency": "usd"},
    }
    sig = {
        "type": "overdue_task",
        "severity": "high",
        "summary": "Follow up on invoice",
        "detail": "Due yesterday",
        "related_id": "t1",
    }
    draft_delegate = AsyncMock()
    empty = MagicMock()
    empty.to_list = AsyncMock(return_value=[])
    mock_db = MagicMock()
    mock_db.deals.find.return_value = empty
    mock_db.workspaces.update_one = AsyncMock()

    with patch.object(server, "db", mock_db), \
         patch.object(server, "get_ws", AsyncMock(return_value=ws)), \
         patch.object(server, "compute_financials", AsyncMock(return_value={
             "mrr": 0, "mrr_known": False, "currency": "usd", "entries": [],
         })), \
         patch.object(server, "_department_signal_inputs", AsyncMock(return_value=[])), \
         patch.object(server, "_recent_updates", AsyncMock(return_value=[])), \
         patch.object(server.decision_engine, "collect_signals", return_value=[sig]), \
         patch.object(server.helm_llm, "draft_decision", new=AsyncMock()), \
         patch.object(server.helm_llm, "draft_delegate", new=draft_delegate), \
         patch.object(server.doc_rate_limit, "insights_over_limit", new=AsyncMock(return_value=False)), \
         patch.object(server.doc_rate_limit, "acquire_insights_slot", new=AsyncMock(return_value=True)), \
         patch.object(server, "_notify_high_severity_alerts", new=AsyncMock(return_value={})), \
         patch.object(server.helm_llm, "anthropic_configured", return_value=True):
        result = await server._generate_insights("ws_solo")

    draft_delegate.assert_not_called()
    assert result.get("ok") is True
    update_doc = mock_db.workspaces.update_one.await_args.args[1]
    saved = update_doc["$set"]["delegate_suggestions"]
    assert len(saved) == 1
    assert saved[0]["personal"] is True
    assert saved[0]["source"] == "personal_later"
    assert "invoice" in saved[0]["title"].lower()


@pytest.mark.asyncio
async def test_generate_insights_with_team_still_drafts_delegate():
    ws = {
        "workspace_id": "ws_team",
        "name": "Team Co",
        "has_team": True,
        "plan": "pro",
        "decision_suggestions": [],
        "delegate_suggestions": [],
        "tasks": {"items": []},
        "financial_settings": {"cash": 100000, "cash_entered": True, "currency": "usd"},
    }
    sig = {
        "type": "overdue_task",
        "severity": "medium",
        "summary": "Chase vendor",
        "detail": "PO open",
        "related_id": "t2",
        "assignee_user_id": "u_maya",
        "assignee_name": "Maya",
    }
    draft_delegate = AsyncMock(return_value={
        "title": "Ask Maya to chase vendor",
        "detail": "PO still open",
        "suggested_owner_user_id": "u_maya",
        "suggested_owner_name": "Maya",
    })
    empty = MagicMock()
    empty.to_list = AsyncMock(return_value=[])
    mock_db = MagicMock()
    mock_db.deals.find.return_value = empty
    mock_db.workspaces.update_one = AsyncMock()

    with patch.object(server, "db", mock_db), \
         patch.object(server, "get_ws", AsyncMock(return_value=ws)), \
         patch.object(server, "compute_financials", AsyncMock(return_value={
             "mrr": 0, "mrr_known": False, "currency": "usd", "entries": [],
         })), \
         patch.object(server, "_department_signal_inputs", AsyncMock(return_value=[])), \
         patch.object(server, "_recent_updates", AsyncMock(return_value=[])), \
         patch.object(server.decision_engine, "collect_signals", return_value=[sig]), \
         patch.object(server.helm_llm, "draft_decision", new=AsyncMock()), \
         patch.object(server.helm_llm, "draft_delegate", new=draft_delegate), \
         patch.object(server.doc_rate_limit, "insights_over_limit", new=AsyncMock(return_value=False)), \
         patch.object(server.doc_rate_limit, "acquire_insights_slot", new=AsyncMock(return_value=True)), \
         patch.object(server, "_notify_high_severity_alerts", new=AsyncMock(return_value={})), \
         patch.object(server.helm_llm, "anthropic_configured", return_value=True):
        await server._generate_insights("ws_team")

    draft_delegate.assert_awaited()
    update_doc = mock_db.workspaces.update_one.await_args.args[1]
    saved = update_doc["$set"]["delegate_suggestions"]
    assert len(saved) == 1
    assert saved[0].get("personal") is not True
    assert saved[0]["source"] == "ai_suggested"
    assert saved[0]["suggested_owner_name"] == "Maya"
