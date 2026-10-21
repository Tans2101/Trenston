"""Document upload usage keyed by billing anniversary period (not calendar month)."""
from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timezone, timedelta
from typing import Any, Optional


def parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            raw = value.strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(raw)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _parse_dt(value: Any) -> Optional[datetime]:
    return parse_dt(value)


def _safe_month_day(year: int, month: int, day: int) -> datetime:
    last = monthrange(year, month)[1]
    return datetime(year, month, min(day, last), tzinfo=timezone.utc)


def _add_months(dt: datetime, months: int) -> datetime:
    month_index = (dt.month - 1) + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    return _safe_month_day(year, month, dt.day)


def billing_anchor(ws: dict | None) -> Optional[datetime]:
    """Prefer Paddle/subscription start; fall back to workspace created_at."""
    ws = ws or {}
    return (
        _parse_dt(ws.get("billing_period_start"))
        or _parse_dt(ws.get("subscription_started_at"))
        or _parse_dt(ws.get("created_at"))
    )


def current_usage_period(ws: dict | None = None, now: datetime | None = None) -> dict:
    """
    Return the active usage period for a workspace.

    Paid workspaces reset on the billing anniversary day derived from
    subscription start (or workspace creation). Free / unknown anchors use
    calendar month as a fallback.
    """
    now = now or datetime.now(timezone.utc)
    anchor = billing_anchor(ws)
    if not anchor:
        start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        if now.month == 12:
            end = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
        return {
            "key": start.strftime("%Y-%m"),
            "start": start,
            "end": end,
        }

    anchor = anchor.astimezone(timezone.utc)
    # Find latest anniversary <= now
    candidate = _safe_month_day(now.year, now.month, anchor.day)
    if candidate > now:
        # previous month
        if now.month == 1:
            candidate = _safe_month_day(now.year - 1, 12, anchor.day)
        else:
            candidate = _safe_month_day(now.year, now.month - 1, anchor.day)
    # Walk back if still after now (shouldn't happen) or walk forward from far past
    # Ensure we're not before anchor's first period
    if candidate < _safe_month_day(anchor.year, anchor.month, anchor.day):
        candidate = _safe_month_day(anchor.year, anchor.month, anchor.day)

    # If candidate is still more than ~1 month behind, jump near now
    while _add_months(candidate, 1) <= now:
        candidate = _add_months(candidate, 1)

    start = candidate
    end = _add_months(start, 1)
    return {
        "key": start.date().isoformat(),
        "start": start,
        "end": end,
    }


async def get_period_extract_count(db, workspace_id: str, period_key: str) -> int:
    doc = await db.document_usage_periods.find_one(
        {"workspace_id": workspace_id, "period": period_key, "action": "extract"},
        {"_id": 0, "count": 1},
    )
    return int((doc or {}).get("count") or 0)


async def increment_period_extract(db, workspace_id: str, period_key: str) -> int:
    await db.document_usage_periods.update_one(
        {"workspace_id": workspace_id, "period": period_key, "action": "extract"},
        {
            "$inc": {"count": 1},
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()},
            "$setOnInsert": {"created_at": datetime.now(timezone.utc).isoformat()},
        },
        upsert=True,
    )
    return await get_period_extract_count(db, workspace_id, period_key)


