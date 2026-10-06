"""Unit tests for /tasks column validation and overdue flags."""
from __future__ import annotations

import asyncio
import os
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_tasks")

import server  # noqa: E402

PRINCIPAL = {
    "user_id": "u_owner",
    "email": "owner@example.com",
    "name": "Owner",
    "workspace_id": "ws1",
    "role": "owner",
    "pack": "owner",
}


def _task_ws(*, items=None):
    return {
        "workspace_id": "ws1",
        "name": "Acme",
        "tasks": {
            "columns": [
                {"id": "backlog", "name": "To-Do"},
                {"id": "in_progress", "name": "In Progress"},
                {"id": "review", "name": "Review"},
                {"id": "done", "name": "Done"},
            ],
            "items": items
            if items is not None
            else [
                {
                    "id": "t1",
                    "title": "Ship",
                    "column": "in_progress",
                    "progress": 40,
                    "assignee_user_id": "u_owner",
                    "assignee": "Owner",
                },
            ],
        },
    }


def _task_db():
    mock_db = MagicMock()
    mock_db.workspaces.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    return mock_db


def test_create_task_rejects_bogus_column():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.create_task(server.TaskInput(title="X", column="bogus"), PRINCIPAL))
    assert exc.value.status_code == 400
    assert "Invalid column" in str(exc.value.detail)


def test_patch_task_rejects_bogus_column():
    mock_db = _task_db()
    with patch.object(server, "get_ws", AsyncMock(return_value=_task_ws())), \
         patch.object(server, "db", mock_db), \
         patch.object(server, "can_section_write", AsyncMock(return_value=True)), \
         patch.object(server, "invalidate_workspace_list_cache"):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(server.patch_task("t1", server.TaskPatch(column="bogus"), PRINCIPAL))
    assert exc.value.status_code == 400
    assert "Invalid column" in str(exc.value.detail)
    mock_db.workspaces.update_one.assert_not_called()


@pytest.mark.parametrize("column", sorted(server.VALID_TASK_COLUMNS))
def test_create_task_accepts_valid_columns(column):
    mock_db = _task_db()
    with patch.object(server, "get_ws", AsyncMock(return_value=_task_ws())), \
         patch.object(server, "db", mock_db), \
         patch.object(server, "notify_task_delegated", AsyncMock()), \
         patch.object(server, "invalidate_workspace_list_cache"):
        out = asyncio.run(server.create_task(server.TaskInput(title="Ok", column=column), PRINCIPAL))
    assert out["ok"] is True
    assert out["task"]["column"] == column


@pytest.mark.parametrize("column", ["backlog", "in_progress", "review", "done"])
def test_patch_task_accepts_valid_columns(column):
    # Start in a different column so the move always writes.
    start = "done" if column != "done" else "backlog"
    ws = _task_ws(items=[{
        "id": "t1", "title": "Ship", "column": start, "progress": 40,
        "assignee_user_id": "u_owner", "assignee": "Owner",
    }])
    mock_db = _task_db()
    with patch.object(server, "get_ws", AsyncMock(return_value=ws)), \
         patch.object(server, "db", mock_db), \
         patch.object(server, "can_section_write", AsyncMock(return_value=True)), \
         patch.object(server, "invalidate_workspace_list_cache"):
        out = asyncio.run(server.patch_task("t1", server.TaskPatch(column=column), PRINCIPAL))
    assert out["ok"] is True
    mock_db.workspaces.update_one.assert_called_once()
