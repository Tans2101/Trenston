"""Security helpers and production guardrails."""
import asyncio
import io
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient
from starlette.datastructures import Headers

# Ensure server module can import (needs Mongo env at import time).
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_security")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import _allowed_auth_redirect, _read_validated_document  # noqa: E402


@pytest.mark.parametrize(
    "url,app_url,origins,expected",
    [
        ("/app", "https://helm.vercel.app", [], True),
        ("https://helm.vercel.app/app", "https://helm.vercel.app", [], True),
        ("https://evil.com/phish", "https://helm.vercel.app", [], False),
        ("//evil.com", "https://helm.vercel.app", [], False),
        ("https://preview.vercel.app/login", "", ["https://preview.vercel.app"], True),
    ],
)
def test_allowed_auth_redirect(monkeypatch, url, app_url, origins, expected):
    import server

    monkeypatch.setattr(server, "APP_URL", app_url)
    monkeypatch.setattr(server, "CORS_ORIGINS", origins)
    assert _allowed_auth_redirect(url) is expected


def test_cors_regex_not_wildcard_dot_star():
    import server

    assert server._cors_regex != ".*"
    assert server._cors_regex != r".*"


def test_production_config_allows_development():
    import server

    server._enforce_production_config()


def test_production_config_refuses_insecure(monkeypatch):
    import server
    from cryptography.fernet import Fernet

    monkeypatch.setattr(server, "ENVIRONMENT", "production")
    monkeypatch.setattr(server, "SESSION_SECRET", "change-me-in-production")
    monkeypatch.setattr(server, "CORS_ORIGINS", [])
    monkeypatch.setattr(server, "ALLOW_DEMO_LOGIN", True)
    monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.delenv("OAUTH_STATE_SECRET", raising=False)
    with pytest.raises(RuntimeError) as exc:
        server._enforce_production_config()
    msg = str(exc.value)
    assert "SESSION_SECRET" in msg
    assert "OAUTH_STATE_SECRET" in msg
    assert "CORS_ORIGINS" in msg
    assert "ALLOW_DEMO_LOGIN" in msg


def test_production_requires_integration_encryption_key(monkeypatch):
    import server

    monkeypatch.setattr(server, "ENVIRONMENT", "production")
    monkeypatch.delenv("INTEGRATION_ENCRYPTION_KEY", raising=False)
    with pytest.raises(RuntimeError) as exc:
        server._enforce_production_config()
    assert "INTEGRATION_ENCRYPTION_KEY" in str(exc.value)


def test_production_rejects_invalid_integration_encryption_key(monkeypatch):
    import server

    monkeypatch.setattr(server, "ENVIRONMENT", "production")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", "not-a-fernet-key")
    with pytest.raises(RuntimeError) as exc:
        server._enforce_production_config()
    assert "valid Fernet key" in str(exc.value)


def test_google_scopes_exclude_gmail():
    """Gmail scopes are restricted (yearly CASA assessment); Trenston must not request them."""
    import server

    assert not any("gmail" in s for s in server.GOOGLE_SCOPES)
    assert "https://www.googleapis.com/auth/calendar.readonly" in server.GOOGLE_SCOPES
    assert "https://www.googleapis.com/auth/calendar.events" in server.GOOGLE_SCOPES
    assert "https://www.googleapis.com/auth/spreadsheets" in server.GOOGLE_SCOPES
    assert "https://www.googleapis.com/auth/drive.file" in server.GOOGLE_SCOPES


def test_integration_oauth_state_is_user_bound_and_single_use():
    import server

    fake_db = MagicMock()
    fake_db.oauth_states.insert_one = AsyncMock()
    config = {
        "configured": True,
        "client_id": "client",
        "redirect_uri": "https://api.example.test/callback",
        "auth_uri": "https://provider.example.test/authorize",
        "scope": "read",
    }
    principal = {"workspace_id": "ws_1", "user_id": "user_1", "pack": "owner"}

    with patch.object(server, "db", fake_db), patch.object(
        server, "_provider_config", return_value=config,
    ):
        result = asyncio.run(server.integration_connect("google", MagicMock(), principal))

    state = parse_qs(urlparse(result["authorization_url"]).query)["state"][0]
    assert server._verify_state(state)[:3] == ("google", "ws_1", "user_1")
    stored = fake_db.oauth_states.insert_one.await_args.args[0]
    assert stored["workspace_id"] == "ws_1"
    assert stored["user_id"] == "user_1"
    assert stored["expires_at"] > datetime.now(timezone.utc)
    assert state not in str(stored)


def test_removed_clerk_secret_and_proxy_endpoints_are_not_exposed():
    import server

    client = TestClient(server.app)
    assert client.get("/api/auth/clerk-edge-secret").status_code == 404
    assert client.get("/api/clerk-proxy/v1/client").status_code == 404


def test_setup_status_requires_setup_secret(monkeypatch):
    import server

    monkeypatch.setattr(server, "SETUP_SECRET", "setup-secret")
    client = TestClient(server.app)
    assert client.get("/api/setup/status").status_code == 401


def _upload(data: bytes, content_type: str) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(data),
        filename="document",
        headers=Headers({"content-type": content_type}),
    )


def test_document_upload_validates_magic_bytes():
    pdf = _upload(b"%PDF-1.7\nsafe", "application/pdf")
    assert asyncio.run(_read_validated_document(pdf)).startswith(b"%PDF-")

    disguised = _upload(b"<script>alert(1)</script>", "application/pdf")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_read_validated_document(disguised))
    assert exc.value.status_code == 400
    assert "declared type" in exc.value.detail


def test_document_upload_stops_at_size_limit():
    import server

    oversized = _upload(b"%PDF-" + b"x" * server.MAX_DOC_BYTES, "application/pdf")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(_read_validated_document(oversized))
    assert exc.value.status_code == 400
    assert "15MB" in exc.value.detail


def test_startup_seals_plaintext_integration_tokens():
    import server
    import credential_crypto as crypto

    plaintext = {"access_token": "ya29.plain", "refresh_token": "1//r"}
    stored = [{"_id": "oid1", "workspace_id": "ws_1", "quickbooks_tokens": plaintext}]

    class TokenCursor:
        def __init__(self, rows):
            self.rows = list(rows)

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self.rows:
                raise StopAsyncIteration
            return self.rows.pop(0)

    workspaces = MagicMock()
    workspaces.find = MagicMock(return_value=TokenCursor(stored))
    workspaces.update_one = AsyncMock()
    workspaces.update_many = AsyncMock(return_value=MagicMock(modified_count=0))
    user_google = MagicMock()
    user_google.find = MagicMock(return_value=TokenCursor([]))
    fake_db = MagicMock()
    fake_db.workspaces = workspaces
    fake_db.user_google_tokens = user_google

    with patch.object(server, "db", fake_db):
        asyncio.run(server._seal_plaintext_integration_tokens())

    workspaces.update_one.assert_awaited_once()
    sealed = workspaces.update_one.await_args.args[1]["$set"]["quickbooks_tokens"]
    assert crypto.is_sealed_credentials(sealed)
    assert crypto.unseal_credentials(sealed)["access_token"] == "ya29.plain"
