"""Unit tests for atomic decision updates + action allowlist."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import server


def _ws(decisions):
    return {
        "workspace_id": "ws1",
        "decisions": decisions,
        "decision_suggestions": [],
    }


@pytest.mark.asyncio
async def test_decision_action_rejects_unknown_action():
    with patch.object(server, "get_ws", AsyncMock(return_value=_ws([
        {"id": "d1", "status": "pending", "title": "T"},
    ]))):
        with pytest.raises(HTTPException) as exc:
            await server.decision_action(
                "d1",
                server.DecisionAction(action="explode"),
                {"user_id": "u1", "workspace_id": "ws1", "pack": "owner", "name": "Ada"},
            )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_decision_action_rejects_terminal_transition():
    with patch.object(server, "get_ws", AsyncMock(return_value=_ws([
        {"id": "d1", "status": "approved", "title": "T"},
    ]))):
        with pytest.raises(HTTPException) as exc:
            await server.decision_action(
                "d1",
                server.DecisionAction(action="rejected"),
                {"user_id": "u1", "workspace_id": "ws1", "pack": "owner", "name": "Ada"},
            )
    assert exc.value.status_code == 400
    assert "resolved" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_decision_action_uses_array_filters():
    update = AsyncMock(return_value=MagicMock(matched_count=1))
    mock_db = MagicMock()
    mock_db.workspaces.update_one = update
    principal = {"user_id": "u1", "workspace_id": "ws1", "pack": "owner", "name": "Ada"}
    ws = _ws([{"id": "d1", "status": "pending", "title": "T"}])
    with (
        patch.object(server, "get_ws", AsyncMock(side_effect=[ws, ws])),
        patch.object(server, "db", mock_db),
        patch.object(server, "invalidate_workspace_list_cache"),
    ):
        out = await server.decision_action(
            "d1",
            server.DecisionAction(action="approved"),
            principal,
        )
    assert out["ok"] is True
    update.assert_awaited_once()
    args, kwargs = update.await_args
    assert "decisions.$[d].status" in args[1]["$set"]
    assert args[1]["$set"]["decisions.$[d].status"] == "approved"
    assert kwargs.get("array_filters") == [{"d.id": "d1"}]


@pytest.mark.asyncio
async def test_create_decision_uses_push():
    update = AsyncMock()
    mock_db = MagicMock()
    mock_db.workspaces.update_one = update
    with (
        patch.object(server, "get_ws", AsyncMock(return_value=_ws([]))),
        patch.object(server, "db", mock_db),
        patch.object(server, "invalidate_workspace_list_cache"),
        patch.object(server, "log_activity", AsyncMock()),
    ):
        out = await server.create_decision(
            server.DecisionInput(title="Ship it"),
            {"user_id": "u1", "workspace_id": "ws1", "pack": "owner"},
        )
    assert out["ok"] is True
    args, _ = update.await_args
    assert "$push" in args[1]
    assert args[1]["$push"]["decisions"]["title"] == "Ship it"


@pytest.mark.asyncio
async def test_delete_decision_uses_pull():
    update = AsyncMock(return_value=MagicMock(matched_count=1, modified_count=1))
    mock_db = MagicMock()
    mock_db.workspaces.update_one = update
    with (
        patch.object(server, "get_ws", AsyncMock(return_value=_ws([{"id": "d1"}]))),
        patch.object(server, "db", mock_db),
        patch.object(server, "invalidate_workspace_list_cache"),
    ):
        out = await server.delete_decision(
            "d1",
            {"user_id": "u1", "workspace_id": "ws1", "pack": "owner"},
        )
    assert out["ok"] is True
    args, _ = update.await_args
    assert args[1] == {"$pull": {"decisions": {"id": "d1"}}}


@pytest.mark.asyncio
async def test_delete_decision_404_when_id_missing():
    update = AsyncMock(return_value=MagicMock(matched_count=1, modified_count=0))
    mock_db = MagicMock()
    mock_db.workspaces.update_one = update
    with (
        patch.object(server, "get_ws", AsyncMock(return_value=_ws([]))),
        patch.object(server, "db", mock_db),
    ):
        with pytest.raises(HTTPException) as exc:
            await server.delete_decision(
                "missing",
                {"user_id": "u1", "workspace_id": "ws1", "pack": "owner"},
            )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_edit_decision_rejects_blank_title():
    with patch.object(server, "get_ws", AsyncMock(return_value=_ws([{"id": "d1", "title": "Old"}]))):
        with pytest.raises(HTTPException) as exc:
            await server.edit_decision(
                "d1",
                server.DecisionInput(title="   "),
                {"user_id": "u1", "workspace_id": "ws1", "pack": "owner"},
            )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_approve_suggestion_uses_atomic_pull_push():
    update = AsyncMock(return_value=MagicMock(matched_count=1, modified_count=1))
    mock_db = MagicMock()
    mock_db.workspaces.update_one = update
    ws = {
        "workspace_id": "ws1",
        "decisions": [{"id": "d_existing", "title": "Keep me"}],
        "decision_suggestions": [{
            "id": "s1",
            "status": "suggested",
            "title": "Ship it",
            "impact": "High",
            "confidence": 70,
        }],
    }
    with (
        patch.object(server, "get_ws", AsyncMock(return_value=ws)),
        patch.object(server, "db", mock_db),
        patch.object(server, "invalidate_workspace_list_cache"),
        patch.object(server, "log_activity", AsyncMock()),
    ):
        out = await server.approve_decision_suggestion(
            "s1",
            {"user_id": "u1", "workspace_id": "ws1", "pack": "owner", "name": "Ada"},
        )
    assert out["ok"] is True
    assert out["decision"]["title"] == "Ship it"
    args, _ = update.await_args
    assert args[0]["decision_suggestions"]["$elemMatch"]["id"] == "s1"
    assert "$pull" in args[1] and "$push" in args[1]
    assert "$set" not in args[1]
    assert args[1]["$push"]["decisions"]["from_suggestion_id"] == "s1"


@pytest.mark.asyncio
async def test_decisions_list_sorted_by_impact():
    ws = _ws([
        {"id": "d_low", "impact": "Low", "due": "2026-01-01", "status": "pending"},
        {"id": "d_high", "impact": "High", "due": "2026-06-01", "status": "pending"},
        {"id": "d_med", "impact": "Medium", "due": "—", "status": "pending"},
    ])
    ws["decision_suggestions"] = [
        {"id": "s_low", "status": "suggested", "impact": "Low", "due": "2026-01-01"},
        {"id": "s_high", "status": "suggested", "impact": "High", "due": "2026-02-01"},
    ]
    with (
        patch.object(server, "get_ws", AsyncMock(return_value=ws)),
        patch.object(server, "can_access_financials", AsyncMock(return_value=True)),
        patch.object(server, "can_section_write", AsyncMock(return_value=True)),
        patch.object(server, "workspace_is_pro", return_value=True),
    ):
        out = await server.decisions(
            {"user_id": "u1", "workspace_id": "ws1", "pack": "owner", "name": "Ada"},
        )
    # High first; Medium with em-dash due sorts after dated High; Low last.
    assert [d["id"] for d in out["decisions"]] == ["d_high", "d_med", "d_low"]
    assert [s["id"] for s in out["suggestions"]] == ["s_high", "s_low"]
    # Em-dash due must not sort before real ISO dates within the same impact.
    ws2 = _ws([
        {"id": "d_dash", "impact": "High", "due": "—", "status": "pending"},
        {"id": "d_dated", "impact": "High", "due": "2026-03-01", "status": "pending"},
    ])
    with (
        patch.object(server, "get_ws", AsyncMock(return_value=ws2)),
        patch.object(server, "can_access_financials", AsyncMock(return_value=True)),
        patch.object(server, "can_section_write", AsyncMock(return_value=True)),
        patch.object(server, "workspace_is_pro", return_value=True),
    ):
        out2 = await server.decisions(
            {"user_id": "u1", "workspace_id": "ws1", "pack": "owner", "name": "Ada"},
        )
    assert [d["id"] for d in out2["decisions"]] == ["d_dated", "d_dash"]
