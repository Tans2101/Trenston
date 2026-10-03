"""GET /briefing date must use the workspace timezone, not UTC."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_briefing_date_timezone")

import server  # noqa: E402


@pytest.mark.asyncio
async def test_briefing_date_uses_workspace_local_weekday():
    # 2026-10-02 20:00 UTC = Friday; Asia/Manila (UTC+8) is already Saturday.
    fixed_utc = datetime(2026, 10, 2, 20, 0, 0, tzinfo=timezone.utc)
    manila_now = fixed_utc.astimezone(ZoneInfo("Asia/Manila"))
    assert manila_now.strftime("%A") == "Saturday"
    assert fixed_utc.strftime("%A") == "Friday"

    ws = {
        "workspace_id": "ws_tz",
        "timezone": "Asia/Manila",
        "briefing": {"headline": "Hello", "what_changed": []},
        "insights_generated_at": "2099-01-01T00:00:00+00:00",
        "decisions": [],
        "decision_suggestions": [],
        "delegate_suggestions": [],
    }
    principal = {"workspace_id": "ws_tz", "user_id": "u1", "role": "owner", "pack": "owner"}
    empty_cursor = MagicMock()
    empty_cursor.sort.return_value = empty_cursor
    empty_cursor.to_list = AsyncMock(return_value=[])

    with patch.object(server, "get_ws", AsyncMock(return_value=ws)), \
         patch.object(server, "can_access_financials", AsyncMock(return_value=False)), \
         patch.object(server, "workspace_is_pro", return_value=False), \
         patch.object(server, "_insights_stale", return_value=False), \
         patch.object(server, "_briefing_gmail_swr", AsyncMock(return_value=([], {
             "connected": False, "needs_reconnect": False, "compose": False,
         }))), \
         patch.object(server, "_briefing_ops_metrics", AsyncMock(return_value=[])), \
         patch.object(server.helm_freshness, "resolve_workspace_data_as_of", AsyncMock(return_value={
             "data_as_of": None, "sources": {},
         })), \
         patch.object(server.tz_utils, "workspace_now", return_value=manila_now), \
         patch.object(server.tz_utils, "workspace_today_iso", return_value=manila_now.date().isoformat()), \
         patch.object(server, "db") as mock_db:
        mock_db.workspaces.update_one = AsyncMock()
        mock_db.activities.find.return_value = empty_cursor
        mock_db.updates.find.return_value = empty_cursor
        result = await server.briefing(principal)

    assert result["date"] == "Saturday"
