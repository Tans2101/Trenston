"""Pure signal detectors for CEO decision / delegate suggestions.

Each detector takes already-fetched workspace data and returns structured
signals the LLM can draft into decision or delegate cards.
"""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
from typing import Optional
import logging
import math
import uuid

from money_fmt import fmt_money_plain
from departments_catalog import TYPE_ENGINEERING_MAINTENANCE, TYPE_HR, TYPE_LEGAL, TYPE_PRODUCTION, TYPE_PROCUREMENT
from department_report_drafts import SPEC_BY_TYPE


logger = logging.getLogger("helm.decision_engine")

SEVERITIES = ("high", "medium", "low")
STALLED_DEAL_DAYS = 14
STALLED_DEPARTMENT_DAYS = 5
URGENT_MAINTENANCE_DAYS = 2
CHRONIC_EQUIPMENT_WINDOW_DAYS = 90
CHRONIC_EQUIPMENT_MIN_COUNT = 3
RUNWAY_MONTHS_THRESHOLD = 6
BURN_INCREASE_PCT = 0.20
EXPENSE_SPIKE_PCT = 0.25
# Brand-new categories (prev month $0) need an absolute/relative floor — % change is undefined.
NEW_EXPENSE_CATEGORY_MIN = 2000.0
NEW_EXPENSE_CATEGORY_SHARE = 0.05
SIGNAL_CAP = 12

# Normalize heterogeneous impact proxies onto one comparable scale.
# $1k ≈ 1 day idle/overdue ≈ 24h downtime for tie-breaks within a severity tier.
IMPACT_DOLLAR_UNIT = 1000.0
IMPACT_DAY_UNIT = 1.0
IMPACT_HOUR_UNIT = 24.0

# Keep in sync with server._MAINT_PRIORITY_RANK — 0 is the top (most urgent) rank.
MAINT_PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}
MAINT_TOP_PRIORITY_RANK = min(MAINT_PRIORITY_RANK.values())

# Signals that become decision suggestions vs delegate suggestions
DECISION_SIGNAL_TYPES = frozenset({
    "runway_risk",
    "burn_increase",
    "expense_spike",
    # First month of material spend in a category with no prior-month baseline.
    "new_expense_category",
    "stalled_deal",
    # Planned follow-up date passed without progress — distinct from general stall.
    "missed_followup",
    # Unresolved high-priority equipment tickets may need CEO-level escalation
    # (downtime), unlike generic department stall nudges.
    "urgent_maintenance",
    # Repeat failures on the same equipment — replace vs keep repairing.
    "chronic_equipment_failure",
    # Past-due production work orders (fact check, not a forecast).
    "overdue_work_order",
    "overdue_procurement",
    "overdue_procurement_blocking_production",
    # Past legal due dates (fact only — no advisory language).
    "overdue_legal_deadline",
    # Leave request awaiting approval longer than the stale threshold.
    "pending_leave_request",
})
DELEGATE_SIGNAL_TYPES = frozenset({
    "overdue_task",
    "recurring_blocker",
    "stalled_department_item",
    "stalled_onboarding",
    # Proactive reminder — lower urgency than stalled/missed deal signals.
    "upcoming_followup",
    # Legal due dates within the next two weeks — reminder, not advisory.
    "upcoming_legal_deadline",
})


def workspace_has_team(workspace: dict | None) -> bool:
    """Whether the CEO can hand work to someone else.

    Explicit `has_team` on the workspace wins. Missing field defaults to True so
    legacy workspaces keep today's delegate behavior until they re-run setup.
    """
    if not isinstance(workspace, dict):
        return True
    if "has_team" not in workspace or workspace.get("has_team") is None:
        return True
    return bool(workspace.get("has_team"))


def personal_later_card_from_signal(sig: dict, *, now: str) -> dict:
    """Solo-founder stand-in for a delegate draft: no assignee, flag-for-later only."""
    summary = (sig.get("summary") or "Follow up").strip() or "Follow up"
    detail = (sig.get("detail") or "").strip()
    return {
        "id": f"del_{uuid.uuid4().hex[:10]}",
        "status": "suggested",
        "source": "personal_later",
        "personal": True,
        "signal_type": sig.get("type"),
        "signal": sig,
        "severity": sig.get("severity"),
        "created_at": now,
        "title": summary[:200],
        "detail": detail[:500],
        "suggested_owner_user_id": None,
        "suggested_owner_name": None,
    }


def _signal(type_: str, severity: str, summary: str, detail: str, related_id=None, **extra) -> dict:
    out = {
        "type": type_,
        "severity": severity if severity in SEVERITIES else "medium",
        "summary": summary,
        "detail": detail,
        "related_id": related_id,
    }
    out.update(extra)
    return out


# ---- Shared overdue date parsing (used by detect_overdue_tasks) ----

def parse_task_due_date(due) -> Optional[date]:
    """Return a calendar date when `due` parses cleanly.

    Free-text due dates (e.g. "Wed", "This week") cannot be evaluated for overdue status.
    """
    if due is None:
        return None
    s = str(due).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%b %d %Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def is_task_overdue(task: dict, today: Optional[date] = None) -> bool:
    if task.get("column") == "done":
        return False
    due_d = parse_task_due_date(task.get("due"))
    if due_d is None:
        return False
    today = today or datetime.now(timezone.utc).date()
    return due_d < today


