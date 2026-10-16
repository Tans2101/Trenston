"""Automations: owner-defined rules plus anomaly alerts.

Everything here is plain code working on the company's own data. There are no
AI/LLM calls, so running it costs nothing and gives the same answer every time.

Rules say: *when* something happens (a signal Trenston already detects, or a
number crossing a limit) *then* do something (create a task, or just show an
alert). Each firing is claimed in ``automation_events`` first, so the same thing
never fires twice in 30 days, and one rule can only fire a handful of times per
run so turning a rule on cannot flood a team with tasks.

Anomaly alerts are statistical checks on the finance ledger (duplicate entries,
the same money typed by hand and synced from accounting,
one-off expenses far above the usual, revenue dropping or stopping). They land
in ``anomaly_alerts`` once per finding.
"""
from __future__ import annotations

import logging
import math
import re
import statistics
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

import accounting_map as amap

logger = logging.getLogger(__name__)

RULES = "automation_rules"
EVENTS = "automation_events"
ANOMALIES = "anomaly_alerts"

MAX_RULES = 25
MAX_FIRINGS_PER_RULE_RUN = 10
EVENT_TTL = timedelta(days=30)
MAX_NAME = 80
MAX_TITLE = 140
MAX_ANOMALIES_PER_SCAN = 10

SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2}
PRIORITIES = ("High", "Medium", "Low")

# Signals the existing decision engine already detects. ``financial`` ones are only
# offered to people who can see the company's finances.
SIGNAL_TRIGGERS: dict[str, dict[str, Any]] = {
    "overdue_work_order": {"label": "A work order is overdue", "financial": False},
    "overdue_procurement": {"label": "A supplier request is overdue", "financial": False},
    "overdue_procurement_blocking_production": {
        "label": "An overdue supplier request is blocking production", "financial": False,
    },
    "overdue_legal_deadline": {"label": "A legal deadline has passed", "financial": False},
    "upcoming_legal_deadline": {"label": "A legal deadline is coming up", "financial": False},
    "urgent_maintenance": {"label": "A maintenance ticket is urgent", "financial": False},
    "chronic_equipment_failure": {"label": "A machine keeps failing", "financial": False},
    "stalled_deal": {"label": "A deal has stalled", "financial": False},
    "missed_followup": {"label": "A sales follow-up was missed", "financial": False},
    "overdue_task": {"label": "A task is overdue", "financial": False},
    "stalled_department_item": {"label": "A department item has stalled", "financial": False},
    "pending_leave_request": {"label": "A leave request is waiting", "financial": False},
    "expense_spike": {"label": "An expense category spikes", "financial": True},
    "new_expense_category": {"label": "A new expense category appears", "financial": True},
    "runway_risk": {"label": "Cash runway gets short", "financial": True},
    "burn_increase": {"label": "Monthly burn jumps", "financial": True},
}

METRIC_TRIGGERS: dict[str, dict[str, Any]] = {
    "runway_months_below": {
        "label": "Cash runway falls below a number of months",
        "unit": "months", "min": 1.0, "max": 60.0, "financial": True,
    },
    "cash_below": {
        "label": "Cash on hand falls below an amount",
        "unit": "amount", "min": 0.0, "max": 1e12, "financial": True,
    },
}

ANOMALY_KINDS = {
    "duplicate_entry": "Possible duplicate entry",
    "cross_source_duplicate": "Possibly counted twice",
    "outlier_expense": "Unusually large expense",
    "revenue_drop": "Revenue dropped",
    "revenue_stopped": "Revenue stopped",
}


class RuleError(ValueError):
    """A rule failed validation. The message is safe to show to the user."""


# ------------------------------------------------------------------ validation

def _clean_text(value: Any, limit: int, *, field: str, required: bool = False) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if required and not text:
        raise RuleError(f"{field} is required.")
    return text[:limit]


