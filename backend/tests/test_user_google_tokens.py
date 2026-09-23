"""Per-user Google Calendar/Gmail token storage."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_user_google_tokens")
if not os.environ.get("INTEGRATION_ENCRYPTION_KEY"):
    from cryptography.fernet import Fernet
    os.environ["INTEGRATION_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

import credential_crypto as cred_crypto  # noqa: E402
import server  # noqa: E402


@pytest.mark.asyncio
async def test_store_and_load_user_google_tokens_are_sealed():
    coll = MagicMock()
    coll.update_one = AsyncMock()
    coll.find_one = AsyncMock(return_value=None)
    coll.delete_one = AsyncMock()
    fake_db = MagicMock()
    fake_db.user_google_tokens = coll

    tokens = {
        "access_token": "ya29.a",
        "refresh_token": "1//r",
        "scope": "https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/gmail.readonly",
    }
    with patch.object(server, "db", fake_db):
        await server._store_user_google_tokens("ws1", "u1", tokens)
        sealed_arg = coll.update_one.await_args.args[1]["$set"]["google_tokens"]
        assert cred_crypto.is_sealed_credentials(sealed_arg)
        coll.find_one = AsyncMock(return_value={
            "workspace_id": "ws1",
            "user_id": "u1",
            "google_tokens": sealed_arg,
        })
        loaded = await server._user_google_tokens("ws1", "u1")
        assert loaded["access_token"] == "ya29.a"
        assert await server._user_google_tokens_present("ws1", "u1") is True

        await server._store_user_google_tokens("ws1", "u1", None)
        coll.delete_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_two_users_keep_separate_google_tokens():
    store: dict[tuple[str, str], dict] = {}

    async def update_one(filt, update, upsert=False):
        key = (filt["workspace_id"], filt["user_id"])
        store[key] = update["$set"]
        return MagicMock()

    async def find_one(filt, projection=None):
        return store.get((filt["workspace_id"], filt["user_id"]))

    async def delete_one(filt):
        store.pop((filt["workspace_id"], filt["user_id"]), None)
        return MagicMock()

    coll = MagicMock()
    coll.update_one = AsyncMock(side_effect=update_one)
    coll.find_one = AsyncMock(side_effect=find_one)
    coll.delete_one = AsyncMock(side_effect=delete_one)
    fake_db = MagicMock()
    fake_db.user_google_tokens = coll

    with patch.object(server, "db", fake_db):
        await server._store_user_google_tokens("ws1", "alice", {"access_token": "alice-tok", "scope": "gmail.readonly"})
        await server._store_user_google_tokens("ws1", "bob", {"access_token": "bob-tok", "scope": "gmail.readonly"})
        alice = await server._user_google_tokens("ws1", "alice")
        bob = await server._user_google_tokens("ws1", "bob")
        assert alice["access_token"] == "alice-tok"
        assert bob["access_token"] == "bob-tok"
        assert await server._user_google_tokens("ws1", "carol") is None


@pytest.mark.asyncio
async def test_briefing_email_threads_uses_caller_tokens_only():
    principal = {"user_id": "u1", "workspace_id": "ws1", "pack": "member", "role": "member"}
    ws = {"workspace_id": "ws1"}
    with patch.object(server, "_user_google_tokens", new=AsyncMock(return_value=None)):
        threads, meta = await server._briefing_email_threads(ws, principal)
    assert threads == []
    assert meta["connected"] is False

    tokens = {
        "access_token": "ya29",
        "scope": "https://www.googleapis.com/auth/gmail.readonly",
    }
    with patch.object(server, "_user_google_tokens", new=AsyncMock(return_value=tokens)), \
            patch.object(server.gcal, "fetch_important_threads", new=AsyncMock(return_value=(
                [{"id": "t1"}], tokens,
            ))), \
            patch.object(server, "_store_user_google_tokens", new=AsyncMock()):
        threads, meta = await server._briefing_email_threads(ws, principal)
    assert threads[0]["id"] == "t1"
    assert meta["connected"] is True


@pytest.mark.asyncio
async def test_google_calendar_snapshot_no_fallback_without_user_tokens():
    principal = {"user_id": "u1", "workspace_id": "ws1"}
    ws = {"workspace_id": "ws1", "google_tokens": {"access_token": "legacy-workspace"}}
    with patch.object(server, "_user_google_tokens", new=AsyncMock(return_value=None)):
        snap = await server._google_calendar_snapshot(ws, principal=principal)
    assert snap is None


def test_store_integration_tokens_rejects_google_field():
    with pytest.raises(ValueError, match="per-user"):
        asyncio.run(server._store_integration_tokens("ws1", "google_tokens", {"access_token": "x"}))


@pytest.mark.asyncio
async def test_store_user_google_tokens_clears_gmail_briefing_cache():
    import time

    ws = {"workspace_id": "ws1"}
    principal = {"user_id": "u1", "workspace_id": "ws1"}
    key = server._gmail_briefing_cache_key(ws, principal)
    server._gmail_briefing_cache[key] = (
        [{"id": "stale"}],
        {"connected": True, "needs_reconnect": False, "compose": True},
        time.monotonic(),
    )
    coll = MagicMock()
    coll.delete_one = AsyncMock()
    coll.update_one = AsyncMock()
    fake_db = MagicMock()
    fake_db.user_google_tokens = coll
    with patch.object(server, "db", fake_db):
        await server._store_user_google_tokens("ws1", "u1", None)
    assert key not in server._gmail_briefing_cache
    coll.delete_one.assert_awaited_once()

    server._gmail_briefing_cache[key] = (
        [{"id": "old"}],
        {"connected": False, "needs_reconnect": False, "compose": False},
        time.monotonic(),
    )
    with patch.object(server, "db", fake_db):
        await server._store_user_google_tokens(
            "ws1", "u1", {"access_token": "ya29", "scope": "gmail.readonly"},
        )
    assert key not in server._gmail_briefing_cache
