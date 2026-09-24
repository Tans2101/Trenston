"""T15: incremental sync by last-modified; voids/deletes remove entries."""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_incremental_sync_deletes")

import quickbooks as qb  # noqa: E402
import sap_b1  # noqa: E402
import server  # noqa: E402
import xero as xr  # noqa: E402
from tests.mongo_mocks import FakeCollection  # noqa: E402


class _Resp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)
        self.headers = {}

    def json(self):
        return self._payload


def _tokens(**extra):
    return {"access_token": "a", "refresh_token": "r", "expires_in": 3600,
            "obtained_at": datetime.now(timezone.utc).isoformat(), **extra}


# ------------------------------ QuickBooks ------------------------------

class _QbClient:
    def __init__(self, entity_rows, cdc=None):
        self.entity_rows = entity_rows
        self.cdc = cdc
        self.queries: list[str] = []
        self.cdc_calls: list[dict] = []

    def __call__(self, *a, **k):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None, headers=None):
        if url.endswith("/cdc"):
            self.cdc_calls.append(params)
            return _Resp(200, self.cdc or {"CDCResponse": []})
        q = params["query"]
        self.queries.append(q)
        entity = re.search(r"FROM (\w+)", q).group(1)
        return _Resp(200, {"QueryResponse": {entity: self.entity_rows.get(entity, [])}})


def test_qb_edited_old_invoice_found_by_last_updated_time(monkeypatch):
    since = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    old_edited = {"Id": "7", "TxnDate": "2025-01-15", "TotalAmt": 999,
                  "MetaData": {"LastUpdatedTime": datetime.now(timezone.utc).isoformat()}}
    client = _QbClient({"Invoice": [old_edited]})
    monkeypatch.setattr(qb.httpx, "AsyncClient", client)
    rows, complete, _t, deleted = asyncio.run(qb.fetch_qb_transactions(_tokens(), "realm", since))
    assert any("MetaData.LastUpdatedTime >=" in q for q in client.queries)
    assert not any("TxnDate" in q for q in client.queries)
    inv = next(r for r in rows if r["qb_txn_id"] == "qb_invoice_7")
    assert inv["month"] == "2025-01" and inv["amount"] == 999
    assert client.cdc_calls and client.cdc_calls[0]["changedSince"]


def test_qb_void_and_cdc_delete_become_deletions(monkeypatch):
    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    voided = {"Id": "8", "TxnDate": "2026-09-01", "TotalAmt": 0, "PrivateNote": "Voided"}
    cdc = {"CDCResponse": [{"QueryResponse": [
        {"Bill": [{"Id": "9", "status": "Deleted"}]},
        {"JournalEntry": [{"Id": "10", "status": "Voided"}]},
    ]}]}
    client = _QbClient({"Invoice": [voided]}, cdc=cdc)
    monkeypatch.setattr(qb.httpx, "AsyncClient", client)
    rows, _c, _t, deleted = asyncio.run(qb.fetch_qb_transactions(_tokens(), "realm", since))
    assert not any(r["qb_txn_id"] == "qb_invoice_8" for r in rows)
    assert set(deleted) == {"qb_invoice_8", "qb_bill_9", "qb_journal_10_"}


def test_qb_since_older_than_30_days_does_full_resync(monkeypatch):
    since = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    client = _QbClient({})
    monkeypatch.setattr(qb.httpx, "AsyncClient", client)
    asyncio.run(qb.fetch_qb_transactions(_tokens(), "realm", since))
    assert not any("LastUpdatedTime" in q for q in client.queries)
    assert client.cdc_calls == []


# -------------------------------- Xero --------------------------------

