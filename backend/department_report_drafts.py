"""Deterministic department activity → unpublished report drafts.

No LLM. Cron-driven rollup of real completion events from the current week.
Missing-vs-zero AI discipline does not apply: this module never calls the model.
Zero completions in a week is a computed count (none finished), not an untracked field.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from plan_usage import parse_dt
import departments_catalog as dept_catalog

logger = logging.getLogger("helm.department_report_drafts")

SOURCE = "department_draft"
STATUS_DRAFT = "draft"
STATUS_DISMISSED = "dismissed"
STATUS_PUBLISHED = "published"

MAX_WORKSPACES = 400
MAX_NAMES = 6
WEEK_DAYS = 7

# Collection / status / display config. Completions use `completed_at` (stamped on status move).
DEPT_SPECS = (
    {
        "type": dept_catalog.TYPE_PRODUCTION,
        "name": "Production",
        "collection": "production_work_orders",
        "status_field": "status",
        "done_value": "completed",
        "label_field": "reference",
        "metric_label": "Work orders finished",
        "noun": "work order",
        "noun_plural": "work orders",
        "verb": "Finished",
    },
    {
        "type": dept_catalog.TYPE_PROCUREMENT,
        "name": "Procurement",
        "collection": "procurement_requests",
        "status_field": "status",
        "done_value": "delivered",
        "label_field": "item",
        "metric_label": "Requests delivered",
        "noun": "procurement request",
        "noun_plural": "procurement requests",
        "verb": "Delivered",
    },
    {
        "type": dept_catalog.TYPE_LEGAL,
        "name": "Legal",
        "collection": "legal_matters",
        "status_field": "status",
        "done_value": "filed",
        "label_field": "title",
        "metric_label": "Matters filed",
        "noun": "legal matter",
        "noun_plural": "legal matters",
        "verb": "Filed",
    },
    {
        "type": dept_catalog.TYPE_ENGINEERING_MAINTENANCE,
        "name": "Engineering & Maintenance",
        "collection": "maintenance_tickets",
        "status_field": "status",
        "done_value": "resolved",
        "label_field": "equipment_name",
        "metric_label": "Tickets resolved",
        "noun": "maintenance ticket",
        "noun_plural": "maintenance tickets",
        "verb": "Resolved",
    },
    {
        "type": dept_catalog.TYPE_HR,
        "name": "HR",
        "collection": "hr_onboarding_instances",
        "status_field": "overall_status",
        "done_value": "active",
        "label_field": "hire_name",
        "metric_label": "Hires onboarded",
        "noun": "onboarding",
        "noun_plural": "onboardings",
        "verb": "Completed onboarding for",
    },
)

SPEC_BY_TYPE = {s["type"]: s for s in DEPT_SPECS}


def apply_status_completion(
    existing: dict,
    updates: dict,
    *,
    done_status: str,
    status_key: str = "status",
    now_iso: str | None = None,
) -> dict:
    """Stamp completed_at when a record first reaches its done status."""
    if status_key not in updates:
        return updates
    now_iso = now_iso or datetime.now(timezone.utc).isoformat()
    new = updates[status_key]
    old = existing.get(status_key)
    if new == done_status and old != done_status:
        updates["completed_at"] = now_iso
    elif new != done_status:
        updates["completed_at"] = None
    return updates


def week_window(now: datetime | None = None) -> tuple[datetime, datetime, str, str]:
    """Current UTC calendar week (Monday 00:00 → next Monday)."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    day = now.astimezone(timezone.utc).date()
    monday = day - timedelta(days=day.weekday())
    start = datetime(monday.year, monday.month, monday.day, tzinfo=timezone.utc)
    end = start + timedelta(days=WEEK_DAYS)
    period = f"Week of {start.strftime('%b')} {start.day}, {start.year}"
    return start, end, period, start.date().isoformat()


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def completion_time(doc: dict) -> Optional[datetime]:
    return _aware(parse_dt(doc.get("completed_at"))) or _aware(parse_dt(doc.get("updated_at")))


def in_week(doc: dict, start: datetime, end: datetime) -> bool:
    ts = completion_time(doc)
    if not ts:
        return False
    return start <= ts < end


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def summarize(spec: dict, items: list[dict]) -> tuple[str, list[dict]]:
    n = len(items)
    labels = [(it.get(spec["label_field"]) or "").strip() or "Untitled" for it in items]
    shown = labels[:MAX_NAMES]
    extra = n - len(shown)
    noun = _plural(n, spec["noun"], spec["noun_plural"])
    if spec["type"] == dept_catalog.TYPE_HR:
        named = ", ".join(shown)
        if extra > 0:
            named = f"{named}, and {extra} more"
        summary = f"{spec['verb']} {named}." if named else f"Completed {n} {noun}."
    else:
        named = ", ".join(shown)
        if extra > 0:
            named = f"{named}, and {extra} more"
        summary = f"{spec['verb']} {n} {noun}: {named}."
    metrics = [{"label": spec["metric_label"], "value": str(n)}]
    return summary, metrics


