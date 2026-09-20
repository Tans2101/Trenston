"""Ask Trenston billing-period quota (separate from AI extracts)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

import plan_usage
import plans


def test_paid_plans_have_ask_helm_caps():
    assert plans.ask_helm_monthly_limit("free") == 10
    assert plans.ask_helm_monthly_limit("starter") == 100
    assert plans.ask_helm_monthly_limit("growth") == 200
    assert plans.ask_helm_monthly_limit("business") == 500
    # Separate from extract quotas
    assert plans.ai_extracts_limit("starter") == 65
    assert plans.ai_extracts_limit("growth") == 150
    assert plans.ai_extracts_limit("business") == 500


@pytest.mark.asyncio
async def test_acquire_period_ask_slot_respects_limit():
    coll = MagicMock()
    coll.find_one_and_update = AsyncMock(side_effect=[
        {"count": 1},
        {"count": 2},
        None,  # at cap
    ])
    db = MagicMock()
    db.document_usage_periods = coll

    assert await plan_usage.acquire_period_ask_slot(db, "ws1", "2026-09-01", 2) is True
    assert await plan_usage.acquire_period_ask_slot(db, "ws1", "2026-09-01", 2) is True
    assert await plan_usage.acquire_period_ask_slot(db, "ws1", "2026-09-01", 2) is False
    assert coll.find_one_and_update.await_count == 3


@pytest.mark.asyncio
async def test_acquire_period_extract_slot_respects_limit():
    coll = MagicMock()
    coll.find_one_and_update = AsyncMock(side_effect=[
        {"count": 1},
        None,
    ])
    db = MagicMock()
    db.document_usage_periods = coll

    assert await plan_usage.acquire_period_extract_slot(db, "ws1", "2026-09-01", 1) is True
    assert await plan_usage.acquire_period_extract_slot(db, "ws1", "2026-09-01", 1) is False
    filt = coll.find_one_and_update.await_args_list[0].args[0]
    assert filt["action"] == "extract"
    assert filt["count"] == {"$lt": 1}


@pytest.mark.asyncio
async def test_acquire_lifetime_extract_slot_respects_limit():
    coll = MagicMock()
    coll.find_one_and_update = AsyncMock(side_effect=[
        {"ai_extracts_lifetime_used": 5},
        None,
    ])
    db = MagicMock()
    db.workspaces = coll

    assert await plan_usage.acquire_lifetime_extract_slot(db, "ws1", 5) is True
    assert await plan_usage.acquire_lifetime_extract_slot(db, "ws1", 5) is False


@pytest.mark.asyncio
async def test_concurrent_extract_slots_only_one_succeeds_at_boundary():
    """Two acquires with one slot left: only one wins (mirrors Ask Trenston)."""
    state = {"count": 1}
    limit = 2

    async def _find_one_and_update(filt, update, **kwargs):
        lt = (filt.get("count") or {}).get("$lt")
        if state["count"] < lt:
            state["count"] += 1
            return {"count": state["count"]}
        return None

    coll = MagicMock()
    coll.find_one_and_update = AsyncMock(side_effect=_find_one_and_update)
    db = MagicMock()
    db.document_usage_periods = coll

    results = await asyncio.gather(
        plan_usage.acquire_period_extract_slot(db, "ws1", "p1", limit),
        plan_usage.acquire_period_extract_slot(db, "ws1", "p1", limit),
    )
    assert sorted(results) == [False, True]
    assert state["count"] == 2


@pytest.mark.asyncio
async def test_concurrent_seat_slots_only_one_succeeds_at_boundary():
    state = {"count": 9}
    limit = 10

    async def _update_one(*_a, **_k):
        return None

    async def _find_one_and_update(filt, update, **kwargs):
        lt = (filt.get("count") or {}).get("$lt")
        if state["count"] < lt:
            state["count"] += 1
            return {"count": state["count"]}
        return None

    coll = MagicMock()
    coll.update_one = AsyncMock(side_effect=_update_one)
    coll.find_one_and_update = AsyncMock(side_effect=_find_one_and_update)
    db = MagicMock()
    db.seat_usage = coll

    results = await asyncio.gather(
        plan_usage.acquire_seat_slot(db, "ws1", limit, membership_count=9),
        plan_usage.acquire_seat_slot(db, "ws1", limit, membership_count=9),
    )
    assert sorted(results) == [False, True]
    assert state["count"] == 10


@pytest.mark.asyncio
async def test_release_period_extract_slot_decrements():
    coll = MagicMock()
    coll.update_one = AsyncMock()
    db = MagicMock()
    db.document_usage_periods = coll
    await plan_usage.release_period_extract_slot(db, "ws1", "p1")
    filt = coll.update_one.await_args.args[0]
    assert filt["action"] == "extract"
    assert filt["count"] == {"$gt": 0}
    assert coll.update_one.await_args.args[1]["$inc"]["count"] == -1


@pytest.mark.asyncio
async def test_get_period_ask_count_defaults_zero():
    coll = MagicMock()
    coll.find_one = AsyncMock(return_value=None)
    db = MagicMock()
    db.document_usage_periods = coll
    assert await plan_usage.get_period_ask_count(db, "ws1", "2026-09-01") == 0
    coll.find_one = AsyncMock(return_value={"count": 7})
    assert await plan_usage.get_period_ask_count(db, "ws1", "2026-09-01") == 7


@pytest.mark.asyncio
async def test_ask_and_extract_use_distinct_actions():
    """Extract and Ask Trenston must not share the same usage counter row."""
    calls = []

    async def _find_one(filt, *a, **k):
        calls.append(dict(filt))
        return {"count": 0}

    coll = MagicMock()
    coll.find_one = AsyncMock(side_effect=_find_one)
    db = MagicMock()
    db.document_usage_periods = coll
    await plan_usage.get_period_extract_count(db, "ws1", "p1")
    await plan_usage.get_period_ask_count(db, "ws1", "p1")
    assert calls[0]["action"] == "extract"
    assert calls[1]["action"] == "ask_helm"
