"""T13: Xero entity coverage, status filters, 429 backoff, 403 handling (fixtures only)."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_xero_entities")

import server  # noqa: E402
import xero as xr  # noqa: E402

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "xero_entities.json").read_text())


class _Resp:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


class _XeroClient:
    instances = 0

    def __init__(self, *, rate_limit_first=0, forbidden=()):
        self.calls: list[tuple[str, dict]] = []
        self.rate_limit_first = rate_limit_first
        self.forbidden = set(forbidden)

    def __call__(self, *a, **k):
        type(self).instances += 1
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None, headers=None):
        key = url.rsplit("/", 1)[-1]
        self.calls.append((key, dict(params or {})))
        if key == "connections":
            return _Resp(200, [{"tenantId": "t1", "tenantName": "Org"}])
        if self.rate_limit_first:
            self.rate_limit_first -= 1
            return _Resp(429, headers={"Retry-After": "2"})
        if key in self.forbidden:
            return _Resp(403, {"Title": "Forbidden"})
        rows = list(FIXTURE.get(key, []))
        if key == "Invoices" and params and "where" in params:
            inv_type = "ACCREC" if 'Type=="ACCREC"' in params["where"] else "ACCPAY"
            rows = [r for r in rows if r["Type"] == inv_type]
        return _Resp(200, {key: rows})


def _tokens():
    return {"access_token": "a", "refresh_token": "r", "expires_in": 1800, "tenant_id": "t1",
            "obtained_at": datetime.now(timezone.utc).isoformat()}


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    async def _no_wait(*_a, **_k):
        return None

    monkeypatch.setattr(xr, "_throttle_xero", _no_wait)
    monkeypatch.setattr(xr.asyncio, "sleep", AsyncMock())
    _XeroClient.instances = 0


def _sync(client, since=None):
    with patch.object(xr.httpx, "AsyncClient", client):
        rows, complete, _tok, deleted = asyncio.run(xr.fetch_xero_transactions(_tokens(), "t1", since))
    return {r["qb_txn_id"]: r for r in rows}, complete, deleted


def test_full_sync_maps_every_type_with_one_client():
    client = _XeroClient()
    rows, complete, deleted = _sync(client)
    assert complete is True and deleted == []
    assert _XeroClient.instances == 1  # one shared AsyncClient per sync
    assert set(rows) == {
        "xero_invoice_inv-a", "xero_invoice_bill-a", "xero_bank_bt-r", "xero_bank_bt-s",
        "xero_cn_cn-r", "xero_cn_cn-p", "xero_mj_mj-1_0", "xero_mj_mj-1_1", "xero_mj_mj-1_2",
    }
    assert (rows["xero_invoice_inv-a"]["type"], rows["xero_invoice_inv-a"]["is_credit"]) == ("revenue", False)
    assert rows["xero_invoice_bill-a"]["type"] == "expense"
    assert rows["xero_bank_bt-r"]["type"] == "revenue" and rows["xero_bank_bt-s"]["type"] == "expense"
    assert (rows["xero_cn_cn-r"]["type"], rows["xero_cn_cn-r"]["is_credit"]) == ("revenue", True)
    assert (rows["xero_cn_cn-p"]["type"], rows["xero_cn_cn-p"]["is_credit"]) == ("expense", True)
    mj = {k: (v["type"], v["is_credit"], v["amount"]) for k, v in rows.items() if k.startswith("xero_mj_")}
    assert mj == {
        "xero_mj_mj-1_0": ("revenue", False, 700),
        "xero_mj_mj-1_1": ("expense", False, 200),
        "xero_mj_mj-1_2": ("expense", True, 25),
    }
    assert [c for c, _ in client.calls].count("Accounts") == 1


def test_full_sync_where_clauses():
    client = _XeroClient()
    _sync(client)
    where = {(k, p.get("where")) for k, p in client.calls if p.get("where")}
    assert ("Invoices", 'Type=="ACCREC" AND (Status=="AUTHORISED" OR Status=="PAID")') in where
    assert ("BankTransactions", 'Status=="AUTHORISED"') in where
    assert ("CreditNotes", '(Status=="AUTHORISED" OR Status=="PAID")') in where


def test_submitted_invoice_excluded_even_if_returned():
    rows, _c, _d = _sync(_XeroClient())
    assert "xero_invoice_inv-b" not in rows


def test_tax_and_currency_fields():
    rows, _c, _d = _sync(_XeroClient())
    inv = rows["xero_invoice_inv-a"]
    assert (inv["tax_amount"], inv["amount_net"], inv["currency"]) == (120, 1000, "php")
    bill = rows["xero_invoice_bill-a"]
    # CurrencyRate 0.02 USD per PHP base -> 110 USD = 5500 PHP.
    assert bill["amount_home"] == 5500 and bill["amount_net_home"] == 5000


def test_429_then_200_succeeds():
    client = _XeroClient(rate_limit_first=2)
    rows, complete, _d = _sync(client)
    assert complete is True
    assert "xero_invoice_inv-a" in rows
    xr.asyncio.sleep.assert_any_await(2.0)


def test_429_forever_is_transient():
    client = _XeroClient(rate_limit_first=100)
    with pytest.raises(xr.XeroTransientError):
        _sync(client)


def test_accounts_forbidden_skips_manual_journals_only():
    rows, complete, _d = _sync(_XeroClient(forbidden={"Accounts"}))
    assert complete is True
    assert not any(k.startswith("xero_mj_") for k in rows)
    assert "xero_invoice_inv-a" in rows


def test_403_with_tenant_listed_is_permission_error():
    with pytest.raises(xr.XeroPermissionError):
        _sync(_XeroClient(forbidden={"Invoices"}))


def test_sync_endpoint_403_keeps_tokens():
    ws = {"workspace_id": "ws1", "xero_tokens": {"sealed": 1}}
    with (
        patch.object(server, "get_ws", new=AsyncMock(return_value=ws)),
        patch.object(server, "_require_integration_token_use", return_value=_tokens()),
        patch.object(server, "_run_xero_sync_for_workspace",
                     new=AsyncMock(side_effect=xr.XeroPermissionError("x"))),
        patch.object(server, "_store_integration_tokens", new_callable=AsyncMock) as store,
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(server.xero_sync_endpoint(principal={"workspace_id": "ws1", "user_id": "u1", "pack": "owner"}))
    assert exc.value.status_code == 403
    assert exc.value.detail == (
        "Trenston doesn't have permission to read this data in Xero. Reconnect and approve all permissions."
    )
    store.assert_not_called()


def test_scopes_include_settings_for_accounts():
    assert "accounting.settings.read" in xr.XERO_SCOPES
    assert "offline_access" in xr.XERO_SCOPES


def test_catalog_flags_xero_reconnect_when_scope_missing():
    import integrations_catalog as cat

    old_grant = {"access_token": "z", "tenant_id": "t1",
                 "scope": "offline_access openid profile email accounting.invoices.read "
                          "accounting.banktransactions.read accounting.manualjournals.read"}
    ints = cat.merge_integrations({"workspace_id": "w", "xero_tokens": old_grant},
                                  google_configured=True, qb_configured=True, xero_configured=True)
    xero = next(i for i in ints if i["id"] == "xero")
    assert xero["connected"] is True and xero["needs_reconsent"] is True
    full = {**old_grant, "scope": xr.XERO_SCOPES}
    ints = cat.merge_integrations({"workspace_id": "w", "xero_tokens": full},
                                  google_configured=True, qb_configured=True, xero_configured=True)
    assert not next(i for i in ints if i["id"] == "xero").get("needs_reconsent")
