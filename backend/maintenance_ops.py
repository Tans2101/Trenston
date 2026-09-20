"""Engineering & Maintenance operational helpers: spares, schedules, AMCs, overhead.

Missing budgets / last_done / costs follow Financials not-entered convention —
never fabricate zeros or due dates from nothing.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional


def _parse_iso_dt(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _parse_date(raw: Any) -> Optional[date]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        if "T" in s:
            s = s.split("T", 1)[0]
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def equipment_key(name: Any) -> str:
    return (str(name or "")).strip().lower()


def enrich_spare(row: dict) -> dict:
    out = {k: v for k, v in row.items() if k != "_id"}
    try:
        qty = float(out.get("quantity_on_hand") or 0)
    except (TypeError, ValueError):
        qty = 0.0
    try:
        mn = float(out.get("minimum_threshold") or 0)
    except (TypeError, ValueError):
        mn = 0.0
    out["quantity_on_hand"] = qty
    out["minimum_threshold"] = mn
    out["is_below_threshold"] = qty < mn
    # Normalize legacy shapes so the UI never calls .filter on a string.
    names = out.get("equipment_names")
    if isinstance(names, str):
        names = [names] if names.strip() else []
    elif not isinstance(names, list):
        single = (out.get("equipment_name") or "").strip()
        names = [single] if single else []
    else:
        names = [str(n).strip() for n in names if str(n or "").strip()]
    out["equipment_names"] = names
    if not (out.get("equipment_name") or "").strip() and names:
        out["equipment_name"] = names[0]
    return out


def spares_below_threshold(spares: list[dict]) -> list[dict]:
    return [s for s in (enrich_spare(r) for r in spares) if s["is_below_threshold"]]


def compute_next_due_at(last_done_at: Any, frequency_days: Any) -> Optional[str]:
    """next_due = last_done + frequency_days. None when last_done not established."""
    last = _parse_iso_dt(last_done_at)
    if last is None:
        return None
    try:
        days = int(frequency_days)
    except (TypeError, ValueError):
        return None
    if days <= 0:
        return None
    due = last + timedelta(days=days)
    return due.astimezone(timezone.utc).isoformat()


def enrich_schedule(row: dict, *, today: Optional[date] = None) -> dict:
    out = {k: v for k, v in row.items() if k != "_id"}
    next_due = compute_next_due_at(out.get("last_done_at"), out.get("frequency_days"))
    out["next_due_at"] = next_due
    out["schedule_established"] = bool(out.get("last_done_at"))
    due_d = _parse_iso_dt(next_due)
    today = today or datetime.now(timezone.utc).date()
    if due_d is None:
        out["is_overdue"] = False
    else:
        out["is_overdue"] = due_d.astimezone(timezone.utc).date() < today
    return out


def overdue_schedules(rows: list[dict], *, today: Optional[date] = None) -> list[dict]:
    return [s for s in (enrich_schedule(r, today=today) for r in rows) if s["is_overdue"]]


def enrich_contract(row: dict, *, today: Optional[date] = None, soon_days: int = 30) -> dict:
    out = {k: v for k, v in row.items() if k != "_id"}
    today = today or datetime.now(timezone.utc).date()
    end = _parse_date(out.get("coverage_end"))
    renewal = _parse_date(out.get("renewal_date")) or end
    out["renewal_effective"] = renewal.isoformat() if renewal else None
    out["expired"] = bool(end and end < today)
    if renewal is None:
        out["renewal_due_soon"] = False
    else:
        delta = (renewal - today).days
        out["renewal_due_soon"] = (not out["expired"]) and 0 <= delta <= soon_days
    return out


def contracts_needing_attention(rows: list[dict], *, today: Optional[date] = None) -> list[dict]:
    out = []
    for r in rows:
        e = enrich_contract(r, today=today)
        if e["expired"] or e["renewal_due_soon"]:
            out.append(e)
    return out


def overhead_rollup(
    *,
    ticket_costs: list[float],
    ledger_costs: list[float],
    budget: Any,
    budget_entered: bool,
) -> dict:
    actual = round(sum(float(x) for x in ticket_costs) + sum(float(x) for x in ledger_costs), 2)
    if not budget_entered or budget is None:
        return {
            "budget_entered": False,
            "budget": None,
            "actual": actual,
            "gap": None,
            "label": "no budget set",
        }
    try:
        b = float(budget)
    except (TypeError, ValueError):
        return {
            "budget_entered": False,
            "budget": None,
            "actual": actual,
            "gap": None,
            "label": "no budget set",
        }
    return {
        "budget_entered": True,
        "budget": round(b, 2),
        "actual": actual,
        "gap": round(actual - b, 2),
        "label": None,
    }
