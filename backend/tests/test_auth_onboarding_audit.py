"""Sign-up to first-company flow: invite-code rotation, company-name cap, double-submit guard.

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


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _Req:
    headers = {}
    client = None


@pytest.fixture
def fake_db(monkeypatch):
    d = AsyncMongoMockClient()["auth_onboarding_audit"]
    monkeypatch.setattr(server, "db", d)

    async def _no_limit(_ip):
        return None

    monkeypatch.setattr(server, "_check_join_rate_limit", _no_limit)
    return d


async def _user(db, uid, email):
    doc = {
        "user_id": uid, "email": email, "name": uid, "age_confirmed": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(doc)
    return doc


async def _workspace(db):
    owner = await _user(db, "user_owner", "owner@acme.test")
    ws = build_workspace("ws_one", "Acme", "user_owner", empty=True)
    await db.workspaces.insert_one(ws)
    await db.memberships.insert_one({
        "membership_id": "mem_owner", "workspace_id": "ws_one", "user_id": "user_owner",
        "email": "owner@acme.test", "role": "owner", "pack": "owner", "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return owner, ws


def test_rotated_code_replaces_the_old_one(fake_db):
    async def go():
        _owner, ws = await _workspace(fake_db)
        old = ws["join_code"]
        principal = {"workspace_id": "ws_one", "user_id": "user_owner"}
        ex = await _user(fake_db, "user_ex", "ex@acme.test")

        joined = await server.join_workspace(server.JoinInput(code=old), _Req(), ex)
        assert joined["ok"] is True

        # The person is removed, but the code is unchanged, so the old code still works.
        await fake_db.memberships.delete_one({"user_id": "user_ex"})

        rotated = await server.rotate_join_code(principal)
        assert rotated["join_code"] != old
        assert (await server.get_join_code(principal))["join_code"] == rotated["join_code"]

        with pytest.raises(HTTPException) as err:
            await server.join_workspace(server.JoinInput(code=old), _Req(), ex)
        assert err.value.status_code == 404

        again = await server.join_workspace(server.JoinInput(code=rotated["join_code"]), _Req(), ex)
        assert again["ok"] is True

    run(go())


def test_company_name_is_capped_like_a_rename(fake_db):
    async def go():
        user = await _user(fake_db, "user_new", "new@fresh.test")
        with pytest.raises(HTTPException) as err:
            await server.create_workspace(server.CreateWsInput(name="x" * 121), user)
        assert err.value.status_code == 400
        assert await fake_db.workspaces.count_documents({}) == 0

        ok = await server.create_workspace(server.CreateWsInput(name="x" * 120), user)
        assert ok["ok"] is True

    run(go())


def test_double_submit_creates_one_company(fake_db):
    async def go():
        user = await _user(fake_db, "user_new", "new@fresh.test")
        first, second = await asyncio.gather(
            server.create_workspace(server.CreateWsInput(name="Dup Co"), user),
            server.create_workspace(server.CreateWsInput(name="Dup Co"), user),
        )
        assert first["workspace_id"] == second["workspace_id"]
        assert await fake_db.workspaces.count_documents({"name": "Dup Co"}) == 1
        assert await fake_db.memberships.count_documents({"user_id": "user_new", "role": "owner"}) == 1

    run(go())


def test_different_names_still_create_separate_companies(fake_db):
    async def go():
        user = await _user(fake_db, "user_new", "new@fresh.test")
        a = await server.create_workspace(server.CreateWsInput(name="Alpha"), user)
        b = await server.create_workspace(server.CreateWsInput(name="Beta"), user)
        assert a["workspace_id"] != b["workspace_id"]

    run(go())


def test_failed_create_does_not_block_an_immediate_retry(fake_db, monkeypatch):
    async def go():
        user = await _user(fake_db, "user_new", "new@fresh.test")
        calls = {"n": 0}

        class _FlakyCollection:
            def __init__(self, inner):
                self._inner = inner

            def __getattr__(self, name):
                return getattr(self._inner, name)

            async def insert_one(self, doc, *a, **k):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise RuntimeError("database hiccup")
                return await self._inner.insert_one(doc, *a, **k)

        class _FlakyDb:
            def __getattr__(self, name):
                col = getattr(fake_db, name)
                return _FlakyCollection(col) if name == "workspaces" else col

        monkeypatch.setattr(server, "db", _FlakyDb())
        with pytest.raises(RuntimeError):
            await server.create_workspace(server.CreateWsInput(name="Retry Co"), user)
        ok = await server.create_workspace(server.CreateWsInput(name="Retry Co"), user)
        assert ok["ok"] is True
        assert await fake_db.workspaces.count_documents({"name": "Retry Co"}) == 1

    run(go())