def normalize_trigger(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise RuleError("Choose when this rule should run.")
    kind = raw.get("type")
    if kind == "signal":
        signal_type = raw.get("signal_type")
        if signal_type not in SIGNAL_TRIGGERS:
            raise RuleError("Choose what should trigger this rule.")
        severity = raw.get("min_severity") or "low"
        if severity not in SEVERITY_RANK:
            raise RuleError("Choose how serious it must be: low, medium or high.")
        return {"type": "signal", "signal_type": signal_type, "min_severity": severity}
    if kind == "metric":
        metric = raw.get("metric")
        spec = METRIC_TRIGGERS.get(metric)
        if not spec:
            raise RuleError("Choose which number to watch.")
        try:
            value = float(raw.get("value"))
        except (TypeError, ValueError):
            raise RuleError("Enter a number for the limit.")
        if not math.isfinite(value) or value < spec["min"] or value > spec["max"]:
            raise RuleError("That limit is outside the allowed range.")
        return {"type": "metric", "metric": metric, "value": round(value, 2)}
    raise RuleError("Choose when this rule should run.")


def normalize_action(raw: Any, member_ids: set[str]) -> dict:
    if not isinstance(raw, dict):
        raise RuleError("Choose what should happen.")
    kind = raw.get("type")
    if kind == "alert":
        return {"type": "alert"}
    if kind == "create_task":
        title = _clean_text(raw.get("title") or "Follow up: {summary}", MAX_TITLE, field="Task title", required=True)
        priority = raw.get("priority") or "Medium"
        if priority not in PRIORITIES:
            raise RuleError("Priority must be High, Medium or Low.")
        try:
            due_in_days = int(raw.get("due_in_days") if raw.get("due_in_days") is not None else 2)
        except (TypeError, ValueError):
            raise RuleError("Due in days must be a whole number.")
        if due_in_days < 0 or due_in_days > 90:
            raise RuleError("Due in days must be between 0 and 90.")
        assignee = (raw.get("assignee_user_id") or "").strip() or None
        if assignee and assignee not in member_ids:
            raise RuleError("That person is not in this workspace.")
        return {
            "type": "create_task", "title": title, "priority": priority,
            "due_in_days": due_in_days, "assignee_user_id": assignee,
        }
    raise RuleError("Choose what should happen.")


def normalize_rule(body: dict, member_ids: set[str]) -> dict:
    """Validate and whitelist a full rule body. Raises RuleError."""
    return {
        "name": _clean_text(body.get("name"), MAX_NAME, field="Name", required=True),
        "enabled": bool(body.get("enabled", True)),
        "trigger": normalize_trigger(body.get("trigger")),
        "action": normalize_action(body.get("action"), member_ids),
    }


def trigger_is_financial(trigger: dict) -> bool:
    if trigger.get("type") == "signal":
        return bool(SIGNAL_TRIGGERS.get(trigger.get("signal_type"), {}).get("financial"))
    if trigger.get("type") == "metric":
        return bool(METRIC_TRIGGERS.get(trigger.get("metric"), {}).get("financial"))
    return False


def starter_templates() -> list[dict]:
    """One-click rules. Every entry must pass normalize_rule (tests enforce it)."""
    task = lambda title, priority, days: {  # noqa: E731
        "type": "create_task", "title": title, "priority": priority, "due_in_days": days,
    }
    return [
        {
            "id": "overdue_work_order",
            "name": "Overdue work order, make a task",
            "blurb": "Never let a late work order sit unnoticed.",
            "trigger": {"type": "signal", "signal_type": "overdue_work_order", "min_severity": "low"},
            "action": task("Chase overdue work order: {summary}", "High", 1),
        },
        {
            "id": "blocking_supplier",
            "name": "Late supplier blocking production",
            "blurb": "A supplier delay that stops the line gets a high-priority task right away.",
            "trigger": {"type": "signal", "signal_type": "overdue_procurement_blocking_production", "min_severity": "low"},
            "action": task("Resolve supplier delay: {summary}", "High", 0),
        },
        {
            "id": "legal_deadline",
            "name": "Legal deadline coming up",
            "blurb": "A task a few days before a filing or renewal is due.",
            "trigger": {"type": "signal", "signal_type": "upcoming_legal_deadline", "min_severity": "low"},
            "action": task("Prepare for legal deadline: {summary}", "High", 3),
        },
        {
            "id": "stalled_deal",
            "name": "Stalled deal, follow up",
            "blurb": "If a deal goes quiet, you get a follow-up task.",
            "trigger": {"type": "signal", "signal_type": "stalled_deal", "min_severity": "low"},
            "action": task("Follow up: {summary}", "Medium", 2),
        },
        {
            "id": "urgent_maintenance",
            "name": "Urgent maintenance",
            "blurb": "Urgent tickets turn into a same-day task.",
            "trigger": {"type": "signal", "signal_type": "urgent_maintenance", "min_severity": "low"},
            "action": task("Handle urgent maintenance: {summary}", "High", 0),
        },
        {
            "id": "short_runway",
            "name": "Runway under 6 months",
            "blurb": "A heads-up in Automations when cash gets short. No task, just the alert.",
            "trigger": {"type": "metric", "metric": "runway_months_below", "value": 6},
            "action": {"type": "alert"},
        },
    ]


# ------------------------------------------------------------------ matching

def _money(value: float, symbol: str = "") -> str:
    return f"{symbol}{value:,.0f}"


def signal_firings(rule: dict, signals: list[dict]) -> list[dict]:
    trig = rule.get("trigger") or {}
    if trig.get("type") != "signal":
        return []
    min_rank = SEVERITY_RANK.get(trig.get("min_severity") or "low", 0)
    out = []
    for sig in signals or []:
        if sig.get("type") != trig.get("signal_type"):
            continue
        severity = sig.get("severity") if sig.get("severity") in SEVERITY_RANK else "medium"
        if SEVERITY_RANK[severity] < min_rank:
            continue
        related = str(sig.get("related_id") or "all")
        out.append({
            "dedupe_key": f"signal:{sig.get('type')}:{related}",
            "summary": str(sig.get("summary") or SIGNAL_TRIGGERS.get(sig.get("type"), {}).get("label", "")),
            "detail": str(sig.get("detail") or ""),
            "severity": severity,
            "related_id": sig.get("related_id"),
        })
    return out


def metric_firings(rule: dict, fin: dict) -> list[dict]:
    trig = rule.get("trigger") or {}
    if trig.get("type") != "metric" or not fin or not fin.get("has_data"):
        return []
    limit = float(trig.get("value") or 0)
    if trig.get("metric") == "runway_months_below":
        runway = fin.get("runway_months")
        if fin.get("cash_entered") is False or runway is None:
            return []
        if float(runway) < limit:
            return [{
                "dedupe_key": "metric:runway_months_below",
                "summary": f"Cash runway is {runway} months (limit {limit:g})",
                "detail": f"Runway fell below your limit of {limit:g} months.",
                "severity": "high" if float(runway) < 3 else "medium",
                "related_id": None,
            }]
    if trig.get("metric") == "cash_below":
        cash = fin.get("cash_value")
        if not fin.get("cash_entered") or cash is None:
            return []
        if float(cash) < limit:
            symbol = fin.get("currency_symbol") or ""
            return [{
                "dedupe_key": "metric:cash_below",
                "summary": f"Cash is {_money(float(cash), symbol)} (limit {_money(limit, symbol)})",
                "detail": "Cash on hand fell below your limit.",
                "severity": "high",
                "related_id": None,
            }]
    return []


def rule_firings(rule: dict, signals: list[dict], fin: dict) -> list[dict]:
    trig_type = (rule.get("trigger") or {}).get("type")
    if trig_type == "signal":
        return signal_firings(rule, signals)
    if trig_type == "metric":
        return metric_firings(rule, fin)
    return []


def render_title(template: str, firing: dict) -> str:
    """Fill {summary}/{detail} with plain replace (never str.format on user text)."""
    text = (template or "").replace("{summary}", firing.get("summary") or "").replace(
        "{detail}", firing.get("detail") or "",
    )
    text = re.sub(r"\s+", " ", text).strip()
    return (text or firing.get("summary") or "Automation follow-up")[:MAX_TITLE]


def build_task(rule: dict, firing: dict, assignee: dict, today: date) -> dict:
    action = rule.get("action") or {}
    due = today + timedelta(days=int(action.get("due_in_days") or 0))
    return {
        "id": f"t_{uuid.uuid4().hex[:8]}",
        "title": render_title(action.get("title") or "", firing),
        "assignee": assignee.get("name") or "Teammate",
        "assignee_user_id": assignee["user_id"],
        "priority": action.get("priority") if action.get("priority") in PRIORITIES else "Medium",
        "column": "backlog",
        "tag": "Automation",
        "due": due.isoformat(),
        "progress": 0,
        "source": "automation",
        "rule_id": rule.get("id"),
    }


# ------------------------------------------------------------------ running rules

def _is_duplicate_key(exc: Exception) -> bool:
    text = str(exc).lower()
    return "e11000" in text or "duplicate key" in text


async def _claim(db, workspace_id: str, rule: dict, firing: dict, now: datetime) -> Optional[dict]:
    """Insert the firing's event; None when the same thing already fired recently."""
    flt = {"workspace_id": workspace_id, "rule_id": rule["id"], "dedupe_key": firing["dedupe_key"]}
    if await db[EVENTS].find_one(flt, {"_id": 0, "id": 1}):
        return None
    event = {
        "id": f"evt_{uuid.uuid4().hex[:12]}",
        **flt,
        "rule_name": rule.get("name"),
        "summary": firing["summary"],
        "severity": firing["severity"],
        "action": (rule.get("action") or {}).get("type"),
        "task_id": None,
        "assignee_name": None,
        "created_at": now.isoformat(),
        "expire_at": now + EVENT_TTL,
    }
    try:
        await db[EVENTS].insert_one(dict(event))
    except Exception as exc:  # pragma: no cover - depends on the live unique index
        if _is_duplicate_key(exc):
            return None
        raise
    return event


async def run_rules(
    db,
    workspace_id: str,
    *,
    rules: list[dict],
    signals: list[dict],
    fin: dict,
    today: date,
    now: datetime,
    resolve_assignee: Callable[[dict], Awaitable[Optional[dict]]],
    push_task: Callable[[dict, dict, dict], Awaitable[None]],
) -> dict:
    """Evaluate enabled rules. ``push_task(rule, task, assignee)`` writes the task."""
    stats = {"rules": 0, "fired": 0, "tasks": 0, "errors": 0}
    for rule in rules:
        if not rule.get("enabled"):
            continue
        stats["rules"] += 1
        fired_here = 0
        for firing in rule_firings(rule, signals, fin):
            if fired_here >= MAX_FIRINGS_PER_RULE_RUN:
                break  # the rest are picked up on the next run
            event = await _claim(db, workspace_id, rule, firing, now)
            if event is None:
                continue
            try:
                updates: dict[str, Any] = {}
                if (rule.get("action") or {}).get("type") == "create_task":
                    assignee = await resolve_assignee(rule)
                    if not assignee:
                        raise RuntimeError("no assignee available")
                    task = build_task(rule, firing, assignee, today)
                    await push_task(rule, task, assignee)
                    updates = {"task_id": task["id"], "assignee_name": assignee.get("name")}
                    stats["tasks"] += 1
                if updates:
                    await db[EVENTS].update_one({"id": event["id"], "workspace_id": workspace_id}, {"$set": updates})
                await db[RULES].update_one(
                    {"id": rule["id"], "workspace_id": workspace_id},
                    {"$set": {"last_fired_at": now.isoformat()}, "$inc": {"fire_count": 1}},
                )
                fired_here += 1
                stats["fired"] += 1
            except Exception:
                # Release the claim so the next run can try again.
                stats["errors"] += 1
                logger.exception("automation rule %s failed in workspace %s", rule.get("id"), workspace_id)
                await db[EVENTS].delete_one({"id": event["id"], "workspace_id": workspace_id})
    return stats


# ------------------------------------------------------------------ anomalies

def _norm_name(entry: dict) -> str:
    return re.sub(r"\s+", " ", str(entry.get("name") or entry.get("category") or "")).strip().lower()


def _prev_month(month: str) -> str:
    year, mon = int(month[:4]), int(month[5:7])
    return f"{year - 1}-12" if mon == 1 else f"{year}-{mon - 1:02d}"


def _valid_month(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value))


