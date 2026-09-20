"""Mongo-backed join-code rate limit (shared across workers)."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

import rate_limit as rl


class _BucketStore:
    def __init__(self):
        self.docs = {}

    async def find_one_and_update(self, query, update, upsert=False, return_document=None):
        _id = query.get("_id")
        count_lt = (query.get("count") or {}).get("$lt")
        doc = self.docs.get(_id)
        if doc is None:
            if not upsert:
                return None
            if count_lt is not None and 0 >= count_lt:
                return None
            doc = {"_id": _id, "count": 0}
            self.docs[_id] = doc
        if count_lt is not None and doc["count"] >= count_lt:
            return None
        inc = (update.get("$inc") or {}).get("count", 0)
        doc["count"] = doc.get("count", 0) + inc
        doc.update(update.get("$set") or {})
        return dict(doc)


@pytest.mark.asyncio
async def test_acquire_join_slot_enforces_limit():
    buckets = _BucketStore()
    events = MagicMock()
    events.insert_one = AsyncMock()
    db = MagicMock(join_rate_buckets=buckets, join_rate_events=events)

    for _ in range(rl.JOIN_RATE_LIMIT):
        assert await rl.acquire_join_slot(db, "1.2.3.4") is True
    assert await rl.acquire_join_slot(db, "1.2.3.4") is False
    # Different IP has its own budget.
    assert await rl.acquire_join_slot(db, "9.9.9.9") is True
    assert events.insert_one.await_count == rl.JOIN_RATE_LIMIT + 1


def test_join_bucket_key_rolls_with_window():
    t0 = datetime(2026, 9, 20, 4, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 9, 20, 4, 14, 59, tzinfo=timezone.utc)
    t2 = datetime(2026, 9, 20, 4, 15, 0, tzinfo=timezone.utc)
    k0 = rl._join_bucket_key("1.2.3.4", now=t0)
    k1 = rl._join_bucket_key("1.2.3.4", now=t1)
    k2 = rl._join_bucket_key("1.2.3.4", now=t2)
    assert k0 == k1
    assert k0 != k2