def _parse_iso_dt(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def expense_totals_by_month_category(entries: list) -> dict:
    """Build {YYYY-MM: {category: amount}} from financial_entries (expense only).

    Recurring expenses use non-overlapping rate windows (see finance_recurrence).
    """
    import finance_recurrence as fin_recur

    horizon = fin_recur.resolve_expense_horizon(entries or [])
    return fin_recur.expand_expense_category_totals(entries or [], horizon)


def detect_runway_risk(fin: dict) -> Optional[dict]:
    """Fire if runway < 6 months, or burn rose materially month over month.

    Missing cash (`cash_entered` false / `runway_months` None) is not zero runway.
    """
    if not fin or not fin.get("has_data"):
        return None
    runway = fin.get("runway_months")
    if fin.get("cash_entered") is False:
        runway = None
    burn_series = fin.get("burn_series") or []
    reasons = []
    severity = "medium"

    if runway is not None and runway < RUNWAY_MONTHS_THRESHOLD:
        reasons.append(f"runway is {runway} months (under {RUNWAY_MONTHS_THRESHOLD})")
        severity = "high" if runway < 3 else "medium"

    burn_delta_pct = None
    if len(burn_series) >= 2:
        prev = float(burn_series[-2].get("burn") or 0)
        curr = float(burn_series[-1].get("burn") or 0)
        if prev > 0 and (curr - prev) / prev >= BURN_INCREASE_PCT:
            burn_delta_pct = round((curr - prev) / prev * 100, 1)
            reasons.append(
                f"net burn rose {burn_delta_pct}% MoM "
                f"({burn_series[-2].get('month')} → {burn_series[-1].get('month')}: "
                f"{prev:.0f} → {curr:.0f})"
            )
            if severity != "high":
                severity = "high" if burn_delta_pct >= 40 else "medium"

    if not reasons:
        return None

    sig_type = "runway_risk" if (runway is not None and runway < RUNWAY_MONTHS_THRESHOLD) else "burn_increase"
    return _signal(
        sig_type,
        severity,
        summary="Cash runway / burn pressure",
        detail="; ".join(reasons) + f". Current burn {fin.get('burn')}, cash {fin.get('cash')}.",
        related_id=None,
        runway_months=runway,
        burn=fin.get("burn"),
        cash=fin.get("cash"),
        burn_delta_pct=burn_delta_pct,
    )


def detect_expense_spike(expense_by_month: dict, *, currency: str = "usd") -> list:
    """Fire per category where latest month spend is up >25% vs prior month."""
    months = sorted(expense_by_month.keys())
    if len(months) < 2:
        return []
    prev_m, curr_m = months[-2], months[-1]
    prev_cats = expense_by_month.get(prev_m) or {}
    curr_cats = expense_by_month.get(curr_m) or {}
    out = []
    for cat, curr_amt in curr_cats.items():
        prev_amt = float(prev_cats.get(cat) or 0)
        if prev_amt <= 0:
            continue
        if (curr_amt - prev_amt) / prev_amt < EXPENSE_SPIKE_PCT:
            continue
        delta_pct = round((curr_amt - prev_amt) / prev_amt * 100, 1)
        severity = "high" if delta_pct >= 50 else "medium"
        out.append(_signal(
            "expense_spike",
            severity,
            summary=f"{cat} spend up {delta_pct}% MoM",
            detail=(
                f"{cat}: {fmt_money_plain(prev_amt, currency)} in {prev_m} → "
                f"{fmt_money_plain(curr_amt, currency)} in {curr_m} "
                f"(+{delta_pct}%)."
            ),
            related_id=cat,
            category=cat,
            prev_month=prev_m,
            curr_month=curr_m,
            prev_amount=round(prev_amt, 2),
            curr_amount=round(float(curr_amt), 2),
            delta_pct=delta_pct,
        ))
    return out


def _new_expense_category_threshold(prev_month_total: float) -> float:
    """Material-spend floor: flat minimum, raised for large prior-month totals."""
    threshold = NEW_EXPENSE_CATEGORY_MIN
    try:
        total = float(prev_month_total or 0)
    except (TypeError, ValueError):
        total = 0.0
    if total > 0:
        threshold = max(threshold, total * NEW_EXPENSE_CATEGORY_SHARE)
    return threshold


def detect_new_expense_category(expense_by_month: dict, *, currency: str = "usd") -> list:
    """Fire for categories with $0 prior-month spend and material current-month spend.

    Distinct from expense_spike: percentage increase from zero is not meaningful.
    """
    months = sorted(expense_by_month.keys())
    if len(months) < 2:
        return []
    prev_m, curr_m = months[-2], months[-1]
    prev_cats = expense_by_month.get(prev_m) or {}
    curr_cats = expense_by_month.get(curr_m) or {}
    prev_total = sum(float(v or 0) for v in prev_cats.values())
    threshold = _new_expense_category_threshold(prev_total)
    out = []
    for cat, curr_amt in curr_cats.items():
        prev_amt = float(prev_cats.get(cat) or 0)
        if prev_amt > 0:
            continue
        try:
            amount = float(curr_amt or 0)
        except (TypeError, ValueError):
            continue
        if amount < threshold:
            continue
        # Larger absolute debuts escalate; share of prior total is secondary context.
        share = (amount / prev_total) if prev_total > 0 else None
        severity = "high" if amount >= threshold * 2 else "medium"
        share_bit = (
            f" ({round(share * 100, 1)}% of {prev_m} total spend)"
            if share is not None else ""
        )
        out.append(_signal(
            "new_expense_category",
            severity,
            summary=f"New expense category: {cat}",
            detail=(
                f"{cat} had no spend in {prev_m} and "
                f"{fmt_money_plain(amount, currency)} in {curr_m}{share_bit}. "
                f"This is a first appearance above the material threshold "
                f"({fmt_money_plain(threshold, currency)}), not a MoM percentage spike."
            ),
            related_id=cat,
            category=cat,
            prev_month=prev_m,
            curr_month=curr_m,
            prev_amount=0.0,
            curr_amount=round(amount, 2),
            threshold=round(threshold, 2),
        ))
    return out


def detect_stalled_deals(
    deals: list,
    *,
    now: Optional[datetime] = None,
    days: int = STALLED_DEAL_DAYS,
    currency: str = "usd",
) -> list:
    """Fire for open deals with no stage change (updated_at) in `days` days."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    out = []
    for d in deals or []:
        stage = d.get("stage")
        if stage in ("won", "lost"):
            continue
        updated = _parse_iso_dt(d.get("updated_at") or d.get("created_at"))
        if updated is None or updated >= cutoff:
            continue
        idle_days = (now - updated).days
        name = d.get("name") or "Untitled deal"
        value = d.get("value")
        value_s = fmt_money_plain(value, currency) if value is not None else "unknown value"
        severity = "high" if idle_days >= days * 2 else "medium"
        out.append(_signal(
            "stalled_deal",
            severity,
            summary=f"Deal stalled: {name}",
            detail=(
                f"{name} has been in stage '{stage}' for {idle_days} days "
                f"({value_s}). Last activity {updated.date().isoformat()}."
            ),
            related_id=d.get("id"),
            deal_name=name,
            stage=stage,
            value=value,
            idle_days=idle_days,
            owner_name=d.get("owner_name") or "",
        ))
    return out


def detect_upcoming_followups(
    deals: list,
    *,
    today: Optional[date] = None,
    within_days: int = 2,
) -> list:
    """Reminder for open deals with next_step_date within the next `within_days` (incl. today)."""
    today = today or datetime.now(timezone.utc).date()
    end = today + timedelta(days=max(0, within_days))
    out = []
    for d in deals or []:
        stage = d.get("stage")
        if stage in ("won", "lost"):
            continue
        due = parse_task_due_date(d.get("next_step_date"))
        if due is None or due < today or due > end:
            continue
        name = d.get("name") or "Untitled deal"
        step = (d.get("next_step") or "").strip() or "Follow up"
        when = "today" if due == today else ("tomorrow" if due == today + timedelta(days=1) else due.isoformat())
        out.append(_signal(
            "upcoming_followup",
            "low",
            summary=f"Follow-up {when}: {name}",
            detail=f"{name}: {step} (due {due.isoformat()}).",
            related_id=d.get("id"),
            deal_name=name,
            stage=stage,
            next_step=step,
            next_step_date=due.isoformat(),
            owner_name=d.get("owner_name") or "",
            owner_user_id=d.get("owner_user_id"),
        ))
    return out


def detect_missed_followups(
    deals: list,
    *,
    today: Optional[date] = None,
) -> list:
    """Open deals whose planned next_step_date has already passed."""
    today = today or datetime.now(timezone.utc).date()
    out = []
    for d in deals or []:
        stage = d.get("stage")
        if stage in ("won", "lost"):
            continue
        due = parse_task_due_date(d.get("next_step_date"))
        if due is None or due >= today:
            continue
        days_late = (today - due).days
        name = d.get("name") or "Untitled deal"
        step = (d.get("next_step") or "").strip() or "Follow up"
        severity = "high" if days_late >= 7 else "medium"
        out.append(_signal(
            "missed_followup",
            severity,
            summary=f"Missed follow-up: {name}",
            detail=(
                f"{name}: planned '{step}' was due {due.isoformat()} "
                f"({days_late} day(s) late), still in '{stage}'."
            ),
            related_id=d.get("id"),
            deal_name=name,
            stage=stage,
            next_step=step,
            next_step_date=due.isoformat(),
            days_late=days_late,
            owner_name=d.get("owner_name") or "",
            owner_user_id=d.get("owner_user_id"),
        ))
    return out


def detect_overdue_tasks(tasks: list, *, today: Optional[date] = None) -> list:
    """Fire for open tasks with a parseable past due date."""
    today = today or datetime.now(timezone.utc).date()
    out = []
    for t in tasks or []:
        if not is_task_overdue(t, today):
            continue
        due_d = parse_task_due_date(t.get("due"))
        days_late = (today - due_d).days if due_d else 0
        title = t.get("title") or "Untitled task"
        assignee = t.get("assignee") or "Unassigned"
        severity = "high" if days_late >= 7 else "medium"
        out.append(_signal(
            "overdue_task",
            severity,
            summary=f"Overdue: {title}",
            detail=(
                f"Task '{title}' assigned to {assignee} was due {due_d.isoformat()} "
                f"({days_late} day(s) late), still in '{t.get('column')}'."
            ),
            related_id=t.get("id"),
            task_title=title,
            assignee_name=assignee,
            assignee_user_id=t.get("assignee_user_id"),
            due=due_d.isoformat() if due_d else t.get("due"),
            days_late=days_late,
            column=t.get("column"),
        ))
    return out


def detect_recurring_blockers(updates: list) -> list:
    """Fire when the same person flagged a blocker on 2+ consecutive calendar days.

    `updates` should cover recent days (e.g. last 7) for the workspace.
    """
    # user_id -> sorted unique days with blocker=True
    by_user: dict = {}
    names: dict = {}
    for u in updates or []:
        if not u.get("blocker"):
            continue
        uid = u.get("user_id")
        day = u.get("day")
        if not uid or not day:
            continue
        by_user.setdefault(uid, set()).add(day)
        names[uid] = u.get("user_name") or u.get("name") or uid

    out = []
    for uid, days in by_user.items():
        ordered = sorted(days)
        # Find longest consecutive streak ending at the most recent day
        streak = 1
        for i in range(len(ordered) - 1, 0, -1):
            try:
                d_cur = date.fromisoformat(ordered[i])
                d_prev = date.fromisoformat(ordered[i - 1])
            except ValueError:
                break
            if (d_cur - d_prev).days == 1:
                streak += 1
            else:
                break
        if streak < 2:
            # Also accept any 2+ consecutive pair anywhere in the window
            streak = 1
            best = 1
            for i in range(1, len(ordered)):
                try:
                    d_cur = date.fromisoformat(ordered[i])
                    d_prev = date.fromisoformat(ordered[i - 1])
                except ValueError:
                    continue
                if (d_cur - d_prev).days == 1:
                    streak += 1
                    best = max(best, streak)
                else:
                    streak = 1
            streak = best
        if streak < 2:
            continue
        name = names.get(uid, uid)
        # Grab latest blocker text if present
        latest_text = ""
        for u in sorted((x for x in updates if x.get("user_id") == uid and x.get("blocker")),
                        key=lambda x: x.get("day") or "", reverse=True):
            latest_text = (u.get("text") or "").strip()
            if latest_text:
                break
        detail = f"{name} flagged a blocker on {streak} consecutive days."
        if latest_text:
            detail += f' Latest: "{latest_text[:160]}"'
        out.append(_signal(
            "recurring_blocker",
            "high" if streak >= 3 else "medium",
            summary=f"Recurring blocker: {name}",
            detail=detail,
            related_id=uid,
            assignee_user_id=uid,
            assignee_name=name,
            streak_days=streak,
            blocker_text=latest_text,
        ))
    return out


def _item_last_activity(item: dict) -> Optional[datetime]:
    return _parse_iso_dt(item.get("updated_at") or item.get("created_at"))


def _item_label(item: dict, spec: dict) -> str:
    return (item.get(spec.get("label_field") or "name") or "").strip() or "Untitled"


def detect_stalled_department_item(
    items: list,
    spec: dict,
    *,
    threshold_days: int = STALLED_DEPARTMENT_DAYS,
    now: Optional[datetime] = None,
) -> list:
    """Flag open department records with no `updated_at` movement past `threshold_days`.

    `spec` is a `department_report_drafts.DEPT_SPECS` row (status_field, done_value, …).
    HR onboarding uses `detect_stalled_onboarding` instead.
    """
    if (spec or {}).get("type") == TYPE_HR:
        return []
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=threshold_days)
    status_field = spec["status_field"]
    done_value = spec["done_value"]
    dept_name = spec.get("name") or spec.get("type") or "Department"
    noun = spec.get("noun") or "item"
    out = []
    for item in items or []:
        status = item.get(status_field)
        if status == done_value:
            continue
        updated = _item_last_activity(item)
        if updated is None or updated >= cutoff:
            continue
        idle_days = (now - updated).days
        label = _item_label(item, spec)
        out.append(_signal(
            "stalled_department_item",
            "medium",
            summary=f"{dept_name}: {label} hasn't moved in {idle_days} days",
            detail=(
                f"{noun.capitalize()} '{label}' is still '{status}' after {idle_days} days "
                f"with no update (last activity {updated.date().isoformat()})."
            ),
            related_id=item.get("id"),
            department_type=spec.get("type"),
            department_name=dept_name,
            item_label=label,
            status=status,
            idle_days=idle_days,
        ))
    return out


def detect_urgent_maintenance(
    items: list,
    spec: dict | None = None,
    *,
    threshold_days: int = URGENT_MAINTENANCE_DAYS,
    now: Optional[datetime] = None,
) -> list:
    """Unresolved top-rank (high) maintenance tickets idle past a short window."""
    spec = spec or SPEC_BY_TYPE[TYPE_ENGINEERING_MAINTENANCE]
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=threshold_days)
    status_field = spec["status_field"]
    done_value = spec["done_value"]
    out = []
    for item in items or []:
        if item.get(status_field) == done_value:
            continue
        rank = MAINT_PRIORITY_RANK.get(str(item.get("priority") or "").lower(), 9)
        if rank != MAINT_TOP_PRIORITY_RANK:
            continue
        updated = _item_last_activity(item)
        if updated is None or updated >= cutoff:
            continue
        idle_days = (now - updated).days
        label = _item_label(item, spec)
        out.append(_signal(
            "urgent_maintenance",
            "high",
            summary=f"Urgent maintenance: {label}",
            detail=(
                f"High-priority ticket on '{label}' is still '{item.get(status_field)}' "
                f"after {idle_days} days with no update (last activity {updated.date().isoformat()}). "
                f"Equipment downtime may need CEO-level escalation."
            ),
            related_id=item.get("id"),
            department_type=spec.get("type"),
            department_name=spec.get("name") or "Engineering & Maintenance",
            item_label=label,
            status=item.get(status_field),
            priority=item.get("priority"),
            idle_days=idle_days,
        ))
    return out


def _equipment_name_key(name) -> str:
    return (str(name) if name is not None else "").strip().lower()


def _ticket_open_interval(
    ticket: dict,
    *,
    now: datetime,
) -> tuple[Optional[datetime], Optional[datetime]]:
    """Return (created_at, end_at) for ticket-open duration (proxy for downtime)."""
    created = _parse_iso_dt(ticket.get("created_at"))
    if created is None:
        return None, None
    status = str(ticket.get("status") or "").strip().lower()
    if status == "resolved":
        # Prefer updated_at (set when marked resolved); completed_at is an equivalent stamp.
        end = (
            _parse_iso_dt(ticket.get("updated_at"))
            or _parse_iso_dt(ticket.get("completed_at"))
            or now
        )
    else:
        end = now
    if end < created:
        end = created
    return created, end


def compute_downtime(
    tickets: list,
    *,
    now: Optional[datetime] = None,
    period_start: Optional[datetime] = None,
    period_end: Optional[datetime] = None,
) -> dict:
    """Ticket-open duration totals (not confirmed machine-down time).

    Resolved tickets: updated_at/completed_at − created_at.
    Open tickets: now − created_at.
    When period_start/period_end are set, only the overlapping portion counts.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    by_equipment: dict[str, dict] = {}
    total_seconds = 0.0
    ticket_count = 0
    for ticket in tickets or []:
        created, end = _ticket_open_interval(ticket, now=now)
        if created is None or end is None:
            continue
        start_c = created
        end_c = end
        if period_start is not None:
            start_c = max(start_c, period_start)
        if period_end is not None:
            end_c = min(end_c, period_end)
        end_c = min(end_c, now)
        if end_c <= start_c:
            continue
        secs = (end_c - start_c).total_seconds()
        if secs <= 0:
            continue
        name = (ticket.get("equipment_name") or "").strip() or "Unknown equipment"
        key = _equipment_name_key(name)
        bucket = by_equipment.setdefault(
            key,
            {
                "equipment_name": name,
                "total_seconds": 0.0,
                "ticket_count": 0,
            },
        )
        bucket["total_seconds"] += secs
        bucket["ticket_count"] += 1
        # Prefer the most recently used display casing.
        if (ticket.get("created_at") or "") >= (bucket.get("_sort") or ""):
            bucket["equipment_name"] = name
            bucket["_sort"] = ticket.get("created_at") or ""
        total_seconds += secs
        ticket_count += 1
    equipment_rows = []
    for bucket in by_equipment.values():
        bucket.pop("_sort", None)
        equipment_rows.append(bucket)
    equipment_rows.sort(key=lambda r: (-r["total_seconds"], r["equipment_name"].lower()))
    return {
        "total_seconds": total_seconds,
        "ticket_count": ticket_count,
        "by_equipment": equipment_rows,
        "metric_label": "time ticket was open",
    }


def build_equipment_history(
    tickets: list,
    equipment_name: str,
    *,
    now: Optional[datetime] = None,
    window_days: int = CHRONIC_EQUIPMENT_WINDOW_DAYS,
    history_limit: int = 8,
) -> dict:
    """Case-insensitive exact-match history for one equipment name."""
    now = now or datetime.now(timezone.utc)
    needle = _equipment_name_key(equipment_name)
    empty = {
        "equipment_name": (equipment_name or "").strip(),
        "ticket_count": 0,
        "ticket_count_90d": 0,
        "last_ticket_date": None,
        "recent_tickets": [],
    }
    if not needle:
        return empty
    matched = []
    for ticket in tickets or []:
        if _equipment_name_key(ticket.get("equipment_name")) != needle:
            continue
        matched.append(ticket)
    matched.sort(key=lambda t: t.get("created_at") or "", reverse=True)
    display = (matched[0].get("equipment_name") or "").strip() if matched else (equipment_name or "").strip()
    cutoff = now - timedelta(days=window_days)
    recent = []
    for ticket in matched:
        created = _parse_iso_dt(ticket.get("created_at"))
        if created is not None and created >= cutoff:
            recent.append(ticket)
    last_date = None
    if matched:
        created = _parse_iso_dt(matched[0].get("created_at"))
        last_date = created.date().isoformat() if created else (str(matched[0].get("created_at") or "")[:10] or None)
    recent_tickets = []
    for ticket in matched[:history_limit]:
        recent_tickets.append({
            "id": ticket.get("id"),
            "description": (ticket.get("description") or "").strip(),
            "status": ticket.get("status"),
            "priority": ticket.get("priority"),
            "created_at": ticket.get("created_at"),
        })
    return {
        "equipment_name": display,
        "ticket_count": len(matched),
        "ticket_count_90d": len(recent),
        "last_ticket_date": last_date,
        "recent_tickets": recent_tickets,
    }


def detect_chronic_equipment_failure(
    tickets: list,
    spec: dict | None = None,
    *,
    window_days: int = CHRONIC_EQUIPMENT_WINDOW_DAYS,
    min_count: int = CHRONIC_EQUIPMENT_MIN_COUNT,
    now: Optional[datetime] = None,
) -> list:
    """Flag equipment with min_count+ tickets inside window_days (pattern, not one slow ticket)."""
    spec = spec or SPEC_BY_TYPE[TYPE_ENGINEERING_MAINTENANCE]
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)
    groups: dict[str, dict] = {}
    for ticket in tickets or []:
        name = (ticket.get("equipment_name") or "").strip()
        if not name:
            continue
        created = _parse_iso_dt(ticket.get("created_at"))
        if created is None or created < cutoff:
            continue
        key = _equipment_name_key(name)
        bucket = groups.setdefault(
            key,
            {"equipment_name": name, "tickets": [], "_latest_created": ""},
        )
        bucket["tickets"].append(ticket)
        created_s = ticket.get("created_at") or ""
        if created_s >= (bucket.get("_latest_created") or ""):
            bucket["equipment_name"] = name
            bucket["_latest_created"] = created_s

    out = []
    for bucket in groups.values():
        bucket.pop("_latest_created", None)
        cluster = bucket["tickets"]
        count = len(cluster)
        if count < min_count:
            continue
        times = sorted(
            t for t in (_parse_iso_dt(x.get("created_at")) for x in cluster) if t is not None
        )
        if not times:
            continue
        span_days = max((now - times[0]).days, (times[-1] - times[0]).days, 1)
        equipment = bucket["equipment_name"]
        downtime = compute_downtime(cluster, now=now)
        downtime_hours = int(round(downtime["total_seconds"] / 3600.0))
        downtime_clause = ""
        if downtime["total_seconds"] > 0:
            downtime_clause = (
                f", totaling {downtime_hours} hour"
                f"{'' if downtime_hours == 1 else 's'} of ticket-open time"
            )
        summary = (
            f"The {equipment} has needed repair {count} times in {span_days} days"
            f"{downtime_clause}, so it may be worth replacing rather than continuing to repair."
        )
        detail = (
            f"'{equipment}' has {count} maintenance tickets in the last {window_days} days "
            f"(first in-window ticket {times[0].date().isoformat()}). "
            f"This is a repeat-failure pattern, not a single stalled ticket. "
            f"Consider replace-vs-repair. "
            f"Downtime figure is time tickets were open, not confirmed machine-down time."
        )
        # related_id: most recent ticket id for deep-link convenience
        latest = max(cluster, key=lambda t: t.get("created_at") or "")
        out.append(_signal(
            "chronic_equipment_failure",
            "high",
            summary=summary,
            detail=detail,
            related_id=latest.get("id"),
            department_type=spec.get("type"),
            department_name=spec.get("name") or "Engineering & Maintenance",
            item_label=equipment,
            equipment_name=equipment,
            ticket_count=count,
            window_days=window_days,
            span_days=span_days,
            downtime_seconds=downtime["total_seconds"],
            downtime_hours=downtime_hours,
        ))
    out.sort(key=lambda s: (-(s.get("ticket_count") or 0), s.get("equipment_name") or ""))
    return out