def _plain_entries(entries: list[dict]) -> list[dict]:
    """Ledger rows a person typed or imported (not recurring, not system-booked)."""
    out = []
    for e in entries or []:
        if not e.get("id") or not _valid_month(e.get("month")):
            continue
        if e.get("recurring") or e.get("source_deal_id") or e.get("source_procurement_request_id"):
            continue
        if e.get("type") not in ("revenue", "expense"):
            continue
        out.append(e)
    return out


def detect_duplicates(entries: list[dict], symbol: str = "") -> list[dict]:
    plain = _plain_entries(entries)
    month_totals: dict[tuple, float] = defaultdict(float)
    for e in plain:
        month_totals[(e["type"], e["month"])] += amap.entry_amount_for_totals(e)
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for e in plain:
        name = _norm_name(e)
        amount = amap.entry_amount_for_totals(e)
        if not name or amount <= 0:
            continue
        groups[(e["type"], e["month"], name, round(amount, 2))].append(e)
    found = []
    for (etype, month, name, amount), rows in groups.items():
        if len(rows) < 2:
            continue
        total = month_totals[(etype, month)]
        # Small repeats (coffee, bus fare) are normal; flag only what moves the month.
        if total <= 0 or amount < 0.02 * total:
            continue
        ids = sorted(str(r["id"]) for r in rows)
        label = rows[0].get("name") or rows[0].get("category") or "entry"
        found.append({
            "key": f"dup:{etype}:{month}:{name}:{amount}",
            "kind": "duplicate_entry",
            "severity": "medium",
            "title": f"{len(rows)} identical {etype} entries: {label}",
            "detail": (
                f"{len(rows)} {etype} entries named \"{label}\" for {_money(amount, symbol)} each in {month}. "
                "If it was entered twice, delete one so your numbers stay right."
            ),
            "entry_ids": ids,
            "month": month,
        })
    return found


