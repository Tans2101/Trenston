"""Recurring financial entry helpers — monthly/annual expansion for burn/runway.

Recurring rows are treated as rate commitments: when several recurring entries
share the same (type, category, cadence), each covers from its start month until
the next later start (exclusive), so logging Payroll every month as recurring
does not triple-count.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Optional


VALID_RECURRENCE = frozenset({"monthly", "annual"})


def normalize_recurrence(
    recurring: bool,
    recurrence: Optional[str],
    entry_type: str,
) -> Optional[str]:
    """Return a cadence string or None. Revenue recurring is always monthly (MRR)."""
    if not recurring:
        return None
    if (entry_type or "").strip().lower() == "revenue":
        return "monthly"
    value = (recurrence or "monthly").strip().lower()
    return value if value in VALID_RECURRENCE else "monthly"


def is_valid_month(month: str) -> bool:
    """True when month is a real YYYY-MM calendar month (01–12)."""
    s = (month or "").strip()
    if len(s) != 7 or s[4] != "-":
        return False
    try:
        datetime.strptime(s, "%Y-%m")
        return True
    except ValueError:
        return False


def current_month(now: Optional[datetime] = None) -> str:
    from datetime import timezone
    dt = now or datetime.now(timezone.utc)
    return dt.strftime("%Y-%m")


def is_future_month(month: str, now: Optional[datetime] = None) -> bool:
    """True when month is a valid YYYY-MM strictly after the real calendar month."""
    s = (month or "").strip()
    return is_valid_month(s) and s > current_month(now)


def is_current_or_past_month(month: str, now: Optional[datetime] = None) -> bool:
    s = (month or "").strip()
    return is_valid_month(s) and s <= current_month(now)


def partition_ledger_entries(
    entries: list[dict[str, Any]],
    now: Optional[datetime] = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split valid entries into (current_or_past, scheduled/upcoming future)."""
    current: list[dict[str, Any]] = []
    scheduled: list[dict[str, Any]] = []
    for e in entries or []:
        month = str(e.get("month") or "").strip()
        if not is_valid_month(month):
            continue
        if is_future_month(month, now):
            scheduled.append(e)
        else:
            current.append(e)
    return current, scheduled


def month_add(month: str, delta: int) -> str:
    """Shift YYYY-MM by delta months."""
    year, mon = map(int, month.split("-"))
    idx = year * 12 + (mon - 1) + delta
    return f"{idx // 12:04d}-{(idx % 12) + 1:02d}"


def months_inclusive(start: str, end: str) -> list[str]:
    """Inclusive month list from start..end (YYYY-MM). Empty if start > end."""
    if not start or not end or start > end:
        return []
    out: list[str] = []
    cur = start
    # Cap runaway loops (e.g. bad data) at 240 months / 20 years
    for _ in range(240):
        out.append(cur)
        if cur >= end:
            break
        cur = month_add(cur, 1)
    return out


def resolve_expense_horizon(
    entries: list[dict[str, Any]],
    now: Optional[datetime] = None,
    *,
    allow_future: bool = False,
) -> str:
    """Latest month to expand recurring entries through for burn/MRR/runway.

    Always capped at the real calendar month by default so a typo or synced
    scheduled invoice (e.g. 2027-01) cannot silently become the "current" month.
    Pass allow_future=True only for an explicit forward-looking view.
    """
    end = current_month(now)
    if not allow_future:
        return end
    months = [
        str(e.get("month"))
        for e in entries or []
        if e.get("month") and is_valid_month(str(e.get("month")))
    ]
    if months:
        end = max(end, max(months))
    return end
def expense_monthly_amount(entry: dict[str, Any]) -> float:
    """Monthlyized expense amount used in burn series (absolute; polarity via is_credit)."""
    import accounting_map as amap
    amount = amap.entry_amount_for_totals(entry)
    if not entry.get("recurring"):
        return amount
    cadence = normalize_recurrence(True, entry.get("recurrence"), "expense")
    if cadence == "annual":
        return round(amount / 12.0, 2)
    return amount


