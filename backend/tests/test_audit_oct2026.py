"""Regression tests for the Oct 2026 logic and security audit."""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_audit_oct2026")
os.environ["PADDLE_PRICE_ID_STARTER"] = "pri_starter_test"
os.environ["PADDLE_PRICE_ID_GROWTH"] = "pri_growth_test"
os.environ["PADDLE_PRICE_ID_BUSINESS"] = "pri_business_test"

import server  # noqa: E402


# ---------------------------------------------------------------- Paddle ordering

def test_stale_paddle_event_detection():
    newer = "2026-10-20T12:00:00Z"
    older = "2026-10-20T11:00:00Z"
    assert server._paddle_event_is_stale(older, newer) is True
    assert server._paddle_event_is_stale(newer, older) is False
    # Same-moment events are applied (idempotent), missing data never blocks.
    assert server._paddle_event_is_stale(newer, newer) is False
    assert server._paddle_event_is_stale(None, newer) is False
    assert server._paddle_event_is_stale(newer, None) is False
    assert server._paddle_event_is_stale("garbage", newer) is False


@pytest.mark.asyncio
async def test_late_active_event_does_not_undo_newer_past_due():
    prev = {
        "workspace_id": "ws_1",
        "subscription_status": "past_due",
        "plan": "growth",
        "paddle_last_event_at": "2026-10-20T12:00:00Z",
    }
    update = AsyncMock()
    with patch.object(server.db, "workspaces", MagicMock(find_one=AsyncMock(return_value=prev), update_one=update)), \
         patch.object(server, "invalidate_plan_cache") as inv, \
         patch.object(server.helm_analytics, "emit_billing_funnel", new=AsyncMock()), \
         patch.object(server, "_maybe_mark_referral_converted", new=AsyncMock()), \
         patch.object(server, "_paddle_trial_fields", return_value={}):
        await server._paddle_provision({
            "occurred_at": "2026-10-20T10:00:00Z",  # older than the past_due we already applied
            "data": {"id": "sub_abc", "items": [{"price": {"id": "pri_growth_test"}}]},
        }, status="active")
    update.assert_not_awaited()
    inv.assert_not_called()


@pytest.mark.asyncio
async def test_late_cancel_event_does_not_override_newer_state():
    prev = {
        "workspace_id": "ws_1",
        "subscription_status": "active",
        "plan": "growth",
        "paddle_last_event_at": "2026-10-20T12:00:00Z",
    }
    update = AsyncMock()
    with patch.object(server.db, "workspaces", MagicMock(find_one=AsyncMock(return_value=prev), update_one=update)), \
         patch.object(server, "invalidate_plan_cache") as inv, \
         patch.object(server.helm_analytics, "emit_billing_funnel", new=AsyncMock()):
        await server._paddle_downgrade({
            "occurred_at": "2026-10-20T09:00:00Z",
            "data": {"id": "sub_abc"},
        }, "past_due")
    update.assert_not_awaited()
    inv.assert_not_called()


@pytest.mark.asyncio
async def test_current_downgrade_still_applies():
    prev = {
        "workspace_id": "ws_1",
        "subscription_status": "active",
        "plan": "growth",
        "paddle_last_event_at": "2026-10-20T09:00:00Z",
    }
    update = AsyncMock()
    with patch.object(server.db, "workspaces", MagicMock(find_one=AsyncMock(return_value=prev), update_one=update)), \
         patch.object(server, "invalidate_plan_cache"), \
         patch.object(server.helm_analytics, "emit_billing_funnel", new=AsyncMock()):
        await server._paddle_downgrade({
            "occurred_at": "2026-10-20T12:00:00Z",
            "data": {"id": "sub_abc"},
        }, "canceled")
    assert update.await_count == 1
    assert update.await_args.args[1]["$set"]["plan"] == "free"


# ------------------------------------------------- Paddle: missing intent, foreign workspace

def _missing_intent_event():
    return {
        "occurred_at": "2026-10-20T12:00:00Z",
        "data": {
            "id": "txn_x",
            "subscription_id": "sub_x",
            "customer_id": "ctm_x",
            "items": [{"price": {"id": "pri_growth_test"}}],
            "custom_data": {
                "checkout_nonce": "forged_nonce",
                "workspace_id": "ws_victim",
                "user_id": "u_attacker",
            },
        },
    }


