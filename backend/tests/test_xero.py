"""Unit tests for Xero token refresh and invoice/bill mapping."""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("XERO_CLIENT_ID", "test-client")
os.environ.setdefault("XERO_CLIENT_SECRET", "test-secret")

import xero as xr  # noqa: E402

# Module constants are read at import; pin them for workers that imported xero earlier.
xr.XERO_CLIENT_ID = os.environ["XERO_CLIENT_ID"]
xr.XERO_CLIENT_SECRET = os.environ["XERO_CLIENT_SECRET"]


def test_map_accrec_invoice_to_revenue():
    inv = {
        "Type": "ACCREC",
        "Status": "AUTHORISED",
        "InvoiceID": "inv-uuid-1",
        "InvoiceNumber": "INV-100",
        "DateString": "2026-04-12",
        "Total": 1500.25,
        "Contact": {"Name": "Acme Ltd"},
        "Reference": "Q2 retainer",
        "LineItems": [{"AccountCode": "200", "Description": "Services"}],
    }
    mapped = xr.map_xero_invoice(inv)
    assert mapped is not None
    assert mapped["type"] == "revenue"
    assert mapped["amount"] == 1500.25
    assert mapped["month"] == "2026-04"
    assert mapped["qb_txn_id"] == "xero_invoice_inv-uuid-1"
    assert mapped["name"] == "Acme Ltd"
    assert mapped["category"] == "200"


def test_map_accpay_bill_to_expense():
    inv = {
        "Type": "ACCPAY",
        "Status": "PAID",
        "InvoiceID": "bill-9",
        "DateString": "2026-01-05",
        "Total": 88,
        "Contact": {"Name": "AWS"},
        "LineItems": [{"Description": "Cloud hosting"}],
    }
    mapped = xr.map_xero_invoice(inv)
    assert mapped["type"] == "expense"
    assert mapped["qb_txn_id"] == "xero_invoice_bill-9"
    assert mapped["name"] == "AWS"
    assert mapped["category"] == "Cloud hosting"


def test_map_skips_draft_and_voided():
    assert xr.map_xero_invoice({"Type": "ACCREC", "Status": "DRAFT", "InvoiceID": "1", "Total": 1}) is None
    assert xr.map_xero_invoice({"Type": "ACCREC", "Status": "VOIDED", "InvoiceID": "1", "Total": 1}) is None


def test_parse_xero_dotnet_date():
    inv = {
        "Type": "ACCREC",
        "Status": "AUTHORISED",
        "InvoiceID": "d1",
        "Date": "/Date(1712880000000+0000)/",
        "Total": 10,
        "Contact": {"Name": "X"},
    }
    mapped = xr.map_xero_invoice(inv)
    assert mapped["month"] == "2024-04"


def test_refresh_skips_when_fresh():
    tokens = {
        "access_token": "abc",
        "refresh_token": "r1",
        "expires_in": 1800,
        "obtained_at": datetime.now(timezone.utc).isoformat(),
        "tenant_id": "t1",
    }
    with patch("xero.httpx.AsyncClient") as mock_client:
        out = asyncio.run(xr.refresh_xero_token(tokens))
    assert out == tokens
    mock_client.assert_not_called()


def test_refresh_preserves_tenant():
    tokens = {
        "access_token": "old",
        "refresh_token": "r1",
        "expires_in": 1800,
        "obtained_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
        "tenant_id": "tenant-abc",
        "tenant_name": "Demo Co",
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": "new",
        "refresh_token": "r2",
        "expires_in": 1800,
    }
    mock_hc = AsyncMock()
    mock_hc.post = AsyncMock(return_value=mock_resp)
    mock_hc.__aenter__ = AsyncMock(return_value=mock_hc)
    mock_hc.__aexit__ = AsyncMock(return_value=None)

    with patch("integration_errors.httpx.AsyncClient", return_value=mock_hc):
        out = asyncio.run(xr.refresh_xero_token(tokens))
    assert out["access_token"] == "new"
    assert out["tenant_id"] == "tenant-abc"
    assert out["tenant_name"] == "Demo Co"


def test_fetch_connections_maps_tenants():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {"id": "c1", "tenantId": "t1", "tenantType": "ORGANISATION", "tenantName": "One"},
        {"id": "c2", "tenantId": "t2", "tenantType": "ORGANISATION", "tenantName": "Two"},
    ]
    mock_hc = AsyncMock()
    mock_hc.get = AsyncMock(return_value=mock_resp)
    mock_hc.__aenter__ = AsyncMock(return_value=mock_hc)
    mock_hc.__aexit__ = AsyncMock(return_value=None)
    with patch("xero.httpx.AsyncClient", return_value=mock_hc):
        rows = asyncio.run(xr.fetch_xero_connections("tok"))
    assert len(rows) == 2
    assert rows[0]["tenant_id"] == "t1"


def test_exclude_submitted_invoices():
    inv = {
        "Type": "ACCREC",
        "Status": "SUBMITTED",
        "InvoiceID": "s1",
        "DateString": "2026-04-12",
        "Total": 10,
        "Contact": {"Name": "A"},
    }
    assert xr.map_xero_invoice(inv) is None


