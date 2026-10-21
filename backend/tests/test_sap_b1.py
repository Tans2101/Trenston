"""SAP Business One Service Layer client + catalog wiring."""
from __future__ import annotations

import socket
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import credential_crypto as cred_crypto
import integrations_catalog as cat
import sap_b1


def _public_addrinfo(host, *args, **kwargs):
    """Pretend host resolves to a public address (not RFC1918 / loopback / TEST-NET)."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.8.8", 0))]


def test_normalize_service_layer_url():
    with patch.object(sap_b1.socket, "getaddrinfo", side_effect=_public_addrinfo):
        assert sap_b1.normalize_service_layer_url("https://erp.example:50000") == "https://erp.example:50000/b1s/v1"
        assert sap_b1.normalize_service_layer_url("https://erp.example:50000/b1s/v1/") == "https://erp.example:50000/b1s/v1"
        assert sap_b1.normalize_service_layer_url("erp.example:50000/b1s") == "https://erp.example:50000/b1s/v1"


def test_normalize_rejects_http_and_private_targets():
    with pytest.raises(ValueError, match="https"):
        sap_b1.normalize_service_layer_url("http://erp.example:50000")

    with pytest.raises(ValueError, match="private or internal"):
        sap_b1.normalize_service_layer_url("https://127.0.0.1:50000")

    with pytest.raises(ValueError, match="private or internal"):
        sap_b1.normalize_service_layer_url("https://10.0.0.5/b1s/v1")

    with pytest.raises(ValueError, match="private or internal"):
        sap_b1.normalize_service_layer_url("https://169.254.169.254/latest/meta-data")

    with pytest.raises(ValueError, match="private or internal"):
        sap_b1.normalize_service_layer_url("https://192.168.1.1/b1s/v1")

    with pytest.raises(ValueError, match="private or internal"):
        sap_b1.normalize_service_layer_url("https://172.16.5.5/b1s/v1")

    def _private_dns(host, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.1.2.3", 0))]

    with patch.object(sap_b1.socket, "getaddrinfo", side_effect=_private_dns):
        with pytest.raises(ValueError, match="private or internal"):
            sap_b1.normalize_service_layer_url("https://internal.corp/b1s/v1")


def test_normalize_rejects_ipv6_loopback_and_ula():
    with pytest.raises(ValueError, match="private or internal"):
        sap_b1.normalize_service_layer_url("https://[::1]:50000/b1s/v1")
    with pytest.raises(ValueError, match="private or internal"):
        sap_b1.normalize_service_layer_url("https://[fc00::1]/b1s/v1")
    with pytest.raises(ValueError, match="private or internal"):
        sap_b1.normalize_service_layer_url("https://[fe80::1]/b1s/v1")


def test_undated_sap_document_is_skipped_not_assigned_today():
    """Missing DocDate/TaxDate used to invent UTC today → wrong ledger month."""
    assert sap_b1._parse_doc_date({"DocEntry": 1}) == ""
    assert sap_b1.map_sap_document(
        {"DocEntry": 1, "DocTotal": 10, "Cancelled": "tNO"}, kind="ar",
    ) is None


def test_fetch_collection_page_uses_params_not_raw_filter_in_path():
    """Filter/select must be httpx-encoded params (spaces/quotes safe)."""
    captured = {}

    class _Resp:
        status_code = 200

    async def fake_get(url, params=None, headers=None):
        captured["url"] = url
        captured["params"] = params
        return _Resp()

    hc = MagicMock()
    hc.get = fake_get
    hc.__aenter__ = AsyncMock(return_value=hc)
    hc.__aexit__ = AsyncMock(return_value=None)

    creds = {
        "service_layer_url": "https://erp.example:50000/b1s/v1",
        "session_id": "sid",
        "route_id": None,
    }

    async def run():
        with (
            patch.object(sap_b1, "_revalidate_service_layer_url", return_value=creds["service_layer_url"]),
            patch.object(sap_b1.httpx, "AsyncClient", return_value=hc),
        ):
            return await sap_b1._fetch_collection_page(
                creds, "Invoices",
                select="DocEntry,DocDate",
                filt="Cancelled eq 'tNO' and UpdateDate ge '2026-01-01'",
                skip=0,
            )

    import asyncio
    asyncio.run(run())
    assert "$filter" not in (captured.get("url") or "")
    assert captured["params"]["$filter"].startswith("Cancelled eq")
    assert captured["params"]["$skip"] == "0"


def test_map_sap_ar_and_ap_documents():
    ar = sap_b1.map_sap_document(
        {
            "DocEntry": 11,
            "DocNum": 1001,
            "DocDate": "2026-09-01",
            "DocTotal": 250.5,
            "CardName": "Acme Corp",
            "Comments": "September invoice",
            "Cancelled": "tNO",
            "DocumentLines": [{"AccountCode": "400000"}],
        },
        kind="ar",
    )
    assert ar["type"] == "revenue"
    assert ar["amount"] == 250.5
    assert ar["month"] == "2026-09"
    assert ar["qb_txn_id"] == "sap_b1_ar_11"
    assert ar["category"] == "400000"
    assert "Acme" in ar["name"]

    ap = sap_b1.map_sap_document(
        {
            "DocEntry": 22,
            "DocDate": "2026-09-02",
            "DocTotal": 80,
            "CardName": "Office Supplies Ltd",
            "Cancelled": "tNO",
        },
        kind="ap",
    )
    assert ap["type"] == "expense"
    assert ap["qb_txn_id"] == "sap_b1_ap_22"
    assert ap["category"] == "Other"


def test_map_skips_cancelled():
    assert sap_b1.map_sap_document(
        {"DocEntry": 1, "DocDate": "2026-09-01", "DocTotal": 10, "Cancelled": "tYES"},
        kind="ar",
    ) is None


def test_catalog_sap_credentials_connected():
    sealed = cred_crypto.seal_credentials({
        "service_layer_url": "https://erp.example:50000/b1s/v1",
        "company_db": "SBODEMOUS",
        "username": "manager",
        "password": "secret",
    })
    ws = {
        "workspace_id": "ws1",
        "sap_b1_credentials": sealed,
        "sap_b1_last_synced_at": "2026-09-10T12:00:00+00:00",
    }
    ints = cat.merge_integrations(ws, google_configured=True, qb_configured=True)
    sap = next(i for i in ints if i["id"] == "sap_b1")
    assert sap["kind"] == "credentials"
    assert sap["configured"] is True
    assert sap["connected"] is True
    assert sap["status"] == "connected"
    assert sap["tenant_name"] == "SBODEMOUS"
    assert sap["last_synced_at"] == "2026-09-10T12:00:00+00:00"
    assert sap["sync_action"] is True


def test_catalog_sap_not_connected_by_default():
    ints = cat.merge_integrations({}, google_configured=True, qb_configured=True)
    sap = next(i for i in ints if i["id"] == "sap_b1")
    assert sap["status"] == "not_connected"
    assert sap["connected"] is False


@pytest.mark.asyncio
async def test_login_stores_session(monkeypatch):
    class FakeResp:
        status_code = 200
        content = b'{"SessionId":"SESS1","SessionTimeout":30}'
        text = ""
        cookies = {"B1SESSION": "SESS1", "ROUTEID": ".node1"}

        def json(self):
            return {"SessionId": "SESS1", "SessionTimeout": 30}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            assert url.endswith("/Login")
            assert json["CompanyDB"] == "SBODEMOUS"
            return FakeResp()

    monkeypatch.setattr(sap_b1.socket, "getaddrinfo", _public_addrinfo)
    monkeypatch.setattr(sap_b1.httpx, "AsyncClient", FakeClient)
    creds = await sap_b1.login(
        service_layer_url="https://erp.example:50000",
        company_db="SBODEMOUS",
        username="manager",
        password="secret",
    )
    assert creds["session_id"] == "SESS1"
    assert creds["company_db"] == "SBODEMOUS"
    assert creds["service_layer_url"].endswith("/b1s/v1")
    assert "password" in creds


@pytest.mark.asyncio
async def test_fetch_sap_transactions_maps_collections(monkeypatch):
    creds = {
        "service_layer_url": "https://erp.example:50000/b1s/v1",
        "company_db": "SBODEMOUS",
        "username": "manager",
        "password": "secret",
        "session_id": "SESS1",
    }

    async def fake_ensure(c):
        return c

    async def fake_collection(c, collection, *, since=None):
        if collection == "Invoices":
            return [{
                "DocEntry": 1,
                "DocDate": "2026-09-01",
                "DocTotal": 100,
                "CardName": "Customer",
                "Cancelled": "tNO",
            }], True, c
        if collection != "PurchaseInvoices":
            return [], True, c
        return [{
            "DocEntry": 2,
            "DocDate": "2026-09-02",
            "DocTotal": 40,
            "CardName": "Vendor",
            "Cancelled": "tNO",
        }], True, c

    monkeypatch.setattr(sap_b1, "ensure_session", fake_ensure)
    monkeypatch.setattr(sap_b1, "_fetch_collection", fake_collection)
    rows, complete, live, deleted = await sap_b1.fetch_sap_transactions(creds)
    assert complete is True
    assert live is creds
    assert deleted == []
    assert {r["type"] for r in rows} == {"revenue", "expense"}
    assert {r["qb_txn_id"] for r in rows} == {
        "sap_b1_ar_1",
        "sap_b1_ap_2",
    }


@pytest.mark.asyncio
async def test_login_auth_error_does_not_echo_body(monkeypatch):
    class FakeResp:
        status_code = 401
        content = b"{}"
        text = "SECRET_INTERNAL_STACK_TRACE"
        cookies = {}

        def json(self):
            return {}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return FakeResp()

    monkeypatch.setattr(sap_b1.socket, "getaddrinfo", _public_addrinfo)
    monkeypatch.setattr(sap_b1.httpx, "AsyncClient", FakeClient)
    with pytest.raises(sap_b1.SapB1AuthError) as ei:
        await sap_b1.login(
            service_layer_url="https://erp.example:50000",
            company_db="SBODEMOUS",
            username="manager",
            password="wrong",
        )
    assert "SECRET_INTERNAL" not in str(ei.value)
    assert str(ei.value) == "SAP connection failed"


@pytest.mark.asyncio
async def test_login_never_requests_private_url(monkeypatch):
    called = {"n": 0}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            called["n"] += 1
            raise AssertionError("should not reach network")

    monkeypatch.setattr(sap_b1.httpx, "AsyncClient", FakeClient)
    with pytest.raises(ValueError, match="private or internal"):
        await sap_b1.login(
            service_layer_url="https://169.254.169.254/",
            company_db="SBODEMOUS",
            username="manager",
            password="secret",
        )
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_fetch_collection_revalidates_url_each_page(monkeypatch):
    """Stored service_layer_url must be re-checked on outbound sync (DNS rebinding)."""
    calls = {"n": 0}
    original = sap_b1.normalize_service_layer_url

    def counting_normalize(url):
        calls["n"] += 1
        return original(url)

    class FakeResp:
        status_code = 200
        text = ""

        def json(self):
            return {"value": []}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return FakeResp()

    monkeypatch.setattr(sap_b1.socket, "getaddrinfo", _public_addrinfo)
    monkeypatch.setattr(sap_b1, "normalize_service_layer_url", counting_normalize)
    monkeypatch.setattr(sap_b1.httpx, "AsyncClient", FakeClient)
    creds = {
        "service_layer_url": "https://erp.example:50000/b1s/v1",
        "session_id": "sess",
        "route_id": None,
    }
    rows, complete, _creds = await sap_b1._fetch_collection(creds, "Invoices")
    assert rows == []
    assert complete is True
    assert calls["n"] >= 1


@pytest.mark.asyncio
async def test_ensure_session_rejects_rebinding_to_private(monkeypatch):
    def _private_dns(host, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.1.2.3", 0))]

    called = {"n": 0}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            called["n"] += 1
            raise AssertionError("must not contact rebinding host")

    monkeypatch.setattr(sap_b1.socket, "getaddrinfo", _private_dns)
    monkeypatch.setattr(sap_b1.httpx, "AsyncClient", FakeClient)
    with pytest.raises(ValueError, match="private or internal"):
        await sap_b1.ensure_session({
            "service_layer_url": "https://evil.example/b1s/v1",
            "session_id": "sess",
            "company_db": "DB",
            "username": "u",
            "password": "p",
        })
    assert called["n"] == 0