def revenue_monthly_amount(entry: dict[str, Any]) -> float:
    """Monthlyized recurring revenue (absolute; polarity via is_credit)."""
    import accounting_map as amap
    return amap.entry_amount_for_totals(entry)


def _signed(entry: dict[str, Any], amount: float) -> float:
    import accounting_map as amap
    return amap.entry_signed_amount(entry, amount)


def _monthlyized(entry: dict[str, Any], entry_type: str) -> float:
    if entry_type == "expense":
        return expense_monthly_amount(entry)
    return revenue_monthly_amount(entry)


def iter_expense_month_amounts(
    entry: dict[str, Any],
    horizon_end: str,
    *,
    series_end: Optional[str] = None,
) -> Iterable[tuple[str, float]]:
    """Yield (YYYY-MM, amount) for one expense entry.

    For recurring rows, `series_end` (inclusive) caps the projection — used when
    a later commitment of the same category/cadence supersedes this rate.
    Without series_end, expands through horizon_end (single-commitment case).
    Credits/refunds yield negative amounts.
    """
    if (entry.get("type") or "").strip().lower() != "expense":
        return
    start = (entry.get("month") or "").strip()
    if not start or not is_valid_month(start):
        return
    amount = float(entry.get("amount") or 0)
    if amount == 0:
        # Still allow amount_home / amount_net-only rows.
        import accounting_map as amap
        if amap.entry_amount_for_totals(entry) == 0:
            return

    if not entry.get("recurring"):
        if start <= horizon_end:
            import accounting_map as amap
            yield start, _signed(entry, amap.entry_amount_for_totals(entry))
        return

    end = horizon_end
    if series_end is not None:
        end = min(end, series_end)
    if start > end:
        return
    monthly = _signed(entry, expense_monthly_amount(entry))
    for month in months_inclusive(start, end):
        yield month, monthly


def expand_entries_by_month(
    entries: list[dict[str, Any]],
    *,
    entry_type: str,
    horizon_end: str,
) -> dict[str, float]:
    """Aggregate amounts by month for one entry type with non-overlapping recurring rates.

    - One-time rows: count only in their own month.
    - Recurring rows grouped by (category, cadence): sorted by start month; each
      covers until the month before the next start (or through horizon).
    - Credits/refunds (`is_credit`) subtract from the month total.
    """
    from collections import defaultdict

    by_month: dict[str, float] = defaultdict(float)
    one_time: list[dict] = []
    recurring: list[dict] = []
    want = (entry_type or "").strip().lower()

    for e in entries or []:
        if (e.get("type") or "").strip().lower() != want:
            continue
        month = (e.get("month") or "").strip()
        if not is_valid_month(month):
            continue
        if e.get("recurring"):
            recurring.append(e)
        else:
            one_time.append(e)

    for e in one_time:
        if e["month"] <= horizon_end:
            import accounting_map as amap
            by_month[e["month"]] += _signed(e, amap.entry_amount_for_totals(e))

    # Group recurring commitments
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for e in recurring:
        cat = (e.get("category") or "Other").strip() or "Other"
        cadence = normalize_recurrence(True, e.get("recurrence"), want) or "monthly"
        groups[(cat, cadence)].append(e)

    for (_cat, _cadence), group in groups.items():
        group.sort(key=lambda x: (x.get("month") or "", x.get("id") or ""))
        for i, e in enumerate(group):
            start = e["month"]
            # Cover until day before next commitment's start
            if i + 1 < len(group):
                next_start = group[i + 1]["month"]
                if next_start <= start:
                    # Same-month duplicate: later id wins for that month only
                    series_end = start
                else:
                    series_end = month_add(next_start, -1)
            else:
                series_end = horizon_end
            end = min(series_end, horizon_end)
            if start > end:
                continue
            monthly = _signed(e, _monthlyized(e, want))
            for month in months_inclusive(start, end):
                by_month[month] += monthly

    return dict(by_month)


