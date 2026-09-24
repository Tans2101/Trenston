"""T5: workspace-local calendar days (default Asia/Manila)."""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_tz_utils")

import seed_data  # noqa: E402
import server  # noqa: E402
import tz_utils  # noqa: E402

FROZEN = datetime(2026, 9, 24, 23, 30, tzinfo=timezone.utc)


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return FROZEN if tz is None or tz is timezone.utc else FROZEN.astimezone(tz)


@pytest.fixture
def frozen():
    with patch.object(tz_utils, "datetime", _FrozenDatetime):
        yield


def test_workspace_today_manila_is_next_day(frozen):
    ws = {"timezone": "Asia/Manila"}
    assert tz_utils.workspace_today(ws) == date(2026, 9, 25)
    assert tz_utils.workspace_today_iso(ws) == "2026-09-25"
    now = tz_utils.workspace_now(ws)
    assert now.utcoffset().total_seconds() == 8 * 3600
    assert (now.hour, now.minute) == (7, 30)


def test_missing_or_invalid_timezone_defaults_to_manila(frozen):
    assert tz_utils.workspace_tz(None).key == "Asia/Manila"
    assert tz_utils.workspace_tz({}).key == "Asia/Manila"
    assert tz_utils.workspace_tz({"timezone": "Mars/Olympus"}).key == "Asia/Manila"
    assert tz_utils.workspace_today_iso({"timezone": "UTC"}) == "2026-09-24"
    assert tz_utils.workspace_today_iso({"timezone": "America/New_York"}) == "2026-09-24"


def test_day_and_week_bounds_utc():
    ws = {"timezone": "Asia/Manila"}
    start, end = tz_utils.day_bounds_utc(ws, date(2026, 9, 25))
    assert start == "2026-09-24T16:00:00+00:00"
    assert end == "2026-09-25T16:00:00+00:00"
    wstart, wend = tz_utils.week_bounds_utc(ws, date(2026, 9, 20))
    assert wstart == "2026-09-19T16:00:00+00:00"
    assert wend == "2026-09-26T16:00:00+00:00"
    ny_start, _ = tz_utils.day_bounds_utc({"timezone": "America/New_York"}, date(2026, 9, 25))
    assert ny_start == "2026-09-25T04:00:00+00:00"


def test_new_workspace_defaults_to_manila():
    assert seed_data.build_workspace("ws1", "Acme", "u1", empty=True)["timezone"] == "Asia/Manila"


def test_updates_me_uses_workspace_local_day(frozen):
    fake_db = MagicMock()
    fake_db.workspaces.find_one = AsyncMock(return_value={"timezone": "Asia/Manila"})
    fake_db.updates.find_one = AsyncMock(return_value=None)
    principal = {"workspace_id": "ws1", "user_id": "u1"}
    with patch.object(server, "db", fake_db):
        out = asyncio.run(server.my_update(principal=principal))
    assert out["day"] == "2026-09-25"
    query = fake_db.updates.find_one.await_args.args[0]
    assert query["day"] == "2026-09-25"


def test_company_patch_rejects_invalid_timezone():
    principal = {"workspace_id": "ws1", "user_id": "u1", "pack": "owner", "role": "owner"}
    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.update_company(server.CompanySetupInput(timezone="Nowhere/Land"), principal=principal))
    assert exc.value.status_code == 400


def test_company_patch_saves_valid_timezone():
    fake_db = MagicMock()
    fake_db.workspaces.update_one = AsyncMock()
    principal = {"workspace_id": "ws1", "user_id": "u1", "pack": "owner", "role": "owner"}
    with patch.object(server, "db", fake_db):
        asyncio.run(server.update_company(server.CompanySetupInput(timezone="Asia/Singapore"), principal=principal))
    update = fake_db.workspaces.update_one.await_args.args[1]["$set"]
    assert update["timezone"] == "Asia/Singapore"
