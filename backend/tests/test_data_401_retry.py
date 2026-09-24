"""T2: a 401 from a data endpoint forces one token refresh, persists it, and retries once."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_data_401_retry")

import google_oauth as gcal  # noqa: E402
import quickbooks as qb  # noqa: E402
import server  # noqa: E402
import xero as xr  # noqa: E402


class _Resp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = json.dumps(self._payload)
        self.headers = {}
        self.content = self.text.encode()

    def json(self):
        return self._payload


def _fresh_tokens(**extra):
    return {
        "access_token": "stale",
        "refresh_token": "r1",
        "expires_in": 3600,
        "obtained_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    }


class _FakeClient:
    """httpx.AsyncClient stand-in: first data call 401, token POST 200, later calls 200."""

    def __init__(self, data_ok_payload, *, data_method="get"):
        self.calls: list[tuple[str, str, str]] = []
        self.data_ok_payload = data_ok_payload
        self.data_method = data_method
        self.first_data_seen = False

    def __call__(self, *a, **k):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def _auth(self, kwargs):
        return (kwargs.get("headers") or {}).get("Authorization", "")

    async def _data(self, method, url, **kwargs):
        self.calls.append((method, url, self._auth(kwargs)))
        if not self.first_data_seen:
            self.first_data_seen = True
            return _Resp(401, {"error": "expired"})
        assert self._auth(kwargs) == "Bearer fresh"
        return _Resp(200, self.data_ok_payload(url) if callable(self.data_ok_payload) else self.data_ok_payload)

    async def get(self, url, **kwargs):
        return await self._data("get", url, **kwargs)

    async def patch(self, url, **kwargs):
        return await self._data("patch", url, **kwargs)

    async def delete(self, url, **kwargs):
        return await self._data("delete", url, **kwargs)

    async def post(self, url, **kwargs):
        if "token" in url:
            self.calls.append(("token", url, ""))
            return _Resp(200, {"access_token": "fresh", "expires_in": 3600, "refresh_token": "r2"})
        return await self._data("post", url, **kwargs)


@pytest.fixture(autouse=True)
def _creds(monkeypatch):
    monkeypatch.setattr(qb, "QB_CLIENT_ID", "cid")
    monkeypatch.setattr(qb, "QB_CLIENT_SECRET", "csec")
    monkeypatch.setattr(xr, "XERO_CLIENT_ID", "cid")
    monkeypatch.setattr(xr, "XERO_CLIENT_SECRET", "csec")

    async def _no_throttle():
        return None

    monkeypatch.setattr(xr, "_throttle_xero", _no_throttle)


def _principal():
    return {"workspace_id": "ws1", "user_id": "u1", "pack": "owner", "role": "owner"}


def test_quickbooks_sync_401_refreshes_persists_and_succeeds():
    fake = _FakeClient({"QueryResponse": {}})
    ws = {"workspace_id": "ws1", "quickbooks_tokens": {"sealed": 1}}
    fake_db = MagicMock()
    fake_db.workspaces.update_one = AsyncMock()
    with (
        patch.object(qb.httpx, "AsyncClient", fake),
        patch.object(server, "db", fake_db),
        patch.object(server, "_integration_tokens", return_value=_fresh_tokens(realmId="realm")),
        patch.object(server, "_upsert_accounting_sync_entries", new=AsyncMock(return_value=0)),
        patch.object(server, "_store_integration_tokens", new_callable=AsyncMock) as store,
    ):
        result = asyncio.run(server._run_quickbooks_sync_for_workspace(ws, _principal()))
    assert result["complete"] is True
    assert [c[0] for c in fake.calls].count("token") == 1
    persisted = store.await_args_list[-1].args
    assert persisted[1] == "quickbooks_tokens"
    assert persisted[2]["access_token"] == "fresh"
    assert persisted[2]["realmId"] == "realm"


def test_quickbooks_second_401_is_auth_error():
    class Always401(_FakeClient):
        async def _data(self, method, url, **kwargs):
            return _Resp(401, {})

    with patch.object(qb.httpx, "AsyncClient", Always401({})):
        with pytest.raises(qb.QuickBooksAuthError):
            asyncio.run(qb._query_qb(_fresh_tokens(), "realm", "Invoice", None))


def test_xero_sync_401_refreshes_persists_and_succeeds():
    def payload(url):
        key = url.rsplit("/", 1)[-1]
        return {key: []}

    fake = _FakeClient(payload)
    ws = {"workspace_id": "ws1", "xero_tokens": {"sealed": 1}}
    fake_db = MagicMock()
    fake_db.workspaces.update_one = AsyncMock()
    with (
        patch.object(xr.httpx, "AsyncClient", fake),
        patch.object(server, "db", fake_db),
        patch.object(server, "_integration_tokens", return_value=_fresh_tokens(tenant_id="t1")),
        patch.object(server, "_upsert_accounting_sync_entries", new=AsyncMock(return_value=0)),
        patch.object(server, "_store_integration_tokens", new_callable=AsyncMock) as store,
    ):
        result = asyncio.run(server._run_xero_sync_for_workspace(ws, _principal()))
    assert result["complete"] is True
    assert [c[0] for c in fake.calls].count("token") == 1
    persisted = store.await_args_list[-1].args
    assert persisted[1] == "xero_tokens"
    assert persisted[2]["access_token"] == "fresh"
    assert persisted[2]["tenant_id"] == "t1"


def test_gmail_threads_401_refreshes_and_retries():
    def payload(url):
        if url.endswith("/profile"):
            return {"emailAddress": "me@acme.com"}
        return {"messages": []}

    class GmailFake(_FakeClient):
        async def get(self, url, **kwargs):
            # The profile call is best-effort; the list call is the one that 401s.
            if url.endswith("/profile"):
                return _Resp(200, payload(url))
            return await self._data("get", url, **kwargs)

    fake = GmailFake(payload)
    tokens = _fresh_tokens(scope="https://www.googleapis.com/auth/gmail.readonly")
    with patch.object(gcal.httpx, "AsyncClient", fake):
        threads, out = asyncio.run(gcal.fetch_important_threads(tokens, "cid", "csec"))
    assert threads == []
    assert out["access_token"] == "fresh"
    assert [c[0] for c in fake.calls].count("token") == 1


@pytest.mark.parametrize("op", ["create", "patch", "delete"])
def test_calendar_writes_401_refresh_and_retry(op):
    fake = _FakeClient({"id": "g1"})
    tokens = _fresh_tokens(scope="https://www.googleapis.com/auth/calendar.events")
    kw = dict(title="T", start_iso="2026-09-25T09:00:00+08:00", end_iso="2026-09-25T10:00:00+08:00")
    with patch.object(gcal.httpx, "AsyncClient", fake):
        if op == "create":
            gid, out = asyncio.run(gcal.create_calendar_event(tokens, "cid", "csec", **kw))
            assert gid == "g1"
        elif op == "patch":
            out = asyncio.run(gcal.patch_calendar_event(tokens, "cid", "csec", "g1", **kw))
        else:
            out = asyncio.run(gcal.delete_calendar_event(tokens, "cid", "csec", "g1"))
    assert out["access_token"] == "fresh"
    assert [c[0] for c in fake.calls].count("token") == 1


def test_calendar_events_route_persists_refreshed_tokens():
    fake = _FakeClient({"items": []})
    tokens = _fresh_tokens()
    with (
        patch.object(gcal.httpx, "AsyncClient", fake),
        patch.object(server, "_require_user_google_tokens", new=AsyncMock(return_value=tokens)),
        patch.object(server, "get_ws", new=AsyncMock(return_value={"workspace_id": "ws1"})),
        patch.object(server, "GOOGLE_CLIENT_ID", "cid"),
        patch.object(server, "GOOGLE_CLIENT_SECRET", "csec"),
        patch.object(server, "_store_user_google_tokens", new_callable=AsyncMock) as store,
    ):
        out = asyncio.run(server.google_calendar_events(principal=_principal()))
    assert out["live"] is True
    store.assert_awaited_once()
    assert store.await_args.args[2]["access_token"] == "fresh"
