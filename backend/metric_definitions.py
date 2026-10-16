"""Trenston's metric definitions: one place that says what each number means.

This is the "semantic layer" of the data model (see docs/DATA_MODEL.md).
Every surface that shows cash, burn, runway, MRR or ARR (Financials, Home,
Metrics, the AI, alerts, the public API, the reserve forecast and the Model
page baseline) must get its numbers from here or from compute_financials,
which calls here. Do not re-derive these formulas anywhere else.

Rules that hold for every metric:
- A figure that was never entered is None ("unknown"), never 0.
- The current month is still in progress, so averages use completed months.
  Only when no completed month exists yet does the current month count.
- Money is in the workspace's home currency (amount_home when present).
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Optional

import modeling

# How many completed months the average burn looks back over. The Model page
# baseline and the cash reserve forecast use the same window.
BURN_WINDOW_MONTHS = 3


def _finite(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def burn_basis(ledger_months: list, current_month: str, *, window: int = BURN_WINDOW_MONTHS) -> dict:
    """Average monthly revenue, expenses and net burn over the burn window.

    Returns {"revenue", "expenses", "net_burn", "months", "includes_current_month"}.
    net_burn is signed: positive means spending more than earning, negative
    means cash is growing. All values are None when there is no ledger data.

    Shares modeling.average_recent so the Financials runway and the Model
    page's "current trajectory" start from exactly the same numbers.
    """
    avg = modeling.average_recent(ledger_months, current_month, window=window)
    months = list(avg.get("months") or [])
    if avg.get("revenue") is None or avg.get("expenses") is None or not months:
        return {
            "revenue": None, "expenses": None, "net_burn": None,
            "months": [], "includes_current_month": False,
        }
    return {
        "revenue": avg["revenue"],
        "expenses": avg["expenses"],
        "net_burn": avg["expenses"] - avg["revenue"],
        "months": months,
        "includes_current_month": bool(current_month) and current_month in months,
    }


def runway_months(cash: Optional[float], net_burn: Optional[float]) -> Optional[float]:
    """Months of cash left at the average net burn, to one decimal place.

    None when cash is unknown or when there is no burn (cash flat or growing).
    0 when cash is zero or negative and the company is burning.
    """
    c = _finite(cash)
    b = _finite(net_burn)
    if c is None or b is None or b <= 0:
        return None
    return round(max(c, 0.0) / b, 1)


def is_cash_growing(cash: Optional[float], net_burn: Optional[float]) -> bool:
    """Cash entered and revenue covers expenses over the window (no runway limit)."""
    return _finite(cash) is not None and _finite(net_burn) is not None and float(net_burn) <= 0


def month_label(month: str) -> str:
    try:
        return datetime.strptime(month, "%Y-%m").strftime("%b %Y")
    except (TypeError, ValueError):
        return str(month or "")


def describe_window(months: list) -> str:
    """'Jul 2026 to Sep 2026', 'Sep 2026', or '' for no months."""
    months = [m for m in (months or []) if m]
    if not months:
        return ""
    if len(months) == 1:
        return month_label(months[0])
    return f"{month_label(months[0])} to {month_label(months[-1])}"


def runway_basis_text(basis: dict) -> str:
    """One plain sentence saying which months the runway is based on."""
    months = basis.get("months") or []
    if not months:
        return ""
    span = describe_window(months)
    n = len(months)
    noun = "month" if n == 1 else f"{n} months"
    text = f"Based on average net burn over {span}" if n > 1 else f"Based on net burn in {span}"
    if basis.get("includes_current_month"):
        text += " (this month is still in progress, so treat it as an early estimate)"
    elif n < BURN_WINDOW_MONTHS:
        text += f" (only {noun} of history so far)"
    return text + "."


# Plain-language definitions. The glossary on the site, the AI's system
# context and docs/DATA_MODEL.md all follow these. Keys match the fields
# compute_financials returns.
METRICS: dict[str, dict[str, str]] = {
    "cash": {
        "label": "Cash in bank",
        "definition": "The bank balance you entered on Financials.",
        "formula": "Entered by a finance editor. Not calculated.",
        "when_unknown": "Never entered. Runway cannot be calculated.",
    },
    "net_burn": {
        "label": "Net burn",
        "definition": "How much more you spend than you earn in a month.",
        "formula": "Expenses minus revenue for the month, in your home currency. Negative means net income.",
        "when_unknown": "No revenue or expenses logged yet.",
    },
    "average_net_burn": {
        "label": "Average net burn",
        "definition": "Net burn averaged over the last 3 completed months.",
        "formula": "Mean of (expenses minus revenue) over the last 3 completed months. The current month counts only when no month is complete yet.",
        "when_unknown": "No revenue or expenses logged yet.",
    },
    "runway": {
        "label": "Runway",
        "definition": "How many months your cash lasts at your recent average net burn.",
        "formula": "Cash in bank divided by average net burn, rounded to one decimal.",
        "when_unknown": "Needs cash in bank and at least one month of entries. When revenue covers expenses there is no runway limit.",
    },
    "mrr": {
        "label": "MRR",
        "definition": "Monthly recurring revenue: revenue marked as recurring, in the latest month with data.",
        "formula": "Sum of recurring revenue for the latest ledger month. One-time sales are never included.",
        "when_unknown": "No recurring revenue logged. One-time sales do not make MRR $0.",
    },
    "arr": {
        "label": "ARR",
        "definition": "Annual recurring revenue.",
        "formula": "MRR times 12.",
        "when_unknown": "Unknown whenever MRR is unknown.",
    },
    "gross_margin": {
        "label": "Gross margin",
        "definition": "The share of revenue left after the direct cost of delivering it.",
        "formula": "Entered by a finance editor as a percentage. Not calculated.",
        "when_unknown": "Never entered.",
    },
}


def definitions() -> list[dict[str, str]]:
    return [{"key": k, **v} for k, v in METRICS.items()]
