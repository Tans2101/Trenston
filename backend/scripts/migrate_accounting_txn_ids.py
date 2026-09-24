#!/usr/bin/env python3
"""Rewrite legacy dated accounting qb_txn_id values to stable, date-free ids.

  QuickBooks  ``{Id}_{YYYY-MM-DD}``                 -> ``qb_<entity>_{Id}``
              ``{Id}_line_{LineId}_{YYYY-MM-DD}``    -> ``qb_journal_{Id}_{LineId}``
  Xero        ``xero_{GUID}_{YYYY-MM-DD}``          -> ``xero_invoice_{GUID}``
              ``xero_{bank|cn|mj}_..._{date}``       -> same without the date
  SAP B1      ``sap_b1_{kind}_{DocEntry}_{date}``    -> ``sap_b1_{kind}_{DocEntry}``

The QuickBooks entity is taken from the row's raw-type / entry type where known.
When several rows collapse onto one new id in a workspace, the most recently
updated row (updated_at, else created_at) is kept and the others are deleted.

Idempotent: rows that already have stable ids are left alone.
Dry-run is the default; pass --apply to write. NEVER point this at a database
without a backup.

  cd backend && python -m scripts.migrate_accounting_txn_ids --mongo-url "$MONGO_URL" --db "$DB_NAME"
  cd backend && python -m scripts.migrate_accounting_txn_ids --mongo-url "$MONGO_URL" --db "$DB_NAME" --apply
"""
from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

from scripts.migrate_qb_txn_ids import _entity_hint_from_doc, rewrite_qb_txn_id


def _ts(raw: Any) -> float:
    if isinstance(raw, datetime):
        dt = raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    if isinstance(raw, str) and raw.strip():
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp()
        except ValueError:
            return 0.0
    return 0.0


def _recency_key(row: dict[str, Any]) -> tuple[float, float]:
    return (_ts(row.get("updated_at")), _ts(row.get("created_at")))


def plan_rewrites(docs: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Pure planning step: which rows get a new id and which duplicates go.

    Returns {"updates": [(_id, new_id)], "deletes": [_id], "scanned": n}.
    """
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    scanned = 0
    for doc in docs:
        scanned += 1
        old = doc.get("qb_txn_id")
        new = rewrite_qb_txn_id(old, **_entity_hint_from_doc(doc))
        target = new or old
        groups[(doc.get("workspace_id") or "", target)].append({**doc, "_target": target, "_changed": bool(new)})

    updates: list[tuple[Any, str]] = []
    deletes: list[Any] = []
    for (_ws, target), rows in groups.items():
        if len(rows) == 1 and not rows[0]["_changed"]:
            continue
        rows.sort(key=_recency_key, reverse=True)
        keeper, dupes = rows[0], rows[1:]
        if keeper["_changed"]:
            updates.append((keeper["_id"], target))
        deletes.extend(d["_id"] for d in dupes)
    return {"updates": updates, "deletes": deletes, "scanned": scanned}


async def migrate(mongo_url: str, db_name: str, *, apply: bool) -> dict[str, Any]:
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    try:
        docs = await db.financial_entries.find(
            {"qb_txn_id": {"$type": "string"}},
            {
                "_id": 1, "workspace_id": 1, "qb_txn_id": 1, "source": 1, "type": 1,
                "created_at": 1, "updated_at": 1,
                "_qb_raw_type": 1, "_xero_raw_type": 1, "_sap_raw_type": 1, "source_entity": 1,
            },
        ).to_list(None)
        plan = plan_rewrites(docs)
        if apply:
            # Delete duplicates first so the unique (workspace_id, qb_txn_id) index never collides.
            for _id in plan["deletes"]:
                await db.financial_entries.delete_one({"_id": _id})
            for _id, new_id in plan["updates"]:
                await db.financial_entries.update_one({"_id": _id}, {"$set": {"qb_txn_id": new_id}})
    finally:
        client.close()
    return {
        "scanned": plan["scanned"],
        "rewritten": len(plan["updates"]),
        "deleted_duplicates": len(plan["deletes"]),
        "applied": apply,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mongo-url", required=True)
    parser.add_argument("--db", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True, help="Report only (default)")
    mode.add_argument("--apply", action="store_true", help="Write changes")
    args = parser.parse_args()
    stats = asyncio.run(migrate(args.mongo_url, args.db, apply=bool(args.apply)))
    label = "APPLIED" if stats["applied"] else "DRY RUN (no writes)"
    print(f"[{label}] scanned={stats['scanned']} rewritten={stats['rewritten']} "
          f"deleted_duplicates={stats['deleted_duplicates']}")


if __name__ == "__main__":
    main()
