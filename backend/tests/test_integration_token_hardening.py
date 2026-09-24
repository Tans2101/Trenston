"""Token refresh classification, 401 retry, and Xero continue-fix."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QUICKBOOKS_CLIENT_ID", "test-client")
os.environ.setdefault("QUICKBOOKS_CLIENT_SECRET", "test-secret")
os.environ.setdefault("XERO_CLIENT_ID", "test-client")
os.environ.setdefault("XERO_CLIENT_SECRET", "test-secret")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_integration_errors")

import integration_errors as ierr  # noqa: E402
import quickbooks as qb  # noqa: E402
import xero as xr  # noqa: E402
import google_oauth as gcal  # noqa: E402
import sap_b1  # noqa: E402
import server  # noqa: E402

qb.QB_CLIENT_ID = "test-client"
qb.QB_CLIENT_SECRET = "test-secret"
xr.XERO_CLIENT_ID = "test-client"
xr.XERO_CLIENT_SECRET = "test-secret"


def _expired_tokens(**extra):
    base = {
        "access_token": "old",
        "refresh_token": "r1",
        "expires_in": 3600,
        "obtained_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
    }
    base.update(extra)
    return base


class _Resp:
    def __init__(self, status_code, text="", payload=None):
        self.status_code = status_code
        self.text = text if text else (json.dumps(payload) if payload is not None else "")
        self._payload = payload or {}

    def json(self):
        return self._payload


def test_is_revoked_only_on_invalid_grant():
    assert ierr.is_revoked_refresh_response(400, '{"error":"invalid_grant"}')
    assert ierr.is_revoked_refresh_response(401, "invalid_grant")
    assert not ierr.is_revoked_refresh_response(500, '{"error":"invalid_grant"}')
    assert not ierr.is_revoked_refresh_response(400, '{"error":"server_error"}')
    assert not ierr.is_revoked_refresh_response(503, "unavailable")


def test_other_4xx_without_invalid_grant_is_retryable():
    exc = ierr.classify_refresh_http_failure(
        provider="QuickBooks",
        status_code=400,
        body='{"error":"invalid_request"}',
        auth_error_cls=Exception,
        retryable_error_cls=ierr.IntegrationRetryableError,
    )
    assert isinstance(exc, ierr.IntegrationRetryableError)


def test_qb_refresh_5xx_keeps_tokens_retryable(monkeypatch):
    monkeypatch.setattr(qb, "QB_CLIENT_ID", "test-client")
    monkeypatch.setattr(qb, "QB_CLIENT_SECRET", "test-secret")
    tokens = _expired_tokens(realmId="123")

    mock_hc = AsyncMock()
    mock_hc.post = AsyncMock(return_value=_Resp(503, "service unavailable"))
    mock_hc.__aenter__ = AsyncMock(return_value=mock_hc)
    mock_hc.__aexit__ = AsyncMock(return_value=None)

    with patch("integration_errors.httpx.AsyncClient", return_value=mock_hc):
        with pytest.raises(qb.QuickBooksRetryableError):
            asyncio.run(qb.refresh_qb_token(tokens))


def test_qb_refresh_invalid_grant_is_auth(monkeypatch):
    monkeypatch.setattr(qb, "QB_CLIENT_ID", "test-client")
    monkeypatch.setattr(qb, "QB_CLIENT_SECRET", "test-secret")
    tokens = _expired_tokens()

    mock_hc = AsyncMock()
    mock_hc.post = AsyncMock(return_value=_Resp(400, payload={"error": "invalid_grant"}))
    mock_hc.__aenter__ = AsyncMock(return_value=mock_hc)
    mock_hc.__aexit__ = AsyncMock(return_value=None)

    with patch("integration_errors.httpx.AsyncClient", return_value=mock_hc):
        with pytest.raises(qb.QuickBooksAuthError):
            asyncio.run(qb.refresh_qb_token(tokens))


def test_xero_refresh_timeout_is_retryable(monkeypatch):
    monkeypatch.setattr(xr, "XERO_CLIENT_ID", "test-client")
    monkeypatch.setattr(xr, "XERO_CLIENT_SECRET", "test-secret")
    tokens = _expired_tokens(tenant_id="t1")

    mock_hc = AsyncMock()
    mock_hc.post = AsyncMock(side_effect=httpx.ConnectTimeout("boom"))
    mock_hc.__aenter__ = AsyncMock(return_value=mock_hc)
    mock_hc.__aexit__ = AsyncMock(return_value=None)

    with patch("integration_errors.httpx.AsyncClient", return_value=mock_hc):
        with pytest.raises(xr.XeroRetryableError):
            asyncio.run(xr.refresh_xero_token(tokens))


def test_google_refresh_invalid_grant_is_auth():
    tokens = _expired_tokens()
    mock_hc = AsyncMock()
    mock_hc.post = AsyncMock(return_value=_Resp(400, payload={"error": "invalid_grant"}))
    mock_hc.__aenter__ = AsyncMock(return_value=mock_hc)
    mock_hc.__aexit__ = AsyncMock(return_value=None)

    with patch("integration_errors.httpx.AsyncClient", return_value=mock_hc):
        with pytest.raises(gcal.GoogleAuthError):
            asyncio.run(gcal.refresh_google_token(tokens, "cid", "csec"))


@pytest.mark.asyncio
async def test_qb_data_401_forces_refresh_and_retries():
    tokens = {
        "access_token": "stale",
        "refresh_token": "r1",
        "expires_in": 3600,
        "obtained_at": datetime.now(timezone.utc).isoformat(),
        "realmId": "realm",
    }
    get_calls = {"n": 0}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            get_calls["n"] += 1
            if get_calls["n"] == 1:
                return _Resp(401, "expired")
            return _Resp(200, payload={"QueryResponse": {"Purchase": [{"Id": "1", "TxnDate": "2024-01-01", "TotalAmt": 10}]}})

        async def post(self, *a, **k):
            return _Resp(200, payload={
                "access_token": "fresh",
                "expires_in": 3600,
                "token_type": "bearer",
            })

    with patch.object(qb.httpx, "AsyncClient", _Client), patch(
        "integration_errors.httpx.AsyncClient", _Client,
    ):
        rows, complete, out_tokens = await qb._query_qb(tokens, "realm", "Purchase", None)
    assert complete is True
    assert len(rows) == 1
    assert out_tokens["access_token"] == "fresh"
    assert get_calls["n"] == 2


def test_accounting_auto_sync_runs_sap_when_xero_missing_tenant():
    workspaces = [{
        "workspace_id": "ws_both",
        "xero_tokens": {"sealed": True},
        "sap_b1_credentials": {"sealed": True},
        "xero_tokens_connected_by": "u1",
        "sap_b1_credentials_connected_by": "u2",
    }]

    class Cursor:
        async def to_list(self, _n):
            return workspaces

    fake_db = MagicMock()
    fake_db.workspaces.find = MagicMock(return_value=Cursor())

    async def fake_sap(c, principal, *, source="sap_b1_sync"):
        return {"synced_count": 4, "last_synced_at": "t"}

    with (
        patch.object(server, "db", fake_db),
        patch.object(server.cred_crypto, "credentials_present", side_effect=lambda v: bool(v)),
        patch.object(server, "_integration_tokens", return_value={"access_token": "x"}),
        patch.object(server, "_run_xero_sync_for_workspace", new_callable=AsyncMock) as xero_run,
        patch.object(server, "_run_sap_b1_sync_for_workspace", side_effect=fake_sap) as sap_run,
    ):
        stats = asyncio.run(server.run_accounting_auto_sync())

    xero_run.assert_not_called()
    assert stats["xero_skipped"] == 1
    assert stats["sap_b1_ok"] == 1
    assert stats["transactions_synced"] == 4


def test_accounting_auto_sync_retryable_does_not_wipe_qb():
    workspaces = [{"workspace_id": "ws_qb", "quickbooks_tokens": {"sealed": True}}]

    class Cursor:
        async def to_list(self, _n):
            return workspaces

    fake_db = MagicMock()
    fake_db.workspaces.find = MagicMock(return_value=Cursor())

    with (
        patch.object(server, "db", fake_db),
        patch.object(server.cred_crypto, "credentials_present", return_value=True),
        patch.object(
            server,
            "_run_quickbooks_sync_for_workspace",
            side_effect=server.qb_sync.QuickBooksRetryableError("503"),
        ),
        patch.object(server, "_store_integration_tokens", new_callable=AsyncMock) as store,
    ):
        stats = asyncio.run(server.run_accounting_auto_sync())

    assert stats["quickbooks_errors"] == 1
    assert stats["quickbooks_auth_errors"] == 0
    store.assert_not_called()
