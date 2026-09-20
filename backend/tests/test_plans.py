"""Plan caps, Free feature blocks, and billing-period usage — no live Mongo required for catalog tests."""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import plans
import plan_usage


def test_normalize_legacy_pro_to_starter():
    """Existing paying workspaces (plan=pro) land on Starter — conscious migration."""
    assert plans.normalize_plan("pro") == "starter"
    assert plans.normalize_plan("PRO") == "starter"


def test_member_caps_per_plan():
    assert plans.seats_limit("free") == 3
    assert plans.seats_limit("starter") == 7
    assert plans.seats_limit("growth") == 20
    assert plans.seats_limit("business") == 35


def test_document_caps_per_plan():
    assert plans.ai_extracts_limit("free") == 0
    assert plans.ai_extracts_lifetime_limit("free") == 5
    assert plans.ai_extracts_lifetime_limit("starter") == 0
    assert plans.ask_helm_monthly_limit("free") == 10
    assert plans.ask_helm_monthly_limit("starter") == 100
    assert plans.ask_helm_monthly_limit("growth") == 200
    assert plans.ask_helm_monthly_limit("business") == 500
    assert plans.ai_extracts_limit("starter") == 65
    assert plans.ai_extracts_limit("growth") == 150
    assert plans.ai_extracts_limit("business") == 500


def test_free_includes_trial_ai_features():
    assert plans.plan_allows("free", plans.FEATURE_AI_EXTRACT, billing_enforced=True) is True
    assert plans.plan_allows("free", plans.FEATURE_ASK_HELM, billing_enforced=True) is True
    assert plans.plan_allows("free", plans.FEATURE_AI_BRIEFING, billing_enforced=True) is True
    assert plans.plan_allows("free", plans.FEATURE_TEAM, billing_enforced=True) is True
    assert plans.plan_allows("free", plans.FEATURE_INTEGRATIONS, billing_enforced=True) is False
    assert plans.plan_allows("free", plans.FEATURE_ADVANCED_REPORTS, billing_enforced=True) is False
    includes = " ".join(plans.PLANS["free"]["includes"])
    assert "5 AI document extracts" in includes
    assert "Google integration" in includes
    assert "No QuickBooks" not in includes
    assert "No AI document upload" not in includes


def test_starter_allows_core_paid_features():
    assert plans.plan_allows("starter", plans.FEATURE_AI_EXTRACT, billing_enforced=True) is True
    assert plans.plan_allows("starter", plans.FEATURE_ASK_HELM, billing_enforced=True) is True
    assert plans.plan_allows("starter", plans.FEATURE_INTEGRATIONS, billing_enforced=True) is True
    assert plans.plan_allows("starter", plans.FEATURE_ADVANCED_REPORTS, billing_enforced=True) is True


def test_growth_and_business_features():
    assert plans.plan_allows("growth", plans.FEATURE_ADVANCED_REPORTS, billing_enforced=True) is True
    assert plans.plan_allows("business", plans.FEATURE_PRIORITY_SUPPORT, billing_enforced=True) is True


def test_plan_allows_provider_matrix():
    assert plans.plan_allows_provider("free", "google", billing_enforced=True) is True
    assert plans.plan_allows_provider("free", "quickbooks", billing_enforced=True) is False
    assert plans.plan_allows_provider("starter", "quickbooks", billing_enforced=True) is True
    assert plans.plan_allows_provider("starter", "xero", billing_enforced=True) is True
    assert plans.plan_allows_provider("starter", "sap_b1", billing_enforced=True) is True
    assert plans.plan_allows_provider("starter", "hubspot", billing_enforced=True) is False
    assert plans.plan_allows_provider("starter", "slack", billing_enforced=True) is False
    assert plans.plan_allows_provider("growth", "hubspot", billing_enforced=True) is True
    assert plans.plan_allows_provider("growth", "slack", billing_enforced=True) is True
    assert plans.plan_allows_provider("business", "hubspot", billing_enforced=True) is True
    assert plans.plan_allows_provider("free", "hubspot", billing_enforced=False) is True


def test_prices_and_trial():
    assert plans.PLANS["free"]["price"] == 0
    assert plans.PLANS["starter"]["price"] == 15
    assert plans.PLANS["growth"]["price"] == 39
    assert plans.PLANS["business"]["price"] == 99
    assert plans.TRIAL_DAYS == 7
    for pid in ("starter", "growth", "business"):
        assert plans.PLANS[pid]["trial_days"] == 7


def test_upgrade_downgrade_helpers():
    assert plans.is_upgrade("free", "starter") is True
    assert plans.is_downgrade("growth", "starter") is True
    assert plans.is_upgrade("business", "starter") is False


