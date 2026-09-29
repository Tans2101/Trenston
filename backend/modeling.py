"""Deterministic cash projection for the Financial Modeling page.

This module is the reference implementation. frontend/src/lib/modeling.js is
a line-for-line port so sliders can recompute in the browser with no network
call. Both are checked against shared/modeling-parity.json; change one and the
parity tests fail until the other matches.

No LLM is involved anywhere in this file. Missing inputs stay None and the
result says why a figure cannot be computed ("no_cash", "no_ledger") instead
of inventing a number.
"""
from __future__ import annotations

import math
import re
from typing import Any, Optional

# Driver bounds. Mirrored in modeling.js and enforced by the scenario API.
GROWTH_PCT_MIN = -50.0
GROWTH_PCT_MAX = 100.0
HORIZONS = (12, 24, 36)
DEFAULT_HORIZON = 24
MAX_HIRES = 20
MAX_EVENTS = 20
MAX_LABEL_LEN = 60
MAX_MONEY = 1e12

# Status values for the headline runway result.
RUNWAY_MONTHS = "months"          # runs out inside the horizon; runway_months set
RUNWAY_CASH_GROWING = "cash_growing"  # every month is net positive
RUNWAY_BEYOND = "beyond_horizon"  # burning, but cash lasts past the horizon
RUNWAY_NO_CASH = "no_cash"        # cash balance not entered
RUNWAY_NO_LEDGER = "no_ledger"    # no revenue or expense data at all


# Plain decimal numbers only, so Python and JS parse exactly the same strings
# (float() also takes "1_000", "nan", "inf"; JS Number() takes "0x10" and "").
_NUMERIC_RE = re.compile(r"^\s*[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?\s*$")


def _num(value: Any, default: Optional[float] = None) -> Optional[float]:
    """Finite float or default. Rejects bool, NaN, Infinity and non-decimal strings."""
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, str):
        if not _NUMERIC_RE.match(value):
            return default
    elif not isinstance(value, (int, float)):
        return default
    try:
        f = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(f):
        return default
    return f


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _label(value: Any) -> str:
    # Non-strings become "" (str(True) and JS String(true) disagree on case).
    if not isinstance(value, str):
        return ""
    return value.strip()[:MAX_LABEL_LEN]


def _int_in(value: Any, lo: int, hi: int, default: int) -> int:
    f = _num(value)
    if f is None:
        return default
    return int(_clamp(math.floor(f), lo, hi))


def sanitize_inputs(raw: Any) -> dict:
    """Clamp every driver into bounds. Never raises; bad values fall back to defaults."""
    raw = raw if isinstance(raw, dict) else {}
    horizon = _int_in(raw.get("horizon"), 0, 1000, DEFAULT_HORIZON)
    if horizon not in HORIZONS:
        horizon = DEFAULT_HORIZON

    hires = []
    for h in (raw.get("hires") or [])[:MAX_HIRES] if isinstance(raw.get("hires"), list) else []:
        if not isinstance(h, dict):
            continue
        hires.append({
            "label": _label(h.get("label")),
            "monthly_cost": _clamp(_num(h.get("monthly_cost"), 0.0), 0.0, MAX_MONEY),
            "start_month": _int_in(h.get("start_month"), 1, horizon, 1),
        })

    events = []
    for e in (raw.get("events") or [])[:MAX_EVENTS] if isinstance(raw.get("events"), list) else []:
        if not isinstance(e, dict):
            continue
        events.append({
            "label": _label(e.get("label")),
            "amount": _clamp(_num(e.get("amount"), 0.0), -MAX_MONEY, MAX_MONEY),
            "month": _int_in(e.get("month"), 1, horizon, 1),
        })

    reserve = _num(raw.get("min_cash_reserve"))
    if reserve is not None:
        reserve = _clamp(reserve, 0.0, MAX_MONEY)

    return {
        "revenue_growth_pct": _clamp(_num(raw.get("revenue_growth_pct"), 0.0), GROWTH_PCT_MIN, GROWTH_PCT_MAX),
        "expense_growth_pct": _clamp(_num(raw.get("expense_growth_pct"), 0.0), GROWTH_PCT_MIN, GROWTH_PCT_MAX),
        "hires": hires,
        "events": events,
        "min_cash_reserve": reserve,
        "horizon": horizon,
    }


