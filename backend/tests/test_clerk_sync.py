"""Clerk instance sync for trenston.com deployment."""
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_clerk_sync")
os.environ["CLERK_SECRET_KEY"] = "sk_live_test"
os.environ["CLERK_JWKS_URL"] = "https://clerk.trenston.com/.well-known/jwks.json"
os.environ["FRONTEND_URL"] = "https://www.trenston.com"
os.environ["APP_URL"] = "https://www.trenston.com"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import clerk_auth  # noqa: E402

# Module constants are read at import; pin them when another suite imported clerk_auth first.
clerk_auth.CLERK_SECRET_KEY = os.environ["CLERK_SECRET_KEY"]
clerk_auth.CLERK_JWKS_URL = os.environ["CLERK_JWKS_URL"]
clerk_auth.FRONTEND_URL = os.environ["FRONTEND_URL"]
clerk_auth.APP_URL_CLERK = os.environ.get("APP_URL", os.environ["FRONTEND_URL"])


def test_clerk_google_oauth_redirect_uris_include_account_portal():
    uris = clerk_auth.clerk_google_oauth_redirect_uris()
    assert "https://clerk.trenston.com/v1/oauth_callback" in uris
    assert "https://accounts.trenston.com/v1/oauth_callback" in uris


def test_helm_frontend_origins_includes_helmcontrol():
    origins = clerk_auth.helm_frontend_origins()
    assert "https://trenston.com" in origins
    assert "http://localhost:3000" in origins


def test_primary_frontend_origin_prefers_helmcontrol():
    assert clerk_auth.primary_frontend_origin() == "https://www.trenston.com"


def test_derive_publishable_key_from_helmcontrol_jwks():
    jwks = "https://clerk.trenston.com/.well-known/jwks.json"
    pk = clerk_auth.derive_publishable_key_from_jwks(jwks, mode="live")
    assert pk == "pk_live_Y2xlcmsudHJlbnN0b24uY29tJA"
    assert clerk_auth.clerk_keys_aligned(pk, jwks)


def test_clerk_primary_origin_from_jwks():
    assert clerk_auth.clerk_primary_origin() == "https://trenston.com"


def test_clerk_post_auth_url_uses_public_www():
    assert clerk_auth.clerk_post_auth_url() == "https://www.trenston.com/app"


def test_clerk_apex_and_www_are_not_multi_domain():
    assert clerk_auth.clerk_multi_domain_auth() is False


def test_clerk_multi_domain_when_sites_differ(monkeypatch):
    monkeypatch.setattr(clerk_auth, "clerk_primary_origin", lambda: "https://apexcoach.tech")
    assert clerk_auth.clerk_multi_domain_auth() is True
    assert clerk_auth.clerk_post_auth_url() == "https://apexcoach.tech/app"


def test_resolve_publishable_key_prefers_env(monkeypatch):
    aligned = clerk_auth.derive_publishable_key_from_jwks(clerk_auth.CLERK_JWKS_URL, mode="live")
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", aligned)
    assert clerk_auth.resolve_clerk_publishable_key() == aligned


def test_resolve_publishable_key_ignores_misaligned_env(monkeypatch):
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", "pk_live_custom")
    derived = clerk_auth.resolve_clerk_publishable_key()
    assert derived.startswith("pk_live_")
    assert clerk_auth.clerk_keys_aligned(derived, clerk_auth.CLERK_JWKS_URL)


def test_resolve_publishable_key_derives_from_jwks(monkeypatch):
    monkeypatch.delenv("CLERK_PUBLISHABLE_KEY", raising=False)
    pk = clerk_auth.resolve_clerk_publishable_key()
    assert pk.startswith("pk_live_")
    assert clerk_auth.clerk_keys_aligned(pk, clerk_auth.CLERK_JWKS_URL)


def test_clerk_secret_publishable_mode_match():
    assert clerk_auth.clerk_secret_publishable_mode_match(
        "pk_live_Y2xlcmsudHJlbnN0b24uY29tJA"
    )
    assert not clerk_auth.clerk_secret_publishable_mode_match("pk_test_abc")


