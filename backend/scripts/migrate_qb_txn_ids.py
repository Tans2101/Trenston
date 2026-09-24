#!/usr/bin/env python3
"""Idempotent rewrite of legacy dated qb_txn_id values → stable ids.

Legacy formats (examples):
  - QuickBooks: ``{id}_{YYYY-MM-DD}`` → ``qb_{entity}_{id}``
  - Xero: ``xero_{uuid}_{date}`` → ``xero_invoice_{uuid}``
  - Xero bank/cn/mj dated variants → undated
  - SAP B1: ``sap_b1_{ar|ap}_{DocEntry}_{date}`` → ``sap_b1_{ar|ap}_{DocEntry}``

When two rows collapse to the same new id, keep the newest ``created_at`` and
delete the duplicates.

Do NOT run against production from this agent. Invoke manually after backup:

  cd backend && python -m scripts.migrate_qb_txn_ids --mongo-url "$MONGO_URL" --db "$DB_NAME" --dry-run
  cd backend && python -m scripts.migrate_qb_txn_ids --mongo-url "$MONGO_URL" --db "$DB_NAME"
"""
from __future__ import annotations

import argparse
import asyncio
import re
from collections import defaultdict
from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorClient

_DATE_SUFFIX = re.compile(r"_(\d{4}-\d{2}-\d{2})$")
_SAP = re.compile(r"^(sap_b1_(?:ar|ap)_\d+)_\d{4}-\d{2}-\d{2}$")
_XERO_INV = re.compile(r"^xero_([0-9a-fA-F-]{8,})_\d{4}-\d{2}-\d{2}$")
_XERO_BANK = re.compile(r"^xero_bank_([^_]+)_\d{4}-\d{2}-\d{2}$")
_XERO_CN = re.compile(r"^xero_cn_([^_]+)_\d{4}-\d{2}-\d{2}$")
_XERO_MJ = re.compile(r"^xero_mj_([^_]+)_(\d+)_\d{4}-\d{2}-\d{2}$")
_QB_LINE = re.compile(r"^(\d+)_line_([^_]+)_\d{4}-\d{2}-\d{2}$")
_QB_PLAIN = re.compile(r"^(\d+)_\d{4}-\d{2}-\d{2}$")


def rewrite_qb_txn_id(old: str, *, source_hint: str = "") -> str | None:
    """Return the new stable id, or None if already stable / unknown."""
    if not old or not isinstance(old, str):
        return None
    # Already stable
    if old.startswith(("qb_", "xero_invoice_", "xero_bank_", "xero_cn_", "xero_mj_", "sap_b1_")):
        if _DATE_SUFFIX.search(old) is None:
            return None
    m = _SAP.match(old)
    if m:
        return m.group(1)
    m = _XERO_INV.match(old)
    if m:
        return f"xero_invoice_{m.group(1)}"
    m = _XERO_BANK.match(old)
    if m:
        return f"xero_bank_{m.group(1)}"
    m = _XERO_CN.match(old)
    if m:
        return f"xero_cn_{m.group(1)}"
    m = _XERO_MJ.match(old)
    if m:
        return f"xero_mj_{m.group(1)}_{m.group(2)}"
    m = _QB_LINE.match(old)
    if m:
        return f"qb_journal_{m.group(1)}_{m.group(2)}"
    m = _QB_PLAIN.match(old)
    if m:
        # Legacy QB rows lack entity type — default to purchase/invoice from source hint.
        hint = (source_hint or "").lower()
        if "invoice" in hint or "revenue" in hint:
            slug = "invoice"
        elif "bill" in hint:
            slug = "bill"
        else:
            slug = "purchase"
        return f"qb_{slug}_{m.group(1)}"
    # Dated xero_ without uuid shape
    if old.startswith("xero_") and _DATE_SUFFIX.search(old):
        base = _DATE_SUFFIX.sub("", old)
        if base.startswith("xero_") and not base.startswith("xero_invoice_"):
            # xero_{id} → xero_invoice_{id}
            rest = base[len("xero_"):]
            if rest and not rest.startswith(("bank_", "cn_", "mj_")):
                return f"xero_invoice_{rest}"
        return base
    return None


async def migrate(mongo_url: str, db_name: str, *, dry_run: bool) -> dict:
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    rewritten = 0
    deleted_dupes = 0
    by_new: dict[tuple[str, str], list[dict]] = defaultdict(list)

    cursor = db.financial_entries.find(
        {"qb_txn_id": {"$exists": True, "$ne": None}},
        {"_id": 1, "workspace_id": 1, "qb_txn_id": 1, "source": 1, "created_at": 1, "type": 1},
    )
    async for doc in cursor:
        old = doc.get("qb_txn_id")
        new = rewrite_qb_txn_id(old, source_hint=str(doc.get("source") or doc.get("type") or ""))
        target = new or old
        by_new[(doc["workspace_id"], target)].append({**doc, "_new_id": target, "_changed": bool(new)})

    for (ws_id, new_id), rows in by_new.items():
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        keeper = rows[0]
        if keeper.get("_changed"):
            rewritten += 1
            if not dry_run:
                await db.financial_entries.update_one(
                    {"_id": keeper["_id"]}, {"$set": {"qb_txn_id": new_id}},
                )
        for dup in rows[1:]:
            deleted_dupes += 1
            if not dry_run:
                await db.financial_entries.delete_one({"_id": dup["_id"]})

    client.close()
    return {"rewritten": rewritten, "deleted_duplicates": deleted_dupes, "dry_run": dry_run}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mongo-url", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    stats = asyncio.run(migrate(args.mongo_url, args.db, dry_run=args.dry_run))
    print(stats)


if __name__ == "__main__":
    main()
