"""Paddle Billing — offline (TestClient + mongomock-motor).

Covers signature verification, idempotency, nonce-binding, past_due, and
canceled-downgrade without a live MongoDB or hosted server.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_paddle_billing")

TEST_SECRET = "test_paddle_webhook_secret_offline"
WS_ID = "ws_paddle_offline"
OWNER = {
    "user_id": "u_owner",
    "email": "owner@acme.com",
    "name": "Owner",
    "workspace_id": WS_ID,
    "role": "owner",
    "pack": "owner",
}
MEMBER = {
    "user_id": "u_member",
    "email": "mem@acme.com",
    "name": "Member",
    "workspace_id": WS_ID,
    "role": "member",
    "pack": "member",
}

import server  # noqa: E402


def _sign(raw: bytes, secret: str = TEST_SECRET):
    ts = str(int(time.time()))
    sig = hmac.new(secret.encode(), f"{ts}:".encode() + raw, hashlib.sha256).hexdigest()
    return {"Content-Type": "application/json", "Paddle-Signature": f"ts={ts};h1={sig}"}


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def paddle_env(monkeypatch):
    monkeypatch.setenv("PADDLE_PRICE_ID_STARTER", "pri_starter_offline")
    monkeypatch.setenv("PADDLE_PRICE_ID_GROWTH", "pri_growth_offline")
    monkeypatch.setenv("PADDLE_PRICE_ID_BUSINESS", "pri_business_offline")
    monkeypatch.setattr(server, "PADDLE_WEBHOOK_SECRET", TEST_SECRET)
    monkeypatch.setattr(server, "PADDLE_CLIENT_TOKEN", "test_client_token")
    monkeypatch.setattr(server, "PADDLE_API_KEY", "test_api_key")
    monkeypatch.setattr(server, "PADDLE_ENV", "sandbox")
    monkeypatch.setattr(server, "DEMO_RESET_ENABLED", True)


@pytest.fixture
def paddle_db(paddle_env):
    db = AsyncMongoMockClient()["test_paddle_billing"]
    _run(db.workspaces.insert_one({
        "workspace_id": WS_ID,
        "name": "Acme",
        "plan": "free",
        "subscription_status": None,
    }))
    with patch.object(server, "db", db):
        yield db
    server.app.dependency_overrides.clear()


@pytest.fixture
def owner_client(paddle_db):
    async def principal():
        return dict(OWNER)

    server.app.dependency_overrides[server.get_principal] = principal
    # Do not use context-manager TestClient — that runs app lifespan against live Mongo.
    yield TestClient(server.app), paddle_db
    server.app.dependency_overrides.clear()


@pytest.fixture
def member_client(paddle_db):
    async def principal():
        return dict(MEMBER)

    server.app.dependency_overrides[server.get_principal] = principal
    yield TestClient(server.app), paddle_db
    server.app.dependency_overrides.clear()


def test_secret_present(paddle_env):
    assert server.PADDLE_WEBHOOK_SECRET, "PADDLE_WEBHOOK_SECRET must be set in backend/.env"


def test_billing_plans_paddle_ready(owner_client):
    client, _db = owner_client
    r = client.get("/api/billing/plans")
    assert r.status_code == 200
    d = r.json()
    assert d["paddle_ready"] is True


def test_config_requires_billing_manage(member_client):
    client, _db = member_client
    r = client.post("/api/billing/paddle/config")
    assert r.status_code == 403


def test_config_returns_token_and_nonce(owner_client):
    client, db = owner_client
    r = client.post("/api/billing/paddle/config")
    assert r.status_code == 200
    d = r.json()
    assert d["client_token"] and d["price_id"]
    assert d["environment"] in ("sandbox", "production")
    assert d["workspace_id"] == WS_ID
    intent = _run(db.paddle_intents.find_one({"_id": d["checkout_nonce"]}))
    assert intent and intent["workspace_id"] == WS_ID and intent["used"] is False


def test_webhook_bad_signature_400(owner_client):
    client, _db = owner_client
    body = json.dumps({"event_id": "evt_bad", "event_type": "transaction.completed"}).encode()
    r = client.post(
        "/api/webhook/paddle",
        data=body,
        headers={"Content-Type": "application/json", "Paddle-Signature": "ts=123;h1=deadbeef"},
    )
    assert r.status_code == 400


def test_webhook_provisions_pro_and_is_idempotent(owner_client):
    client, db = owner_client
    # ensure free first
    r = client.post("/api/demo/reset-plan")
    assert r.status_code == 200
    nonce = client.post("/api/billing/paddle/config").json()["checkout_nonce"]
    eid = f"evt_{uuid.uuid4().hex[:10]}"
    body = json.dumps({
        "event_id": eid, "event_type": "transaction.completed", "occurred_at": "2026-07-26T00:00:00Z",
        "data": {
            "id": "txn_x", "subscription_id": "sub_x", "customer_id": "ctm_x",
            "items": [{"price": {"id": "pri_starter_offline"}}],
            "custom_data": {
                "checkout_nonce": nonce, "workspace_id": WS_ID, "user_id": OWNER["user_id"],
            },
        },
    }).encode()
    hdr = _sign(body)
    r1 = client.post("/api/webhook/paddle", data=body, headers=hdr)
    assert r1.status_code == 200 and r1.json()["received"] is True
    # provisioned — legacy suite asserted "pro"; paid checkout now maps to starter
    ws = _run(db.workspaces.find_one({"workspace_id": WS_ID}))
    assert ws["plan"] == "starter" and ws.get("billing_provider") == "paddle"
    # replay same event -> idempotent (no error), still one event stored
    r2 = client.post("/api/webhook/paddle", data=body, headers=hdr)
    assert r2.status_code == 200
    assert _run(db.paddle_events.count_documents({"_id": eid})) == 1
    # cleanup
    _run(db.paddle_events.delete_one({"_id": eid}))
    client.post("/api/demo/reset-plan")


def test_webhook_nonce_binding_blocks_cross_workspace(owner_client):
    client, db = owner_client
    client.post("/api/demo/reset-plan")
    nonce = client.post("/api/billing/paddle/config").json()["checkout_nonce"]  # bound to WS_ID
    eid = f"evt_{uuid.uuid4().hex[:10]}"
    body = json.dumps({
        "event_id": eid, "event_type": "transaction.completed",
        "data": {
            "id": "txn_y",
            "items": [{"price": {"id": "pri_starter_offline"}}],
            "custom_data": {
                "checkout_nonce": nonce,
                "workspace_id": "ws_SOMEONE_ELSE",
                "user_id": OWNER["user_id"],
            },
        },
    }).encode()
    r = client.post("/api/webhook/paddle", data=body, headers=_sign(body))
    assert r.status_code == 200  # accepted but must NOT provision the wrong ws
    ws = _run(db.workspaces.find_one({"workspace_id": WS_ID}))
    assert ws["plan"] == "free", "cross-workspace nonce must not provision"
    assert _run(db.workspaces.find_one({"workspace_id": "ws_SOMEONE_ELSE"})) is None
    _run(db.paddle_events.delete_one({"_id": eid}))


def test_webhook_subscription_canceled_downgrades(owner_client):
    client, db = owner_client
    sub_id = "sub_cancel_test"
    _run(db.workspaces.update_one(
        {"workspace_id": WS_ID},
        {"$set": {"plan": "starter", "paddle_subscription_id": sub_id, "subscription_status": "active"}},
    ))
    eid = f"evt_{uuid.uuid4().hex[:10]}"
    _run(db.paddle_events.delete_one({"_id": eid}))
    body = json.dumps({
        "event_id": eid, "event_type": "subscription.canceled", "occurred_at": "2026-08-30T00:00:00Z",
        "data": {"id": sub_id},
    }).encode()
    r = client.post("/api/webhook/paddle", data=body, headers=_sign(body))
    assert r.status_code == 200
    ws = _run(db.workspaces.find_one({"workspace_id": WS_ID}))
    assert ws["plan"] == "free"
    assert ws.get("subscription_status") == "canceled"
    _run(db.paddle_events.delete_one({"_id": eid}))
    _run(db.workspaces.update_one(
        {"workspace_id": WS_ID},
        {"$set": {"plan": "free"}, "$unset": {"paddle_subscription_id": ""}},
    ))


def test_webhook_past_due_sets_status(owner_client):
    client, db = owner_client
    sub_id = "sub_pastdue_test"
    _run(db.workspaces.update_one(
        {"workspace_id": WS_ID},
        {"$set": {"plan": "starter", "paddle_subscription_id": sub_id, "subscription_status": "active"}},
    ))
    eid = f"evt_{uuid.uuid4().hex[:10]}"
    body = json.dumps({
        "event_id": eid, "event_type": "subscription.past_due", "occurred_at": "2026-08-30T00:00:00Z",
        "data": {"id": sub_id},
    }).encode()
    r = client.post("/api/webhook/paddle", data=body, headers=_sign(body))
    assert r.status_code == 200
    ws = _run(db.workspaces.find_one({"workspace_id": WS_ID}))
    assert ws.get("subscription_status") == "past_due"
    _run(db.paddle_events.delete_one({"_id": eid}))
    _run(db.workspaces.update_one(
        {"workspace_id": WS_ID},
        {
            "$set": {"plan": "free", "subscription_status": "active"},
            "$unset": {"paddle_subscription_id": ""},
        },
    ))


def test_portal_requires_billing_manage(member_client):
    client, _db = member_client
    r = client.post("/api/payments/paddle/portal")
    assert r.status_code == 403


def test_portal_requires_customer(owner_client):
    client, db = owner_client
    _run(db.workspaces.update_one({"workspace_id": WS_ID}, {"$unset": {"paddle_customer_id": ""}}))
    r = client.post("/api/payments/paddle/portal")
    assert r.status_code == 400
