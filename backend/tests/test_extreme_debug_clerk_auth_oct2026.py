"""Regressions for extreme-debug of backend/clerk_auth.py (Oct 2026)."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_extreme_debug_clerk_auth")
os.environ["CLERK_SECRET_KEY"] = "sk_live_test"
os.environ["CLERK_JWKS_URL"] = "https://clerk.trenston.com/.well-known/jwks.json"
os.environ["FRONTEND_URL"] = "https://www.trenston.com"
os.environ["APP_URL"] = "https://www.trenston.com"

_WEBHOOK_SECRET_BYTES = b"\x11" * 32
_WEBHOOK_SECRET = "whsec_" + base64.b64encode(_WEBHOOK_SECRET_BYTES).decode()
os.environ["CLERK_WEBHOOK_SIGNING_SECRET"] = _WEBHOOK_SECRET

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import clerk_auth  # noqa: E402

clerk_auth.CLERK_SECRET_KEY = os.environ["CLERK_SECRET_KEY"]
clerk_auth.CLERK_JWKS_URL = os.environ["CLERK_JWKS_URL"]
clerk_auth.CLERK_WEBHOOK_SECRET = _WEBHOOK_SECRET


def _sign_raw(body: bytes, *, msg_id: str = "msg_1", ts: int | None = None) -> dict[str, str]:
    ts = int(time.time()) if ts is None else ts
    signed = f"{msg_id}.{ts}.".encode("utf-8") + body
    sig = base64.b64encode(
        hmac.new(_WEBHOOK_SECRET_BYTES, signed, hashlib.sha256).digest()
    ).decode()
    return {
        "svix-id": msg_id,
        "svix-timestamp": str(ts),
        "svix-signature": f"v1,{sig}",
    }


def test_webhook_accepts_utf8_json_with_raw_byte_hmac():
    clerk_auth.CLERK_WEBHOOK_SECRET = _WEBHOOK_SECRET
    body = json.dumps({"type": "user.updated", "data": {"id": "user_1"}}).encode()
    event = clerk_auth.verify_clerk_webhook(body, _sign_raw(body))
    assert event["type"] == "user.updated"


def test_webhook_non_utf8_body_raises_valueerror_not_unicode():
    clerk_auth.CLERK_WEBHOOK_SECRET = _WEBHOOK_SECRET
    body = b"\xff\xfe{not-json"
    headers = _sign_raw(body)
    with pytest.raises(ValueError, match="JSON|signature"):
        clerk_auth.verify_clerk_webhook(body, headers)


@pytest.mark.asyncio
async def test_ssl_ok_false_when_tls_probe_fails():
    """Do not invent ssl_ok from a BAPI domain row (would disable clerk_use_proxy)."""
    clerk_auth._health_probe_cache.pop("ssl", None)
    with patch.object(
        clerk_auth.httpx, "AsyncClient",
    ) as client_cls:
        client = AsyncMock()
        client.get = AsyncMock(side_effect=OSError("tls fail"))
        client_cls.return_value.__aenter__ = AsyncMock(return_value=client)
        client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        ok = await clerk_auth.clerk_custom_domain_ssl_ok()
    assert ok is False


@pytest.mark.asyncio
async def test_assert_clerk_session_rejects_pending():
    class _Resp:
        def __init__(self, data, status=200):
            self.status_code = status
            self._data = data

        def json(self):
            return self._data

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None):
            return _Resp({"user_id": "user_x", "status": "pending"})

    with patch.object(clerk_auth.httpx, "AsyncClient", _Client):
        with pytest.raises(ValueError, match="not active"):
            await clerk_auth.assert_clerk_session_active(sid="sess_x", sub="user_x")


@pytest.mark.asyncio
async def test_bapi_session_helper_requires_jwks_signature():
    """Unsigned token must not authenticate via BAPI session lookup alone."""
    now = int(time.time())
    h = base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "kid": "k"}).encode()).rstrip(b"=").decode()
    p = base64.urlsafe_b64encode(json.dumps({
        "sub": "user_x", "sid": "sess_x", "exp": now + 60,
        "iss": "https://clerk.trenston.com", "azp": "https://www.trenston.com",
    }).encode()).rstrip(b"=").decode()
    forged = f"{h}.{p}.fakesig"
    with patch.object(
        clerk_auth, "_fetch_jwks_async", AsyncMock(return_value={"keys": []}),
    ):
        with pytest.raises(ValueError):
            await clerk_auth._verify_clerk_session_via_bapi(forged)


def test_sync_reports_incomplete_when_portal_fails():
    instance = {
        "environment_type": "production",
        "allowed_origins": list(clerk_auth.helm_frontend_origins()),
    }

    class Resp:
        def __init__(self, data, status=200, text=""):
            self.status_code = status
            self._data = data
            self.text = text
            self.content = b"{}" if data is not None else b""

        def json(self):
            return self._data

    async def mock_get(url, **kwargs):
        u = str(url)
        if u.endswith("/instance"):
            return Resp(instance)
        if "/environment" in u:
            return Resp({
                "user_settings": {
                    "attributes": {"password": {"enabled": True, "required": False}},
                    "sign_up": {},
                    "social": {"oauth_google": {"enabled": True}},
                },
                "auth_config": {"password": "on"},
                "display_config": {
                    "sign_in_url": "https://accounts.trenston.com/sign-in",
                    "sign_up_url": "https://accounts.trenston.com/sign-up",
                    "after_sign_in_url": "https://www.trenston.com/app",
                    "after_sign_up_url": "https://www.trenston.com/app",
                    "after_sign_out_all_url": "https://accounts.trenston.com/sign-in",
                },
            })
        if u.endswith("/redirect_urls"):
            return Resp({"data": [{"url": u} for u in clerk_auth._clerk_redirect_url_list()]})
        if u.endswith("/domains"):
            return Resp({"data": [{"name": "trenston.com", "id": "dom_1"}]})
        return Resp({}, 404)

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=mock_get)
    mock_client.patch = AsyncMock(return_value=Resp({}, 422, "rejected"))
    mock_client.post = AsyncMock(return_value=Resp({}, 201))
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_client
    mock_cm.__aexit__.return_value = None

    with patch("clerk_auth.httpx.AsyncClient", return_value=mock_cm):
        with patch.object(clerk_auth, "clerk_custom_domain_ssl_ok", AsyncMock(return_value=True)):
            result = asyncio.run(clerk_auth.sync_clerk_instance())

    assert result.get("origins_synced") is True
    assert result["synced"] is False
    assert result["reason"] == "origins_ok_auth_incomplete"


def test_production_origins_drop_localhost(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    origins = clerk_auth.helm_frontend_origins()
    assert "http://localhost:3000" not in origins
    parties = clerk_auth.clerk_authorized_parties()
    assert all("localhost" not in p for p in parties)