def month_period_bounds(now: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """UTC calendar month [start, next_month_start)."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
    return start, end


def equipment_reliability_by_name(
    tickets: list,
    *,
    now: Optional[datetime] = None,
    window_days: int = CHRONIC_EQUIPMENT_WINDOW_DAYS,
    min_count: int = CHRONIC_EQUIPMENT_MIN_COUNT,
) -> dict[str, dict]:
    """Map lowercased equipment name → recent repair stats for UI badges."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)
    counts: dict[str, dict] = {}
    for ticket in tickets or []:
        name = (ticket.get("equipment_name") or "").strip()
        if not name:
            continue
        created = _parse_iso_dt(ticket.get("created_at"))
        if created is None or created < cutoff:
            continue
        key = _equipment_name_key(name)
        bucket = counts.setdefault(
            key,
            {"equipment_name": name, "ticket_count_90d": 0, "is_chronic": False},
        )
        bucket["ticket_count_90d"] += 1
        bucket["equipment_name"] = name
    for bucket in counts.values():
        bucket["is_chronic"] = bucket["ticket_count_90d"] >= min_count
    return counts


def detect_stalled_onboarding(
    items: list,
    spec: dict | None = None,
    *,
    threshold_days: int = STALLED_DEPARTMENT_DAYS,
    now: Optional[datetime] = None,
) -> list:
    """HR hires not yet `active` with no progress past `threshold_days`."""
    spec = spec or SPEC_BY_TYPE[TYPE_HR]
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=threshold_days)
    status_field = spec["status_field"]
    done_value = spec["done_value"]
    out = []
    for item in items or []:
        if item.get(status_field) == done_value:
            continue
        updated = _item_last_activity(item)
        if updated is None or updated >= cutoff:
            continue
        idle_days = (now - updated).days
        hire = _item_label(item, spec)
        out.append(_signal(
            "stalled_onboarding",
            "medium",
            summary=f"Onboarding for {hire} hasn't progressed in {idle_days} days",
            detail=(
                f"Onboarding for {hire} is still '{item.get(status_field)}' after {idle_days} days "
                f"with no update (last activity {updated.date().isoformat()})."
            ),
            related_id=item.get("id"),
            department_type=spec.get("type"),
            department_name=spec.get("name") or "HR",
            item_label=hire,
            status=item.get(status_field),
            idle_days=idle_days,
        ))
    return out