def test_jwt_payload_unverified_extracts_sid_sub():
    import base64
    import json

    payload = {"sub": "user_abc", "sid": "sess_xyz", "exp": 9999999999}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    token = f"eyJhbGciOiJSUzI1NiJ9.{body}.sig"
    parsed = clerk_auth._jwt_payload_unverified(token)
    assert parsed["sub"] == "user_abc"
    assert parsed["sid"] == "sess_xyz"


def test_sync_clerk_instance_patches_dev_origin():
    instance_before = {
        "environment_type": "development",
        "allowed_origins": ["http://localhost:3000"],
    }
    instance_after = {
        "environment_type": "development",
        "allowed_origins": sorted(clerk_auth.helm_frontend_origins()),
    }
    env_display = {
        "display_config": {
            "sign_in_url": "https://www.trenston.com/login",
            "sign_up_url": "https://www.trenston.com/sign-up",
            "after_sign_in_url": "https://www.trenston.com/app",
            "after_sign_up_url": "https://www.trenston.com/app",
            "after_sign_out_all_url": "https://www.trenston.com/login",
            "home_url": "https://www.trenston.com",
            "logo_link_url": "https://www.trenston.com",
        }
    }

    class Resp:
        def __init__(self, data, status=200, text=""):
            self.status_code = status
            self._data = data
            self.text = text
            self.content = b"{}" if data is not None else b""

        def json(self):
            return self._data

    domains_resp = Resp({"data": [{"name": "trenston.com", "id": "dom_1"}]})

    async def mock_get(url, **kwargs):
        u = str(url)
        if u.endswith("/instance"):
            # first call before, later verify
            if not hasattr(mock_get, "n"):
                mock_get.n = 0
            mock_get.n += 1
            return Resp(instance_before if mock_get.n == 1 else instance_after)
        if "/environment" in u:
            return Resp(env_display)
        if u.endswith("/redirect_urls"):
            return Resp({"data": []})
        if u.endswith("/domains"):
            return domains_resp
        return Resp({}, 404, "not found")

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=mock_get)
    mock_client.patch = AsyncMock(return_value=Resp({}, 204))
    mock_client.post = AsyncMock(return_value=Resp({}, 201))

    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_client
    mock_cm.__aexit__.return_value = None

    with patch("clerk_auth.httpx.AsyncClient", return_value=mock_cm):
        result = asyncio.run(clerk_auth.sync_clerk_instance())

    assert result["synced"] is True
    assert result["environment_type"] == "development"
    assert mock_client.patch.call_count >= 1
    body = mock_client.patch.call_args_list[0].kwargs["json"]
    assert body["development_origin"] == "https://www.trenston.com"
    assert "https://trenston.com" in body["allowed_origins"]
    assert body["url_based_session_syncing"] is True
    assert result.get("account_portal", {}).get("ok") is True


def test_clerk_bapi_account_portal_requires_v1_path():
    """Bare /account_portal (no /v1) is what returns plain '404 page not found'."""
    assert clerk_auth.CLERK_BAPI.endswith("/v1")
    assert f"{clerk_auth.CLERK_BAPI}/account_portal" == "https://api.clerk.com/v1/account_portal"
    assert f"{clerk_auth.CLERK_BAPI}/display_config" == "https://api.clerk.com/v1/display_config"


def test_clerk_redirect_url_list_includes_www_app():
    urls = clerk_auth._clerk_redirect_url_list()
    assert "https://www.trenston.com/app" in urls
    assert "https://www.trenston.com/sign-up/sso-callback" in urls
    assert "https://trenston.com/app" in urls


def test_sync_skipped_when_not_configured(monkeypatch):
    monkeypatch.setattr(clerk_auth, "CLERK_SECRET_KEY", "")
    result = asyncio.run(clerk_auth.sync_clerk_instance())
    assert result["synced"] is False
    assert result["reason"] == "clerk_not_configured"
