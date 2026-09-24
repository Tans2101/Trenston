"""Unit tests for QuickBooks transaction mapping."""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QUICKBOOKS_CLIENT_ID", "test-client")
os.environ.setdefault("QUICKBOOKS_CLIENT_SECRET", "test-secret")

import quickbooks as qb  # noqa: E402

# Module constants are read at import; pin them for workers that imported quickbooks earlier.
qb.QB_CLIENT_ID = os.environ["QUICKBOOKS_CLIENT_ID"]
qb.QB_CLIENT_SECRET = os.environ["QUICKBOOKS_CLIENT_SECRET"]


def test_map_purchase_to_expense():
    txn = {
        "Id": "99",
        "TxnDate": "2024-03-15",
        "TotalAmt": 250.5,
        "EntityRef": {"name": "AWS"},
        "PrivateNote": "March cloud bill",
        "Line": [{"AccountBasedExpenseLineDetail": {"AccountRef": {"name": "Cloud/Infra"}}}],
    }
    mapped = qb.map_qb_transaction(txn, "purchase")
    assert mapped["type"] == "expense"
    assert mapped["category"] == "Cloud/Infra"
    assert mapped["amount"] == 250.5
    assert mapped["month"] == "2024-03"
    assert mapped["qb_txn_id"] == "qb_purchase_99"
    assert mapped["name"] == "AWS"
    assert mapped["category"] == "Cloud/Infra"
    assert "March cloud bill" in mapped["note"]


def test_map_invoice_to_revenue():
    txn = {
        "Id": "42",
        "TxnDate": "2024-06-01",
        "TotalAmt": 1200,
        "CustomerRef": {"name": "Acme Corp"},
        "DocNumber": "INV-1001",
    }
    mapped = qb.map_qb_transaction(txn, "invoice")
    assert mapped["type"] == "revenue"
    assert mapped["amount"] == 1200
    assert mapped["month"] == "2024-06"
    assert mapped["qb_txn_id"] == "qb_invoice_42"
    assert mapped["name"] == "Acme Corp"


def test_refresh_skips_when_token_fresh():
    tokens = {
        "access_token": "abc",
        "refresh_token": "r1",
        "expires_in": 3600,
        "obtained_at": datetime.now(timezone.utc).isoformat(),
        "realmId": "123",
    }
    with patch("quickbooks.httpx.AsyncClient") as mock_client:
        out = asyncio.run(qb.refresh_qb_token(tokens))
    assert out == tokens
    mock_client.assert_not_called()


def test_refresh_raises_on_failure():
    tokens = {
        "access_token": "abc",
        "refresh_token": "r1",
        "expires_in": 3600,
        "obtained_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
    }
    mock_resp = AsyncMock()
    mock_resp.status_code = 401
    mock_resp.text = "invalid_grant"
    mock_hc = AsyncMock()
    mock_hc.post = AsyncMock(return_value=mock_resp)
    mock_hc.__aenter__ = AsyncMock(return_value=mock_hc)
    mock_hc.__aexit__ = AsyncMock(return_value=None)

    with patch("integration_errors.httpx.AsyncClient", return_value=mock_hc):
        with pytest.raises(qb.QuickBooksAuthError):
            asyncio.run(qb.refresh_qb_token(tokens))


def test_refresh_preserves_refresh_token_when_intuit_omits_it(monkeypatch):
    """Intuit sometimes omits refresh_token on refresh — do not drop the grant."""
    monkeypatch.setattr(qb, "QB_CLIENT_ID", "test-client")
    monkeypatch.setattr(qb, "QB_CLIENT_SECRET", "test-secret")
    tokens = {
        "access_token": "old",
        "refresh_token": "keep-me",
        "expires_in": 3600,
        "obtained_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
        "realmId": "realm-9",
    }
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: {"access_token": "new", "expires_in": 3600}  # no refresh_token
    mock_hc = AsyncMock()
    mock_hc.post = AsyncMock(return_value=mock_resp)
    mock_hc.__aenter__ = AsyncMock(return_value=mock_hc)
    mock_hc.__aexit__ = AsyncMock(return_value=None)

    with patch("integration_errors.httpx.AsyncClient", return_value=mock_hc):
        out = asyncio.run(qb.refresh_qb_token(tokens))
    assert out["access_token"] == "new"
    assert out["refresh_token"] == "keep-me"
    assert out["realmId"] == "realm-9"


