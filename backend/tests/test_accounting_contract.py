"""T11: shared financial_entries contract + stable ids + migration planning."""
from __future__ import annotations

import asyncio
import re
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_accounting_contract")

import accounting_map as amap  # noqa: E402
import quickbooks as qb  # noqa: E402
import sap_b1  # noqa: E402
import server  # noqa: E402
import xero as xr  # noqa: E402
from scripts.migrate_accounting_txn_ids import plan_rewrites  # noqa: E402
from tests.mongo_mocks import FakeCollection  # noqa: E402

CONTRACT = {"currency", "fx_rate", "amount_home", "amount_net", "amount_net_home", "tax_amount"}


def test_money_fields_defaults_and_rounding():
    out = amap.money_fields(110, currency="USD", fx_rate=56.123, tax_amount=10)
    assert out == {
        "currency": "usd",
        "fx_rate": 56.123,
        "amount_home": round(110 * 56.123, 2),
        "amount_net": 100.0,
        "amount_net_home": round(100 * 56.123, 2),
        "tax_amount": 10.0,
    }
    home = amap.money_fields(50, currency=None, fx_rate=None)
    assert home["fx_rate"] == 1.0 and home["amount_home"] == 50 and home["currency"] is None
    assert amap.money_fields(5, tax_amount=9)["amount_net"] == 0  # never negative


def test_every_mapper_emits_contract_and_stable_ids():
    rows = [
        qb.map_qb_transaction({"Id": "7", "TxnDate": "2026-01-02", "TotalAmt": 10}, "bill"),
        xr.map_xero_invoice({
            "Type": "ACCPAY", "Status": "PAID", "InvoiceID": "g-1", "DateString": "2026-01-02", "Total": 10,
        }),
        sap_b1.map_sap_document({"DocEntry": 3, "DocDate": "2026-01-02", "DocTotal": 10}, kind="ap"),
    ]
    rows += qb.map_qb_journal_entry({"Id": "9", "TxnDate": "2026-01-02", "Line": [{
        "Id": "1", "Amount": 4, "DetailType": "JournalEntryLineDetail",
        "JournalEntryLineDetail": {"PostingType": "Debit", "AccountRef": {"name": "Rent", "type": "Expense"}},
    }]})
    for row in rows:
        assert CONTRACT <= set(row), row
        assert not re.search(r"_\d{4}-\d{2}-\d{2}$", row["qb_txn_id"])
    ids = [r["qb_txn_id"] for r in rows]
    assert ids == ["qb_bill_7", "xero_invoice_g-1", "sap_b1_ap_3", "qb_journal_9_1"]


def test_upsert_sets_contract_fields_and_source_entity():
    fin = FakeCollection()
    fake_db = MagicMock()
    fake_db.financial_entries = fin
    fake_db.workspaces.find_one = AsyncMock(return_value={"financial_settings": {"currency": "php"}})
    txn = qb.map_qb_transaction({
        "Id": "5", "TxnDate": "2026-02-01", "TotalAmt": 112, "CurrencyRef": {"value": "USD"},
        "ExchangeRate": 56, "TxnTaxDetail": {"TotalTax": 12},
    }, "bill")
    txn["_qb_raw_type"] = "bill"
    with (
        patch.object(server, "db", fake_db),
        patch.object(server.dept_migrate, "finance_department_id", new=AsyncMock(return_value="d1")),
        patch.object(server, "invalidate_financials_cache"),
    ):
        n = asyncio.run(server._upsert_accounting_sync_entries(
            ws_id="ws1", principal={"user_id": "u1"}, txns=[txn], source="quickbooks_sync",
        ))
    assert n == 1
    doc = fin.docs[0]
    assert doc["qb_txn_id"] == "qb_bill_5"
    assert doc["source_entity"] == "bill"
    assert doc["currency"] == "usd"
    assert doc["fx_rate"] == 56
    assert doc["amount_home"] == 112 * 56
    assert doc["amount_net"] == 100
    assert doc["amount_net_home"] == 100 * 56
    assert doc["tax_amount"] == 12
    assert "_qb_raw_type" not in doc
    assert doc["updated_at"]


def test_migration_plan_rewrites_and_keeps_most_recent():
    docs = [
        {"_id": 1, "workspace_id": "w", "qb_txn_id": "42_2026-01-05", "type": "revenue",
         "created_at": "2026-01-05T00:00:00+00:00"},
        {"_id": 2, "workspace_id": "w", "qb_txn_id": "qb_invoice_42",
         "created_at": "2026-02-01T00:00:00+00:00", "updated_at": "2026-03-01T00:00:00+00:00"},
        {"_id": 3, "workspace_id": "w", "qb_txn_id": "xero_abcdef12-3456_2026-01-01"},
        {"_id": 4, "workspace_id": "w", "qb_txn_id": "sap_b1_ap_9_2026-01-01"},
        {"_id": 5, "workspace_id": "w", "qb_txn_id": "qb_bill_1"},
    ]
    plan = plan_rewrites(docs)
    assert plan["scanned"] == 5
    assert sorted(plan["deletes"]) == [1]  # older dated duplicate of qb_invoice_42
    assert sorted(plan["updates"]) == [(3, "xero_invoice_abcdef12-3456"), (4, "sap_b1_ap_9")]
    # Idempotent: applying the plan and re-planning changes nothing.
    after = [
        {**d, "qb_txn_id": dict(plan["updates"]).get(d["_id"], d["qb_txn_id"])}
        for d in docs if d["_id"] not in plan["deletes"]
    ]
    again = plan_rewrites(after)
    assert again["updates"] == [] and again["deletes"] == []
