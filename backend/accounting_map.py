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


def entry_amount_for_totals(entry: dict[str, Any]) -> float:
    """Prefer net-of-tax home amount for revenue/expense totals.

    Priority: amount_net scaled into home currency when both net + home exist,
    else amount_home, else amount_net, else amount.
    """
    amount = float(entry.get("amount") or 0)
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
    """Apply credit/refund polarity for ledger expansion and burn/MRR."""
    if amount is None:
        base = entry_amount_for_totals(entry)
    else:
        base = float(amount)
    if entry.get("is_credit") or entry.get("is_refund"):
        return -abs(base)
    # Legacy QB rows may still hold a negative amount until the next sync.
    return base
