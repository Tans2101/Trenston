"""Adding and removing people, and deleting accounts or companies, leave nothing behind.

Runs offline against mongomock; no live server or database is needed.
"""
import asyncio
import os

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_db")
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

import server
from seed_data import build_workspace

WS = "ws_clean"


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _Req:
    headers = {}
    client = None


@pytest.fixture
def fake_db(monkeypatch):
    d = AsyncMongoMockClient()["membership_cleanup"]
    monkeypatch.setattr(server, "db", d)

    async def _no_limit(_ip):
        return None

    monkeypatch.setattr(server, "_check_join_rate_limit", _no_limit)
    # Plan seat limits only apply when billing is enforced; these tests need them.
    monkeypatch.setattr(server, "BILLING_ENFORCED", True)
    return d


OWNER = {"workspace_id": WS, "user_id": "u_owner", "pack": "owner", "role": "owner",
         "email": "owner@example.com", "name": "Owner"}


async def _user(db, uid, email=None):
    doc = {"user_id": uid, "email": email or f"{uid}@example.com", "name": uid, "age_confirmed": True,
           "created_at": datetime.now(timezone.utc).isoformat()}
    await db.users.insert_one(doc)
    return doc


async def _company(db):
    await _user(db, "u_owner", "owner@example.com")
    ws = build_workspace(WS, "Clean Co", "u_owner", empty=True)
    await db.workspaces.insert_one(ws)
    await db.memberships.insert_one({
        "membership_id": "m_owner", "workspace_id": WS, "user_id": "u_owner",
        "email": "owner@example.com", "role": "owner", "pack": "owner", "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    await db.departments.insert_one(
        {"department_id": "dep_hr", "workspace_id": WS, "type": "hr", "name": "HR", "enabled": True})
    return ws


async def _join(db, ws, uid):
    user = await _user(db, uid)
    await server.join_workspace(server.JoinInput(code=ws["join_code"]), _Req(), user)
    return user


async def _seat_counter(db):
    return (await db.seat_usage.find_one({"workspace_id": WS}) or {}).get("count")


def test_deleting_an_account_frees_the_seat(fake_db):
    async def go():
        ws = await _company(fake_db)
        a = await _join(fake_db, ws, "u_a")
        await _join(fake_db, ws, "u_b")
        assert await _seat_counter(fake_db) == 3

        await server.delete_account(a)

        assert await fake_db.memberships.count_documents({"workspace_id": WS}) == 2
        assert await _seat_counter(fake_db) == 2
        # The owner can add someone in the freed seat instead of being told to upgrade.
        out = await server.invite_member(server.InviteInput(email="new@example.com"), _Req(), OWNER)
        assert out["ok"] is True

    run(go())


def test_removing_a_person_clears_what_tied_them_to_the_company(fake_db):
    async def go():
        ws = await _company(fake_db)
        c = await _join(fake_db, ws, "u_c")
        await fake_db.department_members.insert_one({"department_id": "dep_hr", "user_id": "u_c", "role": "member"})
        await fake_db.user_google_tokens.insert_one(
            {"workspace_id": WS, "user_id": "u_c", "tokens": {"refresh_token": "r"}})
        m = await fake_db.memberships.find_one({"user_id": "u_c"})

        await server.remove_member(m["membership_id"], OWNER)

        assert await fake_db.department_members.count_documents({"user_id": "u_c"}) == 0
        assert await fake_db.user_google_tokens.count_documents({"user_id": "u_c"}) == 0
        assert await _seat_counter(fake_db) == 1
        # Adding them back starts clean: no department lane quietly returns.
        await server.join_workspace(server.JoinInput(code=ws["join_code"]), _Req(), c)
        assert await fake_db.department_members.count_documents({"user_id": "u_c"}) == 0

    run(go())


def test_removing_a_pending_invite_frees_its_seat(fake_db):
    async def go():
        await _company(fake_db)
        await server.invite_member(server.InviteInput(email="pending@example.com"), _Req(), OWNER)
        assert await _seat_counter(fake_db) == 2  # the owner plus the pending invite
        m = await fake_db.memberships.find_one({"email": "pending@example.com"})
        await server.remove_member(m["membership_id"], OWNER)
        assert await _seat_counter(fake_db) == 1

    run(go())


def test_account_deletion_clears_roster_link_lanes_and_referrals(fake_db):
    async def go():
        ws = await _company(fake_db)
        c = await _join(fake_db, ws, "u_c")
        await fake_db.department_members.insert_one({"department_id": "dep_hr", "user_id": "u_c", "role": "member"})
        await fake_db.referrals.insert_one(
            {"referrer_user_id": "u_c", "referred_email": "friend@example.com", "status": "sent"})
        await fake_db.referrals.insert_one(
            {"referrer_user_id": "u_owner", "referred_user_id": "u_c",
             "referred_email": "u_c@example.com", "status": "signed_up"})
        mem = await fake_db.memberships.find_one({"user_id": "u_c"})

        await server.delete_account(c)

        roster = (await fake_db.workspaces.find_one({"workspace_id": WS}))["people"]["people"]
        row = next(p for p in roster if p.get("name") == "u_c")
        assert "membership_id" not in row and "user_id" not in row
        assert row["name"] == "u_c"  # the company keeps its roster record
        assert await fake_db.department_members.count_documents({"user_id": "u_c"}) == 0
        assert await fake_db.referrals.count_documents({"referrer_user_id": "u_c"}) == 0
        kept = await fake_db.referrals.find_one({"referrer_user_id": "u_owner"})
        assert kept["referred_email"] == "" and kept["referred_user_id"] is None
        assert await fake_db.memberships.count_documents({"membership_id": mem["membership_id"]}) == 0

    run(go())


def test_deleting_the_company_leaves_nobody_pointing_at_it(fake_db):
    async def go():
        ws = await _company(fake_db)
        await _join(fake_db, ws, "u_a")
        await fake_db.users.update_many({}, {"$set": {"active_workspace_id": WS}})

        await server._delete_workspace_data(WS)

        assert await fake_db.workspaces.count_documents({"workspace_id": WS}) == 0
        assert await fake_db.users.count_documents({"active_workspace_id": WS}) == 0

    run(go())


def test_a_clerk_side_delete_frees_the_seat_and_does_not_block_reinviting(fake_db):
    async def go():
        ws = await _company(fake_db)
        await _join(fake_db, ws, "u_a")
        await fake_db.users.update_one({"user_id": "u_a"}, {"$set": {"clerk_id": "clerk_a"}})
        await fake_db.department_members.insert_one({"department_id": "dep_hr", "user_id": "u_a", "role": "member"})
        assert await _seat_counter(fake_db) == 2

        await server._revoke_local_user_for_clerk_delete("clerk_a")

        assert await _seat_counter(fake_db) == 1
        assert await fake_db.department_members.count_documents({"user_id": "u_a"}) == 0
        # The revoked row still carries the old email; inviting that address again must work.
        out = await server.invite_member(server.InviteInput(email="u_a@example.com"), _Req(), OWNER)
        assert out["ok"] is True

    run(go())


def test_a_live_member_still_blocks_a_duplicate_invite(fake_db):
    async def go():
        ws = await _company(fake_db)
        await _join(fake_db, ws, "u_a")
        with pytest.raises(HTTPException) as err:
            await server.invite_member(server.InviteInput(email="u_a@example.com"), _Req(), OWNER)
        assert err.value.status_code == 400

    run(go())


def test_a_failed_tidy_up_never_blocks_account_deletion(fake_db, monkeypatch):
    async def go():
        ws = await _company(fake_db)
        a = await _join(fake_db, ws, "u_a")

        async def boom(*_a, **_k):
            raise RuntimeError("roster unavailable")

        monkeypatch.setattr(server, "unlink_person_membership", boom)
        out = await server.delete_account(a)

        assert out["ok"] is True
        tomb = await fake_db.users.find_one({"user_id": "u_a"})
        assert tomb and tomb.get("deleted_at")
        assert await fake_db.memberships.count_documents({"user_id": "u_a"}) == 0
        assert await _seat_counter(fake_db) == 1  # the seat is still freed

    run(go())
