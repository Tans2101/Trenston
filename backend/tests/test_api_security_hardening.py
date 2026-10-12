"""Hardening for the public API, OAuth connections and activity privacy."""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_api_security_hardening")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import api_keys  # noqa: E402
import oauth_server as oauth  # noqa: E402
import server  # noqa: E402
from tests.mongo_mocks import FakeCollection  # noqa: E402

CLAUDE_CB = "https://claude.ai/api/mcp/auth_callback"
VERIFIER = "v" * 64


def run(coro):
    return asyncio.run(coro)


class AutoDB:
    """Every attribute is a FakeCollection, created on first use."""

    def __init__(self):
        self._c = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._c.setdefault(name, FakeCollection())

    def __getitem__(self, name):
        return getattr(self, name)


def seed_connection(db, user="u1", ws="ws1"):
    db.memberships.docs.append({"user_id": user, "workspace_id": ws, "role": "member", "status": "active", "membership_id": f"m_{user}"})
    raw_key, key_view = run(api_keys.create_key(db, user_id=user, workspace_id=ws, name="k"))
    client = run(oauth.register_client(db, {"client_name": "Claude", "redirect_uris": [CLAUDE_CB]}))
    req = run(oauth.validate_authorize_request(db, {
        "client_id": client["client_id"], "redirect_uri": CLAUDE_CB, "response_type": "code",
        "code_challenge": oauth.pkce_challenge(VERIFIER), "code_challenge_method": "S256",
    }, allowed_resources=[]))
    code = run(oauth.create_code(db, req, user_id=user, workspace_id=ws))
    tok = run(oauth.exchange_code(db, {"code": code, "client_id": client["client_id"], "redirect_uri": CLAUDE_CB, "code_verifier": VERIFIER}))
    return raw_key, client, tok


# ---------------------------------------------------------------- credentials die with the person or workspace

def test_credentials_are_deleted_with_the_workspace_and_never_exported():
    assert set(server._WORKSPACE_CREDENTIAL_COLLECTIONS) == {"api_keys", "oauth_codes", "oauth_grants"}
    assert not set(server._WORKSPACE_CREDENTIAL_COLLECTIONS) & set(server._WORKSPACE_COLLECTIONS)
    db = AutoDB()
    seed_connection(db)
    with patch.object(server, "db", db):
        run(server._delete_workspace_data("ws1"))
    for coll in server._WORKSPACE_CREDENTIAL_COLLECTIONS:
        assert db[coll].docs == [], coll


def test_account_deletion_removes_keys_and_connections():
    db = AutoDB()
    seed_connection(db)
    db.users.docs.append({"user_id": "u1", "email": "a@x.com"})
    with patch.object(server, "db", db):
        run(server.delete_account(user={"user_id": "u1"}))
    assert db.api_keys.docs == [] and db.oauth_grants.docs == []


def test_removing_a_member_revokes_their_keys_so_reinviting_does_not_revive_them():
    db = AutoDB()
    raw_key, client, tok = seed_connection(db)
    principal = {"user_id": "u_owner", "workspace_id": "ws1", "pack": "owner", "role": "owner"}
    with patch.object(server, "db", db), \
            patch.object(server, "_release_seat_reservation", AsyncMock()), \
            patch.object(server, "unlink_person_membership", AsyncMock()), \
            patch.object(server, "invalidate_workspace_list_cache", lambda *a, **k: None):
        run(server.remove_member("m_u1", principal=principal))
    assert run(api_keys.resolve(db, raw_key)) is None
    assert run(api_keys.resolve(db, tok["access_token"])) is None
    # Re-invited later: the old credentials stay dead.
    db.memberships.docs.append({"user_id": "u1", "workspace_id": "ws1", "role": "member", "status": "active"})
    assert run(api_keys.resolve(db, raw_key)) is None
    with pytest.raises(oauth.OAuthError):
        run(oauth.refresh_tokens(db, {"refresh_token": tok["refresh_token"], "client_id": client["client_id"]}))