async def acquire_period_extract_slot(db, workspace_id: str, period_key: str, limit: int) -> bool:
    """Atomically consume one AI-extract slot for the billing period. False when at cap."""
    from pymongo import ReturnDocument
    from pymongo.errors import DuplicateKeyError

    if limit <= 0:
        return False
    now = datetime.now(timezone.utc).isoformat()
    filt = {
        "workspace_id": workspace_id,
        "period": period_key,
        "action": "extract",
        "count": {"$lt": limit},
    }
    update = {
        "$inc": {"count": 1},
        "$set": {"updated_at": now},
        "$setOnInsert": {
            "workspace_id": workspace_id,
            "period": period_key,
            "action": "extract",
            "created_at": now,
        },
    }
    coll = db.document_usage_periods
    try:
        doc = await coll.find_one_and_update(
            filt,
            update,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        doc = await coll.find_one_and_update(
            filt,
            {"$inc": {"count": 1}, "$set": {"updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
    return doc is not None


async def release_period_extract_slot(db, workspace_id: str, period_key: str) -> None:
    """Return one period extract slot after a failed/aborted extract."""
    now = datetime.now(timezone.utc).isoformat()
    await db.document_usage_periods.update_one(
        {
            "workspace_id": workspace_id,
            "period": period_key,
            "action": "extract",
            "count": {"$gt": 0},
        },
        {"$inc": {"count": -1}, "$set": {"updated_at": now}},
    )


ASK_HELM_ACTION = "ask_helm"


async def get_period_ask_count(db, workspace_id: str, period_key: str) -> int:
    """Ask Trenston messages used in this billing period (separate from AI extracts)."""
    doc = await db.document_usage_periods.find_one(
        {"workspace_id": workspace_id, "period": period_key, "action": ASK_HELM_ACTION},
        {"_id": 0, "count": 1},
    )
    return int((doc or {}).get("count") or 0)


async def acquire_period_ask_slot(db, workspace_id: str, period_key: str, limit: int) -> bool:
    """Atomically consume one Ask Trenston slot for the billing period. False when at cap.

    ``limit <= 0`` means Ask is disabled for the plan (same contract as extract slots),
    not unlimited — callers that treat 0 as “skip quota” must not call this.
    """
    from pymongo import ReturnDocument
    from pymongo.errors import DuplicateKeyError

    if limit <= 0:
        return False
    now = datetime.now(timezone.utc).isoformat()
    filt = {
        "workspace_id": workspace_id,
        "period": period_key,
        "action": ASK_HELM_ACTION,
        "count": {"$lt": limit},
    }
    update = {
        "$inc": {"count": 1},
        "$set": {"updated_at": now},
        "$setOnInsert": {
            "workspace_id": workspace_id,
            "period": period_key,
            "action": ASK_HELM_ACTION,
            "created_at": now,
        },
    }
    coll = db.document_usage_periods
    try:
        doc = await coll.find_one_and_update(
            filt,
            update,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        doc = await coll.find_one_and_update(
            filt,
            {"$inc": {"count": 1}, "$set": {"updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
    return doc is not None


# Back-compat aliases used by older call sites
async def get_monthly_extract_count(db, workspace_id: str, month: str | None = None, ws: dict | None = None) -> int:
    period = current_usage_period(ws)
    key = month or period["key"]
    return await get_period_extract_count(db, workspace_id, key)


async def increment_monthly_extract(db, workspace_id: str, month: str | None = None, ws: dict | None = None) -> int:
    period = current_usage_period(ws)
    key = month or period["key"]
    return await increment_period_extract(db, workspace_id, key)


def get_lifetime_extract_count(ws: dict | None) -> int:
    return int((ws or {}).get("ai_extracts_lifetime_used") or 0)


async def increment_lifetime_extract(db, workspace_id: str) -> int:
    """Increment workspace.ai_extracts_lifetime_used. Returns the new count."""
    now = datetime.now(timezone.utc).isoformat()
    await db.workspaces.update_one(
        {"workspace_id": workspace_id},
        {
            "$inc": {"ai_extracts_lifetime_used": 1},
            "$set": {"ai_extracts_lifetime_updated_at": now},
        },
    )
    ws = await db.workspaces.find_one(
        {"workspace_id": workspace_id},
        {"_id": 0, "ai_extracts_lifetime_used": 1},
    )
    return get_lifetime_extract_count(ws)


async def acquire_lifetime_extract_slot(db, workspace_id: str, limit: int) -> bool:
    """Atomically consume one lifetime AI-extract slot. False when at cap."""
    from pymongo import ReturnDocument

    if limit <= 0:
        return False
    now = datetime.now(timezone.utc).isoformat()
    doc = await db.workspaces.find_one_and_update(
        {
            "workspace_id": workspace_id,
            "$expr": {"$lt": [{"$ifNull": ["$ai_extracts_lifetime_used", 0]}, limit]},
        },
        {
            "$inc": {"ai_extracts_lifetime_used": 1},
            "$set": {"ai_extracts_lifetime_updated_at": now},
        },
        return_document=ReturnDocument.AFTER,
    )
    return doc is not None


async def release_lifetime_extract_slot(db, workspace_id: str) -> None:
    """Return one lifetime extract slot after a failed/aborted extract."""
    now = datetime.now(timezone.utc).isoformat()
    await db.workspaces.update_one(
        {
            "workspace_id": workspace_id,
            "$expr": {"$gt": [{"$ifNull": ["$ai_extracts_lifetime_used", 0]}, 0]},
        },
        {
            "$inc": {"ai_extracts_lifetime_used": -1},
            "$set": {"ai_extracts_lifetime_updated_at": now},
        },
    )


SEAT_USAGE_ACTION = "seats"


async def acquire_seat_slot(db, workspace_id: str, limit: int, *, membership_count: int) -> bool:
    """Atomically reserve one seat under `limit`, seeding from membership_count.

    Memberships remain the durable roster; this counter prevents check-then-act
    races between concurrent invites/joins. Call release_seat_slot if the
    membership insert does not complete.
    """
    from pymongo import ReturnDocument
    from pymongo.errors import DuplicateKeyError

    if limit is None:
        return True
    if limit <= 0:
        return False
    try:
        used = max(0, int(membership_count))
    except (TypeError, ValueError):
        used = 0
    if used >= limit:
        return False

    now = datetime.now(timezone.utc).isoformat()
    coll = db.seat_usage
    # Ensure a counter row exists, floored at the live membership count.
    try:
        await coll.update_one(
            {"workspace_id": workspace_id},
            {
                "$max": {"count": used},
                "$set": {"updated_at": now},
                "$setOnInsert": {
                    "workspace_id": workspace_id,
                    "action": SEAT_USAGE_ACTION,
                    "created_at": now,
                },
            },
            upsert=True,
        )
    except DuplicateKeyError:
        await coll.update_one(
            {"workspace_id": workspace_id},
            {"$max": {"count": used}, "$set": {"updated_at": now}},
        )

    doc = await coll.find_one_and_update(
        {"workspace_id": workspace_id, "count": {"$lt": limit}},
        {"$inc": {"count": 1}, "$set": {"updated_at": now}},
        return_document=ReturnDocument.AFTER,
    )
    return doc is not None


async def release_seat_slot(db, workspace_id: str) -> None:
    """Return one reserved seat after a failed invite/join (or member removal)."""
    now = datetime.now(timezone.utc).isoformat()
    await db.seat_usage.update_one(
        {"workspace_id": workspace_id, "count": {"$gt": 0}},
        {"$inc": {"count": -1}, "$set": {"updated_at": now}},
    )
