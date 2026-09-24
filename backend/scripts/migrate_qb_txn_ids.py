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

  cd backend && python -m scripts.migrate_accounting_txn_ids --mongo-url "$MONGO_URL" --db "$DB_NAME"
  cd backend && python -m scripts.migrate_accounting_txn_ids --mongo-url "$MONGO_URL" --db "$DB_NAME" --apply

This module keeps the rewrite helpers (also used by the sync upsert safety net);
its CLI now delegates to migrate_accounting_txn_ids (dry-run by default).
"""
from __future__ import annotations

import argparse
import asyncio
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorClient

_DATE_SUFFIX = re.compile(r"_(\d{4}-\d{2}-\d{2})$")
_SAP = re.compile(r"^(sap_b1_(?:ar|ap)_\d+)_\d{4}-\d{2}-\d{2}$")
_XERO_INV = re.compile(r"^xero_([0-9a-fA-F-]{8,})_\d{4}-\d{2}-\d{2}$")
_XERO_BANK = re.compile(r"^xero_bank_([^_]+)_\d{4}-\d{2}-\d{2}$")
_XERO_CN = re.compile(r"^xero_cn_([^_]+)_\d{4}-\d{2}-\d{2}$")
_XERO_MJ = re.compile(r"^xero_mj_([^_]+)_(\d+)_\d{4}-\d{2}-\d{2}$")
_QB_LINE = re.compile(r"^(\d+)_line_([^_]+)_\d{4}-\d{2}-\d{2}$")
_QB_PLAIN = re.compile(r"^(\d+)_\d{4}-\d{2}-\d{2}$")

# Stable id → legacy dated regex helpers (also used by sync upsert safety net).
_STABLE_QB = re.compile(r"^qb_(invoice|salesreceipt|creditmemo|refundreceipt|purchase|bill|vendorcredit)_(\d+)$")
_STABLE_QB_JE = re.compile(r"^qb_journal_(\d+)_(.+)$")
_STABLE_XERO_INV = re.compile(r"^xero_invoice_(.+)$")
_STABLE_XERO_BANK = re.compile(r"^xero_bank_(.+)$")
_STABLE_XERO_CN = re.compile(r"^xero_cn_(.+)$")
_STABLE_XERO_MJ = re.compile(r"^xero_mj_([^_]+)_(\d+)$")
_STABLE_SAP = re.compile(r"^(sap_b1_(?:ar|ap)_\d+)$")


def qb_entity_slug_from_hints(
    *,
    entry_type: str = "",
    source: str = "",
    raw_type: str = "",
    source_hint: str = "",
) -> str:
    """Map financial_entries type/source hints → qb_* entity slug.

    Prefer explicit entity / entry ``type`` over integration ``source``
    (``quickbooks_sync`` etc. never imply purchase vs invoice).
    """
    raw = (raw_type or "").strip().lower().replace("-", "_").replace(" ", "_")
    raw_map = {
        "invoice": "invoice",
        "sales_receipt": "salesreceipt",
        "salesreceipt": "salesreceipt",
        "credit_memo": "creditmemo",
        "creditmemo": "creditmemo",
        "refund_receipt": "refundreceipt",
        "refundreceipt": "refundreceipt",
        "purchase": "purchase",
        "bill": "bill",
        "vendor_credit": "vendorcredit",
        "vendorcredit": "vendorcredit",
        "journal_entry": "journal",
        "journal": "journal",
    }
    if raw in raw_map:
        return raw_map[raw]

    et = (entry_type or "").strip().lower()
    if et in ("revenue", "income"):
        return "invoice"
    if et == "expense":
        # Legacy main only synced Purchase + Invoice; expense → purchase.
        # Prefer bill only when the hint explicitly says bill.
        combined = f"{source} {source_hint}".lower()
        if "bill" in combined:
            return "bill"
        return "purchase"

    # Fall back to free-text hint — but ignore generic sync source strings.
    hint = f"{source_hint} {source} {entry_type}".lower()
    for noise in ("quickbooks_sync", "quickbooks_auto_sync", "quickbooks", "xero_sync", "xero_auto_sync", "sap_b1"):
        hint = hint.replace(noise, " ")
    if "invoice" in hint or "revenue" in hint or "income" in hint:
        return "invoice"
    if "salesreceipt" in hint or "sales_receipt" in hint:
        return "salesreceipt"
    if "creditmemo" in hint or "credit_memo" in hint:
        return "creditmemo"
    if "refund" in hint:
        return "refundreceipt"
    if "vendorcredit" in hint or "vendor_credit" in hint:
        return "vendorcredit"
    if "bill" in hint:
        return "bill"
    if "purchase" in hint or "expense" in hint:
        return "purchase"
    # Last resort — still better than inventing purchase for revenue rows when type was lost.
    return "purchase"


def rewrite_qb_txn_id(
    old: str,
    *,
    source_hint: str = "",
    entry_type: str = "",
    source: str = "",
    raw_type: str = "",
) -> str | None:
    """Return the new stable id, or None if already stable / unknown."""
    if not old or not isinstance(old, str):
        return None
    # Already stable (no trailing date)
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
        slug = qb_entity_slug_from_hints(
            entry_type=entry_type,
            source=source,
            raw_type=raw_type,
            source_hint=source_hint,
        )
        if slug == "journal":
            slug = "purchase"  # plain dated ids are never journal lines
        return f"qb_{slug}_{m.group(1)}"
    # Dated xero_ without uuid shape
    if old.startswith("xero_") and _DATE_SUFFIX.search(old):
        base = _DATE_SUFFIX.sub("", old)
        if base.startswith("xero_") and not base.startswith("xero_invoice_"):
            rest = base[len("xero_"):]
            if rest and not rest.startswith(("bank_", "cn_", "mj_")):
                return f"xero_invoice_{rest}"
        return base
    # Dated stable-looking ids (e.g. qb_invoice_42_2024-01-01) — strip date
    if old.startswith(("qb_", "xero_invoice_", "xero_bank_", "xero_cn_", "xero_mj_", "sap_b1_")):
        if _DATE_SUFFIX.search(old):
            return _DATE_SUFFIX.sub("", old)
    return None


def legacy_dated_patterns_for_stable(stable_id: str) -> list[str]:
    """Mongo regex patterns for dated legacy ids that rewrite to ``stable_id``.

    Used by sync upsert as a safety net so legacy rows are retired when the
    stable id is written — preventing double-count without requiring migration.
    """
    if not stable_id or not isinstance(stable_id, str):
        return []
    patterns: list[str] = []
    m = _STABLE_QB.match(stable_id)
    if m:
        pid = re.escape(m.group(2))
        patterns.append(f"^{pid}_\\d{{4}}-\\d{{2}}-\\d{{2}}$")
        return patterns
    m = _STABLE_QB_JE.match(stable_id)
    if m:
        je_id, line_id = re.escape(m.group(1)), re.escape(m.group(2))
        patterns.append(f"^{je_id}_line_{line_id}_\\d{{4}}-\\d{{2}}-\\d{{2}}$")
        return patterns
    m = _STABLE_XERO_INV.match(stable_id)
    if m:
        uid = re.escape(m.group(1))
        patterns.append(f"^xero_{uid}_\\d{{4}}-\\d{{2}}-\\d{{2}}$")
        patterns.append(f"^xero_invoice_{uid}_\\d{{4}}-\\d{{2}}-\\d{{2}}$")
        return patterns
    m = _STABLE_XERO_BANK.match(stable_id)
    if m:
        tid = re.escape(m.group(1))
        patterns.append(f"^xero_bank_{tid}_\\d{{4}}-\\d{{2}}-\\d{{2}}$")
        return patterns
    m = _STABLE_XERO_CN.match(stable_id)
    if m:
        cid = re.escape(m.group(1))
        patterns.append(f"^xero_cn_{cid}_\\d{{4}}-\\d{{2}}-\\d{{2}}$")
        return patterns
    m = _STABLE_XERO_MJ.match(stable_id)
    if m:
        mid, idx = re.escape(m.group(1)), re.escape(m.group(2))
        patterns.append(f"^xero_mj_{mid}_{idx}_\\d{{4}}-\\d{{2}}-\\d{{2}}$")
        # Prefix deletes for whole journal when line idx unknown historically
        return patterns
    m = _STABLE_SAP.match(stable_id)
    if m:
        base = re.escape(m.group(1))
        patterns.append(f"^{base}_\\d{{4}}-\\d{{2}}-\\d{{2}}$")
        return patterns
    return patterns


def _created_at_sort_key(row: dict[str, Any]) -> float:
    """Newest-first sort key from created_at (ISO) or Mongo _id generation time."""
    raw = row.get("created_at")
    if isinstance(raw, datetime):
        dt = raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    if isinstance(raw, str) and raw.strip():
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            pass
    oid = row.get("_id")
    try:
        return float(oid.generation_time.timestamp())  # type: ignore[union-attr]
    except Exception:
        return 0.0


def _entity_hint_from_doc(doc: dict[str, Any]) -> dict[str, str]:
    return {
        "entry_type": str(doc.get("type") or ""),
        "source": str(doc.get("source") or ""),
        "raw_type": str(
            doc.get("_qb_raw_type")
            or doc.get("_xero_raw_type")
            or doc.get("_sap_raw_type")
            or ""
        ),
        # Back-compat for callers that only pass source_hint
        "source_hint": str(doc.get("type") or doc.get("source") or ""),
    }


async def migrate(mongo_url: str, db_name: str, *, dry_run: bool) -> dict:
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    rewritten = 0
    deleted_dupes = 0
    by_new: dict[tuple[str, str], list[dict]] = defaultdict(list)

    cursor = db.financial_entries.find(
        {"qb_txn_id": {"$exists": True, "$ne": None}},
        {
            "_id": 1, "workspace_id": 1, "qb_txn_id": 1, "source": 1,
            "created_at": 1, "type": 1,
            "_qb_raw_type": 1, "_xero_raw_type": 1, "_sap_raw_type": 1,
        },
    )
    async for doc in cursor:
        old = doc.get("qb_txn_id")
        hints = _entity_hint_from_doc(doc)
        new = rewrite_qb_txn_id(old, **hints)
        target = new or old
        by_new[(doc["workspace_id"], target)].append({**doc, "_new_id": target, "_changed": bool(new)})

    for (ws_id, new_id), rows in by_new.items():
        rows.sort(key=_created_at_sort_key, reverse=True)
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
    # Superseded by scripts.migrate_accounting_txn_ids (dry-run by default, --apply to write).
    from scripts.migrate_accounting_txn_ids import main as accounting_main

    accounting_main()


if __name__ == "__main__":
    main()