# Cross-source double counting: a row typed in Trenston (or booked from a deal
# or purchase request) that matches a row synced from the accounting system.
CROSS_SOURCE_LOOKBACK_MONTHS = 6
CROSS_SOURCE_MAX_SYNCED_SHOWN = 6
_SYNC_SOURCE_LABELS = (("quickbooks", "QuickBooks"), ("xero", "Xero"), ("sap", "SAP Business One"))


def _is_synced(entry: dict) -> bool:
    """Rows written by the accounting sync carry the provider's transaction id."""
    return bool(entry.get("qb_txn_id"))


def _sync_label(entry: dict) -> str:
    src = str(entry.get("source") or "").lower()
    for prefix, label in _SYNC_SOURCE_LABELS:
        if src.startswith(prefix):
            return label
    return "your accounting system"


def _amounts_match(a: float, b: float) -> bool:
    # Typed amounts are often rounded; allow 0.5% (or 1 unit) of slack.
    return abs(a - b) <= max(1.0, 0.005 * max(a, b))


def detect_cross_source_duplicates(entries: list[dict], current_month: str, symbol: str = "") -> list[dict]:
    """Flag rows that look like the same money counted from two sources.

    Names usually differ ("Rent" typed by hand vs "Office rent - Bill" from
    QuickBooks), so detect_duplicates misses these. Match on type, month and
    amount instead, only when an accounting sync is connected, only for
    material amounts, and only over recent months. Recurring typed rows are
    compared month by month against what was synced.
    """
    if not _valid_month(current_month):
        return []
    import finance_recurrence as fin_recur

    first_month = fin_recur.month_add(current_month, -(CROSS_SOURCE_LOOKBACK_MONTHS - 1))
    synced = [
        e for e in entries or []
        if _is_synced(e) and not e.get("recurring") and e.get("id")
        and e.get("type") in ("revenue", "expense") and _valid_month(e.get("month"))
        and first_month <= e["month"] <= current_month and not e.get("is_credit")
    ]
    if not synced:
        return []

    month_totals: dict[tuple, float] = defaultdict(float)
    synced_by_key: dict[tuple, list[dict]] = defaultdict(list)
    for e in synced:
        amount = amap.entry_amount_for_totals(e)
        if amount <= 0:
            continue
        month_totals[(e["type"], e["month"])] += amount
        synced_by_key[(e["type"], e["month"])].append(e)

    typed = [
        e for e in entries or []
        if not _is_synced(e) and e.get("id") and not e.get("is_credit")
        and e.get("type") in ("revenue", "expense") and _valid_month(e.get("month"))
    ]
    found = []
    used: set[str] = set()
    for t in sorted(typed, key=lambda r: (r["month"], str(r["id"]))):
        if t.get("recurring"):
            monthly = (
                fin_recur.expense_monthly_amount(t) if t["type"] == "expense"
                else fin_recur.revenue_monthly_amount(t)
            )
            start = max(t["month"], first_month)
            months = fin_recur.months_inclusive(start, current_month) if start <= current_month else []
        else:
            monthly = amap.entry_amount_for_totals(t)
            months = [t["month"]] if first_month <= t["month"] <= current_month else []
        if monthly <= 0 or not months:
            continue
        matches = []
        for month in months:
            total = month_totals.get((t["type"], month), 0.0) + monthly
            # Small repeats are normal; only flag what moves the month.
            if total <= 0 or monthly < 0.02 * total:
                continue
            for s in synced_by_key.get((t["type"], month), []):
                sid = str(s["id"])
                if sid in used:
                    continue
                if _amounts_match(monthly, amap.entry_amount_for_totals(s)):
                    matches.append(s)
                    used.add(sid)
                    break
        if not matches:
            continue
        label = t.get("name") or t.get("category") or t["type"]
        src = _sync_label(matches[0])
        months_hit = sorted({m["month"] for m in matches})
        span = months_hit[0] if len(months_hit) == 1 else f"{months_hit[0]} to {months_hit[-1]}"
        synced_name = matches[0].get("name") or matches[0].get("category") or "a synced row"
        if t.get("recurring"):
            fix = (
                f"If {src} already records this, end or delete the recurring row you added "
                "so it is not counted twice."
            )
        else:
            fix = "If they are the same payment, delete the one you added so it is not counted twice."
        found.append({
            "key": f"xsrc:{t['id']}",
            "kind": "cross_source_duplicate",
            "severity": "high" if len(matches) >= 3 else "medium",
            "title": f"{label} may be counted twice",
            "detail": (
                f"\"{label}\" ({_money(monthly, symbol)}, added in Trenston) matches \"{synced_name}\" "
                f"synced from {src} for the same amount in {span}. {fix}"
            ),
            "entry_ids": [str(t["id"])] + [str(m["id"]) for m in matches[:CROSS_SOURCE_MAX_SYNCED_SHOWN]],
            "month": months_hit[-1],
        })
    return found


