"""Cross-department open work items — shared by My Day and People roster."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional
from urllib.parse import quote

import departments_catalog as dept_catalog

WORK_URLS = {
    dept_catalog.TYPE_PRODUCTION: "/app/departments/production",
    dept_catalog.TYPE_PROCUREMENT: "/app/departments/procurement",
    dept_catalog.TYPE_LEGAL: "/app/departments/legal",
    dept_catalog.TYPE_ENGINEERING_MAINTENANCE: "/app/departments/engineering_maintenance",
    dept_catalog.TYPE_HR: "/app/departments/hr",
    dept_catalog.TYPE_SALES: "/app/sales",
}

def _q(value) -> str:
    return quote(str(value or ""), safe="")


def work_item_url(department_type: str, item_id: str = "") -> str:
    """Deep link to one record on its department page.

    Sales deals → ``/app/sales?deal=<id>``; every other department →
    ``<dept path>?item=<id>``. Falls back to the bare page when id is empty.
    """
    base = WORK_URLS.get(department_type) or f"/app/departments/{department_type}"
    if not item_id:
        return base
    if department_type == dept_catalog.TYPE_SALES:
        return f"{base}?deal={_q(item_id)}"
    return f"{base}?item={_q(item_id)}"


def task_url(task_id: str) -> str:
    return f"/app/tasks?task={_q(task_id)}" if task_id else "/app/tasks"


def hr_leave_request_url(request_id: str) -> str:
    base = f"{WORK_URLS[dept_catalog.TYPE_HR]}?tab=leave"
    return f"{base}&request={_q(request_id)}" if request_id else base


def decision_url(decision_id: str) -> str:
    return f"/app/decisions?focus={_q(decision_id)}" if decision_id else "/app/decisions"


# Sources used for People roster workload badges (excludes procurement requested_by).
WORKLOAD_DEPARTMENT_TYPES = (
    dept_catalog.TYPE_PRODUCTION,
    dept_catalog.TYPE_LEGAL,
    dept_catalog.TYPE_ENGINEERING_MAINTENANCE,
    dept_catalog.TYPE_HR,
    dept_catalog.TYPE_SALES,
)


def due_info(raw, today: date) -> tuple[Optional[str], bool]:
    """Normalize a due date string and flag overdue (past calendar day vs ``today``).

    Callers pass workspace-local today from ``/me/work-items`` (or UTC date when
    omitted in lower-level helpers).
    """
    due = (str(raw).strip()[:10] if raw else "") or None
    if not due:
        return None, False
    try:
        d = date.fromisoformat(due)
    except ValueError:
        return due, False
    return due, d < today


def work_row(
    *,
    item_id: str,
    department_type: str,
    title: str,
    due_raw,
    status: str,
    today: date,
    relationship: str = "assigned_to_me",
    url: Optional[str] = None,
) -> dict:
    due, overdue = due_info(due_raw, today)
    entry = dept_catalog.catalog_entry(department_type) or {}
    return {
        "id": item_id,
        "department_type": department_type,
        "title": (title or item_id).strip() or item_id,
        "due_date": due,
        "status": status or "",
        "url": url if url is not None else work_item_url(department_type, item_id),
        "relationship": relationship,
        "overdue": overdue,
        "icon": entry.get("icon") or "briefcase",
        "department_name": entry.get("name") or department_type,
    }


def sort_work_items(items: list[dict]) -> list[dict]:
    """Overdue first, then soonest due; undated last."""

    def _sort_key(it: dict):
        due = it.get("due_date") or "9999-99-99"
        return (0 if it.get("overdue") else 1, due, it.get("title") or "")

    return sorted(items, key=_sort_key)


async def enabled_department_ids(db, workspace_id: str, dept_type: str) -> Optional[list[str]]:
    """All enabled department ids of this type in the workspace (no membership filter)."""
    rows = await db.departments.find(
        {
            "workspace_id": workspace_id,
            "type": dept_type,
            "enabled": True,
        },
        {"_id": 0, "department_id": 1},
    ).to_list(50)
    ids = [r["department_id"] for r in rows if r.get("department_id")]
    return ids or None


async def collect_for_user(
    db,
    workspace_id: str,
    user_id: str,
    *,
    department_ids_by_type: dict[str, Optional[list[str]]],
    today: Optional[date] = None,
    include_procurement: bool = True,
    hr_leave_approve_dept_ids: Optional[list[str]] = None,
) -> list[dict]:
    """Open items for one user, scoped to the provided department id lists (None = skip type).

    ``hr_leave_approve_dept_ids`` — HR department ids where this user may approve
    leave (lead/CEO). Pending leave in those depts appears as ``assigned_to_me``.
    Own open leave (pending/approved) always appears as ``requested_by_me`` when
    the user has HR access.
    """
    today = today or datetime.now(timezone.utc).date()
    uid = user_id
    items: list[dict] = []

    prod_ids = department_ids_by_type.get(dept_catalog.TYPE_PRODUCTION)
    if prod_ids is not None:
        filt = {
            "workspace_id": workspace_id,
            "department_id": {"$in": prod_ids},
            "assigned_user_ids": uid,
            "status": {"$nin": ["completed", "done"]},
        }
        rows = await db.production_work_orders.find(filt, {"_id": 0}).to_list(200)
        for r in rows:
            items.append(work_row(
                item_id=r.get("id") or "",
                department_type=dept_catalog.TYPE_PRODUCTION,
                title=r.get("reference") or r.get("product") or r.get("id") or "Work order",
                due_raw=r.get("due_date"),
                status=r.get("status") or "",
                today=today,
            ))

    legal_ids = department_ids_by_type.get(dept_catalog.TYPE_LEGAL)
    if legal_ids is not None:
        filt = {
            "workspace_id": workspace_id,
            "department_id": {"$in": legal_ids},
            "assigned_to": uid,
            "status": {"$nin": ["filed"]},
        }
        rows = await db.legal_matters.find(filt, {"_id": 0}).to_list(200)
        for r in rows:
            items.append(work_row(
                item_id=r.get("id") or "",
                department_type=dept_catalog.TYPE_LEGAL,
                title=r.get("title") or r.get("id") or "Matter",
                due_raw=r.get("due_date"),
                status=r.get("status") or "",
                today=today,
            ))

    maint_ids = department_ids_by_type.get(dept_catalog.TYPE_ENGINEERING_MAINTENANCE)
    if maint_ids is not None:
        filt = {
            "workspace_id": workspace_id,
            "department_id": {"$in": maint_ids},
            "assigned_technician": uid,
            "status": {"$nin": ["resolved"]},
        }
        rows = await db.maintenance_tickets.find(filt, {"_id": 0}).to_list(200)
        for r in rows:
            items.append(work_row(
                item_id=r.get("id") or "",
                department_type=dept_catalog.TYPE_ENGINEERING_MAINTENANCE,
                title=r.get("equipment_name") or r.get("description") or r.get("id") or "Ticket",
                due_raw=None,
                status=r.get("status") or "",
                today=today,
            ))

    hr_ids = department_ids_by_type.get(dept_catalog.TYPE_HR)
    if hr_ids is not None:
        hr_filt = {
            "workspace_id": workspace_id,
            "department_id": {"$in": hr_ids},
            "overall_status": "in_progress",
            "steps": {"$elemMatch": {"assigned_to": uid, "status": {"$ne": "done"}}},
        }
        for coll_name, label_key, prefix in (
            ("hr_onboarding_instances", "hire_name", "Onboarding"),
            ("hr_offboarding_instances", "employee_name", "Offboarding"),
        ):
            coll = getattr(db, coll_name)
            rows = await coll.find(hr_filt, {"_id": 0}).to_list(200)
            for inst in rows:
                person = (inst.get(label_key) or "").strip() or "Employee"
                for step in inst.get("steps") or []:
                    if step.get("assigned_to") != uid or step.get("status") == "done":
                        continue
                    step_name = (step.get("name") or "Step").strip()
                    items.append(work_row(
                        item_id=f"{inst.get('id')}:{step.get('id')}",
                        department_type=dept_catalog.TYPE_HR,
                        title=f"{prefix} · {person}: {step_name}",
                        due_raw=None,
                        status=step.get("status") or "",
                        today=today,
                    ))

        # Leave requests: own open leave + pending approvals for HR leads.
        leave_seen: set[str] = set()
        own_leave = await db.hr_leave_requests.find(
            {
                "workspace_id": workspace_id,
                "department_id": {"$in": hr_ids},
                "requested_by": uid,
                "status": {"$in": ["pending", "approved"]},
            },
            {"_id": 0},
        ).to_list(200)
        for r in own_leave:
            lid = r.get("id") or ""
            if not lid or lid in leave_seen:
                continue
            leave_seen.add(lid)
            person = (r.get("employee_name") or "").strip() or "Employee"
            leave_type = (r.get("type") or "leave").replace("_", " ")
            items.append(work_row(
                item_id=lid,
                department_type=dept_catalog.TYPE_HR,
                title=r.get("title") or f"Leave · {person}: {leave_type}",
                due_raw=r.get("end_date") or r.get("start_date"),
                status=r.get("status") or "",
                today=today,
                relationship="requested_by_me",
                url=hr_leave_request_url(lid),
            ))

        approve_ids = [d for d in (hr_leave_approve_dept_ids or []) if d and d in set(hr_ids)]
        if approve_ids:
            pending_leave = await db.hr_leave_requests.find(
                {
                    "workspace_id": workspace_id,
                    "department_id": {"$in": approve_ids},
                    "status": "pending",
                },
                {"_id": 0},
            ).to_list(200)
            for r in pending_leave:
                lid = r.get("id") or ""
                if not lid or lid in leave_seen:
                    continue
                leave_seen.add(lid)
                person = (r.get("employee_name") or "").strip() or "Employee"
                leave_type = (r.get("type") or "leave").replace("_", " ")
                items.append(work_row(
                    item_id=lid,
                    department_type=dept_catalog.TYPE_HR,
                    title=r.get("title") or f"Approve leave · {person}: {leave_type}",
                    due_raw=r.get("start_date") or r.get("end_date"),
                    status=r.get("status") or "",
                    today=today,
                    relationship="assigned_to_me",
                    url=hr_leave_request_url(lid),
                ))

    sales_ids = department_ids_by_type.get(dept_catalog.TYPE_SALES)
    if sales_ids is not None:
        filt = {
            "workspace_id": workspace_id,
            "department_id": {"$in": sales_ids},
            "owner_user_id": uid,
            "stage": {"$nin": ["won", "lost"]},
        }
        rows = await db.deals.find(filt, {"_id": 0}).to_list(200)
        for r in rows:
            items.append(work_row(
                item_id=r.get("id") or "",
                department_type=dept_catalog.TYPE_SALES,
                title=r.get("name") or r.get("company") or r.get("id") or "Deal",
                due_raw=r.get("next_step_date") or r.get("close_date"),
                status=r.get("stage") or "",
                today=today,
            ))

    if include_procurement:
        proc_ids = department_ids_by_type.get(dept_catalog.TYPE_PROCUREMENT)
        if proc_ids is not None:
            filt = {
                "workspace_id": workspace_id,
                "department_id": {"$in": proc_ids},
                "requested_by": uid,
                "status": {"$nin": ["delivered", "rejected"]},
            }
            rows = await db.procurement_requests.find(filt, {"_id": 0}).to_list(200)
            for r in rows:
                items.append(work_row(
                    item_id=r.get("id") or "",
                    department_type=dept_catalog.TYPE_PROCUREMENT,
                    title=r.get("item") or r.get("id") or "Request",
                    due_raw=r.get("expected_delivery_date"),
                    status=r.get("status") or "",
                    today=today,
                    relationship="requested_by_me",
                ))

    return sort_work_items(items)


def _bump(counts: dict[str, dict], uid: str, *, overdue: bool) -> None:
    if not uid:
        return
    bucket = counts.setdefault(uid, {"open_item_count": 0, "overdue_item_count": 0})
    bucket["open_item_count"] += 1
    if overdue:
        bucket["overdue_item_count"] += 1


async def workload_counts_by_user(
    db,
    workspace_id: str,
    user_ids: list[str],
    *,
    today: Optional[date] = None,
) -> dict[str, dict[str, int]]:
    """Open/overdue counts per user_id — one query per department type for the workspace.

    No per-viewer department ACL: People is a company-wide roster summary.
    """
    today = today or datetime.now(timezone.utc).date()
    wanted = {u for u in user_ids if u}
    if not wanted:
        return {}
    counts: dict[str, dict[str, int]] = {
        uid: {"open_item_count": 0, "overdue_item_count": 0} for uid in wanted
    }

    prod_ids = await enabled_department_ids(db, workspace_id, dept_catalog.TYPE_PRODUCTION)
    if prod_ids:
        rows = await db.production_work_orders.find(
            {
                "workspace_id": workspace_id,
                "department_id": {"$in": prod_ids},
                "status": {"$nin": ["completed", "done"]},
            },
            {"_id": 0, "assigned_user_ids": 1, "due_date": 1},
        ).to_list(2000)
        for r in rows:
            _, overdue = due_info(r.get("due_date"), today)
            for uid in r.get("assigned_user_ids") or []:
                if uid in wanted:
                    _bump(counts, uid, overdue=overdue)

    legal_ids = await enabled_department_ids(db, workspace_id, dept_catalog.TYPE_LEGAL)
    if legal_ids:
        rows = await db.legal_matters.find(
            {
                "workspace_id": workspace_id,
                "department_id": {"$in": legal_ids},
                "status": {"$nin": ["filed"]},
            },
            {"_id": 0, "assigned_to": 1, "due_date": 1},
        ).to_list(2000)
        for r in rows:
            uid = r.get("assigned_to")
            if uid not in wanted:
                continue
            _, overdue = due_info(r.get("due_date"), today)
            _bump(counts, uid, overdue=overdue)

    maint_ids = await enabled_department_ids(
        db, workspace_id, dept_catalog.TYPE_ENGINEERING_MAINTENANCE,
    )
    if maint_ids:
        rows = await db.maintenance_tickets.find(
            {
                "workspace_id": workspace_id,
                "department_id": {"$in": maint_ids},
                "status": {"$nin": ["resolved"]},
            },
            {"_id": 0, "assigned_technician": 1},
        ).to_list(2000)
        for r in rows:
            uid = r.get("assigned_technician")
            if uid in wanted:
                _bump(counts, uid, overdue=False)

    hr_ids = await enabled_department_ids(db, workspace_id, dept_catalog.TYPE_HR)
    if hr_ids:
        hr_filt = {
            "workspace_id": workspace_id,
            "department_id": {"$in": hr_ids},
            "overall_status": "in_progress",
        }
        for coll_name in ("hr_onboarding_instances", "hr_offboarding_instances"):
            coll = getattr(db, coll_name)
            rows = await coll.find(hr_filt, {"_id": 0, "steps": 1}).to_list(2000)
            for inst in rows:
                for step in inst.get("steps") or []:
                    if step.get("status") == "done":
                        continue
                    uid = step.get("assigned_to")
                    if uid in wanted:
                        _bump(counts, uid, overdue=False)

    sales_ids = await enabled_department_ids(db, workspace_id, dept_catalog.TYPE_SALES)
    if sales_ids:
        rows = await db.deals.find(
            {
                "workspace_id": workspace_id,
                "department_id": {"$in": sales_ids},
                "stage": {"$nin": ["won", "lost"]},
            },
            {"_id": 0, "owner_user_id": 1, "next_step_date": 1, "close_date": 1},
        ).to_list(2000)
        for r in rows:
            uid = r.get("owner_user_id")
            if uid not in wanted:
                continue
            _, overdue = due_info(r.get("next_step_date") or r.get("close_date"), today)
            _bump(counts, uid, overdue=overdue)

    return counts
