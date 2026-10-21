"""The living company map: money, promises and problems as one picture.

Everything here is read from records Trenston already holds (financial entries, tasks,
decisions, deals and the signals the decision engine detects). Nothing is estimated and
no model is called: a node exists only because a real record says so.

The shape is a small graph: hubs (Money in / Money out / Promises / People), leaf nodes
under each hub, Cash in the middle, and problems drawn as red nodes linked to whatever
they are about, each with a plain next step.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Optional

import accounting_map as amap
import decision_engine

MAX_INCOME = 4
MAX_EXPENSE = 5
MAX_PROMISES = 6
MAX_DECISIONS = 3
MAX_PROBLEMS = 8
MAX_PEOPLE = 8
PROMISE_WINDOW_DAYS = 14

# One plain next step per kind of problem, so a red node always says what to do about it.
NEXT_STEP: dict[str, str] = {
    "overdue_task": "Do it, move the date, or drop it.",
    "overdue_work_order": "Chase it or move the date.",
    "overdue_procurement": "Chase the supplier or change the date.",
    "overdue_procurement_blocking_production": "Call the supplier now; production is waiting.",
    "overdue_legal_deadline": "Deal with it or get the deadline moved.",
    "upcoming_legal_deadline": "Put time aside before it lands.",
    "urgent_maintenance": "Get it fixed or schedule the repair.",
    "chronic_equipment_failure": "Decide: repair properly or replace.",
    "stalled_deal": "Follow up this week, or close it as lost.",
    "missed_followup": "Send the follow-up today.",
    "stalled_department_item": "Ask the owner what is blocking it.",
    "pending_leave_request": "Approve or decline it.",
    "expense_spike": "Check the bills in that category.",
    "new_expense_category": "Check it is expected, then keep or cut it.",
    "runway_risk": "Cut spending or bring cash in.",
    "burn_increase": "Find what grew and decide if it stays.",
}

# Where a problem hangs on the map when it has no specific record to attach to.
_HUB_FOR_SIGNAL = {
    "runway_risk": "cash",
    "burn_increase": "out",
    "expense_spike": "out",
    "new_expense_category": "out",
    "stalled_deal": "pipeline",
    "missed_followup": "pipeline",
    "pending_leave_request": "people",
}

ROUTE = {
    "financials": "/app/financials",
    "tasks": "/app/tasks",
    "decisions": "/app/decisions",
    "sales": "/app/sales",
    "people": "/app/people",
}


def _money(value: float, symbol: str) -> str:
    return f"{symbol}{abs(value):,.0f}" if value >= 0 else f"-{symbol}{abs(value):,.0f}"


def _latest_month(ledger_months: list, current_month: str) -> Optional[str]:
    months = sorted(
        m.get("month") for m in ledger_months or []
        if m.get("month") and m["month"] <= current_month
    )
    return months[-1] if months else None


def _group_top(entries: list, kind: str, month: str, limit: int) -> list[tuple[str, float]]:
    totals: dict[str, float] = defaultdict(float)
    for e in entries:
        if e.get("type") != kind or e.get("month") != month:
            continue
        label = (e.get("category") or e.get("name") or "Other").strip() or "Other"
        totals[label] += amap.entry_amount_for_totals(e)
    ranked = sorted(((k, v) for k, v in totals.items() if v > 0), key=lambda kv: -kv[1])
    top = ranked[:limit]
    rest = sum(v for _, v in ranked[limit:])
    if rest > 0:
        top.append(("Everything else", rest))
    return top


def _task_due(task: dict) -> Optional[date]:
    return decision_engine.parse_task_due_date(task.get("due"))


def build_company_map(
    *,
    fin: dict,
    entries: list,
    signals: list,
    deals: list,
    tasks: list,
    decisions: list,
    members: list,
    today: date,
    can_see_finance: bool,
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    sym = fin.get("currency_symbol") or "$"
    team = len(members or []) >= 2

    def node(**kw) -> dict[str, Any]:
        kw.setdefault("tone", "neutral")
        kw.setdefault("sub", "")
        kw.setdefault("to", "")
        nodes.append(kw)
        return kw

    def link(a: str, b: str, tone: str = "neutral") -> None:
        links.append({"source": a, "target": b, "tone": tone})

    ids: set[str] = set()

    def add(**kw) -> str:
        node(**kw)
        ids.add(kw["id"])
        return kw["id"]

    # ---------------------------------------------------------------- money
    if can_see_finance:
        cash_entered = bool(fin.get("cash_entered"))
        runway = fin.get("runway_months")
        if cash_entered:
            if fin.get("runway_no_burn"):
                runway_text = "Not burning cash"
            elif runway is not None:
                runway_text = f"{runway:g} months of runway"
            else:
                runway_text = "Add expenses to see runway"
            tone = "neutral"
            if runway is not None:
                tone = "bad" if runway < 3 else "warn" if runway < 6 else "ok"
            add(id="cash", kind="cash", group="cash", label="Cash",
                sub=f"{_money(float(fin.get('cash_value') or 0), sym)} · {runway_text}",
                tone=tone, to=ROUTE["financials"])
        else:
            add(id="cash", kind="cash", group="cash", label="Cash", sub="Add your cash balance",
                tone="neutral", to=ROUTE["financials"], placeholder=True)
            missing.append({"label": "Your cash balance", "to": ROUTE["financials"]})

        month = _latest_month(fin.get("ledger_months") or [], fin.get("current_month") or "")
        income = _group_top(entries, "revenue", month, MAX_INCOME) if month else []
        expense = _group_top(entries, "expense", month, MAX_EXPENSE) if month else []
        if income or deals:
            add(id="in", kind="hub", group="in", label="Money in",
                sub=f"{month}" if income else "", to=ROUTE["financials"])
            link("in", "cash", "ok")
        else:
            missing.append({"label": "Income", "to": ROUTE["financials"]})
        for i, (name, amount) in enumerate(income):
            nid = f"in:{i}"
            add(id=nid, kind="income", group="in", label=name, sub=_money(amount, sym),
                amount=round(amount, 2), tone="ok", to=ROUTE["financials"])
            link(nid, "in", "ok")
        if expense:
            add(id="out", kind="hub", group="out", label="Money out", sub=f"{month}", to=ROUTE["financials"])
            link("cash", "out")
        else:
            missing.append({"label": "Expenses", "to": ROUTE["financials"]})
        for i, (name, amount) in enumerate(expense):
            nid = f"out:{i}"
            add(id=nid, kind="expense", group="out", label=name, sub=_money(amount, sym),
                amount=round(amount, 2), to=ROUTE["financials"])
            link("out", nid)

    # ------------------------------------------------------------- pipeline
    open_deals = [d for d in deals or [] if d.get("stage") not in ("won", "lost")]
    if open_deals:
        if "in" not in ids:
            add(id="in", kind="hub", group="in", label="Money in", to=ROUTE["sales"])
            if "cash" in ids:
                link("in", "cash", "ok")
        values = [float(d["value"]) for d in open_deals if isinstance(d.get("value"), (int, float))]
        total = sum(values)
        sub = f"{len(open_deals)} open deal{'s' if len(open_deals) != 1 else ''}"
        if values and can_see_finance:
            sub += f" · {_money(total, sym)}"
        add(id="pipeline", kind="pipeline", group="in", label="Pipeline", sub=sub, to=ROUTE["sales"])
        link("pipeline", "in", "ok")
    else:
        missing.append({"label": "Deals you're chasing", "to": ROUTE["sales"]})

    # ------------------------------------------------------------- promises
    open_tasks = [t for t in tasks or [] if t.get("column") != "done"]
    dated = []
    for t in open_tasks:
        d = _task_due(t)
        if d is not None and d <= today + timedelta(days=PROMISE_WINDOW_DAYS):
            dated.append((d, t))
    dated.sort(key=lambda p: p[0])
    pending = [d for d in decisions or [] if d.get("status") == "pending"]
    upcoming_legal = [s for s in signals if s.get("type") == "upcoming_legal_deadline"]

    if dated or pending or upcoming_legal:
        add(id="promises", kind="hub", group="promises", label="Promises & deadlines",
            sub="Next 14 days", to=ROUTE["tasks"])
    else:
        missing.append({"label": "Tasks and deadlines", "to": ROUTE["tasks"]})

    for d, t in dated[:MAX_PROMISES]:
        days = (d - today).days
        if days < 0:
            when, tone = f"{-days} day{'s' if days != -1 else ''} late", "bad"
        elif days == 0:
            when, tone = "Due today", "warn"
        else:
            when, tone = f"Due in {days} day{'s' if days != 1 else ''}", "warn" if days <= 3 else "neutral"
        nid = f"task:{t.get('id')}"
        add(id=nid, kind="task", group="promises", label=t.get("title") or "Untitled task",
            sub=f"{when}" + (f" · {t.get('assignee')}" if team and t.get("assignee") else ""),
            tone=tone, to=ROUTE["tasks"])
        link("promises", nid, tone if tone == "bad" else "neutral")

    for dct in pending[:MAX_DECISIONS]:
        nid = f"decision:{dct.get('id')}"
        due = (dct.get("due") or "").strip()
        add(id=nid, kind="decision", group="promises", label=dct.get("title") or "Untitled decision",
            sub="Waiting on you" + (f" · due {due}" if due and due != "—" else ""),
            tone="warn", to=ROUTE["decisions"])
        link("promises", nid, "warn")
    if len(pending) > MAX_DECISIONS and "promises" in ids:
        extra = len(pending) - MAX_DECISIONS
        add(id="decision:more", kind="decision", group="promises",
            label=f"{extra} more decision{'s' if extra != 1 else ''} waiting", tone="warn", to=ROUTE["decisions"])
        link("promises", "decision:more", "warn")

    for i, s in enumerate(upcoming_legal[:3]):
        nid = f"legal:{s.get('related_id') or i}"
        add(id=nid, kind="deadline", group="promises", label=s.get("summary") or "Legal deadline",
            sub="Coming up", tone="warn", to="/app/departments/legal")
        link("promises", nid, "warn")

    # --------------------------------------------------------------- people
    if team:
        counts: dict[str, dict[str, int]] = defaultdict(lambda: {"open": 0, "late": 0})
        for t in open_tasks:
            uid = t.get("assignee_user_id")
            if not uid:
                continue
            counts[uid]["open"] += 1
            d = _task_due(t)
            if d is not None and d < today:
                counts[uid]["late"] += 1
        add(id="people", kind="hub", group="people", label="Your team", sub=f"{len(members)} people", to=ROUTE["people"])
        busiest = sorted(members, key=lambda m: -counts[m["user_id"]]["open"])[:MAX_PEOPLE]
        for m in busiest:
            c = counts[m["user_id"]]
            nid = f"person:{m['user_id']}"
            sub = f"{c['open']} open" + (f" · {c['late']} late" if c["late"] else "")
            add(id=nid, kind="person", group="people", label=m.get("name") or "Teammate", sub=sub,
                tone="bad" if c["late"] else "neutral", to=ROUTE["people"])
            link("people", nid, "bad" if c["late"] else "neutral")

    # ------------------------------------------------------------- problems
    rank = {"high": 0, "medium": 1}
    problems = [
        s for s in signals
        if s.get("severity") in rank
        and s.get("type") != "upcoming_legal_deadline"
        and (can_see_finance or not decision_engine.is_financial_signal(s))
    ]
    problems.sort(key=lambda s: rank[s["severity"]])
    for i, s in enumerate(problems[:MAX_PROBLEMS]):
        stype = s.get("type") or ""
        related = s.get("related_id")
        target = None
        for prefix in ("task", "legal"):
            cand = f"{prefix}:{related}"
            if related and cand in ids:
                target = cand
                break
        if target is None:
            hub = _HUB_FOR_SIGNAL.get(stype, "promises")
            fallbacks = [hub, "promises", "cash", "people"]
            target = next((h for h in fallbacks if h in ids), None)
        nid = f"problem:{i}"
        tone = "bad" if s["severity"] == "high" else "warn"
        add(id=nid, kind="problem", group="problems", label=s.get("summary") or "Needs a look",
            sub=s.get("detail") or "", action=NEXT_STEP.get(stype, "Open it and decide what to do."),
            tone=tone, severity=s["severity"], signal_type=stype)
        if target:
            link(nid, target, tone)

    leaf_kinds = {"income", "expense", "pipeline", "task", "decision", "deadline", "person", "problem"}
    has_content = any(n["kind"] in leaf_kinds for n in nodes)
    return {
        "ready": has_content,
        "mode": "team" if team else "solo",
        "can_see_finance": can_see_finance,
        "nodes": nodes,
        "links": links,
        "missing": missing,
        "problem_count": sum(1 for n in nodes if n["kind"] == "problem"),
        "as_of": today.isoformat(),
    }
