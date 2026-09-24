"""T14: SAP B1 invoices + credit memos from fixture JSON."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_sap_b1_documents")

import sap_b1  # noqa: E402

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "sap_b1_documents.json").read_text())


def _sync(monkeypatch):
    seen: list[str] = []

    async def fake_ensure(c):
        return c

    async def fake_collection(c, collection, *, since=None):
        seen.append(collection)
        return FIXTURE.get(collection, []), True, c

    monkeypatch.setattr(sap_b1, "ensure_session", fake_ensure)
    monkeypatch.setattr(sap_b1, "_fetch_collection", fake_collection)
    rows, complete, _live, deleted = asyncio.run(sap_b1.fetch_sap_transactions({"session_id": "s"}))
    return {r["qb_txn_id"]: r for r in rows}, complete, deleted, seen


def test_all_four_document_types(monkeypatch):
    rows, complete, deleted, seen = _sync(monkeypatch)
    assert complete is True and deleted == []
    assert seen == ["Invoices", "PurchaseInvoices", "CreditNotes", "PurchaseCreditNotes"]
    expected = {
        "sap_b1_ar_11": ("revenue", False, "invoice"),
        "sap_b1_ar_12": ("revenue", False, "invoice"),
        "sap_b1_ap_21": ("expense", False, "purchase_invoice"),
        "sap_b1_ap_22": ("expense", True, "purchase_invoice"),
        "sap_b1_ar_cn_31": ("revenue", True, "credit_memo"),
        "sap_b1_ap_cn_41": ("expense", True, "purchase_credit_memo"),
    }
    assert {k: (v["type"], v["is_credit"], v["_sap_raw_type"]) for k, v in rows.items()} == expected
    assert "sap_b1_ar_13" not in rows  # zero total skipped


def test_local_currency_invoice_money(monkeypatch):
    inv = _sync(monkeypatch)[0]["sap_b1_ar_11"]
    assert (inv["amount"], inv["tax_amount"], inv["amount_net"]) == (1120, 120, 1000)
    assert (inv["amount_home"], inv["amount_net_home"], inv["fx_rate"]) == (1120, 1000, 1.0)
    assert inv["currency"] == "php"


def test_foreign_currency_invoice_uses_fc_and_local_home(monkeypatch):
    inv = _sync(monkeypatch)[0]["sap_b1_ar_12"]
    assert inv["currency"] == "usd"
    assert inv["amount"] == 100 and inv["tax_amount"] == 10.71
    assert inv["amount_net"] == 89.29
    assert inv["fx_rate"] == 56
    assert inv["amount_home"] == 5600 and inv["amount_net_home"] == 5000


def test_negative_total_is_credit_not_dropped(monkeypatch):
    row = _sync(monkeypatch)[0]["sap_b1_ap_22"]
    assert row["amount"] == 50 and row["is_credit"] is True


def test_select_includes_currency_and_update_fields(monkeypatch):
    captured = {}

    async def fake_page(creds, collection, *, select, filt, skip):
        captured["select"] = select

        class R:
            status_code = 200

            def json(self):
                return {"value": []}

        return R()

    monkeypatch.setattr(sap_b1, "_fetch_collection_page", fake_page)
    asyncio.run(sap_b1._fetch_collection({"session_id": "s"}, "CreditNotes"))
    fields = set(captured["select"].split(","))
    assert {"DocCurrency", "DocRate", "VatSum", "DocTotalSys", "VatSumSys", "UpdateDate", "UpdateTime"} <= fields