def detect_outlier_expenses(entries: list[dict], current_month: str, symbol: str = "") -> list[dict]:
    plain = [e for e in _plain_entries(entries) if e["type"] == "expense"]
    recent = {current_month, _prev_month(current_month)}
    month_totals: dict[str, float] = defaultdict(float)
    for e in plain:
        month_totals[e["month"]] += amap.entry_amount_for_totals(e)
    by_category: dict[str, list[dict]] = defaultdict(list)
    for e in plain:
        by_category[str(e.get("category") or "").strip().lower()].append(e)
    found = []
    for rows in by_category.values():
        for e in rows:
            if e["month"] not in recent:
                continue
            amount = amap.entry_amount_for_totals(e)
            history = [
                amap.entry_amount_for_totals(h) for h in rows
                if h["id"] != e["id"] and h["month"] < e["month"]
            ]
            history = [h for h in history if h > 0]
            if amount <= 0 or len(history) < 4:
                continue
            median = statistics.median(history)
            if median <= 0 or amount < 3 * median:
                continue
            mean = statistics.fmean(history)
            spread = statistics.pstdev(history)
            if spread > 0 and amount <= mean + 3 * spread:
                continue
            if month_totals[e["month"]] <= 0 or amount < 0.05 * month_totals[e["month"]]:
                continue
            label = e.get("name") or e.get("category") or "expense"
            found.append({
                "key": f"outlier:{e['id']}",
                "kind": "outlier_expense",
                "severity": "high" if amount >= 10 * median else "medium",
                "title": f"Unusually large expense: {label}",
                "detail": (
                    f"{_money(amount, symbol)} in {e['month']}, about {amount / median:.1f}x the usual "
                    f"{_money(median, symbol)} for {e.get('category') or 'this category'}. "
                    "Check it is right (extra zero? one-off purchase?)."
                ),
                "entry_ids": [str(e["id"])],
                "month": e["month"],
            })
    return found


