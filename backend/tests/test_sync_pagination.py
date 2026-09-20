"""Sync fetchers paginate and report incomplete when safety caps are hit."""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_sync_pagination")

import quickbooks as qb
import xero as xr


class _Resp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_qb_query_paginates_until_short_page():
    pages = [
        _Resp(200, {"QueryResponse": {"Purchase": [{"Id": str(i)} for i in range(qb.QB_PAGE_SIZE)]}}),
        _Resp(200, {"QueryResponse": {"Purchase": [{"Id": "last"}]}}),
    ]
    calls = {"n": 0}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            resp = pages[calls["n"]]
            calls["n"] += 1
            return resp

    with patch.object(qb.httpx, "AsyncClient", _Client):
        rows, complete = await qb._query_qb("tok", "realm", "Purchase", None)
    assert complete is True
    assert len(rows) == qb.QB_PAGE_SIZE + 1
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_qb_query_incomplete_when_max_pages_hit(monkeypatch):
    monkeypatch.setattr(qb, "QB_MAX_PAGES", 2)
    monkeypatch.setattr(qb, "QB_PAGE_SIZE", 2)

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return _Resp(200, {"QueryResponse": {"Invoice": [{"Id": "1"}, {"Id": "2"}]}})

    with patch.object(qb.httpx, "AsyncClient", _Client):
        rows, complete = await qb._query_qb("tok", "realm", "Invoice", None)
    assert complete is False
    assert len(rows) == 4


@pytest.mark.asyncio
async def test_xero_pages_until_short():
    payloads = [
        _Resp(200, {"Invoices": [{"InvoiceID": str(i)} for i in range(xr.XERO_PAGE_SIZE)]}),
        _Resp(200, {"Invoices": [{"InvoiceID": "tail"}]}),
    ]
    calls = {"n": 0}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            resp = payloads[calls["n"]]
            calls["n"] += 1
            return resp

    with patch.object(xr.httpx, "AsyncClient", _Client):
        rows, complete = await xr._fetch_invoices("tok", "tenant", "ACCREC", None)
    assert complete is True
    assert len(rows) == xr.XERO_PAGE_SIZE + 1
