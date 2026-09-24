"""Production daily output, overtime, and optional yield tracking.

Missing logs / inputs are "not logged" — never fabricated zeros.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

import tz_utils


DEFAULT_OVERTIME_RATE_PER_HOUR = 0.0  # unset until CEO configures
COMMON_UNITS = ("units", "kg", "liters", "boxes", "meters", "tons", "pieces")


def normalize_unit(raw: Any, *, required: bool = False, field: str = "unit") -> str:
    """Free-text unit (pick-list suggestion or custom). Never invent a default."""
    u = (str(raw).strip() if raw is not None else "")[:32]
    if required and not u:
        raise ValueError(f"{field} is required (e.g. kg, liters, boxes, or your own)")
    return u


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


def normalize_log_date(raw: Any) -> str:
    d = _parse_date(raw)
    if not d:
        raise ValueError("date must be YYYY-MM-DD")
    return d.isoformat()


def today_iso(ws: Optional[dict] = None) -> str:
    """Workspace-local production day (default Asia/Manila)."""
    return tz_utils.workspace_today_iso(ws)


def parse_nonneg_float(raw: Any, *, field: str) -> Optional[float]:
    if raw is None or raw == "":
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a number")
    if v < 0:
        raise ValueError(f"{field} must be non-negative")
    return v


def yield_ratio(output: Optional[float], input_qty: Optional[float]) -> Optional[float]:
    """output/input when both present and input > 0. Else None (not comparable)."""
    if output is None or input_qty is None:
        return None
    if input_qty <= 0:
        return None
    return round(float(output) / float(input_qty), 4)


def yield_pct(output: Optional[float], input_qty: Optional[float]) -> Optional[float]:
    r = yield_ratio(output, input_qty)
    if r is None:
        return None
    return round(r * 100.0, 1)


def units_comparable(output_unit: str, input_unit: str) -> bool:
    a = (output_unit or "").strip().lower()
    b = (input_unit or "").strip().lower()
    return bool(a and b and a == b)


def enrich_daily_log(log: dict, *, expected_yield_pct: Optional[float] = None) -> dict:
    out = {k: v for k, v in log.items() if k != "_id"}
    target = out.get("target_quantity")
    actual = out.get("actual_quantity")
    out["target_logged"] = target is not None
    out["actual_logged"] = actual is not None
    if target is not None and actual is not None and float(target) > 0:
        out["target_completion_pct"] = round(100.0 * float(actual) / float(target), 1)
        out["shortfall"] = round(float(target) - float(actual), 4)
    else:
        out["target_completion_pct"] = None
        out["shortfall"] = None

    in_qty = out.get("input_quantity")
    out_u = (out.get("unit") or "").strip()
    in_u = (out.get("input_unit") or "").strip()
    comparable = units_comparable(out_u, in_u)
    out["yield_comparable"] = comparable
    if comparable and in_qty is not None and actual is not None:
        out["actual_yield_pct"] = yield_pct(actual, in_qty)
    else:
        out["actual_yield_pct"] = None
        # When units differ, expose raw pair instead of a bogus ratio.
        out["yield_raw"] = {
            "output_quantity": actual,
            "output_unit": out_u or None,
            "input_quantity": in_qty,
            "input_unit": in_u or None,
        } if (actual is not None or in_qty is not None) else None

    ot_hours = out.get("overtime_hours")
    ot_rate = out.get("overtime_rate_per_hour")
    if ot_hours is not None and ot_rate is not None:
        out["overtime_cost"] = round(float(ot_hours) * float(ot_rate), 2)
    else:
        out["overtime_cost"] = None

    expected = expected_yield_pct
    if expected is None:
        expected = out.get("expected_yield_pct")
    out["expected_yield_pct"] = expected
    actual_y = out.get("actual_yield_pct")
    if actual_y is not None and expected is not None:
        # Flag when actual is meaningfully below expected (≥10 percentage points).
        drop = float(expected) - float(actual_y)
        out["yield_below_benchmark"] = drop >= 10.0
        out["yield_drop_pp"] = round(drop, 1)
    else:
        out["yield_below_benchmark"] = False
        out["yield_drop_pp"] = None
    return out


def rollup_work_order_logs(
    logs: list[dict],
    *,
    quantity_planned: Optional[float] = None,
    yield_tracking_enabled: bool = False,
    expected_yield_pct: Optional[float] = None,
) -> dict:
    """Cumulative actual vs planned for one work order from daily logs."""
    if not logs:
        return {
            "has_logs": False,
            "days_logged": 0,
            "cumulative_target": None,
            "cumulative_actual": None,
            "cumulative_shortfall": None,
            "vs_planned_pct": None,
            "quantity_planned": quantity_planned,
            "overtime_hours": None,
            "overtime_cost": None,
            "avg_actual_yield_pct": None,
            "yield_below_benchmark_days": 0,
        }

    enriched = [enrich_daily_log(l, expected_yield_pct=expected_yield_pct) for l in logs]
    targets = [float(e["target_quantity"]) for e in enriched if e.get("target_quantity") is not None]
    actuals = [float(e["actual_quantity"]) for e in enriched if e.get("actual_quantity") is not None]
    cum_target = round(sum(targets), 4) if targets else None
    cum_actual = round(sum(actuals), 4) if actuals else None
    shortfall = None
    if cum_target is not None and cum_actual is not None:
        shortfall = round(cum_target - cum_actual, 4)

    vs_planned = None
    if quantity_planned is not None and float(quantity_planned) > 0 and cum_actual is not None:
        vs_planned = round(100.0 * cum_actual / float(quantity_planned), 1)

    ot_hours = [float(e["overtime_hours"]) for e in enriched if e.get("overtime_hours") is not None]
    ot_costs = [float(e["overtime_cost"]) for e in enriched if e.get("overtime_cost") is not None]
    yields = [float(e["actual_yield_pct"]) for e in enriched if e.get("actual_yield_pct") is not None]
    below = sum(1 for e in enriched if e.get("yield_below_benchmark"))

    return {
        "has_logs": True,
        "days_logged": len(enriched),
        "cumulative_target": cum_target,
        "cumulative_actual": cum_actual,
        "cumulative_shortfall": shortfall,
        "vs_planned_pct": vs_planned,
        "quantity_planned": quantity_planned,
        "overtime_hours": round(sum(ot_hours), 2) if ot_hours else None,
        "overtime_cost": round(sum(ot_costs), 2) if ot_costs else None,
        "avg_actual_yield_pct": round(sum(yields) / len(yields), 1) if yields and yield_tracking_enabled else None,
        "yield_below_benchmark_days": below if yield_tracking_enabled else 0,
    }


def department_day_summary(
    work_orders: list[dict],
    logs_by_wo: dict[str, list[dict]],
    *,
    day: Optional[str] = None,
) -> dict:
    """Today's total target vs actual across active work orders.

    Totals are only summed when all logged rows share one unit. Mixed units
    return per-unit breakdowns instead of a bogus combined number.
    """
    day = day or today_iso()
    active = [
        wo for wo in work_orders
        if (wo.get("status") or "") != "completed"
    ]
    ot_hours: list[float] = []
    ot_costs: list[float] = []
    orders_with_log = 0
    orders_missing_log = 0
    # unit_key → {target, actual, shortfall contributions}
    by_unit: dict[str, dict] = {}

    for wo in active:
        wid = wo.get("id")
        logs = logs_by_wo.get(wid) or []
        today_logs = [l for l in logs if (l.get("date") or "")[:10] == day]
        if not today_logs:
            orders_missing_log += 1
            continue
        orders_with_log += 1
        wo_unit = (wo.get("unit") or "").strip()
        for log in today_logs:
            e = enrich_daily_log(log, expected_yield_pct=wo.get("expected_yield_pct"))
            u = (e.get("unit") or wo_unit or "").strip() or "(no unit)"
            bucket = by_unit.setdefault(u, {"unit": u, "target": 0.0, "actual": 0.0,
                                            "has_target": False, "has_actual": False})
            if e.get("target_quantity") is not None:
                bucket["target"] += float(e["target_quantity"])
                bucket["has_target"] = True
            if e.get("actual_quantity") is not None:
                bucket["actual"] += float(e["actual_quantity"])
                bucket["has_actual"] = True
            if e.get("overtime_hours") is not None:
                ot_hours.append(float(e["overtime_hours"]))
            if e.get("overtime_cost") is not None:
                ot_costs.append(float(e["overtime_cost"]))

    unit_rows = []
    for u, b in sorted(by_unit.items(), key=lambda kv: kv[0]):
        t = round(b["target"], 4) if b["has_target"] else None
        a = round(b["actual"], 4) if b["has_actual"] else None
        unit_rows.append({
            "unit": u if u != "(no unit)" else "",
            "total_target": t,
            "total_actual": a,
            "shortfall": (
                round(t - a, 4) if t is not None and a is not None else None
            ),
        })

    mixed = len(unit_rows) > 1
    single = unit_rows[0] if len(unit_rows) == 1 else None
    total_target = single["total_target"] if single and not mixed else None
    total_actual = single["total_actual"] if single and not mixed else None
    # When mixed, do not invent a combined total — callers show by_unit.
    if mixed:
        total_target = None
        total_actual = None

    return {
        "date": day,
        "active_work_orders": len(active),
        "orders_with_log": orders_with_log,
        "orders_missing_log": orders_missing_log,
        "has_data": orders_with_log > 0,
        "mixed_units": mixed,
        "unit": (single["unit"] if single else None),
        "by_unit": unit_rows,
        "total_target": total_target,
        "total_actual": total_actual,
        "shortfall": (
            round(total_target - total_actual, 4)
            if total_target is not None and total_actual is not None
            else None
        ),
        "overtime_hours": round(sum(ot_hours), 2) if ot_hours else None,
        "overtime_cost": round(sum(ot_costs), 2) if ot_costs else None,
    }


def period_overtime_rollup(logs: list[dict]) -> dict:
    hours = []
    costs = []
    for log in logs:
        e = enrich_daily_log(log)
        if e.get("overtime_hours") is not None:
            hours.append(float(e["overtime_hours"]))
        if e.get("overtime_cost") is not None:
            costs.append(float(e["overtime_cost"]))
    return {
        "has_data": bool(hours or costs),
        "overtime_hours": round(sum(hours), 2) if hours else None,
        "overtime_cost": round(sum(costs), 2) if costs else None,
        "days_with_overtime": len(hours),
    }
