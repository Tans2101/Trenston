"""Shared financial_entries shape for QuickBooks, Xero, and SAP B1 mappers.

Stable qb_txn_id format (no dates): `{source}_{entity_type}_{provider_id}`.
See backend/scripts/migrate_qb_txn_ids.py for rewriting legacy dated ids.

Downstream totals prefer amount_net (net of tax) converted via amount_home.
Entries without currency default to the workspace home currency.

Cross-currency rows without a valid FX rate are quarantined (fx_missing=True)
and excluded from totals — never invent rate 1.0 for foreign amounts.
"""
from __future__ import annotations

from typing import Any, Optional

# Version of the provider-record -> ledger-row mapping (QuickBooks, Xero, SAP B1).
# Every synced row is stamped with it (financial_entries.mapping_version). Bump
# it whenever a mapper changes how a record becomes a row (category, sign, tax,
# currency, month): the next sync for each workspace then re-pulls everything
# from the provider once and rewrites every row with the new logic. The
# provider is the raw ("bronze") copy; Trenston does not store raw payloads.
MAPPING_VERSION = "2026-10-16.2"

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


def _float_or(value: Any, default: Optional[float]) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def fx_rate_home_per_foreign(rate: Any) -> Optional[float]:
    """Normalize a home-units-per-foreign-unit rate; missing/invalid → None."""
    val = _float_or(rate, None)
    if val is None or val <= 0:
        return None
    return val


def apply_exchange_rate(
    amount: float,
    exchange_rate: Any,
    *,
    currency: Any = None,
    home_currency: Any = None,
) -> tuple[Optional[float], bool]:
    """Convert amount to home currency.

    Returns (converted_amount_or_None, fx_missing).
    Same-currency / unknown-currency without a home contrast → rate 1.0.
    Cross-currency with missing/invalid rate → (None, True); never invent 1.0.
    """
    code = str(currency or "").strip().lower() or None
    home = str(home_currency or "").strip().lower() or None
    rate = fx_rate_home_per_foreign(exchange_rate)
    cross = bool(code and home and code != home)
    if cross and rate is None:
        return None, True
    use_rate = rate if rate is not None else 1.0
    return round(float(amount) * use_rate, 2), False


def money_fields(
    amount: float,
    *,
    currency: Any = None,
    home_currency: Any = None,
    fx_rate: Any = None,
    tax_amount: Any = 0.0,
    amount_net: Any = None,
    amount_home: Any = None,
    amount_net_home: Any = None,
) -> dict[str, Any]:
    """Shared money contract for every accounting / manual row.

    - currency: lowercase ISO code (None when the source does not say)
    - home_currency: workspace home ISO code (used to detect cross-currency)
    - fx_rate: home-currency units per one document-currency unit (1.0 = home)
    - amount_home: amount * fx_rate unless the source supplies it
    - tax_amount: absolute tax on the document
    - amount_net: amount excluding tax (>= 0) unless the source supplies it
    - amount_net_home: amount_net * fx_rate unless the source supplies it
    - fx_missing: True when document currency ≠ home and no valid rate
      (home amounts omitted; totals must exclude the row)
    All magnitudes are non-negative; polarity lives in ``is_credit``.
    """
    amt = abs(_float_or(amount, 0.0) or 0.0)
    code = str(currency or "").strip().lower() or None
    home_code = str(home_currency or "").strip().lower() or None
    parsed_rate = fx_rate_home_per_foreign(fx_rate)
    tax = abs(_float_or(tax_amount, 0.0) or 0.0)
    net = _float_or(amount_net, None)
    net = abs(net) if net is not None else max(amt - tax, 0.0)
    supplied_home = _float_or(amount_home, None)
    supplied_net_home = _float_or(amount_net_home, None)

    cross = bool(code and home_code and code != home_code)
    fx_missing = bool(
        cross and parsed_rate is None and supplied_home is None and supplied_net_home is None
    )
    if fx_missing:
        return {
            "currency": code,
            "fx_rate": None,
            "amount_home": None,
            "amount_net": round(net, 2),
            "amount_net_home": None,
            "tax_amount": round(tax, 2),
            "fx_missing": True,
        }

    # Document currency known but home not yet — leave rate/home unset so the
    # sync upsert (which knows home) can quarantine or convert. Never invent 1.0.
    if code and not home_code and parsed_rate is None and supplied_home is None and supplied_net_home is None:
        return {
            "currency": code,
            "fx_rate": None,
            "amount_home": None,
            "amount_net": round(net, 2),
            "amount_net_home": None,
            "tax_amount": round(tax, 2),
            "fx_missing": False,
        }

    rate = parsed_rate if parsed_rate is not None else 1.0
    home = abs(supplied_home) if supplied_home is not None else amt * rate
    net_home = abs(supplied_net_home) if supplied_net_home is not None else net * rate
    return {
        "currency": code,
        "fx_rate": round(rate, 8),
        "amount_home": round(home, 2),
        "amount_net": round(net, 2),
        "amount_net_home": round(net_home, 2),
        "tax_amount": round(tax, 2),
        "fx_missing": False,
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
    Quarantined cross-currency rows (fx_missing) contribute 0.
    Polarity is applied separately via ``entry_signed_amount``.
    """
    if entry.get("fx_missing"):
        return 0.0
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
    if entry.get("fx_missing"):
        return 0.0
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