def build_draft_doc(
    *,
    workspace_id: str,
    spec: dict,
    items: list[dict],
    period: str,
    week_start: str,
    now_iso: str,
    existing: dict | None = None,
) -> dict | None:
    if not items:
        return None
    summary, metrics = summarize(spec, items)
    title = f"{spec['name']} activity: {period.lower()}"
    return {
        "id": (existing or {}).get("id") or f"drft_{uuid.uuid4().hex[:10]}",
        "workspace_id": workspace_id,
        "department_type": spec["type"],
        "title": title,
        "type": spec["name"],
        "period": period,
        "summary": summary,
        "metrics": metrics,
        "source": SOURCE,
        "status": STATUS_DRAFT,
        "week_start": week_start,
        "item_ids": [it.get("id") for it in items if it.get("id")],
        "created_at": (existing or {}).get("created_at") or now_iso,
        "updated_at": now_iso,
    }


def serialize_draft(doc: dict) -> dict:
    return {
        "id": doc.get("id"),
        "title": doc.get("title") or "",
        "type": doc.get("type") or "",
        "period": doc.get("period") or "",
        "summary": doc.get("summary") or "",
        "metrics": doc.get("metrics") or [],
        "source": SOURCE,
        "status": STATUS_DRAFT,
        "department_type": doc.get("department_type"),
        "week_start": doc.get("week_start"),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


def filter_completed(rows: list[dict], spec: dict, start: datetime, end: datetime) -> list[dict]:
    out = []
    for row in rows:
        if (row.get(spec["status_field"]) or "") != spec["done_value"]:
            continue
        if in_week(row, start, end):
            out.append(row)
    out.sort(key=lambda r: completion_time(r) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return out


async def _rows(db, spec: dict, workspace_id: str) -> list[dict]:
    col = getattr(db, spec["collection"])
    cursor = col.find(
        {"workspace_id": workspace_id, spec["status_field"]: spec["done_value"]},
        {"_id": 0},
    )
    if hasattr(cursor, "to_list"):
        return await cursor.to_list(500)
    return list(cursor)


async def list_open_drafts(db, workspace_id: str) -> list[dict]:
    cursor = db.department_report_drafts.find(
        {"workspace_id": workspace_id, "status": STATUS_DRAFT, "source": SOURCE},
        {"_id": 0},
    ).sort("updated_at", -1)
    if hasattr(cursor, "to_list"):
        rows = await cursor.to_list(50)
    else:
        rows = list(cursor)
    return [serialize_draft(r) for r in rows]


async def dismiss_draft(db, workspace_id: str, draft_id: str) -> bool:
    result = await db.department_report_drafts.update_one(
        {"id": draft_id, "workspace_id": workspace_id, "status": STATUS_DRAFT},
        {"$set": {"status": STATUS_DISMISSED, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return bool(getattr(result, "modified_count", 0) or getattr(result, "matched_count", 0))


async def mark_published(db, workspace_id: str, draft_id: str) -> bool:
    result = await db.department_report_drafts.update_one(
        {"id": draft_id, "workspace_id": workspace_id, "status": STATUS_DRAFT},
        {"$set": {"status": STATUS_PUBLISHED, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return bool(getattr(result, "modified_count", 0) or getattr(result, "matched_count", 0))


async def run_department_drafts(db, *, now: datetime | None = None) -> dict:
    """Scan workspaces and upsert this week's department drafts. Skips empty weeks."""
    now = now or datetime.now(timezone.utc)
    start, end, period, week_key = week_window(now)
    now_iso = now.isoformat()
    stats = {"workspaces": 0, "drafts_upserted": 0, "skipped_empty": 0, "skipped_closed": 0}

    workspaces_cur = db.workspaces.find({}, {"_id": 0, "workspace_id": 1})
    workspaces = await workspaces_cur.to_list(MAX_WORKSPACES) if hasattr(workspaces_cur, "to_list") else list(workspaces_cur)
    for ws in workspaces:
        wid = ws.get("workspace_id")
        if not wid:
            continue
        stats["workspaces"] += 1
        depts_cur = db.departments.find(
            {"workspace_id": wid, "enabled": True, "type": {"$in": list(SPEC_BY_TYPE)}},
            {"_id": 0, "type": 1},
        )
        depts = await depts_cur.to_list(20) if hasattr(depts_cur, "to_list") else list(depts_cur)
        enabled = {d.get("type") for d in depts}
        for spec in DEPT_SPECS:
            if spec["type"] not in enabled:
                continue
            try:
                rows = await _rows(db, spec, wid)
            except Exception:
                logger.exception("draft scan failed %s %s", wid, spec["type"])
                continue
            items = filter_completed(rows, spec, start, end)
            existing = await db.department_report_drafts.find_one(
                {"workspace_id": wid, "department_type": spec["type"], "week_start": week_key},
                {"_id": 0},
            )
            if existing and existing.get("status") in (STATUS_DISMISSED, STATUS_PUBLISHED):
                stats["skipped_closed"] += 1
                continue
            if not items:
                stats["skipped_empty"] += 1
                if existing and existing.get("status") == STATUS_DRAFT:
                    await db.department_report_drafts.delete_one(
                        {"id": existing["id"], "workspace_id": wid},
                    )
                continue
            doc = build_draft_doc(
                workspace_id=wid,
                spec=spec,
                items=items,
                period=period,
                week_start=week_key,
                now_iso=now_iso,
                existing=existing,
            )
            if existing:
                await db.department_report_drafts.update_one(
                    {"id": existing["id"], "workspace_id": wid},
                    {"$set": {k: v for k, v in doc.items() if k != "id"}},
                )
            else:
                await db.department_report_drafts.insert_one(doc)
            stats["drafts_upserted"] += 1
    return stats
