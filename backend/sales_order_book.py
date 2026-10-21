"""Sales order book + monthly target helpers.

Settled definition (do not reopen): monthly target `actual` is ONLY the sum of
`sales_order_book` lines with `status == "confirmed"` whose attributed month
(`expected_close_month` when set, else YYYY-MM of `created_at`) equals that
month. The `deals` collection and deal stages are never consulted — a won deal
with no matching order-book line does not move actual at all.

Missing targets / empty books are "not set" / "no data" — never fabricated zeros.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

ORDER_BOOK_STATUSES = frozenset({"confirmed", "expected", "in_negotiation"})


def current_month(today: Optional[date] = None) -> str:
    d = today or datetime.now(timezone.utc).date()
    return f"{d.year:04d}-{d.month:02d}"


def add_months(ym: str, n: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    m += n
    while m > 12:
        m -= 12
        y += 1
    while m < 1:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}"


def next_n_months(n: int = 3, *, today: Optional[date] = None) -> list[str]:
    start = current_month(today)
    return [add_months(start, i) for i in range(n)]


def normalize_month(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if len(s) >= 7 and s[4] == "-":
        try:
            datetime.strptime(s[:7], "%Y-%m")
            return s[:7]
        except ValueError:
            return None
    return None


def _created_month(entry: dict) -> Optional[str]:
    return normalize_month(entry.get("created_at"))


def attribute_month(entry: dict) -> Optional[str]:
    """Month a line counts toward for targets / this-month rollups."""
    em = normalize_month(entry.get("expected_close_month"))
    if em:
        return em
    return _created_month(entry)


def compute_total(price: float, quantity: float) -> float:
    try:
        return round(float(price) * float(quantity), 2)
    except (TypeError, ValueError):
        return 0.0


def order_book_summary(
    entries: list[dict],
    *,
    month: Optional[str] = None,
    today: Optional[date] = None,
) -> dict:
    month = month or current_month(today)
    confirmed_this = 0.0
    expected_this = 0.0
    by_country: dict[str, dict] = {}
    by_product: dict[str, dict] = {}
    by_country_month: dict[str, dict] = {}
    by_product_month: dict[str, dict] = {}
    forward_months = next_n_months(3, today=today)
    forward: dict[str, dict] = {
        m: {"month": m, "expected": 0.0, "in_negotiation": 0.0, "confirmed": 0.0, "count": 0}
        for m in forward_months
    }

    for e in entries:
        status = (e.get("status") or "expected").strip().lower()
        try:
            total = float(e.get("total_value") or 0)
        except (TypeError, ValueError):
            total = 0.0
        country = (e.get("country") or "").strip() or "(no country)"
        product = (e.get("product") or "").strip() or "(no product)"
        attr = attribute_month(e)

        if attr == month:
            if status == "confirmed":
                confirmed_this += total
            elif status in ("expected", "in_negotiation"):
                expected_this += total
            cm = by_country_month.setdefault(
                country, {"country": country, "total_value": 0.0, "count": 0},
            )
            cm["total_value"] = round(cm["total_value"] + total, 2)
            cm["count"] += 1
            pm = by_product_month.setdefault(
                product, {"product": product, "total_value": 0.0, "count": 0},
            )
            pm["total_value"] = round(pm["total_value"] + total, 2)
            pm["count"] += 1

        c = by_country.setdefault(country, {"country": country, "total_value": 0.0, "count": 0})
        c["total_value"] = round(c["total_value"] + total, 2)
        c["count"] += 1
        p = by_product.setdefault(product, {"product": product, "total_value": 0.0, "count": 0})
        p["total_value"] = round(p["total_value"] + total, 2)
        p["count"] += 1

        if attr in forward:
            forward[attr]["count"] += 1
            if status == "confirmed":
                forward[attr]["confirmed"] = round(forward[attr]["confirmed"] + total, 2)
            elif status == "in_negotiation":
                forward[attr]["in_negotiation"] = round(forward[attr]["in_negotiation"] + total, 2)
            else:
                forward[attr]["expected"] = round(forward[attr]["expected"] + total, 2)

    return {
        "month": month,
        "confirmed_this_month": round(confirmed_this, 2),
        "expected_this_month": round(expected_this, 2),
        "by_country": sorted(by_country.values(), key=lambda x: -x["total_value"]),
        "by_product": sorted(by_product.values(), key=lambda x: -x["total_value"]),
        "by_country_this_month": sorted(
            by_country_month.values(), key=lambda x: -x["total_value"],
        ),
        "by_product_this_month": sorted(
            by_product_month.values(), key=lambda x: -x["total_value"],
        ),
        "forward_pipeline": [forward[m] for m in forward_months],
        "line_count": len(entries),
    }


def target_vs_actual(
    *,
    target_row: Optional[dict],
    confirmed_actual: float,
) -> dict:
    """Company-wide monthly target vs confirmed order-book actual only.

    `confirmed_actual` must be order-book confirmed sum for the month — never
    derived from won deals. No target set → target_entered false, no fabricated
    pct/gap.
    """
    entered = False
    target = None
    if target_row is not None and target_row.get("target") is not None:
        try:
            target = float(target_row["target"])
            entered = True
        except (TypeError, ValueError):
            target = None
            entered = False

    try:
        actual = round(float(confirmed_actual or 0), 2)
    except (TypeError, ValueError):
        actual = 0.0
    if not entered:
        return {
            "target_entered": False,
            "target": None,
            "actual": actual,
            "gap": None,
            "pct_of_target": None,
            "label": "no target set",
        }
    gap = round(actual - float(target), 2)
    pct = round(100.0 * actual / float(target), 1) if float(target) > 0 else None
    return {
        "target_entered": True,
        "target": round(float(target), 2),
        "actual": actual,
        "gap": gap,
        "pct_of_target": pct,
        "label": None,
    }
