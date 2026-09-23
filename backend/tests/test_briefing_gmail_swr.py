"""Briefing Gmail stale-while-revalidate + parallel assembly."""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_briefing_gmail_swr")

import server  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_gmail_cache():
    server.clear_gmail_briefing_cache()
    yield
    server.clear_gmail_briefing_cache()


@pytest.mark.asyncio
async def test_gmail_swr_serves_cache_without_waiting_on_live_fetch():
    ws = {"workspace_id": "ws_g", "google_tokens": {"access_token": "x"}}
    principal = {"user_id": "u1", "workspace_id": "ws_g", "pack": "owner", "role": "owner"}
    cached_threads = [{"id": "t1", "subject": "Hello"}]
    cached_meta = {"connected": True, "needs_reconnect": False, "compose": True}
    key = server._gmail_briefing_cache_key(ws, principal)
    server._gmail_briefing_cache[key] = (cached_threads, cached_meta, time.monotonic())

    slow = AsyncMock(side_effect=AssertionError("live fetch should not run on fresh cache"))
    with patch.object(server, "_briefing_email_threads", new=slow):
        threads, meta = await server._briefing_gmail_swr(ws, principal)
    assert threads == cached_threads
    assert meta["compose"] is True
    slow.assert_not_called()


@pytest.mark.asyncio
async def test_gmail_swr_cold_miss_awaits_live_fetch():
    ws = {"workspace_id": "ws_g2"}
    principal = {"user_id": "u2", "workspace_id": "ws_g2"}
    live = AsyncMock(return_value=([{"id": "fresh"}], {"connected": True, "needs_reconnect": False, "compose": False}))
    with patch.object(server, "_briefing_email_threads", new=live), \
            patch.object(server, "_user_google_tokens_present", new=AsyncMock(return_value=True)):
        threads, meta = await server._briefing_gmail_swr(ws, principal)
    assert threads[0]["id"] == "fresh"
    live.assert_awaited_once()
    key = server._gmail_briefing_cache_key(ws, principal)
    assert key in server._gmail_briefing_cache


@pytest.mark.asyncio
async def test_gmail_swr_soft_stale_returns_cache_and_schedules_refresh():
    ws = {"workspace_id": "ws_g3"}
    principal = {"user_id": "u3", "workspace_id": "ws_g3"}
    key = server._gmail_briefing_cache_key(ws, principal)
    stale_at = time.monotonic() - (server.GMAIL_BRIEFING_SOFT_TTL_SECONDS + 1)
    server._gmail_briefing_cache[key] = (
        [{"id": "stale"}],
        {"connected": True, "needs_reconnect": False, "compose": False},
        stale_at,
    )
    scheduled = {"n": 0}

    def fake_schedule(workspace, principal, cache_key):
        scheduled["n"] += 1

    with patch.object(server, "_schedule_gmail_briefing_refresh", side_effect=fake_schedule), \
         patch.object(server, "_briefing_email_threads", new=AsyncMock(side_effect=AssertionError("no wait"))):
        threads, _meta = await server._briefing_gmail_swr(ws, principal)
    assert threads[0]["id"] == "stale"
    assert scheduled["n"] == 1


@pytest.mark.asyncio
async def test_briefing_runs_gmail_concurrently_with_other_loads():
    """Gmail delay must not stack on top of financials delay."""
    ws = {
        "workspace_id": "ws_par",
        "briefing": {"headline": "Hello", "what_changed": []},
        "insights_generated_at": "2099-01-01T00:00:00+00:00",
        "decisions": [],
        "decision_suggestions": [],
        "delegate_suggestions": [],
    }
    principal = {"workspace_id": "ws_par", "user_id": "u1", "role": "owner", "pack": "owner"}
    empty_cursor = MagicMock()
    empty_cursor.sort.return_value = empty_cursor
    empty_cursor.to_list = AsyncMock(return_value=[])

    async def slow_fin(*_a, **_k):
        await asyncio.sleep(0.15)
        return {
            "mrr": 0, "mrr_known": False, "mrr_delta": 0,
            "runway_months": None, "burn": 0, "burn_known": False, "burn_tone": "neutral",
            "runway_no_burn": False, "cash_entered": False,
        }

    async def slow_gmail(*_a, **_k):
        await asyncio.sleep(0.15)
        return [], {"connected": False, "needs_reconnect": False, "compose": False}

    with patch.object(server, "get_ws", AsyncMock(return_value=ws)), \
         patch.object(server, "can_access_financials", AsyncMock(return_value=True)), \
         patch.object(server, "compute_financials", side_effect=slow_fin), \
         patch.object(server, "_briefing_gmail_swr", side_effect=slow_gmail), \
         patch.object(server, "workspace_is_pro", return_value=False), \
         patch.object(server, "_insights_stale", return_value=False), \
         patch.object(server.helm_freshness, "resolve_workspace_data_as_of", AsyncMock(return_value={
             "data_as_of": None, "sources": {},
         })), \
         patch.object(server, "db") as mock_db:
        mock_db.workspaces.update_one = AsyncMock()
        mock_db.activities.find.return_value = empty_cursor
        mock_db.updates.find.return_value = empty_cursor
        t0 = time.monotonic()
        result = await server.briefing(principal)
        elapsed = time.monotonic() - t0

    # Sequential would be ~0.30s+; parallel should stay near max(~0.15).
    assert elapsed < 0.28, f"briefing looks sequential ({elapsed:.2f}s)"
    assert result.get("headline") == "Hello"


@pytest.mark.asyncio
async def test_gmail_timeout_writes_cache_so_reload_does_not_restall():
    ws = {"workspace_id": "ws_to"}
    principal = {"user_id": "u_to", "workspace_id": "ws_to"}

    async def boom_wait_for(coro, timeout=None):
        if asyncio.iscoroutine(coro):
            coro.close()
        raise asyncio.TimeoutError

    with patch.object(server, "_user_google_tokens_present", new=AsyncMock(return_value=True)), \
            patch.object(server.asyncio, "wait_for", side_effect=boom_wait_for):
        threads, meta = await server._briefing_gmail_swr(ws, principal)
    assert threads == []
    assert meta["connected"] is True
    key = server._gmail_briefing_cache_key(ws, principal)
    assert key in server._gmail_briefing_cache

    with patch.object(server, "_briefing_email_threads", new=AsyncMock(side_effect=AssertionError("no live"))):
        threads2, _meta2 = await server._briefing_gmail_swr(ws, principal)
    assert threads2 == []


@pytest.mark.asyncio
async def test_gmail_cold_miss_single_flight():
    ws = {"workspace_id": "ws_sf"}
    principal = {"user_id": "u_sf", "workspace_id": "ws_sf"}
    calls = {"n": 0}

    async def slow_fetch(*_a, **_k):
        calls["n"] += 1
        await asyncio.sleep(0.05)
        return [{"id": "one"}], {"connected": True, "needs_reconnect": False, "compose": False}

    with patch.object(server, "_briefing_email_threads", side_effect=slow_fetch), \
            patch.object(server, "_user_google_tokens_present", new=AsyncMock(return_value=True)):
        a, b = await asyncio.gather(
            server._briefing_gmail_swr(ws, principal),
            server._briefing_gmail_swr(ws, principal),
        )
    assert a[0][0]["id"] == "one"
    assert b[0][0]["id"] == "one"
    assert calls["n"] == 1