@pytest.mark.asyncio
async def test_missing_intent_is_refused_when_payer_is_not_a_member():
    ws_update = AsyncMock()
    with patch.object(server.db, "paddle_intents", MagicMock(
        find_one_and_update=AsyncMock(return_value=None), find_one=AsyncMock(return_value=None),
    )), patch.object(server.db, "workspaces", MagicMock(
        find_one=AsyncMock(return_value={"workspace_id": "ws_victim"}), update_one=ws_update,
    )), patch.object(server.db, "memberships", MagicMock(find_one=AsyncMock(return_value=None))), \
         patch.object(server, "invalidate_plan_cache"), \
         patch.object(server.helm_analytics, "emit_billing_funnel", new=AsyncMock()), \
         patch.object(server, "_maybe_mark_referral_converted", new=AsyncMock()), \
         patch.object(server, "_paddle_trial_fields", return_value={}):
        await server._paddle_provision(_missing_intent_event(), status="active")
    ws_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_intent_is_refused_when_payer_cannot_manage_billing():
    ws_update = AsyncMock()
    plain_member = {"user_id": "u_attacker", "workspace_id": "ws_victim", "role": "member", "pack": "member", "status": "active"}
    with patch.object(server.db, "paddle_intents", MagicMock(
        find_one_and_update=AsyncMock(return_value=None), find_one=AsyncMock(return_value=None),
    )), patch.object(server.db, "workspaces", MagicMock(
        find_one=AsyncMock(return_value={"workspace_id": "ws_victim"}), update_one=ws_update,
    )), patch.object(server.db, "memberships", MagicMock(find_one=AsyncMock(return_value=plain_member))), \
         patch.object(server, "invalidate_plan_cache"), \
         patch.object(server.helm_analytics, "emit_billing_funnel", new=AsyncMock()), \
         patch.object(server, "_maybe_mark_referral_converted", new=AsyncMock()), \
         patch.object(server, "_paddle_trial_fields", return_value={}):
        await server._paddle_provision(_missing_intent_event(), status="active")
    ws_update.assert_not_awaited()


# ------------------------------------------------------------ HR user id validation

@pytest.mark.asyncio
async def test_hr_user_id_must_belong_to_the_workspace():
    with patch.object(server.db, "memberships", MagicMock(find_one=AsyncMock(return_value=None))):
        with pytest.raises(HTTPException) as exc:
            await server._active_workspace_user_id("ws_1", "u_from_another_company", "Manager")
    assert exc.value.status_code == 400
    assert "Manager" in exc.value.detail


@pytest.mark.asyncio
async def test_hr_user_id_blank_and_valid():
    found = {"membership_id": "m1"}
    with patch.object(server.db, "memberships", MagicMock(find_one=AsyncMock(return_value=found))) as m:
        assert await server._active_workspace_user_id("ws_1", "  ", "Manager") is None
        assert await server._active_workspace_user_id("ws_1", None, "Manager") is None
        assert await server._active_workspace_user_id("ws_1", " u_ok ", "Manager") == "u_ok"
    query = m.find_one.await_args.args[0]
    assert query == {"workspace_id": "ws_1", "user_id": "u_ok", "status": "active"}


# ------------------------------------------------------------ background tasks kept alive

@pytest.mark.asyncio
async def test_spawn_keeps_a_reference_until_done():
    gate = asyncio.Event()
    ran = []

    async def job():
        await gate.wait()
        ran.append(True)

    task = server._spawn(job())
    assert task in server._BACKGROUND_TASKS
    gate.set()
    await task
    await asyncio.sleep(0)
    assert ran == [True]
    assert task not in server._BACKGROUND_TASKS


@pytest.mark.asyncio
async def test_spawn_logs_failures_without_raising():
    async def boom():
        raise RuntimeError("nope")

    task = server._spawn(boom())
    with pytest.raises(RuntimeError):
        await task
    await asyncio.sleep(0)
    assert task not in server._BACKGROUND_TASKS
