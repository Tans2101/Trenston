"""Scheduling a downgrade must change the Paddle subscription, not only Trenston's plan."""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_schedule_plan")

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

import plans as helm_plans
import server

WS = "ws_sched"
OWNER = {"user_id": "u1", "workspace_id": WS, "pack": "owner", "role": "owner"}
END = "2026-11-17T00:00:00Z"


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


@pytest.fixture
def env(monkeypatch):
    db = AsyncMongoMockClient()["sched"]
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setenv("PADDLE_PRICE_ID_STARTER", "pri_starter")
    monkeypatch.setenv("PADDLE_PRICE_ID_GROWTH", "pri_growth")
    calls = []

    async def fake_request(method, path, body=None):
        calls.append((method, path, body))
        return {"current_billing_period": {"ends_at": END}, "scheduled_change": {"effective_at": END}}

    monkeypatch.setattr(server, "_paddle_request", fake_request)
    run(db.workspaces.insert_one({
        "workspace_id": WS, "plan": "growth", "paddle_subscription_id": "sub_1",
        "billing_provider": "paddle", "subscription_status": "active",
    }))
    server.invalidate_plan_cache(WS)
    return db, calls


def schedule(plan):
    return run(server.schedule_plan_change(server.SchedulePlanInput(plan=plan), principal=OWNER))


def test_downgrade_to_free_cancels_paddle_at_period_end(env):
    db, calls = env
    out = schedule("free")
    assert calls == [("POST", "/subscriptions/sub_1/cancel", {"effective_from": "next_billing_period"})]
    assert out["pending_plan"] == "free"
    assert out["pending_plan_effective_at"] == END


def test_downgrade_to_lower_paid_plan_swaps_price_without_billing(env):
    db, calls = env
    schedule("starter")
    assert calls == [("PATCH", "/subscriptions/sub_1", {
        "items": [{"price_id": "pri_starter", "quantity": 1}],
        "proration_billing_mode": "do_not_bill",
    })]


def test_undo_scheduled_cancel_clears_it_and_restores_price(env):
    db, calls = env
    schedule("free")
    calls.clear()
    out = schedule("growth")
    assert out["pending_plan"] is None
    assert calls[0] == ("PATCH", "/subscriptions/sub_1", {"scheduled_change": None})
    assert calls[1][2]["items"] == [{"price_id": "pri_growth", "quantity": 1}]


def test_paddle_failure_does_not_record_downgrade(env, monkeypatch):
    db, calls = env

    async def boom(*a, **k):
        raise HTTPException(status_code=503, detail="nope")

    monkeypatch.setattr(server, "_paddle_request", boom)
    with pytest.raises(HTTPException):
        schedule("free")
    ws = run(db.workspaces.find_one({"workspace_id": WS}))
    assert not ws.get("pending_plan")


def test_renewal_event_keeps_paid_plan_until_scheduled_date(env):
    db, calls = env
    future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    run(db.workspaces.update_one({"workspace_id": WS}, {"$set": {
        "pending_plan": "starter", "pending_plan_effective_at": future}}))
    event = {"data": {"id": "sub_1", "subscription_id": "sub_1", "status": "active",
                      "items": [{"price": {"id": "pri_starter"}}]}}
    run(server._paddle_provision(event, status="active"))
    ws = run(db.workspaces.find_one({"workspace_id": WS}))
    assert ws["plan"] == "growth"


class _Req:
    def __init__(self, body):
        self._b = body

    async def json(self):
        return self._b


def config(env_db, plan, monkeypatch):
    monkeypatch.setattr(server, "PADDLE_CLIENT_TOKEN", "tok")
    return run(server.paddle_config(_Req({"plan": plan}), principal={**OWNER, "name": "O", "email": "o@x"}))


def test_upgrade_with_existing_subscription_changes_it_in_place(env, monkeypatch):
    db, calls = env
    monkeypatch.setenv("PADDLE_PRICE_ID_BUSINESS", "pri_business")
    monkeypatch.setattr(server, "log_activity", lambda *a, **k: asyncio.sleep(0))
    out = config(db, "business", monkeypatch)
    assert out == {"upgraded": True, "plan": "business"}
    assert calls == [("PATCH", "/subscriptions/sub_1", {
        "items": [{"price_id": "pri_business", "quantity": 1}],
        "proration_billing_mode": "prorated_immediately",
    })]
    assert run(db.paddle_intents.count_documents({})) == 0  # no second checkout
    assert run(db.workspaces.find_one({"workspace_id": WS}))["plan"] == "business"


def test_new_customer_still_gets_checkout(env, monkeypatch):
    db, calls = env
    run(db.workspaces.update_one({"workspace_id": WS}, {"$set": {"plan": "free"},
                                                      "$unset": {"paddle_subscription_id": ""}}))
    server.invalidate_plan_cache(WS)
    out = config(db, "starter", monkeypatch)
    assert out["checkout_nonce"] and not calls
