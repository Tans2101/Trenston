"""Stable qb_txn_id, currency/tax fields, and migration rewrite."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import accounting_map as amap
import quickbooks as qb
import sap_b1
import xero as xr
from scripts.migrate_qb_txn_ids import (
    legacy_dated_patterns_for_stable,
    qb_entity_slug_from_hints,
    rewrite_qb_txn_id,
)


def test_qb_stable_id_and_currency_tax():
    mapped = qb.map_qb_transaction(
        {
            "Id": "99",
            "TxnDate": "2024-03-15",
            "TotalAmt": 110,
            "CurrencyRef": {"value": "USD"},
            "ExchangeRate": 1,
            "TxnTaxDetail": {"TotalTax": 10},
            "EntityRef": {"name": "AWS"},
        },
        "purchase",
    )
    assert mapped["qb_txn_id"] == "qb_purchase_99"
    assert mapped["currency"] == "usd"
    assert mapped["amount"] == 110
    assert mapped["amount_net"] == 100
    assert mapped["amount_home"] == 110
    assert mapped["tax_amount"] == 10
    assert mapped["fx_rate"] == 1.0
    assert mapped["amount_net_home"] == 100


def test_xero_currency_and_subtotal():
    mapped = xr.map_xero_invoice({
        "Type": "ACCREC",
        "Status": "AUTHORISED",
        "InvoiceID": "inv-1",
        "DateString": "2026-04-12",
        "Total": 115,
        "SubTotal": 100,
        "CurrencyCode": "AUD",
        "CurrencyRate": 0.65,
        "Contact": {"Name": "Acme"},
    })
    assert mapped["qb_txn_id"] == "xero_invoice_inv-1"
    assert mapped["currency"] == "aud"
    assert mapped["amount_net"] == 100
    assert mapped["tax_amount"] == 0  # no TotalTax in fixture
    # Xero CurrencyRate is document currency PER base currency -> divide.
    assert mapped["amount_home"] == round(115 / 0.65, 2)
    assert mapped["amount_net_home"] == round(100 / 0.65, 2)


def test_sap_currency_vat_and_stable_id():
    mapped = sap_b1.map_sap_document(
        {
            "DocEntry": 5,
            "DocDate": "2026-09-01",
            # SAP: DocTotal/VatSum are local currency; *Fc are document currency.
            "DocTotal": 123.2,
            "VatSum": 13.2,
            "DocTotalFc": 112,
            "VatSumFc": 12,
            "DocCurrency": "EUR",
            "DocRate": 1.1,
            "CardName": "Customer",
            "Cancelled": "tNO",
        },
        kind="ar",
    )
    assert mapped["qb_txn_id"] == "sap_b1_ar_5"
    assert mapped["currency"] == "eur"
    assert mapped["amount_net"] == 100
    assert mapped["amount"] == 112
    assert mapped["tax_amount"] == 12
    assert mapped["amount_home"] == 123.2
    assert mapped["amount_net_home"] == 110


def test_entry_amount_for_totals_prefers_net_home():
    entry = {"amount": 110, "amount_net": 100, "amount_home": 220}
    assert amap.entry_amount_for_totals(entry) == 200.0  # 220 * 100/110


def test_entry_signed_preserves_legacy_negative():
    """Legacy QB rows stored signed negative amounts without is_credit."""
    legacy = {"amount": -40}
    assert amap.entry_signed_amount(legacy) == -40.0
    # Magnitude from caller still gets legacy polarity
    assert amap.entry_signed_amount(legacy, 40.0) == -40.0
    # Credit flag still wins
    assert amap.entry_signed_amount({"amount": 40, "is_credit": True}) == -40.0
    # Positive non-credit stays positive
    assert amap.entry_signed_amount({"amount": 40}) == 40.0
    # Legacy negative with net/home uses home magnitude, keeps sign
    legacy_fx = {"amount": -110, "amount_net": 100, "amount_home": 220}
    assert amap.entry_signed_amount(legacy_fx) == -200.0


def test_migrate_prefers_entry_type_over_sync_source():
    # The live bug: source=quickbooks_sync must not force purchase for revenue.
    assert rewrite_qb_txn_id(
        "42_2024-06-01",
        entry_type="revenue",
        source="quickbooks_sync",
    ) == "qb_invoice_42"
    assert rewrite_qb_txn_id(
        "42_2024-06-01",
        entry_type="expense",
        source="quickbooks_auto_sync",
    ) == "qb_purchase_42"
    assert rewrite_qb_txn_id(
        "7_2024-01-01",
        entry_type="expense",
        source="quickbooks_sync",
        source_hint="bill",
    ) == "qb_bill_7"
    # Invoice + purchase with same numeric Id must NOT collide
    inv = rewrite_qb_txn_id("42_2024-06-01", entry_type="revenue", source="quickbooks_sync")
    pur = rewrite_qb_txn_id("42_2024-07-01", entry_type="expense", source="quickbooks_sync")
    assert inv == "qb_invoice_42"
    assert pur == "qb_purchase_42"
    assert inv != pur


def test_migrate_rewrite_rules():
    assert rewrite_qb_txn_id("99_2024-03-15", entry_type="expense") == "qb_purchase_99"
    assert rewrite_qb_txn_id("xero_inv-uuid-1_2026-04-12") == "xero_invoice_inv-uuid-1"
    assert rewrite_qb_txn_id("sap_b1_ar_1_2026-09-01") == "sap_b1_ar_1"
    assert rewrite_qb_txn_id("qb_purchase_99") is None  # already stable
    assert rewrite_qb_txn_id("qb_invoice_42_2024-01-01") == "qb_invoice_42"


def test_legacy_dated_patterns_for_stable():
    assert legacy_dated_patterns_for_stable("qb_invoice_42") == [r"^42_\d{4}-\d{2}-\d{2}$"]
    assert legacy_dated_patterns_for_stable("qb_journal_99_1") == [
        r"^99_line_1_\d{4}-\d{2}-\d{2}$"
    ]
    pats = legacy_dated_patterns_for_stable("xero_invoice_abc-def")
    assert r"^xero_abc\-def_\d{4}-\d{2}-\d{2}$" in pats
    assert legacy_dated_patterns_for_stable("sap_b1_ar_5") == [
        r"^sap_b1_ar_5_\d{4}-\d{2}-\d{2}$"
    ]


def test_qb_entity_slug_ignores_sync_source_alone():
    assert qb_entity_slug_from_hints(entry_type="revenue", source="quickbooks_sync") == "invoice"
    assert qb_entity_slug_from_hints(entry_type="expense", source="quickbooks_sync") == "purchase"
    assert qb_entity_slug_from_hints(raw_type="bill", source="quickbooks_sync") == "bill"
