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
from scripts.migrate_qb_txn_ids import rewrite_qb_txn_id


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
    assert mapped["currency"] == "USD"
    assert mapped["amount"] == 110
    assert mapped["amount_net"] == 100
    assert mapped["amount_home"] == 110


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
    assert mapped["currency"] == "AUD"
    assert mapped["amount_net"] == 100
    assert mapped["amount_home"] == round(115 * 0.65, 2)


def test_sap_currency_vat_and_stable_id():
    mapped = sap_b1.map_sap_document(
        {
            "DocEntry": 5,
            "DocDate": "2026-09-01",
            "DocTotal": 112,
            "VatSum": 12,
            "DocCurrency": "EUR",
            "DocRate": 1.1,
            "CardName": "Customer",
            "Cancelled": "tNO",
        },
        kind="ar",
    )
    assert mapped["qb_txn_id"] == "sap_b1_ar_5"
    assert mapped["currency"] == "EUR"
    assert mapped["amount_net"] == 100
    assert mapped["amount_home"] == round(112 * 1.1, 2)


def test_entry_amount_for_totals_prefers_net_home():
    entry = {"amount": 110, "amount_net": 100, "amount_home": 220}
    assert amap.entry_amount_for_totals(entry) == 200.0  # 220 * 100/110


def test_migrate_rewrite_rules():
    assert rewrite_qb_txn_id("99_2024-03-15", source_hint="purchase") == "qb_purchase_99"
    assert rewrite_qb_txn_id("xero_inv-uuid-1_2026-04-12") == "xero_invoice_inv-uuid-1"
    assert rewrite_qb_txn_id("sap_b1_ar_1_2026-09-01") == "sap_b1_ar_1"
    assert rewrite_qb_txn_id("qb_purchase_99") is None  # already stable
