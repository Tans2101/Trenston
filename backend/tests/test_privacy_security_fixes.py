"""Security/privacy hardening: DSAR export, token gates, age confirm, setup status."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_privacy_security_fixes")

import server  # noqa: E402


def test_can_use_integration_tokens_connector_or_owner():
    ws = {
        "workspace_id": "ws_1",
        "quickbooks_tokens": {"access_token": "x"},
        "quickbooks_tokens_connected_by": "user_a",
    }
    connector = {"user_id": "user_a", "role": "member", "pack": "ops"}
    other = {"user_id": "user_b", "role": "member", "pack": "ops"}
    owner = {"user_id": "user_c", "role": "owner", "pack": "owner"}
    with patch.object(server, "_integration_tokens", return_value={"access_token": "x"}):
        assert server._can_use_integration_tokens(connector, ws, "quickbooks_tokens") is True
        assert server._can_use_integration_tokens(other, ws, "quickbooks_tokens") is False
        assert server._can_use_integration_tokens(owner, ws, "quickbooks_tokens") is True


def test_can_use_integration_tokens_legacy_owners_only():
    ws = {"workspace_id": "ws_1", "quickbooks_tokens": {"access_token": "x"}}
    member = {"user_id": "user_b", "role": "member", "pack": "ops"}
    owner = {"user_id": "user_c", "role": "owner", "pack": "owner"}
    with patch.object(server, "_integration_tokens", return_value={"access_token": "x"}):
        assert server._can_use_integration_tokens(member, ws, "quickbooks_tokens") is False
        assert server._can_use_integration_tokens(owner, ws, "quickbooks_tokens") is True


def test_require_integration_token_use_forbids_non_connector():
    ws = {
        "workspace_id": "ws_1",
        "quickbooks_tokens": {"access_token": "x"},
        "quickbooks_tokens_connected_by": "user_a",
    }
    other = {"user_id": "user_b", "role": "member", "pack": "ops"}
    with patch.object(server, "_integration_tokens", return_value={"access_token": "x"}):
        try:
            server._require_integration_token_use(other, ws, "quickbooks_tokens")
            assert False, "expected HTTPException"
        except HTTPException as exc:
            assert exc.status_code == 403


def test_google_tokens_not_usable_via_workspace_acl():
    """Google is per-user; workspace google_tokens ACL helpers always deny."""
    ws = {"workspace_id": "ws_1", "google_tokens": {"access_token": "x"}}
    owner = {"user_id": "user_c", "role": "owner", "pack": "owner"}
    assert server._can_use_integration_tokens(owner, ws, "google_tokens") is False


def test_setup_status_is_boolean_health_only(monkeypatch):
    monkeypatch.setattr(server, "SETUP_SECRET", "setup-secret")
    monkeypatch.setattr(server, "_mongo_ping", AsyncMock(return_value=True))
    monkeypatch.setattr(server.clerk_auth, "clerk_configured", lambda: True)
    monkeypatch.setattr(server.clerk_auth, "clerk_api_ok", AsyncMock(return_value=True))
    monkeypatch.setattr(
        server.doc_storage,
        "probe_r2",
        lambda: {"configured": False, "ok": False},
    )
    client = TestClient(server.app)
    res = client.get("/api/setup/status", headers={"X-Setup-Secret": "setup-secret"})
    assert res.status_code == 200
    body = res.json()
    # indexes_ok/index_errors (added for background index-health monitoring) are
    # still "boolean health only" — a bool/null flag and a capped list of short
    # error strings, gated behind the same setup secret. No infra inventory.
    assert set(body.keys()) == {
        "ok", "mongo", "clerk_configured", "clerk_api_ok", "r2", "indexes_ok", "index_errors",
    }
    assert body["r2"] == {"configured": False, "ok": False}
    assert body["index_errors"] == []
    assert "integrations_configured" not in body
    assert "git_commit" not in body


def test_export_workspace_package_strips_tokens_and_includes_collections():
    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        async def to_list(self, _limit):
            return list(self.rows)

    class Coll:
        def __init__(self, rows=None):
            self.rows = rows or []

        def find(self, *_a, **_k):
            return Cursor(self.rows)

    fake = MagicMock()
    fake.workspaces.find_one = AsyncMock(return_value={
        "workspace_id": "ws_1",
        "name": "Acme",
        "google_tokens": {"access_token": "secret"},
    })
    fake.departments.find = MagicMock(return_value=Cursor([{"department_id": "d1", "workspace_id": "ws_1"}]))
    fake.department_members.find = MagicMock(return_value=Cursor([]))
    fake.memberships.find = MagicMock(return_value=Cursor([{"user_id": "u1", "workspace_id": "ws_1"}]))

    collections = {
        name: Coll([{"workspace_id": "ws_1", "id": f"{name}_1"}])
        for name in server._WORKSPACE_COLLECTIONS
    }

    def getitem(_self, name):
        return collections[name]

    fake.__getitem__ = getitem

    with patch.object(server, "db", fake):
        package = asyncio.run(server._export_workspace_package("ws_1"))

    assert package["workspace"]["name"] == "Acme"
    assert "google_tokens" not in package["workspace"]
    assert "document_ai_usage" in package["collections"]
    assert "product_events" in package["collections"]
    assert package["collections"]["financial_entries"][0]["id"] == "financial_entries_1"


def test_workspace_collections_include_document_ai_usage():
    assert "document_ai_usage" in server._WORKSPACE_COLLECTIONS
    assert "product_events" in server._WORKSPACE_COLLECTIONS
