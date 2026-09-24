"""T16: totals use net-of-tax home amounts; legacy rows unchanged."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_home_currency_totals")

import accounting_map as amap  # noqa: E402
import finance_recurrence as fr  # noqa: E402
import financial_export as fx  # noqa: E402


def _synced(id_, etype, amount, currency, fx_rate, tax=0.0, is_credit=False):
    return {
        "id": id_, "type": etype, "category": "Sales" if etype == "revenue" else "Cloud",
        "name": id_, "month": "2026-09", "recurring": False, "is_credit": is_credit,
        "amount": amount, **amap.money_fields(amount, currency=currency, fx_rate=fx_rate, tax_amount=tax),
    }


def test_mixed_usd_php_sum_in_home_currency():
    entries = [
        _synced("usd-inv", "revenue", 112, "usd", 56, tax=12),      # 100 USD net -> 5600 PHP
        _synced("php-inv", "revenue", 1120, "php", 1, tax=120),     # 1000 PHP net
        _synced("usd-cn", "revenue", 11.2, "usd", 56, tax=1.2, is_credit=True),  # -560 PHP
        _synced("usd-bill", "expense", 50, "usd", 56),              # 2800 PHP
    ]
    rev = fr.expand_entries_by_month(entries, entry_type="revenue", horizon_end="2026-09")
    exp = fr.expand_entries_by_month(entries, entry_type="expense", horizon_end="2026-09")
    assert rev["2026-09"] == 5600 + 1000 - 560
    assert exp["2026-09"] == 2800
    assert dict(fr.iter_expense_month_amounts(entries[3], "2026-09")) == {"2026-09": 2800}


def test_legacy_and_manual_entries_unaffected():
    legacy = {"type": "expense", "category": "Rent", "month": "2026-09", "amount": 700, "recurring": False}
    legacy_negative = {"type": "expense", "category": "Rent", "month": "2026-09", "amount": -50, "recurring": False}
    assert amap.entry_amount_for_totals(legacy) == 700
    assert amap.entry_signed_amount(legacy_negative) == -50
    exp = fr.expand_entries_by_month([legacy, legacy_negative], entry_type="expense", horizon_end="2026-09")
    assert exp["2026-09"] == 650


def test_pre_contract_synced_rows_keep_previous_math():
    # Rows synced before amount_net_home existed: net scaled into home.
    row = {"type": "revenue", "amount": 110, "amount_net": 100, "amount_home": 220, "month": "2026-09"}
    assert amap.entry_amount_for_totals(row) == 200


def test_export_line_items_match_totals():
    entries = [_synced("usd-inv", "revenue", 112, "usd", 56, tax=12),
               _synced("usd-cn", "revenue", 11.2, "usd", 56, tax=1.2, is_credit=True)]
    items = fx.period_line_items(entries, "2026-09", "2026-09")
    assert sorted(i["amount"] for i in items) == [-560, 5600]
