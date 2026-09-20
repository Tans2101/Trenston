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
    assert mapped["qb_txn_id"] == "xero_inv-uuid-1_2026-04-12"
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
    assert mapped["qb_txn_id"].startswith("xero_bill-9_")
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

    with patch("xero.httpx.AsyncClient", return_value=mock_hc):
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
