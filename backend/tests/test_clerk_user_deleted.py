"""Clerk user.deleted webhook + local auth rejection for deleted accounts."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_clerk_user_deleted")
os.environ["CLERK_SECRET_KEY"] = "sk_live_test"
os.environ["CLERK_JWKS_URL"] = "https://clerk.trenston.com/.well-known/jwks.json"
os.environ["FRONTEND_URL"] = "https://www.trenston.com"
os.environ["APP_URL"] = "https://www.trenston.com"

# Deterministic whsec for signature tests (32 zero bytes → known base64).
_WEBHOOK_SECRET_BYTES = b"\x00" * 32
_WEBHOOK_SECRET = "whsec_" + base64.b64encode(_WEBHOOK_SECRET_BYTES).decode()
os.environ["CLERK_WEBHOOK_SIGNING_SECRET"] = _WEBHOOK_SECRET

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import clerk_auth  # noqa: E402
import server  # noqa: E402

clerk_auth.CLERK_SECRET_KEY = os.environ["CLERK_SECRET_KEY"]
clerk_auth.CLERK_JWKS_URL = os.environ["CLERK_JWKS_URL"]
clerk_auth.CLERK_WEBHOOK_SECRET = _WEBHOOK_SECRET


def _sign(body: bytes, *, msg_id: str = "msg_test_1", ts: int | None = None) -> dict[str, str]:
    ts = int(time.time()) if ts is None else ts
    body_text = body.decode("utf-8")
    signed = f"{msg_id}.{ts}.{body_text}".encode("utf-8")
    sig = base64.b64encode(
        hmac.new(_WEBHOOK_SECRET_BYTES, signed, hashlib.sha256).digest()
    ).decode()
    return {
        "svix-id": msg_id,
        "svix-timestamp": str(ts),
        "svix-signature": f"v1,{sig}",
    }


def test_verify_clerk_webhook_accepts_valid_signature():
    body = json.dumps({"type": "user.deleted", "data": {"id": "user_abc"}}).encode()
    headers = _sign(body)
    event = clerk_auth.verify_clerk_webhook(body, headers)
    assert event["type"] == "user.deleted"
    assert event["data"]["id"] == "user_abc"


def test_verify_clerk_webhook_rejects_bad_signature():
    body = json.dumps({"type": "user.deleted", "data": {"id": "user_abc"}}).encode()
    headers = _sign(body)
    headers["svix-signature"] = "v1,AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    with pytest.raises(ValueError, match="Invalid Svix signature"):
        clerk_auth.verify_clerk_webhook(body, headers)


def test_verify_clerk_webhook_rejects_stale_timestamp():
    body = json.dumps({"type": "user.deleted", "data": {"id": "user_abc"}}).encode()
    headers = _sign(body, ts=int(time.time()) - 600)
    with pytest.raises(ValueError, match="tolerance"):
        clerk_auth.verify_clerk_webhook(body, headers)


class _FakeUsers:
    def __init__(self, docs):
        self.docs = {d["user_id"]: dict(d) for d in docs}
        self.inserted = []

    def _match(self, doc, query) -> bool:
        for k, v in query.items():
            if isinstance(v, dict) and "$type" in v:
                if v["$type"] == "string" and not isinstance(doc.get(k), str):
                    return False
                continue
            if isinstance(v, dict) and "$regex" in v:
                import re as _re
                if not _re.search(v["$regex"], str(doc.get(k) or ""), flags=_re.I if "i" in (v.get("$options") or "") else 0):
                    return False
                continue
            if doc.get(k) != v:
                return False
        return True

    async def find_one(self, query, projection=None):
        for doc in self.docs.values():
            if self._match(doc, query):
                return {k: v for k, v in doc.items() if k != "_id"}
        return None

    async def update_one(self, query, update):
        doc = await self.find_one(query)
        if not doc:
            return MagicMock(modified_count=0)
        uid = doc["user_id"]
        if "$set" in update:
            self.docs[uid].update(update["$set"])
        if "$unset" in update:
            for key in update["$unset"]:
                self.docs[uid].pop(key, None)
        return MagicMock(modified_count=1)

    async def insert_one(self, doc):
        from pymongo.errors import DuplicateKeyError

        email = doc.get("email")
        clerk_id = doc.get("clerk_id")
        for existing in self.docs.values():
            if email and existing.get("email") == email:
                raise DuplicateKeyError("E11000 duplicate key error collection: users index: email_1")
            if clerk_id and existing.get("clerk_id") == clerk_id:
                raise DuplicateKeyError("E11000 duplicate key error collection: users index: clerk_id_1")
        self.docs[doc["user_id"]] = dict(doc)
        self.inserted.append(doc)
        return MagicMock(inserted_id=doc["user_id"])


class _FakeSessions:
    def __init__(self):
        self.deleted = []

    async def delete_many(self, query):
        self.deleted.append(query)
        return MagicMock(deleted_count=1)


class _FakeMemberships:
    def __init__(self):
        self.updates = []

    def find(self, *_args, **_kwargs):
        return MagicMock(to_list=AsyncMock(return_value=[]))

    async def update_many(self, query, update):
        self.updates.append((query, update))
        return MagicMock(modified_count=1)


def test_revoke_local_user_for_clerk_delete():
    users = _FakeUsers([{
        "user_id": "u1",
        "email": "a@example.com",
        "clerk_id": "user_abc",
        "active_workspace_id": "ws1",
    }])
    sessions = _FakeSessions()
    memberships = _FakeMemberships()

    with patch.object(server, "db", MagicMock(users=users, user_sessions=sessions, memberships=memberships)):
        result = asyncio.run(server._revoke_local_user_for_clerk_delete("user_abc"))

    assert result["ok"] is True
    assert result["reason"] == "revoked"
    assert users.docs["u1"].get("deleted_at")
    assert "clerk_id" not in users.docs["u1"]
    assert users.docs["u1"]["clerk_deleted_id"] == "user_abc"
    assert sessions.deleted == [{"user_id": "u1"}]
    assert memberships.updates


def test_upsert_clerk_user_reclaims_soft_deleted_email():
    """Shared sign-up path: tombstone still holding email must not block create."""
    users = _FakeUsers([{
        "user_id": "u_old",
        "email": "founder@example.com",
        "clerk_deleted_id": "user_old",
        "deleted_at": "2026-01-01T00:00:00+00:00",
    }])

    with patch.object(server, "db", MagicMock(users=users)), \
         patch.object(server, "_bootstrap", AsyncMock()):
        user = asyncio.run(server._upsert_clerk_user(
            email="founder@example.com",
            name="Founder",
            picture=None,
            clerk_id="user_new",
        ))

    assert user["email"] == "founder@example.com"
    assert user["clerk_id"] == "user_new"
    assert users.docs["u_old"]["email"].startswith("deleted+u_old")
    assert users.inserted and users.inserted[0]["clerk_id"] == "user_new"


def test_upsert_clerk_user_duplicate_active_email_returns_409():
    users = _FakeUsers([{
        "user_id": "u_live",
        "email": "taken@example.com",
        "clerk_id": "user_other",
    }])

    with patch.object(server, "db", MagicMock(users=users)), \
         patch.object(server, "_bootstrap", AsyncMock()), \
         patch.object(server, "_find_user_by_identity", AsyncMock(side_effect=[None, None, None])):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(server._upsert_clerk_user(
                email="taken@example.com",
                name="X",
                picture=None,
                clerk_id="user_new",
            ))
    assert exc.value.status_code == 409
    assert "could not be created" in exc.value.detail.lower()


def test_user_from_clerk_jwt_rejects_deleted_account():
    users = _FakeUsers([{
        "user_id": "u1",
        "email": "deleted+u1@invalid.local",
        "clerk_id": "user_abc",
        "deleted_at": "2026-01-01T00:00:00+00:00",
    }])
    sessions = _FakeSessions()

    async def fake_decode(_token):
        return {"sub": "user_abc", "sid": "sess_1"}

    with patch.object(server, "db", MagicMock(users=users, user_sessions=sessions)), \
         patch.object(server.clerk_auth, "clerk_configured", return_value=True), \
         patch.object(server.clerk_auth, "decode_clerk_jwt", side_effect=fake_decode):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(server._user_from_clerk_jwt("a.b.c"))
    assert exc.value.status_code == 401
    assert "Account deleted" in exc.value.detail
    assert sessions.deleted == [{"user_id": "u1"}]


def test_user_from_clerk_jwt_rejects_tombstone_without_clerk_id():
    users = _FakeUsers([{
        "user_id": "u1",
        "email": "deleted+u1@invalid.local",
        "clerk_deleted_id": "user_abc",
        "deleted_at": "2026-01-01T00:00:00+00:00",
    }])
    sessions = _FakeSessions()

    async def fake_decode(_token):
        return {"sub": "user_abc", "sid": "sess_1"}

    with patch.object(server, "db", MagicMock(users=users, user_sessions=sessions)), \
         patch.object(server.clerk_auth, "clerk_configured", return_value=True), \
         patch.object(server.clerk_auth, "decode_clerk_jwt", side_effect=fake_decode):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(server._user_from_clerk_jwt("a.b.c"))
    assert exc.value.status_code == 401
    assert "Account deleted" in exc.value.detail


def test_user_from_request_does_not_cookie_fallback_on_clerk_401():
    """Regression: deleted Clerk JWT must not fall back to Trenston cookie."""

    class Req:
        headers = {"Authorization": "Bearer aaa.bbb.ccc"}
        cookies = {"session_token": "still-valid-cookie"}

    with patch.object(
        server,
        "_user_from_clerk_jwt",
        AsyncMock(side_effect=HTTPException(status_code=401, detail="Account deleted. Sign in again.")),
    ), patch.object(server.db, "user_sessions", MagicMock(find_one=AsyncMock())) as sessions:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(server._user_from_request(Req()))
    assert exc.value.status_code == 401
    assert "Account deleted" in exc.value.detail
    sessions.find_one.assert_not_called()


def test_cookie_auth_revokes_when_clerk_user_gone():
    """Cookie-only path must not survive a Clerk Dashboard delete (webhook lag)."""
    from datetime import datetime, timedelta, timezone

    users = _FakeUsers([{
        "user_id": "u1",
        "email": "a@example.com",
        "clerk_id": "user_abc",
    }])
    sessions = _FakeSessions()
    memberships = _FakeMemberships()
    expires = datetime.now(timezone.utc) + timedelta(days=1)

    class Req:
        headers = {}
        cookies = {"session_token": "cookie-1"}

    async def find_session(query, projection=None):
        if query.get("session_token") == "cookie-1":
            return {"user_id": "u1", "session_token": "cookie-1", "expires_at": expires}
        return None

    server._CLERK_ALIVE_CACHE.clear()
    with patch.object(
        server,
        "db",
        MagicMock(
            users=users,
            user_sessions=MagicMock(find_one=find_session, delete_many=sessions.delete_many),
            memberships=memberships,
        ),
    ), patch.object(server.clerk_auth, "clerk_configured", return_value=True), \
       patch.object(server.clerk_auth, "clerk_user_exists", AsyncMock(return_value=False)):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(server._user_from_request(Req()))
    assert exc.value.status_code == 401
    assert "Account deleted" in exc.value.detail
    assert users.docs["u1"].get("deleted_at")
    assert sessions.deleted == [{"user_id": "u1"}]


def test_cookie_auth_fails_open_when_clerk_probe_unknown():
    from datetime import datetime, timedelta, timezone

    users = _FakeUsers([{
        "user_id": "u1",
        "email": "a@example.com",
        "clerk_id": "user_abc",
    }])
    expires = datetime.now(timezone.utc) + timedelta(days=1)

    class Req:
        headers = {}
        cookies = {"session_token": "cookie-1"}

    async def find_session(query, projection=None):
        return {"user_id": "u1", "session_token": "cookie-1", "expires_at": expires}

    server._CLERK_ALIVE_CACHE.clear()
    with patch.object(
        server,
        "db",
        MagicMock(users=users, user_sessions=MagicMock(find_one=find_session, delete_many=AsyncMock())),
    ), patch.object(server.clerk_auth, "clerk_configured", return_value=True), \
       patch.object(server.clerk_auth, "clerk_user_exists", AsyncMock(return_value=None)):
        out = asyncio.run(server._user_from_request(Req()))
    assert out["user_id"] == "u1"
    assert not users.docs["u1"].get("deleted_at")


@pytest.mark.asyncio
async def test_clerk_webhook_user_deleted_revokes(monkeypatch):
    body = json.dumps({
        "type": "user.deleted",
        "data": {"id": "user_abc", "deleted": True},
    }).encode()
    signed_headers = _sign(body)

    class Req:
        def __init__(self):
            self.headers = signed_headers

        async def body(self):
            return body

    revoke = AsyncMock(return_value={"ok": True, "reason": "revoked", "user_id": "u1"})
    events = MagicMock()
    events.insert_one = AsyncMock(return_value=None)
    events.delete_one = AsyncMock(return_value=None)

    monkeypatch.setattr(server.clerk_auth, "CLERK_WEBHOOK_SECRET", _WEBHOOK_SECRET)
    with patch.object(server, "db", MagicMock(clerk_events=events)), \
         patch.object(server, "_revoke_local_user_for_clerk_delete", revoke):
        out = await server.clerk_webhook(Req())
    assert out == {"received": True}
    revoke.assert_awaited_once_with("user_abc")


@pytest.mark.asyncio
async def test_delete_clerk_user_success(monkeypatch):
    class Resp:
        status_code = 200

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def delete(self, url, headers=None):
            assert url.endswith("/users/user_del_1")
            return Resp()

    monkeypatch.setattr(clerk_auth, "CLERK_SECRET_KEY", "sk_live_test")
    monkeypatch.setattr(clerk_auth.httpx, "AsyncClient", lambda **kw: Client())
    out = await clerk_auth.delete_clerk_user("user_del_1")
    assert out["ok"] is True
    assert out["clerk_id"] == "user_del_1"


@pytest.mark.asyncio
async def test_delete_account_calls_clerk_when_clerk_id(monkeypatch):
    user = {"user_id": "u9", "clerk_id": "user_del_9"}
    memberships = MagicMock()
    memberships.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))
    mock_db = MagicMock()
    mock_db.memberships = memberships
    mock_db.memberships.delete_many = AsyncMock()
    mock_db.user_sessions.delete_many = AsyncMock()
    mock_db.chat_messages.delete_many = AsyncMock()
    mock_db.updates.delete_many = AsyncMock()
    mock_db.private_notes.delete_many = AsyncMock()
    mock_db.user_google_tokens.delete_many = AsyncMock()
    mock_db.product_events.delete_many = AsyncMock()
    mock_db.activities.update_many = AsyncMock()
    mock_db.users.update_one = AsyncMock()
    mock_db.department_members.delete_many = AsyncMock()
    mock_db.referrals.delete_many = AsyncMock()
    mock_db.referrals.update_many = AsyncMock()
    # API keys / OAuth connections are deleted through db[collection].
    mock_db.__getitem__.return_value = MagicMock(delete_many=AsyncMock())
    clerk_delete = AsyncMock(return_value={"ok": True})
    with patch.object(server, "db", mock_db), \
         patch.object(clerk_auth, "delete_clerk_user", clerk_delete):
        out = await server.delete_account(user=user)
    assert out == {"ok": True, "clerk_deleted": True}
    clerk_delete.assert_awaited_once_with("user_del_9")
    mock_db.users.update_one.assert_awaited()
    set_fields = mock_db.users.update_one.await_args.args[1]["$set"]
    assert set_fields["clerk_deleted_id"] == "user_del_9"
    assert set_fields["email"].startswith("deleted+u9@")
    assert "deleted_at" in set_fields
