"""AI output history: append-only, hash-chained, tamper-evident."""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

import ai_audit


def _db():
    db = AsyncMongoMockClient()["audit_test"]
    asyncio.run(db.ai_output_log.create_index([("workspace_id", 1), ("seq", 1)], unique=True))
    return db


def _add(db, ws="w1", text="Runway is 4.9 months.", inputs=None, kind="briefing_note"):
    return asyncio.run(ai_audit.record(
        db, ws, kind=kind, text=text, inputs=inputs or {"cash": 1}, model="m", actor_user_id="u1",
    ))


def test_records_chain_in_order_and_verify():
    db = _db()
    a = _add(db, text="one")
    b = _add(db, text="two")
    c = _add(db, text={"making_money": "x"}, kind="money_summary")
    assert (a["seq"], b["seq"], c["seq"]) == (1, 2, 3)
    assert a["prev_hash"] == ai_audit.GENESIS_HASH
    assert b["prev_hash"] == a["hash"] and c["prev_hash"] == b["hash"]
    assert c["text"] == '{"making_money":"x"}'
    out = asyncio.run(ai_audit.verify_chain(db, "w1"))
    assert out == {"ok": True, "count": 3, "tip": c["hash"]}


def test_workspaces_have_separate_chains():
    db = _db()
    _add(db, ws="w1")
    other = _add(db, ws="w2")
    assert other["seq"] == 1 and other["prev_hash"] == ai_audit.GENESIS_HASH


def test_editing_an_old_record_is_detected():
    db = _db()
    for t in ("one", "two", "three"):
        _add(db, text=t)
    asyncio.run(db.ai_output_log.update_one({"workspace_id": "w1", "seq": 2}, {"$set": {"text": "edited"}}))
    out = asyncio.run(ai_audit.verify_chain(db, "w1"))
    assert out["ok"] is False and out["broken_at"] == 2 and out["reason"] == "record changed"


def test_rehashing_an_edit_still_breaks_the_next_link():
    db = _db()
    for t in ("one", "two", "three"):
        _add(db, text=t)
    rec = asyncio.run(db.ai_output_log.find_one({"seq": 2}, {"_id": 0}))
    rec["text"] = "edited"
    rec["hash"] = ai_audit.record_hash(rec)
    asyncio.run(db.ai_output_log.replace_one({"seq": 2}, rec))
    out = asyncio.run(ai_audit.verify_chain(db, "w1"))
    assert out["ok"] is False and out["broken_at"] == 3 and out["reason"] == "chain link changed"


def test_deleting_a_record_is_detected():
    db = _db()
    for t in ("one", "two", "three"):
        _add(db, text=t)
    asyncio.run(db.ai_output_log.delete_one({"seq": 2}))
    out = asyncio.run(ai_audit.verify_chain(db, "w1"))
    assert out["ok"] is False and out["broken_at"] == 3 and out["reason"] == "missing record"


def test_input_fingerprint_ignores_key_order():
    assert ai_audit.fingerprint({"a": 1, "b": 2}) == ai_audit.fingerprint({"b": 2, "a": 1})
    assert ai_audit.fingerprint({"a": 1}) != ai_audit.fingerprint({"a": 2})


def test_concurrent_writers_get_distinct_seqs():
    db = _db()

    async def many():
        return await asyncio.gather(*[
            ai_audit.record(db, "w1", kind="k", text=str(i), inputs={}, model="m") for i in range(5)
        ])

    recs = asyncio.run(many())
    assert sorted(r["seq"] for r in recs if r) == [1, 2, 3, 4, 5]
    assert asyncio.run(ai_audit.verify_chain(db, "w1"))["ok"] is True


def test_a_broken_database_never_breaks_the_caller():
    class Boom:
        def __getitem__(self, _name):
            raise RuntimeError("db down")

    assert asyncio.run(ai_audit.record(Boom(), "w1", kind="k", text="t", inputs={}, model="m")) is None
