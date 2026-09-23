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
    update = AsyncMock(return_value=MagicMock(matched_count=1))
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