def test_purchase_credit_is_refund():
    txn = {
        "Id": "7",
        "TxnDate": "2024-04-01",
        "TotalAmt": 50,
        "Credit": True,
        "EntityRef": {"name": "Vendor"},
    }
    mapped = qb.map_qb_transaction(txn, "purchase")
    assert mapped["type"] == "expense"
    assert mapped["is_credit"] is True


def test_map_sales_receipt_and_credit_memo():
    sr = qb.map_qb_transaction(
        {"Id": "1", "TxnDate": "2024-05-01", "TotalAmt": 100, "CustomerRef": {"name": "A"}},
        "sales_receipt",
    )
    assert sr["type"] == "revenue"
    assert sr["is_credit"] is False
    cm = qb.map_qb_transaction(
        {"Id": "2", "TxnDate": "2024-05-02", "TotalAmt": 20, "CustomerRef": {"name": "A"}},
        "credit_memo",
    )
    assert cm["type"] == "revenue"
    assert cm["is_credit"] is True


def test_map_bill_and_vendor_credit():
    bill = qb.map_qb_transaction(
        {"Id": "3", "TxnDate": "2024-05-03", "TotalAmt": 80, "VendorRef": {"name": "V"}},
        "bill",
    )
    assert bill["type"] == "expense"
    vc = qb.map_qb_transaction(
        {"Id": "4", "TxnDate": "2024-05-04", "TotalAmt": 15, "VendorRef": {"name": "V"}},
        "vendor_credit",
    )
    assert vc["type"] == "expense"
    assert vc["is_credit"] is True


def test_map_journal_entry_pl_lines_only():
    je = {
        "Id": "je1",
        "TxnDate": "2024-06-10",
        "Line": [
            {
                "Id": "0",
                "Amount": 100,
                "DetailType": "JournalEntryLineDetail",
                "Description": "Revenue",
                "JournalEntryLineDetail": {
                    "PostingType": "Credit",
                    "AccountType": "Income",
                    "AccountRef": {"name": "Services"},
                },
            },
            {
                "Id": "1",
                "Amount": 40,
                "DetailType": "JournalEntryLineDetail",
                "Description": "Bank",
                "JournalEntryLineDetail": {
                    "PostingType": "Debit",
                    "AccountType": "Bank",
                    "AccountRef": {"name": "Checking"},
                },
            },
            {
                "Id": "2",
                "Amount": 40,
                "DetailType": "JournalEntryLineDetail",
                "Description": "COGS",
                "JournalEntryLineDetail": {
                    "PostingType": "Debit",
                    "AccountType": "Cost of Goods Sold",
                    "AccountRef": {"name": "COGS"},
                },
            },
        ],
    }
    rows = qb.map_qb_journal_entry(je)
    assert len(rows) == 2
    rev = next(r for r in rows if r["type"] == "revenue")
    exp = next(r for r in rows if r["type"] == "expense")
    assert rev["is_credit"] is False  # Credit to income = revenue
    assert exp["is_credit"] is False  # Debit to COGS = expense


def test_qb_minorversion_constant():
    assert qb.QB_MINOR_VERSION == 75


def test_warn_if_qb_env_missing_in_prod(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("QUICKBOOKS_ENV", raising=False)
    monkeypatch.delenv("QB_ENVIRONMENT", raising=False)
    monkeypatch.setattr(qb, "QB_ENV_EXPLICITLY_SET", False)
    msg = qb.warn_if_qb_env_missing_in_prod()
    assert msg and "CRITICAL" in msg
    diag = qb.qb_env_diagnostics()
    assert diag["quickbooks_env_warning"]