def test_map_bank_receive_and_spend():
    recv = xr.map_xero_bank_transaction({
        "Type": "RECEIVE",
        "Status": "AUTHORISED",
        "BankTransactionID": "b1",
        "DateString": "2026-04-01",
        "Total": 200,
        "Contact": {"Name": "Customer"},
    })
    assert recv["type"] == "revenue"
    spend = xr.map_xero_bank_transaction({
        "Type": "SPEND",
        "Status": "AUTHORISED",
        "BankTransactionID": "b2",
        "DateString": "2026-04-01",
        "Total": 50,
        "Contact": {"Name": "Vendor"},
    })
    assert spend["type"] == "expense"
    assert xr.map_xero_bank_transaction({
        "Type": "RECEIVE-OVERPAYMENT",
        "Status": "AUTHORISED",
        "BankTransactionID": "b3",
        "Total": 10,
    }) is None


def test_map_credit_notes():
    ar = xr.map_xero_credit_note({
        "Type": "ACCRECCREDIT",
        "Status": "AUTHORISED",
        "CreditNoteID": "cn1",
        "DateString": "2026-04-02",
        "Total": 30,
        "Contact": {"Name": "A"},
    })
    assert ar["type"] == "revenue" and ar["is_credit"] is True
    ap = xr.map_xero_credit_note({
        "Type": "ACCPAYCREDIT",
        "Status": "PAID",
        "CreditNoteID": "cn2",
        "DateString": "2026-04-02",
        "Total": 12,
        "Contact": {"Name": "V"},
    })
    assert ap["type"] == "expense" and ap["is_credit"] is True


def test_map_manual_journal_pl_only():
    rows = xr.map_xero_manual_journal({
        "ManualJournalID": "mj1",
        "Status": "POSTED",
        "DateString": "2026-04-03",
        "Narration": "Adj",
        "JournalLines": [
            {"AccountType": "REVENUE", "LineAmount": -100, "Description": "Sales", "AccountCode": "200"},
            {"AccountType": "BANK", "LineAmount": 100, "Description": "Bank", "AccountCode": "090"},
            {"AccountType": "EXPENSE", "LineAmount": 40, "Description": "Office", "AccountCode": "400"},
        ],
    }, {"200": "REVENUE", "090": "ASSET", "400": "EXPENSE"})
    assert len(rows) == 2
    assert {r["type"] for r in rows} == {"revenue", "expense"}


def test_xero_scopes_are_granular():
    assert "accounting.transactions.read" not in xr.XERO_SCOPES
    assert "accounting.invoices.read" in xr.XERO_SCOPES
    assert "accounting.banktransactions.read" in xr.XERO_SCOPES
    assert "accounting.manualjournals.read" in xr.XERO_SCOPES


@pytest.mark.asyncio
async def test_xero_429_respects_retry_after(monkeypatch):
    monkeypatch.setattr(xr, "XERO_MIN_INTERVAL_SEC", 0)
    monkeypatch.setattr(xr, "XERO_MAX_RETRIES_429", 2)
    calls = {"n": 0}

    class _Resp:
        def __init__(self, code, headers=None):
            self.status_code = code
            self.headers = headers or {}
            self.text = ""
        def json(self):
            return {"Invoices": []}

    class _Client:
        def __init__(self, *a, **k):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def get(self, *a, **k):
            calls["n"] += 1
            if calls["n"] < 3:
                return _Resp(429, {"Retry-After": "0"})
            return _Resp(200)

    sleeps = []
    async def fake_sleep(sec):
        sleeps.append(sec)

    with patch.object(xr.httpx, "AsyncClient", _Client), patch.object(xr.asyncio, "sleep", fake_sleep):
        rows, complete, status = await xr._fetch_collection_once(
            "tok", "ten", path="Invoices", result_key="Invoices",
            where='Type=="ACCREC"', since=None,
        )
    assert status is None
    assert calls["n"] == 3
    assert sleeps  # backed off


@pytest.mark.asyncio
async def test_xero_403_permissions_without_wipe(monkeypatch):
    monkeypatch.setattr(xr, "XERO_MIN_INTERVAL_SEC", 0)

    class _Resp:
        status_code = 403
        text = "forbidden"
        headers = {}
        def json(self):
            return {}

    class _Client:
        def __init__(self, *a, **k):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def get(self, *a, **k):
            return _Resp()

    async def fake_connections(token):
        return [{"tenant_id": "ten", "tenant_name": "Org", "connection_id": "c1"}]

    monkeypatch.setattr(xr, "fetch_xero_connections", fake_connections)
    with patch.object(xr.httpx, "AsyncClient", _Client):
        with pytest.raises(xr.XeroPermissionsError):
            await xr._fetch_collection(
                {"access_token": "tok"}, "ten",
                path="Invoices", result_key="Invoices",
                where='Type=="ACCREC"', since=None, label="Invoices",
            )