def detect_revenue_change(ledger_months: list[dict], current_month: str) -> list[dict]:
    """Compare the last full month with the average of up to 3 months before it."""
    rows = sorted(
        (m for m in ledger_months or [] if _valid_month(m.get("month")) and m["month"] < current_month),
        key=lambda m: m["month"],
    )
    if len(rows) < 3:
        return []
    last, prior = rows[-1], rows[-4:-1]
    prior_rev = [float(m.get("revenue") or 0) for m in prior]
    if sum(1 for r in prior_rev if r > 0) < 2:
        return []
    avg = statistics.fmean(prior_rev)
    if avg <= 0:
        return []
    last_rev = float(last.get("revenue") or 0)
    month = last["month"]
    if last_rev <= 0:
        return [{
            "key": f"revenue_stopped:{month}",
            "kind": "revenue_stopped",
            "severity": "high",
            "title": f"No revenue recorded in {month}",
            "detail": (
                f"You averaged {avg:,.0f} a month before, and nothing was recorded for {month}. "
                "If sales happened, add them; if not, this needs attention."
            ),
            "entry_ids": [],
            "month": month,
        }]
    drop = (avg - last_rev) / avg
    if drop < 0.30:
        return []
    return [{
        "key": f"revenue_drop:{month}",
        "kind": "revenue_drop",
        "severity": "high" if drop >= 0.5 else "medium",
        "title": f"Revenue down {drop * 100:.0f}% in {month}",
        "detail": (
            f"{last_rev:,.0f} in {month} versus an average of {avg:,.0f} over the 3 months before. "
            "Check for missing entries, then look at what changed."
        ),
        "entry_ids": [],
        "month": month,
    }]


