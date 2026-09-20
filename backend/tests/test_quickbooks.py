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
    assert mapped["qb_txn_id"] == "99_2024-03-15"
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
    assert mapped["qb_txn_id"] == "42_2024-06-01"
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

    with patch("quickbooks.httpx.AsyncClient", return_value=mock_hc):
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

    with patch("quickbooks.httpx.AsyncClient", return_value=mock_hc):
        out = asyncio.run(qb.refresh_qb_token(tokens))
    assert out["access_token"] == "new"
    assert out["refresh_token"] == "keep-me"
    assert out["realmId"] == "realm-9"
