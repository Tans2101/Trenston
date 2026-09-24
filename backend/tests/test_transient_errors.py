"""T1: temporary provider errors must never disconnect a customer.

For each provider: 5xx / timeout on token refresh -> <Provider>TransientError (tokens kept);
400 {"error":"invalid_grant"} -> <Provider>AuthError.
"""
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
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_transient_errors")

import google_oauth as gcal  # noqa: E402
import integration_errors as ierr  # noqa: E402
import quickbooks as qb  # noqa: E402
import sap_b1  # noqa: E402
import server  # noqa: E402
import xero as xr  # noqa: E402


class _Resp:
    def __init__(self, status_code, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload
        if text is not None:
            self.text = text
        else:
            self.text = json.dumps(payload) if payload is not None else ""
        self.content = self.text.encode()
        self.cookies = {}

    def json(self):
        if self._payload is None:
            return json.loads(self.text)
        return self._payload


def _client_returning(*, post=None, get=None):
    hc = AsyncMock()
    hc.post = AsyncMock(**post) if post else AsyncMock()
    hc.get = AsyncMock(**get) if get else AsyncMock()
    hc.__aenter__ = AsyncMock(return_value=hc)
    hc.__aexit__ = AsyncMock(return_value=None)
    return hc


def _expired(**extra):
    base = {
        "access_token": "old",
        "refresh_token": "r1",
        "expires_in": 3600,
        "obtained_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
    }
    base.update(extra)
    return base


@pytest.fixture(autouse=True)
def _oauth_creds(monkeypatch):
    monkeypatch.setattr(qb, "QB_CLIENT_ID", "cid")
    monkeypatch.setattr(qb, "QB_CLIENT_SECRET", "csec")
    monkeypatch.setattr(xr, "XERO_CLIENT_ID", "cid")
    monkeypatch.setattr(xr, "XERO_CLIENT_SECRET", "csec")


def _refresh(provider: str, tokens: dict):
    if provider == "quickbooks":
        return qb.refresh_qb_token(tokens)
    if provider == "xero":
        return xr.refresh_xero_token(tokens)
    return gcal.refresh_google_token(tokens, "cid", "csec")


_ERRORS = {
    "quickbooks": (qb.QuickBooksTransientError, qb.QuickBooksAuthError),
    "xero": (xr.XeroTransientError, xr.XeroAuthError),
    "google": (gcal.GoogleTransientError, gcal.GoogleAuthError),
}


@pytest.mark.parametrize("provider", ["quickbooks", "xero", "google"])
def test_refresh_500_is_transient(provider):
    transient, _ = _ERRORS[provider]
    hc = _client_returning(post={"return_value": _Resp(500, text="upstream down")})
    with patch("integration_errors.httpx.AsyncClient", return_value=hc):
        with pytest.raises(transient):
            asyncio.run(_refresh(provider, _expired()))


@pytest.mark.parametrize("provider", ["quickbooks", "xero", "google"])
def test_refresh_invalid_grant_is_auth(provider):
    _, auth = _ERRORS[provider]
    hc = _client_returning(post={"return_value": _Resp(400, {"error": "invalid_grant"})})
    with patch("integration_errors.httpx.AsyncClient", return_value=hc):
        with pytest.raises(auth):
            asyncio.run(_refresh(provider, _expired()))


@pytest.mark.parametrize("provider", ["quickbooks", "xero", "google"])
def test_refresh_timeout_is_transient(provider):
    transient, _ = _ERRORS[provider]
    hc = _client_returning(post={"side_effect": httpx.ReadTimeout("slow")})
    with patch("integration_errors.httpx.AsyncClient", return_value=hc):
        with pytest.raises(transient):
            asyncio.run(_refresh(provider, _expired()))


@pytest.mark.parametrize("provider", ["quickbooks", "xero", "google"])
@pytest.mark.parametrize(
    "resp",
    [
        _Resp(429, {"error": "rate_limited"}),
        _Resp(400, {"error": "invalid_request"}),
        _Resp(401, {"error": "invalid_client"}),
        _Resp(400, text="invalid_grant but not json"),
        _Resp(200, text="<html>not json</html>"),
    ],
)
def test_refresh_other_failures_are_transient(provider, resp):
    transient, _ = _ERRORS[provider]
    hc = _client_returning(post={"return_value": resp})
    with patch("integration_errors.httpx.AsyncClient", return_value=hc):
        with pytest.raises(transient):
            asyncio.run(_refresh(provider, _expired()))


def test_is_revoked_requires_json_invalid_grant():
    assert ierr.is_revoked_refresh_response(400, '{"error":"invalid_grant"}')
    assert ierr.is_revoked_refresh_response(401, '{"error":"invalid_grant"}')
    assert not ierr.is_revoked_refresh_response(401, "invalid_grant")
    assert not ierr.is_revoked_refresh_response(400, '{"error":"invalid_token"}')
    assert not ierr.is_revoked_refresh_response(500, '{"error":"invalid_grant"}')


def test_missing_refresh_token_stays_auth():
    with pytest.raises(qb.QuickBooksAuthError):
        asyncio.run(qb.refresh_qb_token({"obtained_at": None}))


# --------------------------- SAP Business One ---------------------------


@pytest.fixture
def _sap_no_dns(monkeypatch):
    monkeypatch.setattr(sap_b1, "normalize_service_layer_url", lambda url: url)


def _sap_login():
    return sap_b1.login(
        service_layer_url="https://sap.example.com/b1s/v1",
        company_db="DB", username="u", password="p",
    )


def test_sap_login_500_is_transient(_sap_no_dns):
    hc = _client_returning(post={"return_value": _Resp(503, text="down")})
    with patch.object(sap_b1.httpx, "AsyncClient", return_value=hc):
        with pytest.raises(sap_b1.SapB1TransientError):
            asyncio.run(_sap_login())


def test_sap_login_timeout_is_transient(_sap_no_dns):
    hc = _client_returning(post={"side_effect": httpx.ConnectTimeout("slow")})
    with patch.object(sap_b1.httpx, "AsyncClient", return_value=hc):
        with pytest.raises(sap_b1.SapB1TransientError):
            asyncio.run(_sap_login())


def test_sap_login_bad_credentials_is_auth(_sap_no_dns):
    body = {"error": {"code": 100000027, "message": {"value": "Enter a valid user name and password"}}}
    hc = _client_returning(post={"return_value": _Resp(401, body)})
    with patch.object(sap_b1.httpx, "AsyncClient", return_value=hc):
        with pytest.raises(sap_b1.SapB1AuthError):
            asyncio.run(_sap_login())


def test_sap_ensure_session_transport_error_does_not_relogin(_sap_no_dns):
    creds = {
        "service_layer_url": "https://sap.example.com/b1s/v1",
        "company_db": "DB", "username": "u", "password": "p", "session_id": "s1",
    }
    hc = _client_returning(get={"side_effect": httpx.ConnectError("unreachable")})
    with (
        patch.object(sap_b1.httpx, "AsyncClient", return_value=hc),
        patch.object(sap_b1, "login", new_callable=AsyncMock) as relogin,
    ):
        with pytest.raises(sap_b1.SapB1TransientError):
            asyncio.run(sap_b1.ensure_session(creds))
    relogin.assert_not_called()


# --------------------------- server.py call sites ---------------------------


def _principal():
    return {"workspace_id": "ws1", "user_id": "u1", "pack": "owner", "role": "owner"}


@pytest.mark.parametrize(
    "endpoint,runner,exc,field",
    [
        ("quickbooks_sync", "_run_quickbooks_sync_for_workspace", qb.QuickBooksTransientError, "quickbooks_tokens"),
        ("xero_sync_endpoint", "_run_xero_sync_for_workspace", xr.XeroTransientError, "xero_tokens"),
        ("sap_b1_sync_endpoint", "_run_sap_b1_sync_for_workspace", sap_b1.SapB1TransientError, "sap_b1_credentials"),
    ],
)
def test_sync_endpoint_transient_returns_503_and_keeps_tokens(endpoint, runner, exc, field):
    ws = {"workspace_id": "ws1", field: {"sealed": True}, "qb_last_synced_at": "2026-01-01"}
    with (
        patch.object(server, "get_ws", new=AsyncMock(return_value=ws)),
        patch.object(server, "_require_integration_token_use", return_value={"access_token": "a"}),
        patch.object(server, runner, new=AsyncMock(side_effect=exc("boom"))),
        patch.object(server, "_store_integration_tokens", new_callable=AsyncMock) as store,
    ):
        with pytest.raises(HTTPException) as err:
            asyncio.run(getattr(server, endpoint)(principal=_principal()))
    assert err.value.status_code == 503
    assert "temporarily unavailable" in err.value.detail
    store.assert_not_called()


def test_qb_sync_refresh_500_keeps_tokens_stored():
    """End to end through the runner: Intuit 500 on refresh -> 503, tokens never cleared."""
    ws = {"workspace_id": "ws1", "quickbooks_tokens": {"sealed": True}}
    hc = _client_returning(post={"return_value": _Resp(500, text="oops")})
    with (
        patch.object(server, "get_ws", new=AsyncMock(return_value=ws)),
        patch.object(server, "_require_integration_token_use", return_value={"access_token": "a"}),
        patch.object(server, "_integration_tokens", return_value=_expired(realmId="r1")),
        patch("integration_errors.httpx.AsyncClient", return_value=hc),
        patch.object(server, "_store_integration_tokens", new_callable=AsyncMock) as store,
    ):
        with pytest.raises(HTTPException) as err:
            asyncio.run(server.quickbooks_sync(principal=_principal()))
    assert err.value.status_code == 503
    store.assert_not_called()


def test_google_calendar_events_transient_keeps_tokens():
    with (
        patch.object(server, "_require_user_google_tokens", new=AsyncMock(return_value={"access_token": "a"})),
        patch.object(server, "get_ws", new=AsyncMock(return_value={"workspace_id": "ws1"})),
        patch.object(server.gcal, "fetch_today_calendar", new=AsyncMock(side_effect=gcal.GoogleTransientError("x"))),
        patch.object(server, "_store_user_google_tokens", new_callable=AsyncMock) as store,
    ):
        with pytest.raises(HTTPException) as err:
            asyncio.run(server.google_calendar_events(principal=_principal()))
    assert err.value.status_code == 503
    store.assert_not_called()


def test_google_calendar_events_auth_error_wipes_tokens():
    with (
        patch.object(server, "_require_user_google_tokens", new=AsyncMock(return_value={"access_token": "a"})),
        patch.object(server, "get_ws", new=AsyncMock(return_value={"workspace_id": "ws1"})),
        patch.object(server.gcal, "fetch_today_calendar", new=AsyncMock(side_effect=gcal.GoogleAuthError("x"))),
        patch.object(server, "_store_user_google_tokens", new_callable=AsyncMock) as store,
    ):
        with pytest.raises(HTTPException) as err:
            asyncio.run(server.google_calendar_events(principal=_principal()))
    assert err.value.status_code == 401
    store.assert_awaited_once_with("ws1", "u1", None)


def test_auto_sync_counts_transient_as_errors_without_wipe():
    workspaces = [{
        "workspace_id": "ws1",
        "quickbooks_tokens": {"s": 1},
        "xero_tokens": {"s": 1},
        "sap_b1_credentials": {"s": 1},
    }]

    class Cursor:
        async def to_list(self, _n):
            return workspaces

    fake_db = MagicMock()
    fake_db.workspaces.find = MagicMock(return_value=Cursor())
    with (
        patch.object(server, "db", fake_db),
        patch.object(server.cred_crypto, "credentials_present", return_value=True),
        patch.object(server, "_integration_tokens", return_value={"tenant_id": "t1"}),
        patch.object(server, "_run_quickbooks_sync_for_workspace", new=AsyncMock(side_effect=qb.QuickBooksTransientError("x"))),
        patch.object(server, "_run_xero_sync_for_workspace", new=AsyncMock(side_effect=xr.XeroTransientError("x"))),
        patch.object(server, "_run_sap_b1_sync_for_workspace", new=AsyncMock(side_effect=sap_b1.SapB1TransientError("x"))),
        patch.object(server, "_store_integration_tokens", new_callable=AsyncMock) as store,
    ):
        stats = asyncio.run(server.run_accounting_auto_sync())
    assert stats["quickbooks_errors"] == stats["xero_errors"] == stats["sap_b1_errors"] == 1
    assert stats["quickbooks_auth_errors"] == stats["xero_auth_errors"] == stats["sap_b1_auth_errors"] == 0
    store.assert_not_called()
