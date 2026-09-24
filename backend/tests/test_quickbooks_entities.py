"""T12: QuickBooks entity coverage from fixture JSON (no live Intuit calls)."""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_quickbooks_entities")

import quickbooks as qb  # noqa: E402

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "quickbooks_entities.json").read_text())


class _Resp:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload
        self.text = ""

    def json(self):
        return self._payload


class _QbClient:
    def __init__(self):
        self.entities: list[str] = []

    def __call__(self, *a, **k):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None, headers=None):
        assert params["minorversion"] == str(qb.QB_MINOR_VERSION)
        entity = re.search(r"FROM (\w+)", params["query"]).group(1)
        self.entities.append(entity)
        return _Resp({"QueryResponse": {entity: FIXTURE.get(entity, [])}})


@pytest.fixture
def synced(monkeypatch):
    client = _QbClient()
    monkeypatch.setattr(qb.httpx, "AsyncClient", client)
    tokens = {"access_token": "a", "refresh_token": "r", "expires_in": 3600,
              "obtained_at": datetime.now(timezone.utc).isoformat()}
    rows, complete, _tok, deleted = asyncio.run(qb.fetch_qb_transactions(tokens, "realm", None))
    return {r["qb_txn_id"]: r for r in rows}, complete, deleted, client


def test_all_entities_fetched_and_accounts_once(synced):
    _rows, complete, deleted, client = synced
    assert complete is True and deleted == []
    assert client.entities.count("Account") == 1
    for entity in ("Invoice", "SalesReceipt", "CreditMemo", "RefundReceipt", "Purchase", "Bill", "VendorCredit", "JournalEntry"):
        assert entity in client.entities


@pytest.mark.parametrize("txn_id,etype,is_credit,entity", [
    ("qb_invoice_101", "revenue", False, "invoice"),
    ("qb_salesreceipt_102", "revenue", False, "sales_receipt"),
    ("qb_creditmemo_103", "revenue", True, "credit_memo"),
    ("qb_refundreceipt_104", "revenue", True, "refund_receipt"),
    ("qb_purchase_105", "expense", False, "purchase"),
    ("qb_purchase_106", "expense", True, "purchase"),
    ("qb_bill_107", "expense", False, "bill"),
    ("qb_vendorcredit_108", "expense", True, "vendor_credit"),
])
def test_entity_polarity(synced, txn_id, etype, is_credit, entity):
    rows = synced[0]
    row = rows[txn_id]
    assert row["type"] == etype
    assert row["is_credit"] is is_credit
    assert row["_qb_raw_type"] == entity


def test_invoice_tax_excluded_net(synced):
    inv = synced[0]["qb_invoice_101"]
    assert inv["currency"] == "php"
    assert (inv["amount"], inv["tax_amount"], inv["amount_net"]) == (1120, 120, 1000)


def test_bill_tax_inclusive_multicurrency(synced):
    bill = synced[0]["qb_bill_107"]
    # TotalAmt includes tax in both modes -> net = TotalAmt - TotalTax.
    assert bill["amount_net"] == 900
    assert bill["fx_rate"] == 56.5
    assert bill["amount_home"] == round(1000 * 56.5, 2)
    assert bill["amount_net_home"] == round(900 * 56.5, 2)


def test_journal_entry_mixed_accounts(synced):
    rows = synced[0]
    je = {k: v for k, v in rows.items() if k.startswith("qb_journal_109_")}
    assert set(je) == {"qb_journal_109_0", "qb_journal_109_1", "qb_journal_109_2", "qb_journal_109_3"}
    assert (je["qb_journal_109_0"]["type"], je["qb_journal_109_0"]["is_credit"]) == ("revenue", False)
    assert (je["qb_journal_109_1"]["type"], je["qb_journal_109_1"]["is_credit"]) == ("revenue", True)
    assert (je["qb_journal_109_2"]["type"], je["qb_journal_109_2"]["is_credit"]) == ("expense", False)
    assert (je["qb_journal_109_3"]["type"], je["qb_journal_109_3"]["is_credit"]) == ("expense", True)
    # Bank (Asset) line is not P&L and is skipped.


def test_env_warning_is_boolean_flag(monkeypatch):
    monkeypatch.setenv("RENDER", "1")
    monkeypatch.setattr(qb, "QB_ENV_EXPLICITLY_SET", False)
    diag = qb.qb_env_diagnostics()
    assert diag["quickbooks_env_warning"] is True
    assert diag["quickbooks_env_warning_detail"]
    monkeypatch.setattr(qb, "QB_ENV_EXPLICITLY_SET", True)
    assert qb.qb_env_diagnostics()["quickbooks_env_warning"] is False
