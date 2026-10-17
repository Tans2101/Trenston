"""Append-only, hash-chained record of what Trenston's AI told each workspace.

Why: a regenerated briefing or money summary overwrites the old one on screen.
This log keeps every version, fixed to the time it was written, so anyone can
later see exactly what Trenston said on a given day and what data it was based on.

How it stays honest:
- Records are only ever inserted, never updated (no code path edits them).
- Each record stores the hash of the record before it (`prev_hash`) and its own
  hash over every field. Changing or deleting an old record breaks the chain,
  and `verify_chain` reports the first record where it breaks.
- `input_hash` is a fingerprint of the exact data the AI was given, so the record
  proves what it was based on without storing a second copy of the ledger.

Writing to the log must never break the feature that produced the text, so
`record` swallows its own errors (logged) and returns None.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

COLLECTION = "ai_output_log"
GENESIS_HASH = "0" * 64
VERSION = 1
_MAX_RETRIES = 5
_HASHED_FIELDS = (
    "v", "workspace_id", "seq", "created_at", "kind", "text",
    "input_hash", "model", "actor_user_id", "prev_hash",
)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def fingerprint(value: Any) -> str:
    """SHA-256 of a value in a stable JSON form (key order does not matter)."""
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def record_hash(rec: dict) -> str:
    return fingerprint({k: rec.get(k) for k in _HASHED_FIELDS})


async def record(
    db,
    workspace_id: str,
    *,
    kind: str,
    text: Any,
    inputs: Any,
    model: Optional[str],
    actor_user_id: Optional[str] = None,
) -> Optional[dict]:
    """Append one AI output to the workspace's chain. Returns the stored record, or None on failure."""
    from pymongo.errors import DuplicateKeyError

    try:
        coll = db[COLLECTION]
        body = text if isinstance(text, str) else _canonical(text)
        for _attempt in range(_MAX_RETRIES):
            last = await coll.find_one(
                {"workspace_id": workspace_id},
                {"_id": 0, "seq": 1, "hash": 1},
                sort=[("seq", -1)],
            )
            rec = {
                "v": VERSION,
                "workspace_id": workspace_id,
                "seq": (last["seq"] + 1) if last else 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "kind": kind,
                "text": body,
                "input_hash": fingerprint(inputs),
                "model": model,
                "actor_user_id": actor_user_id,
                "prev_hash": last["hash"] if last else GENESIS_HASH,
            }
            rec["hash"] = record_hash(rec)
            try:
                # Insert a copy: drivers add `_id` to the dict they are given.
                await coll.insert_one(dict(rec))
                return rec
            except DuplicateKeyError:
                # Another request took this seq a moment ago; re-read the tip and retry.
                continue
        logger.warning("ai_audit: gave up after %s retries for %s", _MAX_RETRIES, workspace_id)
    except Exception:
        logger.exception("ai_audit: could not record %s for %s", kind, workspace_id)
    return None


async def verify_chain(db, workspace_id: str) -> dict:
    """Walk a workspace's chain in order. ok=False names the first broken seq and why."""
    cursor = db[COLLECTION].find({"workspace_id": workspace_id}, {"_id": 0}).sort("seq", 1)
    prev = GENESIS_HASH
    expected_seq = 1
    count = 0
    async for rec in cursor:
        count += 1
        if rec.get("seq") != expected_seq:
            return {"ok": False, "count": count, "broken_at": rec.get("seq"), "reason": "missing record"}
        if rec.get("prev_hash") != prev:
            return {"ok": False, "count": count, "broken_at": rec.get("seq"), "reason": "chain link changed"}
        if record_hash(rec) != rec.get("hash"):
            return {"ok": False, "count": count, "broken_at": rec.get("seq"), "reason": "record changed"}
        prev = rec["hash"]
        expected_seq += 1
    return {"ok": True, "count": count, "tip": prev}
