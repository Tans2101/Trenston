"""Shared financial_entries shape for QuickBooks, Xero, and SAP B1 mappers.

Stable qb_txn_id format (no dates): `{source}_{entity_type}_{provider_id}`.
See backend/scripts/migrate_qb_txn_ids.py for rewriting legacy dated ids.

Downstream totals prefer amount_net (net of tax) converted via amount_home.
Entries without currency default to the workspace home currency.
"""
from __future__ import annotations

from typing import Any, Optional

# Single fallback for uncategorized line items across all accounting sources.
DEFAULT_UNCATEGORIZED = "Other"


def fallback_category(category: Optional[str]) -> str:
    return (str(category or "").strip() or DEFAULT_UNCATEGORIZED)


def normalize_mapped_amount(raw: Any) -> tuple[float, bool]:
    """Return (non-negative amount, is_credit).

    Credits/refunds (negative source totals) store abs(amount) with is_credit=True
    so burn/MRR subtract rather than depending on a signed amount field.
    """
    try:
        signed = float(raw or 0)
    except (TypeError, ValueError):
        signed = 0.0
    amount = round(abs(signed), 2)
    return amount, signed < 0


def apply_exchange_rate(amount: float, exchange_rate: Any) -> float:
    """Convert amount to home currency. Missing/invalid rate → assume 1.0."""
    try:
        rate = float(exchange_rate) if exchange_rate not in (None, "") else 1.0
    except (TypeError, ValueError):
        rate = 1.0
    if rate <= 0:
        rate = 1.0
    return round(float(amount) * rate, 2)


def _float_or(value: Any, default: Optional[float]) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def fx_rate_home_per_foreign(rate: Any) -> float:
    """Normalize a home-units-per-foreign-unit rate; missing/invalid -> 1.0."""
    val = _float_or(rate, 1.0)
    return val if val and val > 0 else 1.0


def money_fields(
    amount: float,
    *,
    currency: Any = None,
    fx_rate: Any = 1.0,
    tax_amount: Any = 0.0,
    amount_net: Any = None,
    amount_home: Any = None,
    amount_net_home: Any = None,
) -> dict[str, Any]:
    """Shared money contract for every accounting row.

    - currency: lowercase ISO code (None when the source does not say)
    - fx_rate: home-currency units per one document-currency unit (1.0 = home)
    - amount_home: amount * fx_rate unless the source supplies it
    - tax_amount: absolute tax on the document
    - amount_net: amount excluding tax (>= 0) unless the source supplies it
    - amount_net_home: amount_net * fx_rate unless the source supplies it
    All magnitudes are non-negative; polarity lives in ``is_credit``.
    """
    amt = abs(_float_or(amount, 0.0) or 0.0)
    rate = fx_rate_home_per_foreign(fx_rate)
    tax = abs(_float_or(tax_amount, 0.0) or 0.0)
    net = _float_or(amount_net, None)
    net = abs(net) if net is not None else max(amt - tax, 0.0)
    home = _float_or(amount_home, None)
    home = abs(home) if home is not None else amt * rate
    net_home = _float_or(amount_net_home, None)
    net_home = abs(net_home) if net_home is not None else net * rate
    code = str(currency or "").strip().lower() or None
    return {
        "currency": code,
        "fx_rate": round(rate, 8),
        "amount_home": round(home, 2),
        "amount_net": round(net, 2),
        "amount_net_home": round(net_home, 2),
        "tax_amount": round(tax, 2),
    }


def _raw_amount(entry: dict[str, Any]) -> float:
    try:
        return float(entry.get("amount") or 0)
    except (TypeError, ValueError):
        return 0.0


def entry_amount_for_totals(entry: dict[str, Any]) -> float:
    """Net-of-tax, home-currency magnitude for revenue/expense totals (always absolute).

    Priority: amount_net_home (current sync contract); for rows synced before it
    existed, amount_net scaled into home currency when both net + home exist, else
    amount_home, else amount_net; legacy/manual rows fall back to amount.
    Polarity is applied separately via ``entry_signed_amount``.
    """
    net_home = _float_or(entry.get("amount_net_home"), None)
    if net_home is not None:
        return round(abs(net_home), 2)
    amount = _raw_amount(entry)
    amount_net = entry.get("amount_net")
    amount_home = entry.get("amount_home")
    try:
        net = float(amount_net) if amount_net is not None else None
    except (TypeError, ValueError):
        net = None
    try:
        home = float(amount_home) if amount_home is not None else None
    except (TypeError, ValueError):
        home = None

    if net is not None and home is not None and amount:
        return round(abs(home) * (abs(net) / abs(amount)), 2)
    if home is not None:
        return abs(home)
    if net is not None:
        return abs(net)
    return abs(amount)


def entry_signed_amount(entry: dict[str, Any], amount: Optional[float] = None) -> float:
    """Apply credit/refund polarity for ledger expansion and burn/MRR.

    Legacy QB rows may still hold a negative ``amount`` without ``is_credit``.
    Those keep negative polarity (using net/home magnitude when available).
    """
    raw = _raw_amount(entry)
    is_credit = bool(entry.get("is_credit") or entry.get("is_refund"))

    if amount is None:
        if raw < 0 and not is_credit:
            # Legacy signed amount: preserve negative polarity.
            mag = entry_amount_for_totals({**entry, "amount": abs(raw)})
            return -abs(mag)
        base = entry_amount_for_totals(entry)
    else:
        base = float(amount)
        if raw < 0 and not is_credit:
            # Caller passed a magnitude (often abs); still honor legacy sign.
            return -abs(base)

    if is_credit:
        return -abs(base)
    return abs(base)
