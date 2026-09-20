"""Unit tests for window-keyed rate-limit buckets."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("DB_NAME", "test_rate_limit")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

import rate_limit as rl


class _FakeBuckets:
    """Minimal async find_one_and_update that mirrors Mongo counter semantics."""

    def __init__(self):
        self.docs: dict[str, dict] = {}

    async def find_one_and_update(self, filt, update, upsert=False, return_document=None):
        _id = filt.get("_id")
        max_before = filt.get("count", {}).get("$lt")
        doc = self.docs.get(_id)
        if doc is None:
            if not upsert:
                return None
            # Simulate upsert race: only insert when filter would match a new doc.
            # New docs start at count 0, so $lt limit always holds for limit > 0.
            if max_before is not None and 0 >= max_before:
                return None
            doc = {"_id": _id, "count": 0}
            set_on_insert = (update.get("$setOnInsert") or {})
            doc.update(set_on_insert)
            self.docs[_id] = doc
        if max_before is not None and doc.get("count", 0) >= max_before:
            return None
        inc = (update.get("$inc") or {}).get("count", 0)
        doc["count"] = int(doc.get("count") or 0) + int(inc)
        doc.update(update.get("$set") or {})
        return dict(doc)


def _db_with_buckets(buckets: _FakeBuckets):
    db = MagicMock()
    db.document_rate_buckets = buckets
    db.insights_rate_buckets = buckets
    db.ask_helm_rate_buckets = buckets
    db.document_rate_events = MagicMock()
    db.document_rate_events.insert_one = AsyncMock(return_value=None)
    db.insights_rate_events = MagicMock()
    db.insights_rate_events.insert_one = AsyncMock(return_value=None)
    db.ask_helm_rate_events = MagicMock()
    db.ask_helm_rate_events.insert_one = AsyncMock(return_value=None)
    return db


def test_window_id_advances_with_clock():
    now = datetime(2026, 9, 18, 10, 30, tzinfo=timezone.utc)
    later = now + timedelta(seconds=rl.ROLLING_WINDOW_SECONDS)
    assert rl.window_id(now, rl.ROLLING_WINDOW_SECONDS) + 1 == rl.window_id(
        later, rl.ROLLING_WINDOW_SECONDS,
    )
    assert "w" in rl.window_bucket_key("ws:upload", now, rl.ROLLING_WINDOW_SECONDS)


@pytest.mark.asyncio
async def test_acquire_event_slot_blocks_within_window_then_resets():
    buckets = _FakeBuckets()
    db = _db_with_buckets(buckets)
    now = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)

    # Monkeypatch _acquire to use fixed now via wrapping acquire with patched datetime —
    # call the helper directly for precise control.
    assert await rl._acquire_window_bucket(
        buckets, base_key="ws1:upload", limit=2, window_seconds=3600, now=now,
    )
    assert await rl._acquire_window_bucket(
        buckets, base_key="ws1:upload", limit=2, window_seconds=3600, now=now,
    )
    assert await rl._acquire_window_bucket(
        buckets, base_key="ws1:upload", limit=2, window_seconds=3600, now=now,
    ) is False

    next_window = now + timedelta(seconds=3600)
    assert await rl._acquire_window_bucket(
        buckets, base_key="ws1:upload", limit=2, window_seconds=3600, now=next_window,
    ) is True
    # Two distinct window keys exist — old window cannot permanently lock out.
    keys = list(buckets.docs.keys())
    assert len(keys) == 2
    assert keys[0] != keys[1]


@pytest.mark.asyncio
async def test_acquire_event_slot_records_event_on_success():
    buckets = _FakeBuckets()
    db = _db_with_buckets(buckets)
    ok = await rl.acquire_event_slot(db, "ws_a", "extract", limit=5)
    assert ok is True
    db.document_rate_events.insert_one.assert_awaited()
    # Cap reached
    for _ in range(4):
        assert await rl.acquire_event_slot(db, "ws_a", "extract", limit=5)
    assert await rl.acquire_event_slot(db, "ws_a", "extract", limit=5) is False


@pytest.mark.asyncio
async def test_insights_and_ask_slots_use_their_windows():
    buckets = _FakeBuckets()
    db = _db_with_buckets(buckets)
    assert await rl.acquire_insights_slot(db, "ws_b", limit=1) is True
    assert await rl.acquire_insights_slot(db, "ws_b", limit=1) is False
    assert await rl.acquire_ask_helm_slot(db, "ws_b", limit=1) is True
    assert await rl.acquire_ask_helm_slot(db, "ws_b", limit=1) is False