def test_refresh_refused_and_connection_ended_when_member_left():
    db = AutoDB()
    _, client, tok = seed_connection(db)
    db.memberships.docs.clear()
    with pytest.raises(oauth.OAuthError) as e:
        run(oauth.refresh_tokens(db, {"refresh_token": tok["refresh_token"], "client_id": client["client_id"]}))
    assert e.value.error == "invalid_grant"
    assert db.oauth_grants.docs[0]["revoked_at"]


def test_spent_tokens_and_codes_carry_ttl_expiry():
    db = AutoDB()
    seed_connection(db)
    oauth_tokens = [d for d in db.api_keys.docs if d.get("kind") == "oauth"]
    assert oauth_tokens and all(isinstance(d["expire_at"], datetime) for d in oauth_tokens)
    personal = [d for d in db.api_keys.docs if d.get("kind") == "personal"]
    assert personal and all("expire_at" not in d for d in personal)
    assert all(isinstance(d["expire_at"], datetime) for d in db.oauth_codes.docs)


# ---------------------------------------------------------------- consent screen honesty

def test_only_claudes_real_callback_is_marked_verified():
    db = AutoDB()
    good = run(oauth.register_client(db, {"client_name": "Claude", "redirect_uris": [CLAUDE_CB]}))
    fake = run(oauth.register_client(db, {"client_name": "Claude", "redirect_uris": ["https://evil.example/cb"]}))
    base = {"response_type": "code", "code_challenge": oauth.pkce_challenge(VERIFIER), "code_challenge_method": "S256"}
    ok = run(oauth.validate_authorize_request(db, {**base, "client_id": good["client_id"], "redirect_uri": CLAUDE_CB}, allowed_resources=[]))
    spoof = run(oauth.validate_authorize_request(db, {**base, "client_id": fake["client_id"], "redirect_uri": "https://evil.example/cb"}, allowed_resources=[]))
    assert ok["verified_as"] == "Claude"
    assert spoof["verified_as"] is None and spoof["redirect_host"] == "evil.example"


# ---------------------------------------------------------------- financial activity stays behind the Financials gate

def test_activity_filter_hides_finance_rows_without_access():
    assert server._activity_filter("ws1", financials_visible=True) == {"workspace_id": "ws1"}
    hidden = server._activity_filter("ws1", financials_visible=False)
    assert hidden["module"] == {"$nin": ["financials"]}


@pytest.fixture
def activity_db():
    db = AutoDB()
    db.workspaces.docs.append({"workspace_id": "ws1", "name": "Acme", "plan": "growth"})
    db.memberships.docs += [
        {"user_id": "u_owner", "workspace_id": "ws1", "role": "owner", "status": "active"},
        {"user_id": "u_mem", "workspace_id": "ws1", "role": "member", "pack": "member", "status": "active"},
    ]
    now = datetime.now(timezone.utc).isoformat()
    db.activities.docs += [
        {"activity_id": "a1", "workspace_id": "ws1", "module": "financials", "summary": "Logged revenue · Client $300 (2026-10)", "created_at": now},
        {"activity_id": "a2", "workspace_id": "ws1", "module": "tasks", "summary": "Created task · Ship v2", "created_at": now},
    ]
    return db


@pytest.mark.parametrize("who,expect_finance", [("u_mem", False), ("u_owner", True)])
def test_activity_feed_respects_financials_access(activity_db, who, expect_finance):
    pack = "member" if who == "u_mem" else "owner"

    async def principal():
        return {"user_id": who, "name": "N", "email": "e@x.com", "workspace_id": "ws1", "pack": pack, "role": pack}

    server.app.dependency_overrides[server.get_principal] = principal
    try:
        with patch.object(server, "db", activity_db):
            items = TestClient(server.app).get("/api/activities").json()["items"]
    finally:
        server.app.dependency_overrides.clear()
    summaries = " ".join(i["summary"] for i in items)
    assert ("$300" in summaries) is expect_finance
    assert "Ship v2" in summaries
