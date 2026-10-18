"""Phase 3 account lifecycle: tombstone delete, join/revoke, remove sessions, seats."""
import asyncio
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_account_lifecycle")

import server
from seed_data import build_workspace

WS = "ws_life"


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _Req:
    headers = {}
    client = None


@pytest.fixture
def fake_db(monkeypatch):
    d = AsyncMongoMockClient()["account_lifecycle"]
    monkeypatch.setattr(server, "db", d)

    async def _no_limit(_ip):
        return None

    monkeypatch.setattr(server, "_check_join_rate_limit", _no_limit)
    monkeypatch.setattr(server, "BILLING_ENFORCED", True)
    monkeypatch.setattr(server, "send_invite_email", AsyncMock(return_value={"sent": False}))
    return d


OWNER = {
    "workspace_id": WS, "user_id": "u_owner", "pack": "owner", "role": "owner",
    "email": "owner@example.com", "name": "Owner",
}


async def _user(db, uid, email=None, **extra):
    doc = {
        "user_id": uid,
        "email": email or f"{uid}@example.com",
        "name": uid,
        "age_confirmed": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    }
    await db.users.insert_one(doc)
    return doc


async def _company(db):
    await _user(db, "u_owner", "owner@example.com")
    ws = build_workspace(WS, "Life Co", "u_owner", empty=True)
    await db.workspaces.insert_one(ws)
    await db.memberships.insert_one({
        "membership_id": "m_owner", "workspace_id": WS, "user_id": "u_owner",
        "email": "owner@example.com", "role": "owner", "pack": "owner", "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return ws


def test_in_app_delete_tombstones_even_when_clerk_fails(fake_db, monkeypatch):
    """Hard-delete left a re-upsert hole when Clerk delete failed; tombstone closes it."""
    async def go():
        await _company(fake_db)
        user = await _user(fake_db, "u_victim", "victim@example.com", clerk_id="clerk_victim")
        await fake_db.memberships.insert_one({
            "membership_id": "m_victim", "workspace_id": WS, "user_id": "u_victim",
            "email": "victim@example.com", "role": "member", "pack": "member", "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        await fake_db.user_sessions.insert_one(
            {"session_token": "tok", "user_id": "u_victim", "expires_at": "2099-01-01T00:00:00+00:00"},
        )

        async def boom(_cid):
            raise RuntimeError("Clerk BAPI down")

        monkeypatch.setattr(server.clerk_auth, "delete_clerk_user", boom)
        out = await server.delete_account(user)
        assert out["ok"] is True
        assert out["clerk_deleted"] is False

        row = await fake_db.users.find_one({"user_id": "u_victim"})
        assert row["deleted_at"]
        assert row["clerk_deleted_id"] == "clerk_victim"
        assert "clerk_id" not in row
        assert row["email"].startswith("deleted+u_victim@")
        assert await fake_db.user_sessions.count_documents({"user_id": "u_victim"}) == 0

        # Same Clerk JWT must not recreate access.
        with pytest.raises(HTTPException) as err:
            await server._reject_if_deleted(row)
        assert err.value.status_code == 401

    run(go())


def test_join_reactivates_after_revoked_membership(fake_db):
    async def go():
        ws = await _company(fake_db)
        user = await _user(fake_db, "u_rejoin")
        await fake_db.memberships.insert_one({
            "membership_id": "m_rev", "workspace_id": WS, "user_id": "u_rejoin",
            "email": "u_rejoin@example.com", "role": "member", "pack": "member",
            "status": "revoked", "revoked_at": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        out = await server.join_workspace(server.JoinInput(code=ws["join_code"]), _Req(), user)
        assert out["ok"] is True
        mem = await fake_db.memberships.find_one({"user_id": "u_rejoin", "workspace_id": WS})
        assert mem["status"] == "active"
        assert mem["membership_id"] != "m_rev"
        refreshed = await fake_db.users.find_one({"user_id": "u_rejoin"})
        assert refreshed["active_workspace_id"] == WS

    run(go())


def test_list_members_hides_revoked_and_counts_seats(fake_db):
    async def go():
        await _company(fake_db)
        await fake_db.memberships.insert_one({
            "membership_id": "m_live", "workspace_id": WS, "user_id": "u_live",
            "email": "live@example.com", "role": "member", "pack": "member", "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        await fake_db.memberships.insert_one({
            "membership_id": "m_dead", "workspace_id": WS, "user_id": "u_dead",
            "email": "dead@example.com", "role": "member", "pack": "member", "status": "revoked",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        out = await server.list_members(OWNER)
        emails = {m["email"] for m in out["members"]}
        assert "live@example.com" in emails
        assert "dead@example.com" not in emails
        assert out["seats_used"] == 2  # owner + live

    run(go())


def test_remove_member_clears_active_workspace_and_sessions_when_last_company(fake_db):
    async def go():
        await _company(fake_db)
        await _user(fake_db, "u_gone", active_workspace_id=WS)
        await fake_db.memberships.insert_one({
            "membership_id": "m_gone", "workspace_id": WS, "user_id": "u_gone",
            "email": "gone@example.com", "role": "member", "pack": "member", "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        await fake_db.user_sessions.insert_one(
            {"session_token": "s1", "user_id": "u_gone", "expires_at": "2099-01-01T00:00:00+00:00"},
        )

        await server.remove_member("m_gone", OWNER)

        u = await fake_db.users.find_one({"user_id": "u_gone"})
        assert "active_workspace_id" not in u or not u.get("active_workspace_id")
        assert await fake_db.user_sessions.count_documents({"user_id": "u_gone"}) == 0

    run(go())


def test_remove_member_keeps_sessions_when_other_company_exists(fake_db):
    async def go():
        await _company(fake_db)
        await _user(fake_db, "u_multi", active_workspace_id=WS)
        await fake_db.workspaces.insert_one(
            build_workspace("ws_other", "Other Co", "u_multi", empty=True),
        )
        await fake_db.memberships.insert_one({
            "membership_id": "m_here", "workspace_id": WS, "user_id": "u_multi",
            "email": "multi@example.com", "role": "member", "pack": "member", "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        await fake_db.memberships.insert_one({
            "membership_id": "m_other", "workspace_id": "ws_other", "user_id": "u_multi",
            "email": "multi@example.com", "role": "member", "pack": "member", "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        await fake_db.user_sessions.insert_one(
            {"session_token": "s2", "user_id": "u_multi", "expires_at": "2099-01-01T00:00:00+00:00"},
        )

        await server.remove_member("m_here", OWNER)

        assert await fake_db.user_sessions.count_documents({"user_id": "u_multi"}) == 1
        u = await fake_db.users.find_one({"user_id": "u_multi"})
        assert "active_workspace_id" not in u or not u.get("active_workspace_id")

    run(go())


def test_workspace_delete_wipes_sessions_for_orphaned_members(fake_db, monkeypatch):
    async def go():
        await _company(fake_db)
        await _user(fake_db, "u_a", active_workspace_id=WS)
        await fake_db.memberships.insert_one({
            "membership_id": "m_a", "workspace_id": WS, "user_id": "u_a",
            "email": "a@example.com", "role": "member", "pack": "member", "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        await fake_db.user_sessions.insert_one(
            {"session_token": "sa", "user_id": "u_a", "expires_at": "2099-01-01T00:00:00+00:00"},
        )
        await fake_db.user_sessions.insert_one(
            {"session_token": "so", "user_id": "u_owner", "expires_at": "2099-01-01T00:00:00+00:00"},
        )
        monkeypatch.setattr(server.doc_storage, "r2_configured", lambda: True)

        await server._delete_workspace_data(WS)

        assert await fake_db.user_sessions.count_documents({"user_id": "u_a"}) == 0
        assert await fake_db.user_sessions.count_documents({"user_id": "u_owner"}) == 0

    run(go())


def test_invite_skips_tombstoned_user_row(fake_db):
    async def go():
        await _company(fake_db)
        await _user(
            fake_db, "u_tomb", "ghost@example.com",
            deleted_at=datetime.now(timezone.utc).isoformat(),
        )
        out = await server.invite_member(
            server.InviteInput(email="ghost@example.com"), _Req(), OWNER,
        )
        assert out["ok"] is True
        assert out["auto_joined"] is False
        mem = await fake_db.memberships.find_one({"email": "ghost@example.com"})
        assert mem["status"] == "invited"
        assert mem.get("user_id") is None

    run(go())