def test_paddle_price_ids_from_env_only(monkeypatch):
    for key in (
        "PADDLE_PRICE_ID_STARTER",
        "PADDLE_PRICE_ID_GROWTH",
        "PADDLE_PRICE_ID_BUSINESS",
        "PADDLE_PRICE_ID",
    ):
        monkeypatch.delenv(key, raising=False)
    assert plans.paddle_price_id_for("starter") == ""
    assert plans.any_paddle_price_configured() is False
    monkeypatch.setenv("PADDLE_PRICE_ID_STARTER", "pri_starter_test")
    monkeypatch.setenv("PADDLE_PRICE_ID_GROWTH", "pri_growth_test")
    monkeypatch.setenv("PADDLE_PRICE_ID_BUSINESS", "pri_business_test")
    assert plans.paddle_price_id_for("starter") == "pri_starter_test"
    assert plans.paddle_price_id_for("growth") == "pri_growth_test"
    assert plans.paddle_price_id_for("business") == "pri_business_test"
    # Legacy single PADDLE_PRICE_ID must NOT silently map to a tier
    monkeypatch.setenv("PADDLE_PRICE_ID", "pri_legacy")
    assert plans.plan_for_paddle_price("pri_legacy") is None
    assert plans.plan_for_paddle_price("pri_starter_test") == "starter"


def test_billing_anniversary_period_resets():
    ws = {"billing_period_start": "2026-01-15T12:00:00+00:00"}
    mid = datetime(2026, 3, 20, tzinfo=timezone.utc)
    period = plan_usage.current_usage_period(ws, now=mid)
    assert period["start"].day == 15
    assert period["start"].month == 3
    assert period["end"].month == 4
    assert period["key"] == "2026-03-15"

    # After anniversary day rolls into next period
    next_day = datetime(2026, 4, 15, 1, tzinfo=timezone.utc)
    period2 = plan_usage.current_usage_period(ws, now=next_day)
    assert period2["key"] == "2026-04-15"
    assert period2["key"] != period["key"]


def test_public_plan_list_shape():
    rows = plans.public_plan_list()
    assert len(rows) == 4
    assert {r["id"] for r in rows} == {"free", "starter", "growth", "business"}
    free = next(r for r in rows if r["id"] == "free")
    assert free["checkout_available"] is False
    assert free["seats"] == 3
    assert free["integration_providers"] == []
    starter = next(r for r in rows if r["id"] == "starter")
    growth = next(r for r in rows if r["id"] == "growth")
    assert starter["seats"] == 7
    assert growth["seats"] == 20
    assert starter["integration_providers"] == ["quickbooks", "xero", "sap_b1"]
    assert "hubspot" in growth["integration_providers"]
    assert any("Up to 7 Trenston seats" in line for line in starter["includes"])
    assert any("Up to 20 Trenston seats" in line for line in growth["includes"])
    assert any("QuickBooks" in line and "Xero" in line and "SAP" in line for line in starter["includes"])
    assert any("HubSpot" in line for line in starter["includes"]) is False
    assert any("CEO Pack" in line for line in starter["includes"])
    assert any("HubSpot" in line for line in growth["includes"])
    assert free["ai_extracts_lifetime"] == 5
    assert free["ask_helm_mo"] == 10
    assert any("5 AI document extracts" in line for line in free["includes"])
    biz = next(r for r in rows if r["id"] == "business")
    assert biz["seats"] == 35


def test_lifetime_extract_count_reads_workspace_field():
    assert plan_usage.get_lifetime_extract_count(None) == 0
    assert plan_usage.get_lifetime_extract_count({"ai_extracts_lifetime_used": 5}) == 5


@pytest.mark.asyncio
async def test_starter_seat_enforcement_allows_7th_blocks_8th():
    """Invite-time cap reads plans.seats_limit(), not a hardcoded figure for Starter."""
    os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
    os.environ.setdefault("DB_NAME", "test_starter_seats")
    import server
    from fastapi import HTTPException

    with patch.object(server, "BILLING_ENFORCED", True), \
         patch.object(server, "_seat_count", new=AsyncMock(return_value=6)), \
         patch.object(server.plan_usage, "acquire_seat_slot", new=AsyncMock(return_value=True)) as acquire:
        await server._enforce_seat_available("ws_test", "starter")
        acquire.assert_awaited_once()
        assert acquire.await_args.kwargs["membership_count"] == 6
        assert acquire.await_args.args[2] == 7

    with patch.object(server, "BILLING_ENFORCED", True), \
         patch.object(server, "_seat_count", new=AsyncMock(return_value=7)), \
         patch.object(server.plan_usage, "acquire_seat_slot", new=AsyncMock(return_value=False)):
        with pytest.raises(HTTPException) as ei:
            await server._enforce_seat_available("ws_test", "starter")
        assert ei.value.status_code == 403
        assert "7/7" in ei.value.detail


@pytest.mark.asyncio
async def test_growth_seat_enforcement_allows_20th_blocks_21st():
    """Invite-time cap reads plans.seats_limit() for Growth (20)."""
    os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
    os.environ.setdefault("DB_NAME", "test_growth_seats")
    import server
    from fastapi import HTTPException

    with patch.object(server, "BILLING_ENFORCED", True), \
         patch.object(server, "_seat_count", new=AsyncMock(return_value=19)), \
         patch.object(server.plan_usage, "acquire_seat_slot", new=AsyncMock(return_value=True)):
        await server._enforce_seat_available("ws_test", "growth")

    with patch.object(server, "BILLING_ENFORCED", True), \
         patch.object(server, "_seat_count", new=AsyncMock(return_value=20)), \
         patch.object(server.plan_usage, "acquire_seat_slot", new=AsyncMock(return_value=False)):
        with pytest.raises(HTTPException) as ei:
            await server._enforce_seat_available("ws_test", "growth")
        assert ei.value.status_code == 403
        assert "20/20" in ei.value.detail
