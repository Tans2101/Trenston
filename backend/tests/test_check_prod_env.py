"""Production env check must fail the Render build without a Fernet key."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import check_prod_env  # noqa: E402


def _required_env(monkeypatch):
    monkeypatch.setenv("DB_NAME", "helm")
    monkeypatch.setenv("SESSION_SECRET", "a-strong-session-secret-for-tests")
    monkeypatch.setenv("FRONTEND_URL", "https://www.trenston.com")
    monkeypatch.setenv("APP_URL", "https://www.trenston.com")
    monkeypatch.setenv("CORS_ORIGINS", "https://www.trenston.com")
    monkeypatch.setenv("MONGO_URL", "mongodb+srv://user:pass@cluster.mongodb.net/")
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_live_test")
    monkeypatch.setenv("CLERK_JWKS_URL", "https://clerk.trenston.com/.well-known/jwks.json")
    monkeypatch.setenv("COOKIE_SECURE", "true")
    monkeypatch.setenv("ALLOW_DEMO_LOGIN", "false")
    monkeypatch.delenv("CLERK_PUBLISHABLE_KEY", raising=False)


def test_build_fails_without_integration_encryption_key(monkeypatch, capsys):
    _required_env(monkeypatch)
    monkeypatch.delenv("INTEGRATION_ENCRYPTION_KEY", raising=False)
    assert check_prod_env.main() == 1
    out = capsys.readouterr().out
    assert "INTEGRATION_ENCRYPTION_KEY" in out
    assert "MISSING required env" in out


def test_build_fails_on_passphrase_instead_of_fernet(monkeypatch, capsys):
    _required_env(monkeypatch)
    monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", "not-a-fernet-key")
    assert check_prod_env.main() == 1
    out = capsys.readouterr().out
    assert "Fernet" in out


def test_build_passes_with_fernet_key(monkeypatch):
    _required_env(monkeypatch)
    monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    assert check_prod_env.main() == 0
    assert "INTEGRATION_ENCRYPTION_KEY" in check_prod_env.ALWAYS_REQUIRED
    assert "INTEGRATION_ENCRYPTION_KEY" not in check_prod_env.RECOMMENDED


def test_warns_on_app_url_leading_whitespace(monkeypatch, capsys):
    _required_env(monkeypatch)
    monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("APP_URL", "\t\nhttps://www.trenston.com")
    assert check_prod_env.main() == 0
    out = capsys.readouterr().out
    assert "APP_URL has leading/trailing whitespace" in out
    assert "Not Found" in out


def test_warns_when_clerk_webhook_secret_missing(monkeypatch, capsys):
    _required_env(monkeypatch)
    monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.delenv("CLERK_WEBHOOK_SIGNING_SECRET", raising=False)
    monkeypatch.delenv("CLERK_WEBHOOK_SECRET", raising=False)
    assert check_prod_env.main() == 0
    out = capsys.readouterr().out
    assert "CLERK_WEBHOOK_SIGNING_SECRET" in out
    assert "/api/webhook/clerk" in out
