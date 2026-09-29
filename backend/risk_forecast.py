"""Predictive risk alerts: deterministic projections from workspace data.

Each detector is pure, returns None when data is insufficient (never an
invented number), and emits a signal in the same shape as decision_engine's
other detectors so it flows through the existing Decision Center, Briefing
and alert pipeline. No LLM is used to compute anything here; the LLM drafting
step may only reword the text built below.

Every signal carries:
  what_would_change  deterministic advice, used as the recommendation when AI is off
  forecast           {metric, window, current_value, prior_value, projected_date,
                      confidence, data_points, ...} shown in the card detail
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from money_fmt import fmt_money_plain

# Cash runway forecast: warn when cash is projected to cross the founder's
# minimum reserve within this many days.
RESERVE_ALERT_HORIZON_DAYS = 180
RESERVE_HIGH_SEVERITY_DAYS = 60
# "Cutting burn by X" suggestion: X is this share of average monthly burn.
RESERVE_CUT_SUGGESTION_PCT = 0.10
DAYS_PER_MONTH = 30.44
FORECAST_MAX_MONTHS = 36
# Burn acceleration: burn rose in each of the last two complete months and by
# at least this much across the three-month window.
BURN_ACCEL_TOTAL_PCT = 0.25
BURN_ACCEL_HIGH_PCT = 0.60
# Revenue decline: each of the last two complete months is below its trailing
# three-month average by at least this much.
REVENUE_DECLINE_PCT = 0.15
REVENUE_DECLINE_HIGH_PCT = 0.30
# Team output: tasks completed in the last 4 weeks vs the 4 weeks before.
TEAM_TREND_WINDOW_DAYS = 28
TEAM_TREND_MIN_TASKS = 8
TEAM_TREND_DROP_PCT = 0.30
TEAM_TREND_HIGH_DROP_PCT = 0.60
# Pipeline coverage: open pipeline vs the sales targets set for the next 3 months.
PIPELINE_COVERAGE_MIN = 1.0
PIPELINE_COVERAGE_HIGH = 0.5

SIGNAL_TYPES = (
    "cash_runway_forecast",
    "burn_acceleration",
    "revenue_decline",
    "team_output_trend",
    "pipeline_coverage",
)


def _signal(type_: str, severity: str, summary: str, detail: str, **extra) -> dict:
    """Same shape as decision_engine._signal (kept local to avoid a circular import).

    notify_key is stable across days: summaries contain day counts that change
    daily, and alert debounce must not treat each day as a new alert.
    """
    return {
        "type": type_,
        "severity": severity,
        "summary": summary,
        "detail": detail,
        "related_id": None,
        "notify_key": f"{type_}:{severity}",
        **extra,
    }


def forecast_confidence(points: int) -> str:
    """Confidence label from how many data points a projection rests on."""
    if points >= 6:
        return "high"
    if points >= 3:
        return "medium"
    return "low"


def _parse_iso_dt(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _finite(value) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def complete_ledger_months(fin: dict) -> list:
    """Ledger rows for finished months only (the current month is still partial)."""
    current = str((fin or {}).get("current_month") or "")
    rows = []
    for r in (fin or {}).get("ledger_months") or []:
        m = str(r.get("month") or "")
        if not m or (current and m >= current):
            continue
        rev, exp = _finite(r.get("revenue")), _finite(r.get("expenses"))
        if rev is None or exp is None:
            continue
        rows.append({"month": m, "revenue": rev, "expenses": exp})
    rows.sort(key=lambda r: r["month"])
    return rows


def linear_slope(values: list) -> float:
    """Least-squares slope per step. 0 with fewer than 3 points."""
    n = len(values)
    if n < 3:
        return 0.0
    mean_x = (n - 1) / 2.0
    mean_y = sum(values) / n
    num = sum((i - mean_x) * (v - mean_y) for i, v in enumerate(values))
    den = sum((i - mean_x) ** 2 for i in range(n))
    return num / den if den else 0.0


def months_until_below(cash: float, reserve: float, avg_burn: float, slope: float,
                       *, max_months: int = FORECAST_MAX_MONTHS) -> Optional[float]:
    """Months until cash drops below reserve, with burn = avg_burn + slope*k in month k.

    0 when already below. None when it does not happen within max_months.
    """
    if cash < reserve:
        return 0.0
    c = cash
    for k in range(1, max_months + 1):
        nxt = c - (avg_burn + slope * k)
        if nxt < reserve:
            drop = c - nxt
            frac = (c - reserve) / drop if drop > 0 else 0.0
            return (k - 1) + frac
        c = nxt
    return None


def detect_cash_runway_forecast(fin: dict, *, today: Optional[date] = None) -> Optional[dict]:
    """Projected date cash crosses the founder's minimum reserve.

    Needs cash entered, a reserve set, and 2+ complete months of ledger data.
    Uses the last-3-month average burn plus its linear trend (up to 6 months).
    """
    if not fin or not fin.get("cash_entered"):
        return None
    reserve = _finite(fin.get("min_cash_reserve"))
    cash = _finite(fin.get("cash_value"))
    if reserve is None or cash is None:
        return None
    rows = complete_ledger_months(fin)
    if len(rows) < 2:
        return None
    today = today or datetime.now(timezone.utc).date()
    currency = fin.get("currency") or "usd"
    burns = [r["expenses"] - r["revenue"] for r in rows]
    recent = burns[-3:]
    avg_burn = sum(recent) / len(recent)
    trend_points = burns[-6:]
    slope = linear_slope(trend_points)
    months = months_until_below(cash, reserve, avg_burn, slope)
    if months is None:
        return None
    days = int(round(months * DAYS_PER_MONTH))
    if days > RESERVE_ALERT_HORIZON_DAYS:
        return None

    reserve_s = fmt_money_plain(reserve, currency)
    cash_s = fmt_money_plain(cash, currency)
    when = today + timedelta(days=days)
    window = f"{rows[-len(recent)]['month']} to {rows[-1]['month']}"
    cut = None
    days_after_cut = None

    if days == 0:
        summary = "Cash is below your minimum reserve"
        change = "Raise cash, cut burn, or lower the reserve in Financials if it no longer fits."
        detail = f"Cash is {cash_s}, below your minimum cash reserve of {reserve_s}. {change}"
    else:
        if avg_burn > 0:
            cut = avg_burn * RESERVE_CUT_SUGGESTION_PCT
            m2 = months_until_below(cash, reserve, avg_burn - cut, slope)
            days_after_cut = int(round(m2 * DAYS_PER_MONTH)) if m2 is not None else None
        if cut and days_after_cut is not None:
            change = (
                f"Cutting burn by {fmt_money_plain(cut, currency)} a month would move that to about "
                f"{days_after_cut} days ({(today + timedelta(days=days_after_cut)).isoformat()})."
            )
        elif cut:
            change = (
                f"Cutting burn by {fmt_money_plain(cut, currency)} a month would keep cash above "
                f"the reserve for at least {FORECAST_MAX_MONTHS} months at the current trend."
            )
        else:
            change = "Burn is rising from a low base. Review upcoming expenses before they land."
        summary = f"Minimum cash reserve reached in about {days} days"
        detail = (
            f"At your current burn you reach your minimum cash reserve of {reserve_s} in about "
            f"{days} days ({when.isoformat()}). Cash today is {cash_s}; average monthly burn over "
            f"{window} is {fmt_money_plain(avg_burn, currency)}. {change}"
        )

    return _signal(
        "cash_runway_forecast",
        "high" if days <= RESERVE_HIGH_SEVERITY_DAYS else "medium",
        summary=summary,
        detail=detail,
        category="Financial",
        runway_months=round(months, 2),
        days_until_reserve=days,
        what_would_change=change,
        forecast={
            "metric": "Cash vs minimum reserve",
            "window": window,
            "current_value": cash,
            "prior_value": None,
            "reserve": reserve,
            "average_burn": avg_burn,
            "burn_trend_per_month": slope,
            "projected_date": when.isoformat(),
            "cut_amount": cut,
            "projected_days_after_cut": days_after_cut,
            "confidence": forecast_confidence(len(trend_points)),
            "data_points": len(trend_points),
        },
    )


def detect_burn_acceleration(fin: dict) -> Optional[dict]:
    """Burn rose in each of the last two complete months and by >= BURN_ACCEL_TOTAL_PCT overall."""
    rows = complete_ledger_months(fin)
    if len(rows) < 3:
        return None
    last = rows[-3:]
    b = [r["expenses"] - r["revenue"] for r in last]
    if not (0 < b[0] < b[1] < b[2]):
        return None
    rise = (b[2] - b[0]) / b[0]
    if rise < BURN_ACCEL_TOTAL_PCT:
        return None
    currency = (fin or {}).get("currency") or "usd"
    pct = round(rise * 100, 1)
    window = f"{last[0]['month']} to {last[-1]['month']}"
    change = (
        "Check which expense categories grew in Financials. Bringing burn back to "
        f"{fmt_money_plain(b[0], currency)} a month would undo the increase."
    )
    return _signal(
        "burn_acceleration",
        "high" if rise >= BURN_ACCEL_HIGH_PCT else "medium",
        summary=f"Burn has risen {pct}% over three months",
        detail=(
            f"Net burn rose two months in a row, from {fmt_money_plain(b[0], currency)} to "
            f"{fmt_money_plain(b[2], currency)} a month ({window}). {change}"
        ),
        category="Financial",
        burn_delta_pct=pct,
        prev_amount=b[0],
        curr_amount=b[2],
        what_would_change=change,
        forecast={
            "metric": "Monthly net burn",
            "window": window,
            "current_value": b[2],
            "prior_value": b[0],
            "projected_date": None,
            "confidence": forecast_confidence(len(rows)),
            "data_points": len(rows),
        },
    )


def detect_revenue_decline(fin: dict) -> Optional[dict]:
    """Last two complete months each below their trailing 3-month average by >= REVENUE_DECLINE_PCT."""
    rows = complete_ledger_months(fin)
    if len(rows) < 5:
        return None
    rev = [r["revenue"] for r in rows]
    trail_prev = sum(rev[-5:-2]) / 3
    trail_last = sum(rev[-4:-1]) / 3
    if trail_prev <= 0 or trail_last <= 0:
        return None
    drop_prev = 1 - rev[-2] / trail_prev
    drop_last = 1 - rev[-1] / trail_last
    if drop_prev < REVENUE_DECLINE_PCT or drop_last < REVENUE_DECLINE_PCT:
        return None
    currency = (fin or {}).get("currency") or "usd"
    pct = round(drop_last * 100, 1)
    change = "Look at which customers or products fell off, and at the Sales pipeline for replacements."
    return _signal(
        "revenue_decline",
        "high" if drop_last >= REVENUE_DECLINE_HIGH_PCT else "medium",
        summary=f"Revenue is {pct}% below its recent average",
        detail=(
            "Revenue has been below its trailing three-month average for two months in a row. "
            f"{rows[-1]['month']}: {fmt_money_plain(rev[-1], currency)} vs an average of "
            f"{fmt_money_plain(trail_last, currency)}. {change}"
        ),
        category="Financial",
        prev_amount=trail_last,
        curr_amount=rev[-1],
        what_would_change=change,
        forecast={
            "metric": "Monthly revenue",
            "window": f"{rows[-5]['month']} to {rows[-1]['month']}",
            "current_value": rev[-1],
            "prior_value": trail_last,
            "projected_date": None,
            "confidence": forecast_confidence(len(rows)),
            "data_points": len(rows),
        },
    )


def _parse_due(due) -> Optional[date]:
    # Local import: decision_engine imports this module.
    from decision_engine import parse_task_due_date
    return parse_task_due_date(due)


def task_overdue_on(task: dict, day: date) -> bool:
    """Was this task overdue at the end of `day`? Uses due, created_at and done_at."""
    due_d = _parse_due(task.get("due"))
    if due_d is None or due_d >= day:
        return False
    created = _parse_iso_dt(task.get("created_at"))
    if created is not None and created.date() > day:
        return False
    done = _parse_iso_dt(task.get("done_at"))
    if done is not None:
        return done.date() > day
    # Done with no timestamp: we cannot tell when, so do not count it.
    return task.get("column") != "done"


def detect_team_output_trend(tasks: list, *, today: Optional[date] = None) -> Optional[dict]:
    """Tasks completed in the last 4 weeks vs the 4 weeks before (needs TEAM_TREND_MIN_TASKS prior)."""
    today = today or datetime.now(timezone.utc).date()
    w = TEAM_TREND_WINDOW_DAYS
    recent_start = today - timedelta(days=w)
    prior_start = today - timedelta(days=2 * w)
    recent = prior = 0
    for t in tasks or []:
        done = _parse_iso_dt(t.get("done_at"))
        if done is None:
            continue
        d = done.date()
        if recent_start <= d < today:
            recent += 1
        elif prior_start <= d < recent_start:
            prior += 1
    if prior < TEAM_TREND_MIN_TASKS:
        return None
    drop = 1 - recent / prior
    if drop < TEAM_TREND_DROP_PCT:
        return None
    overdue_now = sum(1 for t in tasks or [] if task_overdue_on(t, today))
    overdue_before = sum(1 for t in tasks or [] if task_overdue_on(t, recent_start))
    pct = round(drop * 100)
    change = "Check My Day blockers and whether work is being tracked as tasks, then rebalance or cut scope."
    return _signal(
        "team_output_trend",
        "high" if drop >= TEAM_TREND_HIGH_DROP_PCT else "medium",
        summary=f"Tasks completed have dropped {pct}% over four weeks",
        detail=(
            f"{recent} tasks were completed in the last four weeks, down from {prior} in the four weeks "
            f"before. Overdue tasks: {overdue_now} now, {overdue_before} four weeks ago. {change}"
        ),
        category="Team",
        what_would_change=change,
        forecast={
            "metric": "Tasks completed per four weeks",
            "window": f"{prior_start.isoformat()} to {today.isoformat()}",
            "current_value": recent,
            "prior_value": prior,
            "overdue_now": overdue_now,
            "overdue_four_weeks_ago": overdue_before,
            "projected_date": None,
            "confidence": forecast_confidence(prior + recent),
            "data_points": prior + recent,
        },
    )


def detect_pipeline_coverage(deals: list, targets: list | None, *, currency: str = "usd") -> Optional[dict]:
    """Open pipeline value vs sales targets set for the next 3 months. Silent with no targets."""
    total = 0.0
    months = []
    for row in targets or []:
        v = _finite((row or {}).get("target"))
        if v is None or v <= 0:
            continue
        total += v
        months.append(str(row.get("month") or ""))
    if total <= 0:
        return None
    open_value = 0.0
    for d in deals or []:
        if d.get("stage") in ("won", "lost"):
            continue
        v = _finite(d.get("value"))
        if v is not None and v > 0:
            open_value += v
    coverage = open_value / total
    if coverage >= PIPELINE_COVERAGE_MIN:
        return None
    pct = round(coverage * 100)
    gap = total - open_value
    months = sorted(m for m in months if m)
    window = f"{months[0]} to {months[-1]}" if months else "the next 3 months"
    change = f"Adding {fmt_money_plain(gap, currency)} of qualified pipeline would cover the targets."
    return _signal(
        "pipeline_coverage",
        "high" if coverage < PIPELINE_COVERAGE_HIGH else "medium",
        summary=f"Open pipeline covers {pct}% of your sales targets",
        detail=(
            f"Open deals total {fmt_money_plain(open_value, currency)} against "
            f"{fmt_money_plain(total, currency)} of sales targets for {window}. {change}"
        ),
        category="Financial",
        prev_amount=total,
        curr_amount=open_value,
        what_would_change=change,
        forecast={
            "metric": "Open pipeline vs sales targets",
            "window": window,
            "current_value": open_value,
            "prior_value": total,
            "projected_date": None,
            "confidence": forecast_confidence(len(months)),
            "data_points": len(months),
        },
    )


def collect(fin: dict, tasks: list, deals: list, sales_targets: list | None, *,
            today: date, currency: str = "usd") -> list:
    out = []
    for sig in (
        detect_cash_runway_forecast(fin, today=today),
        detect_burn_acceleration(fin),
        detect_revenue_decline(fin),
        detect_team_output_trend(tasks, today=today),
        detect_pipeline_coverage(deals, sales_targets, currency=currency),
    ):
        if sig:
            out.append(sig)
    return out


def dedupe_overlapping(signals: list) -> list:
    """One card per underlying condition.

    The reserve forecast is a sharper version of the "runway under 6 months"
    card, and burn acceleration supersedes a single-month burn increase.
    """
    types = {s.get("type") for s in signals or []}
    drop = set()
    if "cash_runway_forecast" in types:
        drop.add("runway_risk")
    if "burn_acceleration" in types:
        drop.add("burn_increase")
    return [s for s in signals or [] if s.get("type") not in drop]