def expand_expense_category_totals(
    entries: list[dict[str, Any]],
    horizon_end: str,
) -> dict[str, dict[str, float]]:
    """Build {YYYY-MM: {category: amount}} for expenses with non-overlapping rates."""
    from collections import defaultdict

    out: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    one_time: list[dict] = []
    recurring: list[dict] = []

    for e in entries or []:
        if (e.get("type") or "").strip().lower() != "expense":
            continue
        month = (e.get("month") or "").strip()
        if not is_valid_month(month):
            continue
        if e.get("recurring"):
            recurring.append(e)
        else:
            one_time.append(e)

    for e in one_time:
        if e["month"] <= horizon_end:
            cat = (e.get("category") or "Other").strip() or "Other"
            import accounting_map as amap
            out[e["month"]][cat] += _signed(e, amap.entry_amount_for_totals(e))

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for e in recurring:
        cat = (e.get("category") or "Other").strip() or "Other"
        cadence = normalize_recurrence(True, e.get("recurrence"), "expense") or "monthly"
        groups[(cat, cadence)].append(e)

    for (cat, _cadence), group in groups.items():
        group.sort(key=lambda x: (x.get("month") or "", x.get("id") or ""))
        for i, e in enumerate(group):
            start = e["month"]
            if i + 1 < len(group):
                next_start = group[i + 1]["month"]
                series_end = start if next_start <= start else month_add(next_start, -1)
            else:
                series_end = horizon_end
            end = min(series_end, horizon_end)
            if start > end:
                continue
            monthly = _signed(e, expense_monthly_amount(e))
            for month in months_inclusive(start, end):
                out[month][cat] += monthly

    return {m: dict(cats) for m, cats in out.items()}


def line_items_for_period(
    entries: list[dict[str, Any]],
    period: str,
    horizon_end: str,
) -> list[dict[str, Any]]:
    """Active ledger lines for one month using the same supersession as expand_entries_by_month.

    Each recurring (type, category, cadence) group contributes at most one rate that
    covers `period`. One-time rows count only when their month equals `period`.
    """
    from collections import defaultdict

    if not is_valid_month(period) or not is_valid_month(horizon_end):
        return []

    rows: list[dict[str, Any]] = []
    one_time: list[dict] = []
    recurring_by_type: dict[str, list[dict]] = {"revenue": [], "expense": []}

    for e in entries or []:
        entry_type = (e.get("type") or "").strip().lower()
        if entry_type not in ("revenue", "expense"):
            continue
        start = (e.get("month") or "").strip()
        if not is_valid_month(start):
            continue
        if e.get("recurring"):
            recurring_by_type[entry_type].append(e)
        else:
            one_time.append(e)

    for e in one_time:
        start = e["month"]
        if start != period or start > horizon_end:
            continue
        category = (e.get("category") or "Other").strip() or "Other"
        import accounting_map as amap
        rows.append({
            "name": e.get("name"),
            "category": category,
            "type": (e.get("type") or "").strip().lower(),
            "amount": amap.entry_amount_for_totals(e),
            # Magnitude above; credits/refunds (incl. legacy negative amounts) flagged here.
            "is_credit": amap.entry_signed_amount(e) < 0,
            "id": e.get("id"),
            "month": start,
            "recurring": False,
        })

    for entry_type, recurring in recurring_by_type.items():
        groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for e in recurring:
            cat = (e.get("category") or "Other").strip() or "Other"
            cadence = normalize_recurrence(True, e.get("recurrence"), entry_type) or "monthly"
            groups[(cat, cadence)].append(e)

        for (cat, _cadence), group in groups.items():
            group.sort(key=lambda x: (x.get("month") or "", x.get("id") or ""))
            for i, e in enumerate(group):
                start = e["month"]
                if i + 1 < len(group):
                    next_start = group[i + 1]["month"]
                    series_end = start if next_start <= start else month_add(next_start, -1)
                else:
                    series_end = horizon_end
                end = min(series_end, horizon_end)
                if start > end or period < start or period > end:
                    continue
                rows.append({
                    "name": e.get("name"),
                    "category": cat,
                    "type": entry_type,
                    "amount": float(_monthlyized(e, entry_type)),
                    "is_credit": _signed(e, 1.0) < 0,
                    "id": e.get("id"),
                    "month": start,
                    "recurring": True,
                })

    return rows
