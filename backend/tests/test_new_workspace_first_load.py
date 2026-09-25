"""Regression for the new-company crash: a workspace created via the exact
WorkspaceGate -> POST /workspaces -> build_workspace(..., empty=True) path
must load /company and /briefing (the endpoints a brand-new user's first
pages fetch) without raising, and every field build_workspace(empty=True)
leaves unset must be handled by null-safe access, not a direct KeyError.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_new_workspace_first_load")

import seed_data  # noqa: E402
import server  # noqa: E402

OWNER = {"workspace_id": "ws1", "user_id": "u1", "pack": "owner", "role": "owner", "name": "Brand New Owner"}


def _empty_workspace():
    return seed_data.build_workspace("ws1", "Acme Robotics", "u1", empty=True)


def test_company_endpoint_loads_empty_workspace():
    ws = _empty_workspace()
    with patch.object(server, "get_ws", new=AsyncMock(return_value=ws)):
        out = asyncio.run(server.company(principal=OWNER))
    assert out["name"] == "Acme Robotics"
    assert out["currency"] == "usd"


def test_briefing_endpoint_loads_empty_workspace():
    """Exercises /briefing (the /app index route's first fetch) against a
    truly empty workspace, with only the heavy, unrelated internals
    (financials, Gmail sync, freshness, ops metrics) stubbed out so this
    test stays focused on whether briefing() itself chokes on the
    empty=True document shape."""
    ws = _empty_workspace()

    fake_db = MagicMock()
    fake_db.workspaces.update_one = AsyncMock()
    fake_activities_cursor = MagicMock()
    fake_activities_cursor.sort.return_value.to_list = AsyncMock(return_value=[])
    fake_db.activities.find.return_value = fake_activities_cursor
    fake_updates_cursor = MagicMock()
    fake_updates_cursor.sort.return_value.to_list = AsyncMock(return_value=[])
    fake_db.updates.find.return_value = fake_updates_cursor

    with (
        patch.object(server, "db", fake_db),
        patch.object(server, "get_ws", new=AsyncMock(return_value=ws)),
        patch.object(server, "can_access_financials", new=AsyncMock(return_value=False)),
        patch.object(
            server, "_briefing_gmail_swr",
            new=AsyncMock(return_value=([], {"connected": False, "needs_reconnect": False})),
        ),
        patch.object(server, "_briefing_ops_metrics", new=AsyncMock(return_value=[])),
        patch.object(
            server.helm_freshness, "resolve_workspace_data_as_of",
            new=AsyncMock(return_value={"data_as_of": None, "sources": {}}),
        ),
        patch.object(server, "_insights_stale", return_value=False),
    ):
        out = asyncio.run(server.briefing(principal=OWNER))

    assert out["headline"]
    assert isinstance(out["metrics"], list)
    assert isinstance(out["what_changed"], list)
