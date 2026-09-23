"""Unit tests for Paddle provision plan mapping (no live webhook required)."""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_paddle_provision")
os.environ["PADDLE_PRICE_ID_STARTER"] = "pri_starter_test"
os.environ["PADDLE_PRICE_ID_GROWTH"] = "pri_growth_test"
os.environ["PADDLE_PRICE_ID_BUSINESS"] = "pri_business_test"

import plans as helm_plans
import server


def test_paddle_price_id_from_event_shapes():
    assert server._paddle_price_id_from_event({
        "items": [{"price": {"id": "pri_growth_test"}, "quantity": 1}],
    }) == "pri_growth_test"
    assert server._paddle_price_id_from_event({
        "items": [{"price_id": "pri_starter_test"}],
    }) == "pri_starter_test"
    assert server._paddle_price_id_from_event({
        "details": {"line_items": [{"price": {"id": "pri_business_test"}}]},
    }) == "pri_business_test"
    assert server._paddle_price_id_from_event({}) is None


def test_plan_for_paddle_price_maps_env_ids():
    assert helm_plans.plan_for_paddle_price("pri_growth_test") == helm_plans.PLAN_GROWTH
    assert helm_plans.plan_for_paddle_price("pri_unknown") is None


@pytest.mark.asyncio
async def test_recovery_path_updates_plan_from_price():
    prev = {
        "workspace_id": "ws_1",
        "subscription_status": "active",
        "plan": "starter",
    }
    update = AsyncMock()
    find_one = AsyncMock(return_value=prev)
    with patch.object(server.db, "workspaces", MagicMock(find_one=find_one, update_one=update)), \
         patch.object(server, "invalidate_plan_cache") as inv, \
         patch.object(server.helm_analytics, "emit_billing_funnel", new=AsyncMock()), \
         patch.object(server, "_maybe_mark_referral_converted", new=AsyncMock()), \
         patch.object(server, "_paddle_trial_fields", return_value={}):
        await server._paddle_provision({
            "occurred_at": "2026-09-18T12:00:00Z",
            "data": {
                "id": "sub_abc",
                "customer_id": "ctm_1",
                "items": [{"price": {"id": "pri_growth_test"}}],
            },
        }, status="active")
    assert update.await_count == 1
    set_fields = update.await_args.args[1]["$set"]
    assert set_fields["plan"] == "growth"
    assert set_fields["subscription_status"] == "active"
    inv.assert_called_once_with("ws_1")


@pytest.mark.asyncio
async def test_used_checkout_nonce_is_refused():
    intent = {
        "_id": "nonce1",
        "workspace_id": "ws_1",
        "user_id": "u_1",
        "plan": "starter",
        "price_id": "pri_starter_test",
        "used": True,
    }
    update = AsyncMock()
    claim = AsyncMock(return_value=None)  # atomic claim fails because used
    with patch.object(server.db, "paddle_intents", MagicMock(
        find_one_and_update=claim,
        find_one=AsyncMock(return_value=intent),
        update_one=update,
    )), patch.object(server.db, "workspaces", MagicMock(update_one=AsyncMock(), find_one=AsyncMock())):
        await server._paddle_provision({
            "data": {
                "id": "sub_x",
                "custom_data": {
                    "checkout_nonce": "nonce1",
                    "workspace_id": "ws_1",
                    "user_id": "u_1",
                },
            },
        }, status="active")
    update.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_intent_still_provisions_from_custom_data():
    """P0 regression: TTL'd/missing intent must not ACK-and-drop a paid checkout."""
    ws_update = AsyncMock()
    ws_find = AsyncMock(return_value={
        "workspace_id": "ws_paid",
        "billing_period_start": None,
        "subscription_status": "free",
    })
    claim = AsyncMock(return_value=None)
    intent_find = AsyncMock(return_value=None)  # expired / TTL'd
    with patch.object(server.db, "paddle_intents", MagicMock(
        find_one_and_update=claim,
        find_one=intent_find,
    )), patch.object(server.db, "workspaces", MagicMock(
        find_one=ws_find,
        update_one=ws_update,
    )), patch.object(server, "invalidate_plan_cache") as inv, \
         patch.object(server.helm_analytics, "emit_billing_funnel", new=AsyncMock()), \
         patch.object(server, "_maybe_mark_referral_converted", new=AsyncMock()), \
         patch.object(server, "_paddle_trial_fields", return_value={}):
        await server._paddle_provision({
            "occurred_at": "2026-09-18T12:00:00Z",
            "data": {
                "id": "txn_late",
                "subscription_id": "sub_late",
                "customer_id": "ctm_late",
                "items": [{"price": {"id": "pri_growth_test"}}],
                "custom_data": {
                    "checkout_nonce": "expired_nonce",
                    "workspace_id": "ws_paid",
                    "user_id": "u_paid",
                },
            },
        }, status="active")
    assert ws_update.await_count == 1
    set_fields = ws_update.await_args.args[1]["$set"]
    assert set_fields["plan"] == "growth"
    assert set_fields["subscription_status"] == "active"
    assert set_fields["paddle_subscription_id"] == "sub_late"
    inv.assert_called_once_with("ws_paid")


@pytest.mark.asyncio
async def test_atomic_intent_claim_before_entitlements():
    claimed = {
        "_id": "nonce_claim",
        "workspace_id": "ws_1",
        "user_id": "u_1",
        "plan": "starter",
        "price_id": "pri_starter_test",
        "used": True,
    }
    claim = AsyncMock(return_value=claimed)
    ws_update = AsyncMock()
    with patch.object(server.db, "paddle_intents", MagicMock(
        find_one_and_update=claim,
        find_one=AsyncMock(),
    )), patch.object(server.db, "workspaces", MagicMock(
        find_one=AsyncMock(return_value={"workspace_id": "ws_1", "subscription_status": None}),
        update_one=ws_update,
    )), patch.object(server, "invalidate_plan_cache"), \
         patch.object(server.helm_analytics, "emit_billing_funnel", new=AsyncMock()), \
         patch.object(server, "_maybe_mark_referral_converted", new=AsyncMock()), \
         patch.object(server, "_paddle_trial_fields", return_value={}):
        await server._paddle_provision({
            "occurred_at": "2026-09-18T12:00:00Z",
            "data": {
                "id": "sub_claim",
                "customer_id": "ctm_1",
                "items": [{"price": {"id": "pri_starter_test"}}],
                "custom_data": {
                    "checkout_nonce": "nonce_claim",
                    "workspace_id": "ws_1",
                    "user_id": "u_1",
                },
            },
        }, status="active")
    claim.assert_awaited_once()
    filt = claim.await_args.args[0]
    assert filt == {
        "_id": "nonce_claim",
        "workspace_id": "ws_1",
        "user_id": "u_1",
        "used": False,
    }
    assert ws_update.await_count == 1