def detect_pending_leave_requests(
    requests: list,
    *,
    stale_days: int = 3,
    now: Optional[datetime] = None,
) -> list:
    """Flag `pending` leave requests with no update for more than `stale_days`.

    Fact-only text — someone is waiting on an approve/deny decision.
    Does not touch confidential HR records; leave requests only.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max(0, stale_days))
    out = []
    for req in requests or []:
        if (req.get("status") or "").strip().lower() != "pending":
            continue
        updated = _item_last_activity(req)
        if updated is None or updated >= cutoff:
            continue
        pending_days = (now - updated).days
        name = (req.get("employee_name") or "").strip() or "an employee"
        out.append(_signal(
            "pending_leave_request",
            "medium",
            summary=f"Leave request from {name} has been pending {pending_days} days.",
            detail=(
                f"Leave request from {name} has been pending {pending_days} days "
                f"(last update {updated.date().isoformat()})."
            ),
            related_id=req.get("id"),
            department_type=TYPE_HR,
            department_name="HR",
            item_label=name,
            status="pending",
            pending_days=pending_days,
            employee_id=req.get("employee_id"),
        ))
    return out


def detect_overdue_work_orders(work_orders: list, *, today: Optional[date] = None) -> list:
    """Flag work orders whose due_date has passed and status is not done/completed.

    Straightforward date comparison only — no projection or estimation.
    Accepts legacy status \"done\" and the fixed-queue status \"completed\".
    """
    today = today or datetime.now(timezone.utc).date()
    out = []
    for wo in work_orders or []:
        if wo.get("status") in ("done", "completed"):
            continue
        due_d = parse_task_due_date(wo.get("due_date"))
        if due_d is None or due_d >= today:
            continue
        days_late = (today - due_d).days
        label = (wo.get("reference") or "").strip() or "Untitled work order"
        severity = "high" if days_late >= 7 else "medium"
        out.append(_signal(
            "overdue_work_order",
            severity,
            summary=f"Overdue work order: {label}",
            detail=(
                f"Work order '{label}' was due {due_d.isoformat()} "
                f"({days_late} day(s) late) and is still '{wo.get('status')}'."
            ),
            related_id=wo.get("id"),
            department_type="production",
            department_name="Production",
            item_label=label,
            due=due_d.isoformat(),
            days_late=days_late,
            status=wo.get("status"),
        ))
    return out


def compute_average_cycle_time(work_orders: list, *, min_samples: int = 3) -> Optional[dict]:
    """Average completed_at - created_at across completed work orders.

    Returns None when there are fewer than min_samples completed orders —
    never a fabricated 0 from empty history.
    """
    durations = []
    for wo in work_orders or []:
        if wo.get("status") not in ("completed", "done"):
            continue
        created = _parse_iso_dt(wo.get("created_at"))
        completed = _parse_iso_dt(wo.get("completed_at"))
        if created is None or completed is None:
            continue
        if completed < created:
            continue
        durations.append((completed - created).total_seconds())
    if len(durations) < min_samples:
        return None
    avg = sum(durations) / len(durations)
    return {
        "average_seconds": round(avg, 3),
        "sample_count": len(durations),
    }



def detect_overdue_procurement_requests(requests: list, *, today: Optional[date] = None) -> list:
    """Flag procurement requests that are still ordered past expected_delivery_date.

    Plain calendar-date comparison only — no projection. Combined high-severity
    signal when the late request also blocks production work orders.
    """
    today = today or datetime.now(timezone.utc).date()
    out = []
    for req in requests or []:
        if req.get("status") != "ordered":
            continue
        due_d = parse_task_due_date(req.get("expected_delivery_date"))
        if due_d is None or due_d >= today:
            continue
        days_late = (today - due_d).days
        item = (req.get("item") or "").strip() or "Untitled request"
        blocking = list(req.get("blocking_production_orders") or [])
        if blocking:
            wo = blocking[0]
            ref = (wo.get("reference") or "").strip() or "a work order"
            wo_due = (wo.get("due_date") or "").strip()
            due_bit = f" (due {wo_due})" if wo_due else ""
            out.append(_signal(
                "overdue_procurement_blocking_production",
                "high",
                summary=f"Late material holding up {ref}",
                detail=(
                    f"The part for {ref}{due_bit} is {days_late} day(s) overdue from the vendor "
                    f"({item})."
                    + (
                        " High-priority request."
                        if (req.get("priority") or "").strip().lower() == "high"
                        else ""
                    )
                ),
                related_id=req.get("id"),
                department_type="procurement",
                department_name="Procurement",
                item_label=item,
                due=due_d.isoformat(),
                days_late=days_late,
                status=req.get("status"),
                blocking_references=[(b.get("reference") or "") for b in blocking],
            ))
        else:
            severity = "high" if days_late >= 7 else "medium"
            out.append(_signal(
                "overdue_procurement",
                severity,
                summary=f"Overdue procurement: {item}",
                detail=(
                    f"Purchase request '{item}' was expected {due_d.isoformat()} "
                    f"({days_late} day(s) late) and is still ordered."
                ),
                related_id=req.get("id"),
                department_type="procurement",
                department_name="Procurement",
                item_label=item,
                due=due_d.isoformat(),
                days_late=days_late,
                status=req.get("status"),
            ))
    return out




def detect_upcoming_legal_deadlines(
    matters: list,
    *,
    today: Optional[date] = None,
    within_days: int = 14,
) -> list:
    """Plain date comparison for open legal matters with a due_date.

    Upcoming (today..today+within_days) → upcoming_legal_deadline (low).
    Past due → overdue_legal_deadline (medium/high). Filed matters are ignored.
    Signal text states the fact only — no assessment of what to do.
    """
    today = today or datetime.now(timezone.utc).date()
    horizon = today + timedelta(days=max(0, within_days))
    out = []
    for m in matters or []:
        if (m.get("status") or "").strip().lower() == "filed":
            continue
        due_d = parse_task_due_date(m.get("due_date"))
        if due_d is None:
            continue
        title = (m.get("title") or "").strip() or "Untitled matter"
        mtype = (m.get("matter_type") or "other").strip().lower() or "other"
        if mtype == "compliance":
            label = f"Compliance renewal for {title}"
        elif mtype == "contract":
            label = f"Contract renewal for {title}"
        else:
            label = f"Legal deadline for {title}"
        if due_d < today:
            days_late = (today - due_d).days
            severity = "high" if days_late >= 7 else "medium"
            out.append(_signal(
                "overdue_legal_deadline",
                severity,
                summary=f"{label} was due {due_d.isoformat()}",
                detail=(
                    f"{label} was due {due_d.isoformat()} "
                    f"({days_late} day(s) ago) and is still '{m.get('status')}'."
                ),
                related_id=m.get("id"),
                department_type="legal",
                department_name="Legal",
                item_label=title,
                matter_type=mtype,
                due=due_d.isoformat(),
                days_late=days_late,
                status=m.get("status"),
            ))
        elif due_d <= horizon:
            days_until = (due_d - today).days
            when = (
                "today" if days_until == 0
                else ("tomorrow" if days_until == 1 else f"in {days_until} days")
            )
            out.append(_signal(
                "upcoming_legal_deadline",
                "low",
                summary=f"{label} is due {when}",
                detail=f"{label} is due {due_d.isoformat()} ({when}).",
                related_id=m.get("id"),
                department_type="legal",
                department_name="Legal",
                item_label=title,
                matter_type=mtype,
                due=due_d.isoformat(),
                days_until=days_until,
                status=m.get("status"),
            ))
    return out



def collect_department_signals(
    department_items: list | None,
    *,
    now: Optional[datetime] = None,
) -> list:
    """Run department stall detectors. `department_items` is [{spec, items}, ...] for enabled depts only."""
    now = now or datetime.now(timezone.utc)
    signals = []
    for bundle in department_items or []:
        spec = bundle.get("spec") or {}
        items = bundle.get("items") or []
        dtype = spec.get("type")
        if dtype == TYPE_HR:
            signals.extend(detect_stalled_onboarding(items, spec, now=now))
            leave_requests = bundle.get("leave_requests") or []
            signals.extend(detect_pending_leave_requests(leave_requests, now=now))
            continue
        if dtype == TYPE_PRODUCTION:
            specific = detect_overdue_work_orders(items, today=now.date())
            signals.extend(specific)
            specific_ids = {s.get("related_id") for s in specific}
            generic = detect_stalled_department_item(items, spec, now=now)
            generic = [s for s in generic if s.get("related_id") not in specific_ids]
            signals.extend(generic)
            continue
        if dtype == TYPE_PROCUREMENT:
            specific = detect_overdue_procurement_requests(items, today=now.date())
            signals.extend(specific)
            specific_ids = {s.get("related_id") for s in specific}
            generic = detect_stalled_department_item(items, spec, now=now)
            generic = [s for s in generic if s.get("related_id") not in specific_ids]
            signals.extend(generic)
            continue
        if dtype == TYPE_LEGAL:
            specific = detect_upcoming_legal_deadlines(items, today=now.date())
            signals.extend(specific)
            specific_ids = {s.get("related_id") for s in specific}
            generic = detect_stalled_department_item(items, spec, now=now)
            generic = [s for s in generic if s.get("related_id") not in specific_ids]
            signals.extend(generic)
            continue
        generic = detect_stalled_department_item(items, spec, now=now)
        if dtype == TYPE_ENGINEERING_MAINTENANCE:
            urgent = detect_urgent_maintenance(items, spec, now=now)
            urgent_ids = {s.get("related_id") for s in urgent}
            generic = [s for s in generic if s.get("related_id") not in urgent_ids]
            signals.extend(urgent)
            signals.extend(detect_chronic_equipment_failure(items, spec, now=now))
        signals.extend(generic)
    return signals


def compute_impact_score(signal: dict) -> float:
    """Comparable impact proxy for tie-breaks within a severity tier.

    Dollars (deal value, expense spike), days overdue/idle, and downtime hours
    are normalized onto one scale so alphabetical type names never decide
    which signals survive SIGNAL_CAP.
    """
    if not signal:
        return 0.0

    dollars = 0.0
    for key in ("value", "curr_amount"):
        raw = signal.get(key)
        if raw is None:
            continue
        try:
            dollars = max(dollars, abs(float(raw)))
        except (TypeError, ValueError):
            pass
    prev = signal.get("prev_amount")
    curr = signal.get("curr_amount")
    if prev is not None and curr is not None:
        try:
            dollars = max(dollars, abs(float(curr) - float(prev)))
        except (TypeError, ValueError):
            pass

    days = 0.0
    for key in ("idle_days", "days_late", "pending_days", "streak_days", "span_days"):
        raw = signal.get(key)
        if raw is None:
            continue
        try:
            days = max(days, float(raw))
        except (TypeError, ValueError):
            pass
    # Upcoming reminders: sooner = more impact (within the reminder window).
    if signal.get("days_until") is not None:
        try:
            days = max(days, max(0.0, 14.0 - float(signal["days_until"])))
        except (TypeError, ValueError):
            pass

    hours = 0.0
    if signal.get("downtime_hours") is not None:
        try:
            hours = max(0.0, float(signal["downtime_hours"]))
        except (TypeError, ValueError):
            pass
    elif signal.get("downtime_seconds") is not None:
        try:
            hours = max(0.0, float(signal["downtime_seconds"]) / 3600.0)
        except (TypeError, ValueError):
            pass

    # Runway pressure: months under the threshold ≈ days of exposure.
    if signal.get("runway_months") is not None:
        try:
            runway = float(signal["runway_months"])
            days = max(days, max(0.0, (RUNWAY_MONTHS_THRESHOLD - runway) * 30.0))
        except (TypeError, ValueError):
            pass
    if signal.get("burn_delta_pct") is not None:
        try:
            # 20% MoM ≈ 4 impact-days; keeps burn spikes competitive with stalls.
            days = max(days, float(signal["burn_delta_pct"]) / 5.0)
        except (TypeError, ValueError):
            pass

    score = (
        dollars / IMPACT_DOLLAR_UNIT
        + days / IMPACT_DAY_UNIT
        + hours / IMPACT_HOUR_UNIT
    )
    if not math.isfinite(score):
        return 0.0
    return round(score, 4)


def rank_and_cap_signals(signals: list, *, cap: int = SIGNAL_CAP) -> list:
    """Sort by severity, then impact (desc); truncate and log when over cap."""
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    ranked = list(signals or [])
    for s in ranked:
        s["impact_score"] = compute_impact_score(s)
    ranked.sort(
        key=lambda s: (
            severity_rank.get(s.get("severity"), 9),
            -float(s.get("impact_score") or 0),
            s.get("type") or "",
            str(s.get("related_id") or ""),
        )
    )
    if len(ranked) <= cap:
        return ranked
    kept = ranked[:cap]
    cut = ranked[cap:]
    cut_types = sorted({(c.get("type") or "?") for c in cut})
    logger.info(
        "decision signals truncated: total=%s kept=%s cut=%s cut_types=%s",
        len(ranked),
        cap,
        len(cut),
        ",".join(cut_types),
    )
    return kept


def collect_signals(
    *,
    fin: dict,
    expense_by_month: dict,
    deals: list,
    tasks: list,
    updates: list,
    currency: str = "usd",
    department_items: list | None = None,
    now: Optional[datetime] = None,
) -> list:
    """Run all detectors and return a flat list of signals."""
    signals = []
    runway = detect_runway_risk(fin)
    if runway:
        signals.append(runway)
    signals.extend(detect_expense_spike(expense_by_month, currency=currency))
    signals.extend(detect_new_expense_category(expense_by_month, currency=currency))
    signals.extend(detect_stalled_deals(deals, currency=currency, now=now))
    today = (now or datetime.now(timezone.utc)).date()
    signals.extend(detect_upcoming_followups(deals, today=today))
    signals.extend(detect_missed_followups(deals, today=today))
    signals.extend(detect_overdue_tasks(tasks, today=today))
    signals.extend(detect_recurring_blockers(updates))
    signals.extend(collect_department_signals(department_items, now=now))
    # Cap volume so one regenerate can't spawn dozens of LLM calls.
    # Severity first; within a tier, impact — not alphabetical type names.
    return rank_and_cap_signals(signals, cap=SIGNAL_CAP)
