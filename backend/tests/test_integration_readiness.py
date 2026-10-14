"""Integration readiness fixes: revoke on disconnect, HubSpot refresh classification,
sync watermark overlap, SAP certificate errors."""
import asyncio
import os
import ssl
from datetime import datetime, timedelta, timezone

import httpx
import pytest

os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

import hubspot  # noqa: E402
import integration_revoke  # noqa: E402
import sap_b1  # noqa: E402


def _patch_client(monkeypatch, handler):
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs.pop("verify", None)
        return real(transport=httpx.MockTransport(handler), **{k: v for k, v in kwargs.items() if k in ("timeout", "follow_redirects")})

    for mod in (hubspot, integration_revoke, sap_b1):
        monkeypatch.setattr(mod.httpx, "AsyncClient", factory)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_hubspot_refresh_5xx_is_transient_not_disconnect(monkeypatch):
    monkeypatch.setattr(hubspot, "HUBSPOT_CLIENT_ID", "id")
    monkeypatch.setattr(hubspot, "HUBSPOT_CLIENT_SECRET", "secret")
    _patch_client(monkeypatch, lambda req: httpx.Response(502, text="bad gateway"))
    with pytest.raises(hubspot.HubSpotTransientError):
        run(hubspot.refresh_hubspot_token({"refresh_token": "r"}))


def test_hubspot_refresh_bad_token_is_auth_error(monkeypatch):
    monkeypatch.setattr(hubspot, "HUBSPOT_CLIENT_ID", "id")
    monkeypatch.setattr(hubspot, "HUBSPOT_CLIENT_SECRET", "secret")
    _patch_client(monkeypatch, lambda req: httpx.Response(400, json={"status": "BAD_REFRESH_TOKEN", "message": "x"}))
    with pytest.raises(hubspot.HubSpotAuthError):
        run(hubspot.refresh_hubspot_token({"refresh_token": "r"}))


def test_hubspot_429_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(200, json={"results": []})

    _patch_client(monkeypatch, handler)

    async def no_sleep(_):
        return None

    monkeypatch.setattr(hubspot.asyncio, "sleep", no_sleep)

    async def go():
        async with httpx.AsyncClient() as hc:
            return await hubspot._send(hc, "get", "https://api.hubapi.com/x")

    assert run(go()).status_code == 200
    assert calls["n"] == 2


def test_revoke_helpers_hit_provider_endpoints(monkeypatch):
    seen = []

    def handler(req):
        seen.append((req.method, str(req.url)))
        return httpx.Response(200)

    _patch_client(monkeypatch, handler)
    tokens = {"refresh_token": "rt", "access_token": "at"}
    assert run(integration_revoke.revoke_google(tokens))
    assert run(integration_revoke.revoke_quickbooks(tokens, "id", "s"))
    assert run(integration_revoke.revoke_xero(tokens, "id", "s"))
    assert run(integration_revoke.revoke_hubspot(tokens))
    urls = " ".join(u for _, u in seen)
    assert "oauth2.googleapis.com/revoke" in urls
    assert "developer.api.intuit.com" in urls
    assert "identity.xero.com/connect/revocation" in urls
    assert ("DELETE", "https://api.hubapi.com/oauth/v1/refresh-tokens/rt") in seen


def test_revoke_never_raises_on_network_error(monkeypatch):
    def handler(req):
        raise httpx.ConnectError("down")

    _patch_client(monkeypatch, handler)
    assert run(integration_revoke.revoke_google({"refresh_token": "x"})) is False
    assert run(integration_revoke.revoke_hubspot({"refresh_token": "x"})) is False


def test_sap_certificate_error_detected():
    inner = ssl.SSLCertVerificationError("certificate verify failed: self-signed certificate")
    try:
        try:
            raise inner
        except ssl.SSLError as e:
            raise httpx.ConnectError("connect failed") from e
    except httpx.ConnectError as outer:
        assert sap_b1._is_certificate_error(outer)
    assert not sap_b1._is_certificate_error(httpx.ConnectError("connection refused"))


def test_sync_watermark_overlaps_start(monkeypatch):
    import server

    wm = datetime.fromisoformat(server._sync_watermark())
    now = datetime.now(timezone.utc)
    assert now - timedelta(minutes=6) < wm < now - timedelta(minutes=4)