def detect_anomalies(entries: list[dict], fin: dict, current_month: str) -> list[dict]:
    if not entries or not _valid_month(current_month):
        return []
    symbol = (fin or {}).get("currency_symbol") or ""
    found = (
        detect_duplicates(entries, symbol)
        + detect_cross_source_duplicates(entries, current_month, symbol)
        + detect_outlier_expenses(entries, current_month, symbol)
        + detect_revenue_change((fin or {}).get("ledger_months") or [], current_month)
    )
    found.sort(key=lambda a: (-SEVERITY_RANK.get(a["severity"], 1), a["key"]))
    return found


async def store_anomalies(db, workspace_id: str, found: list[dict], now: datetime) -> dict:
    """Insert new findings once; resolve open ones whose condition is gone."""
    current_keys = {a["key"] for a in found}
    new = 0
    for a in found:
        if new >= MAX_ANOMALIES_PER_SCAN:
            break  # the rest arrive on later scans; they stay "current" so nothing resolves early
        flt = {"workspace_id": workspace_id, "key": a["key"]}
        if await db[ANOMALIES].find_one(flt, {"_id": 0, "id": 1}):
            continue
        doc = {
            "id": f"anom_{uuid.uuid4().hex[:12]}", **flt,
            "kind": a["kind"], "severity": a["severity"], "title": a["title"],
            "detail": a["detail"], "entry_ids": a.get("entry_ids") or [], "month": a.get("month"),
            "status": "open", "created_at": now.isoformat(),
        }
        try:
            await db[ANOMALIES].insert_one(doc)
            new += 1
        except Exception as exc:  # pragma: no cover - depends on the live unique index
            if not _is_duplicate_key(exc):
                raise
    resolved = 0
    open_rows = await db[ANOMALIES].find(
        {"workspace_id": workspace_id, "status": "open"}, {"_id": 0, "id": 1, "key": 1},
    ).to_list(200)
    for row in open_rows:
        if row.get("key") not in current_keys:
            await db[ANOMALIES].update_one(
                {"id": row["id"], "workspace_id": workspace_id, "status": "open"},
                {"$set": {"status": "resolved", "resolved_at": now.isoformat()}},
            )
            resolved += 1
    return {"new": new, "resolved": resolved}
