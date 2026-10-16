"""Idempotent migration: fold Sales & Accounting/Finance into the department system.

Safe to run repeatedly — does not duplicate departments, memberships, or backfills.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import departments_catalog as catalog

logger = logging.getLogger(__name__)

SALES_FINANCE_TYPES = (catalog.TYPE_SALES, catalog.TYPE_ACCOUNTING_FINANCE)


async def get_enabled_department(db, workspace_id: str, dept_type: str) -> Optional[dict]:
    return await db.departments.find_one(
        {"workspace_id": workspace_id, "type": dept_type, "enabled": True},
        {"_id": 0},
    )


async def get_enabled_departments_by_type(
    db, workspace_id: str, dept_types: list[str] | tuple[str, ...],
) -> dict[str, Optional[dict]]:
    """One query for many department types → ``{type: department|None}``."""
    types = [t for t in dept_types if t]
    out: dict[str, Optional[dict]] = {t: None for t in types}
    if not types:
        return out
    rows = await db.departments.find(
        {"workspace_id": workspace_id, "type": {"$in": list(types)}, "enabled": True},
        {"_id": 0},
    ).to_list(100)
    for row in rows:
        dtype = row.get("type")
        if dtype in out and out[dtype] is None:
            out[dtype] = row
    return out


async def ensure_enabled_department(db, workspace_id: str, dept_type: str) -> tuple[dict, bool]:
    """Return (department, created_or_reenabled).

    Honors unique (workspace_id, type): re-enables a disabled row instead of inserting a second.
    Concurrent first-enable races (startup migration vs first ledger write) are safe.
    """
    from pymongo.errors import DuplicateKeyError

    existing = await db.departments.find_one(
        {"workspace_id": workspace_id, "type": dept_type},
        {"_id": 0},
    )
    if existing:
        if existing.get("enabled"):
            return existing, False
        await db.departments.update_one(
            {"workspace_id": workspace_id, "type": dept_type},
            {"$set": {"enabled": True}},
        )
        existing = {**existing, "enabled": True}
        return existing, True

    now = datetime.now(timezone.utc).isoformat()
    department_id = f"dept_{uuid.uuid4().hex[:12]}"
    doc = {
        "department_id": department_id,
        "workspace_id": workspace_id,
        "type": dept_type,
        "name": catalog.default_name(dept_type),
        "enabled": True,
        "created_at": now,
    }
    try:
        await db.departments.insert_one(dict(doc))
    except DuplicateKeyError:
        # Another request created (workspace_id, type) between find and insert.
        raced = await db.departments.find_one(
            {"workspace_id": workspace_id, "type": dept_type},
            {"_id": 0},
        )
        if not raced:
            raise
        if not raced.get("enabled"):
            await db.departments.update_one(
                {"workspace_id": workspace_id, "type": dept_type},
                {"$set": {"enabled": True}},
            )
            raced = {**raced, "enabled": True}
        return raced, False
    return doc, True


async def ensure_department_member(db, department_id: str, user_id: str, role: str = "member") -> bool:
    """Ensure a membership row exists. Returns True if a new row was inserted.

    Does not change role on existing rows (idempotent; preserves leads).
    """
    from pymongo.errors import DuplicateKeyError

    if not user_id or not department_id:
        return False
    existing = await db.department_members.find_one(
        {"department_id": department_id, "user_id": user_id},
        {"_id": 0},
    )
    if existing:
        return False
    try:
        await db.department_members.insert_one({
            "department_id": department_id,
            "user_id": user_id,
            "role": role if role in catalog.DEPARTMENT_MEMBER_ROLES else "member",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except DuplicateKeyError:
        return False
    return True


async def enroll_user_in_sales_finance(db, workspace_id: str, user_id: str) -> None:
    """Enroll one user into Sales and Accounting & Finance when those depts exist."""
    if not user_id:
        return
    for dtype in SALES_FINANCE_TYPES:
        dept = await get_enabled_department(db, workspace_id, dtype)
        if not dept:
            continue
        await ensure_department_member(db, dept["department_id"], user_id, role="member")


async def migrate_workspace_sales_finance(db, workspace_id: str) -> dict[str, Any]:
    """Enable Sales + Accounting & Finance, enroll members, backfill department_id."""
    summary: dict[str, Any] = {
        "workspace_id": workspace_id,
        "sales_created": False,
        "finance_created": False,
        "members_enrolled_sales": 0,
        "members_enrolled_finance": 0,
        "deals_backfilled": 0,
        "finance_entries_backfilled": 0,
    }

    sales, sales_new = await ensure_enabled_department(db, workspace_id, catalog.TYPE_SALES)
    finance, finance_new = await ensure_enabled_department(
        db, workspace_id, catalog.TYPE_ACCOUNTING_FINANCE,
    )
    summary["sales_created"] = sales_new
    summary["finance_created"] = finance_new
    sales_id = sales["department_id"]
    finance_id = finance["department_id"]

    members = await db.memberships.find(
        {"workspace_id": workspace_id, "user_id": {"$ne": None, "$exists": True}},
        {"_id": 0, "user_id": 1},
    ).to_list(5000)
    seen: set[str] = set()
    for m in members:
        uid = m.get("user_id")
        if not uid or uid in seen:
            continue
        seen.add(uid)
        if await ensure_department_member(db, sales_id, uid, role="member"):
            summary["members_enrolled_sales"] += 1
        if await ensure_department_member(db, finance_id, uid, role="member"):
            summary["members_enrolled_finance"] += 1

    missing_dept = {
        "$or": [
            {"department_id": {"$exists": False}},
            {"department_id": None},
            {"department_id": ""},
        ],
    }
    deals_res = await db.deals.update_many(
        {"workspace_id": workspace_id, **missing_dept},
        {"$set": {"department_id": sales_id}},
    )
    summary["deals_backfilled"] = int(getattr(deals_res, "modified_count", 0) or 0)

    fin_res = await db.financial_entries.update_many(
        {"workspace_id": workspace_id, **missing_dept},
        {"$set": {"department_id": finance_id}},
    )
    summary["finance_entries_backfilled"] = int(getattr(fin_res, "modified_count", 0) or 0)
    if summary["finance_entries_backfilled"]:
        try:
            # Drop financials TTL so dept-scoped KPIs don't serve a stale window.
            import simple_cache
            simple_cache.invalidate(f"financials:{workspace_id}")
            simple_cache.invalidate_prefix(f"financials:{workspace_id}:")
            simple_cache.invalidate_prefix(f"list:financials_page:{workspace_id}:")
        except Exception:
            logger.exception("financials cache invalidate after dept backfill failed for %s", workspace_id)

    logger.info(
        "sales/finance department migration workspace=%s sales_created=%s finance_created=%s "
        "enrolled_sales=%s enrolled_finance=%s deals_backfilled=%s finance_backfilled=%s",
        workspace_id,
        summary["sales_created"],
        summary["finance_created"],
        summary["members_enrolled_sales"],
        summary["members_enrolled_finance"],
        summary["deals_backfilled"],
        summary["finance_entries_backfilled"],
    )
    return summary


async def migrate_all_workspaces_sales_finance(db) -> list[dict[str, Any]]:
    """Run migration for every workspace. Idempotent."""
    workspaces = await db.workspaces.find({}, {"_id": 0, "workspace_id": 1}).to_list(10000)
    results = []
    for ws in workspaces:
        ws_id = ws.get("workspace_id")
        if not ws_id:
            continue
        try:
            results.append(await migrate_workspace_sales_finance(db, ws_id))
        except Exception:
            logger.exception("sales/finance migration failed for workspace %s", ws_id)
    logger.info("sales/finance department migration complete for %d workspace(s)", len(results))
    return results


async def sales_department_id(db, workspace_id: str) -> Optional[str]:
    dept = await get_enabled_department(db, workspace_id, catalog.TYPE_SALES)
    if dept and dept.get("department_id"):
        return dept["department_id"]
    dept, _ = await ensure_enabled_department(db, workspace_id, catalog.TYPE_SALES)
    return (dept or {}).get("department_id")


async def finance_department_id(db, workspace_id: str) -> Optional[str]:
    dept = await get_enabled_department(db, workspace_id, catalog.TYPE_ACCOUNTING_FINANCE)
    if dept and dept.get("department_id"):
        return dept["department_id"]
    dept, _ = await ensure_enabled_department(db, workspace_id, catalog.TYPE_ACCOUNTING_FINANCE)
    return (dept or {}).get("department_id")