def test_xero_incremental_uses_rfc1123_if_modified_since(monkeypatch):
    seen: list[tuple[dict, dict]] = []

    class Client:
        def __call__(self, *a, **k):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None, headers=None):
            seen.append((dict(params or {}), dict(headers or {})))
            key = url.rsplit("/", 1)[-1]
            if key == "Invoices" and 'ACCREC' in (params or {}).get("where", ""):
                return _Resp(200, {"Invoices": [
                    {"InvoiceID": "old-edit", "Type": "ACCREC", "Status": "AUTHORISED",
                     "DateString": "2025-02-01T00:00:00", "Total": 50},
                    {"InvoiceID": "gone", "Type": "ACCREC", "Status": "VOIDED",
                     "DateString": "2026-09-01T00:00:00", "Total": 10},
                ]})
            return _Resp(200, {key: []})

    async def _no_wait():
        return None

    monkeypatch.setattr(xr, "_throttle_xero", _no_wait)
    monkeypatch.setattr(xr.httpx, "AsyncClient", Client())
    rows, _c, _t, deleted = asyncio.run(xr.fetch_xero_transactions(
        _tokens(tenant_id="t1"), "t1", "2026-09-24T23:30:00+00:00",
    ))
    assert seen[0][1]["If-Modified-Since"] == "Thu, 24 Sep 2026 23:30:00 GMT"
    assert all("Date>=" not in p.get("where", "") and "Status" not in p.get("where", "") for p, _h in seen)
    assert [r["qb_txn_id"] for r in rows] == ["xero_invoice_old-edit"]
    assert deleted == ["xero_invoice_gone"]


# ------------------------------- SAP B1 -------------------------------

def test_sap_incremental_filter_and_cancelled_deletes(monkeypatch):
    filters: list[str] = []

    async def fake_page(creds, collection, *, select, filt, skip):
        filters.append(filt)
        docs = []
        if collection == "Invoices":
            docs = [
                {"DocEntry": 1, "DocDate": "2025-01-01", "DocTotal": 100, "Cancelled": "tNO"},
                {"DocEntry": 2, "DocDate": "2026-09-01", "DocTotal": 100, "Cancelled": "tYES"},
            ]

        class R:
            status_code = 200

            def json(self):
                return {"value": docs}

        return R()

    async def fake_ensure(c):
        return c

    monkeypatch.setattr(sap_b1, "_fetch_collection_page", fake_page)
    monkeypatch.setattr(sap_b1, "ensure_session", fake_ensure)
    rows, _c, _l, deleted = asyncio.run(sap_b1.fetch_sap_transactions({"session_id": "s"}, "2026-09-20T00:00:00+00:00"))
    assert all("UpdateDate ge '2026-09-20'" in f for f in filters)
    assert all("DocDate" not in f for f in filters)
    assert all("tYES" in f for f in filters)  # cancelled docs included in incremental
    assert [r["qb_txn_id"] for r in rows] == ["sap_b1_ar_1"]
    assert deleted == ["sap_b1_ar_2"]


# ------------------------------- server -------------------------------

def test_delete_helper_removes_entries_and_invalidates_cache():
    fin = FakeCollection([
        {"workspace_id": "w", "qb_txn_id": "qb_invoice_8"},
        {"workspace_id": "w", "qb_txn_id": "qb_journal_10_0"},
        {"workspace_id": "w", "qb_txn_id": "qb_journal_10_1"},
        {"workspace_id": "w", "qb_txn_id": "qb_journal_100_0"},
        {"workspace_id": "other", "qb_txn_id": "qb_invoice_8"},
    ])
    fake_db = MagicMock()
    fake_db.financial_entries = fin
    with patch.object(server, "db", fake_db), patch.object(server, "invalidate_financials_cache") as inv:
        n = asyncio.run(server._delete_accounting_entries("w", ["qb_invoice_8", "qb_journal_10_"]))
    assert n == 3
    assert sorted((d["workspace_id"], d["qb_txn_id"]) for d in fin.docs) == [
        ("other", "qb_invoice_8"), ("w", "qb_journal_100_0"),
    ]
    inv.assert_called_once_with("w")


def test_sync_with_only_deletions_invalidates_cache():
    fin = FakeCollection([{"workspace_id": "w", "qb_txn_id": "xero_invoice_gone"}])
    fake_db = MagicMock()
    fake_db.financial_entries = fin
    fake_db.workspaces.find_one = AsyncMock(return_value={})
    with (
        patch.object(server, "db", fake_db),
        patch.object(server.dept_migrate, "finance_department_id", new=AsyncMock(return_value=None)),
        patch.object(server, "invalidate_financials_cache") as inv,
    ):
        asyncio.run(server._upsert_accounting_sync_entries(
            ws_id="w", principal={"user_id": "u"}, txns=[], source="xero_sync",
            deleted_ids=["xero_invoice_gone"],
        ))
    assert fin.docs == []
    inv.assert_called_with("w")