def add_months(ym: str, n: int) -> str:
    """'2026-09' + 3 -> '2026-12'. Invalid input returns ''."""
    try:
        y, m = (int(p) for p in str(ym).split("-")[:2])
    except (TypeError, ValueError):
        return ""
    if not (1 <= m <= 12):
        return ""
    idx = y * 12 + (m - 1) + int(n)
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def project_cash(inputs: Any, baseline: Any) -> dict:
    """Project month-by-month revenue, expenses and cash from a baseline.

    baseline: {cash, revenue, expenses, start_month}
      cash      cash in bank today, or None when not entered
      revenue   average monthly revenue, or None when there is no ledger
      expenses  average monthly expenses, or None when there is no ledger
      start_month  'YYYY-MM' of the current month; month 1 is the next month

    Month m (1..horizon):
      revenue_m  = revenue  * (1 + g_rev)^m
      expenses_m = expenses * (1 + g_exp)^m + sum(hire.monthly_cost for hires started by m)
      net_m      = revenue_m - expenses_m + sum(one-time event amounts in m)
      cash_m     = cash_{m-1} + net_m
    """
    x = sanitize_inputs(inputs)
    b = baseline if isinstance(baseline, dict) else {}
    cash0 = _num(b.get("cash"))
    rev0 = _num(b.get("revenue"))
    exp0 = _num(b.get("expenses"))
    start = str(b.get("start_month") or "")
    horizon = x["horizon"]
    reserve = x["min_cash_reserve"]

    result: dict = {
        "horizon": horizon,
        "points": [],
        "runway_status": RUNWAY_NO_LEDGER,
        "runway_months": None,
        "cash_out_month": None,
        "reserve_breach_month": None,
        "break_even_month": None,
        "ending_cash": None,
        "cash_known": cash0 is not None,
        "ledger_known": rev0 is not None or exp0 is not None,
    }
    if rev0 is None and exp0 is None:
        return result

    rev0 = rev0 or 0.0
    exp0 = exp0 or 0.0
    g_rev = x["revenue_growth_pct"] / 100.0
    g_exp = x["expense_growth_pct"] / 100.0

    cash = cash0
    all_positive = True
    points = []
    for m in range(1, horizon + 1):
        revenue = rev0 * (1.0 + g_rev) ** m
        expenses = exp0 * (1.0 + g_exp) ** m
        for h in x["hires"]:
            if h["start_month"] <= m:
                expenses += h["monthly_cost"]
        one_time = 0.0
        for e in x["events"]:
            if e["month"] == m:
                one_time += e["amount"]
        net = revenue - expenses + one_time
        if net < 0:
            all_positive = False
        if result["break_even_month"] is None and revenue >= expenses and revenue > 0:
            result["break_even_month"] = m

        prev_cash = cash
        if cash is not None:
            cash = cash + net
            if result["cash_out_month"] is None and cash < 0:
                result["cash_out_month"] = m
                # Linear interpolation inside the month cash crosses zero.
                span = prev_cash - cash
                frac = (prev_cash / span) if span > 0 and prev_cash > 0 else 0.0
                result["runway_months"] = (m - 1) + frac
            if reserve is not None and result["reserve_breach_month"] is None and cash < reserve:
                result["reserve_breach_month"] = m

        points.append({
            "m": m,
            "month": add_months(start, m),
            "revenue": revenue,
            "expenses": expenses,
            "net": net,
            "cash": cash,
        })

    result["points"] = points
    if cash0 is None:
        result["runway_status"] = RUNWAY_NO_CASH
        return result

    # Already below zero / below reserve before month 1.
    if cash0 < 0:
        result["cash_out_month"] = 0
        result["runway_months"] = 0.0
    if reserve is not None and cash0 < reserve:
        result["reserve_breach_month"] = 0

    result["ending_cash"] = cash
    if result["runway_months"] is not None:
        result["runway_status"] = RUNWAY_MONTHS
    elif all_positive:
        result["runway_status"] = RUNWAY_CASH_GROWING
    else:
        result["runway_status"] = RUNWAY_BEYOND
    return result


def baseline_inputs(inputs: Any) -> dict:
    """The 'current trajectory' comparison: no growth, hires or events; same reserve and horizon."""
    x = sanitize_inputs(inputs)
    return {
        "revenue_growth_pct": 0.0,
        "expense_growth_pct": 0.0,
        "hires": [],
        "events": [],
        "min_cash_reserve": x["min_cash_reserve"],
        "horizon": x["horizon"],
    }


def average_recent(ledger_months: list, current_month: str, *, window: int = 3) -> dict:
    """Average revenue/expenses over the last `window` complete months.

    The current month is still in progress, so it is excluded when at least
    one complete month exists (a half-finished month would understate both).
    """
    rows = [r for r in (ledger_months or []) if isinstance(r, dict) and r.get("month")]
    rows.sort(key=lambda r: r["month"])
    complete = [r for r in rows if r["month"] < current_month]
    use = (complete or rows)[-window:]
    if not use:
        return {"revenue": None, "expenses": None, "months": []}
    n = len(use)
    return {
        "revenue": sum(float(r.get("revenue") or 0) for r in use) / n,
        "expenses": sum(float(r.get("expenses") or 0) for r in use) / n,
        "months": [r["month"] for r in use],
    }
