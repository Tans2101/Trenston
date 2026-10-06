"""Unit tests for Telemetry activity heatmap aggregation."""
import os
import sys
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_activity_heatmap")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import _activity_heatmap_for_workspace  # noqa: E402


@pytest.mark.asyncio
async def test_activity_heatmap_empty_workspace():
    cursor = MagicMock()
    cursor.__aiter__ = lambda self: self
    cursor.__anext__ = AsyncMock(side_effect=StopAsyncIteration)
    today = date(2026, 10, 6)

    with patch("server.db") as mock_db:
        mock_db.activities.find.return_value = cursor
        out = await _activity_heatmap_for_workspace("ws_empty", today=today, weeks=12)

    assert out["total"] == 0
    assert len(out["columns"]) == 12
    assert all(len(col["bins"]) == 7 for col in out["columns"])
    assert all(bin_["count"] == 0 for col in out["columns"] for bin_ in col["bins"])


@pytest.mark.asyncio
async def test_activity_heatmap_groups_by_day_with_raw_counts():
    today = date(2026, 10, 6)
    today_dt = datetime(2026, 10, 6, 12, 0, 0, tzinfo=timezone.utc)
    yesterday = today_dt - timedelta(days=1)
    docs = [
        {"created_at": today_dt.isoformat()},
        {"created_at": today_dt.isoformat()},
        {"created_at": yesterday.isoformat()},
    ]

    async def _aiter(self):
        for d in docs:
            yield d

    cursor = MagicMock()
    cursor.__aiter__ = _aiter

    with patch("server.db") as mock_db:
        mock_db.activities.find.return_value = cursor
        out = await _activity_heatmap_for_workspace("ws_busy", today=today, weeks=4)

    assert out["total"] == 3
    assert len(out["columns"]) == 4
    by_date = {
        bin_["date"]: bin_["count"]
        for col in out["columns"]
        for bin_ in col["bins"]
    }
    assert by_date[today.isoformat()] == 2
    assert by_date[yesterday.date().isoformat()] == 1
    # Future days in the current week stay at 0
    tomorrow = today + timedelta(days=1)
    if tomorrow.isoformat() in by_date:
        assert by_date[tomorrow.isoformat()] == 0


@pytest.mark.asyncio
async def test_activity_heatmap_window_uses_today_param_not_utc_now():
    """Window edges follow ``today``; activity buckets stay UTC date of created_at.

    2026-09-24T17:00:00Z is Sep 25 01:00 in Asia/Manila but still UTC Sep 24
    for bucketing (FIX 1 keeps UTC-date buckets; only the window uses today).
    """
    crossing = "2026-09-24T17:00:00+00:00"
    docs = [{"created_at": crossing}]

    async def _aiter(self):
        for d in docs:
            yield d

    cursor = MagicMock()
    cursor.__aiter__ = _aiter

    with patch("server.db") as mock_db:
        mock_db.activities.find.return_value = cursor
        # Asia/Manila local today after the UTC day rolled (Thu Sep 25)
        manila = await _activity_heatmap_for_workspace(
            "ws_tz", today=date(2026, 9, 25), weeks=2,
        )
        # UTC workspace still on Wed Sep 24
        utc_ws = await _activity_heatmap_for_workspace(
            "ws_tz", today=date(2026, 9, 24), weeks=2,
        )
        # Crossing a Sunday changes the grid anchor
        sunday = await _activity_heatmap_for_workspace(
            "ws_tz", today=date(2026, 9, 27), weeks=2,
        )
        saturday = await _activity_heatmap_for_workspace(
            "ws_tz", today=date(2026, 9, 26), weeks=2,
        )

    manila_by = {b["date"]: b["count"] for col in manila["columns"] for b in col["bins"]}
    utc_by = {b["date"]: b["count"] for col in utc_ws["columns"] for b in col["bins"]}
    # UTC-date bucketing: activity lands on 2026-09-24 for both workspace todays
    assert manila_by.get("2026-09-24") == 1
    assert utc_by.get("2026-09-24") == 1
    # Future cutoff uses today: Sep 25 is future for UTC today, included for Manila
    assert "2026-09-25" in manila_by
    assert utc_by.get("2026-09-25", 0) == 0
    assert manila_by.get("2026-09-26", 0) == 0

    sunday_dates = [b["date"] for col in sunday["columns"] for b in col["bins"]]
    saturday_dates = [b["date"] for col in saturday["columns"] for b in col["bins"]]
    assert sunday_dates[0] == "2026-09-20"  # this_sunday for Sep 27 → Sep 20 start (2 weeks)
    assert saturday_dates[0] == "2026-09-13"
    assert sunday_dates != saturday_dates
