"""Hourly QuickBooks/Xero auto-sync cron."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_accounting_autosync")

import server  # noqa: E402


def test_accounting_auto_sync_runs_connected_workspaces():
    workspaces = [
        {
            "workspace_id": "ws_qb",
            "quickbooks_tokens": {"sealed": True},
            "quickbooks_tokens_connected_by": "user_a",
        },
        {
            "workspace_id": "ws_xero",
            "xero_tokens": {"sealed": True},
            "xero_tokens_connected_by": "user_b",
        },
        {"workspace_id": "ws_empty"},
    ]

    class Cursor:
        async def to_list(self, _n):
            return workspaces

    fake_db = MagicMock()
    fake_db.workspaces.find = MagicMock(return_value=Cursor())

    async def fake_qb(c, principal, *, source="quickbooks_sync"):
        assert principal["user_id"] == "user_a"
        assert source == "quickbooks_auto_sync"
        return {"synced_count": 3, "last_synced_at": "t"}

    async def fake_xero(c, principal, *, source="xero_sync"):
        assert principal["user_id"] == "user_b"
        assert source == "xero_auto_sync"
        return {"synced_count": 2, "last_synced_at": "t"}

    with (
        patch.object(server, "db", fake_db),
        patch.object(server.cred_crypto, "credentials_present", side_effect=lambda v: bool(v)),
        patch.object(server, "_integration_tokens", return_value={"tenant_id": "ten_1"}),
        patch.object(server, "_run_quickbooks_sync_for_workspace", side_effect=fake_qb),
        patch.object(server, "_run_xero_sync_for_workspace", side_effect=fake_xero),
    ):
        stats = asyncio.run(server.run_accounting_auto_sync())

    assert stats["workspaces_scanned"] == 3
    assert stats["quickbooks_ok"] == 1
    assert stats["xero_ok"] == 1
    assert stats["transactions_synced"] == 5
    assert stats["quickbooks_errors"] == 0
    assert stats["xero_errors"] == 0


def test_accounting_auto_sync_skips_xero_without_tenant():
    workspaces = [{"workspace_id": "ws_xero", "xero_tokens": {"sealed": True}}]

    class Cursor:
        async def to_list(self, _n):
            return workspaces

    fake_db = MagicMock()
    fake_db.workspaces.find = MagicMock(return_value=Cursor())

    with (
        patch.object(server, "db", fake_db),
        patch.object(server.cred_crypto, "credentials_present", return_value=True),
        patch.object(server, "_integration_tokens", return_value={"access_token": "x"}),
        patch.object(server, "_run_xero_sync_for_workspace", new_callable=AsyncMock) as xero_run,
    ):
        stats = asyncio.run(server.run_accounting_auto_sync())

    xero_run.assert_not_called()
    assert stats["xero_skipped"] == 1


def test_accounting_auto_sync_clears_expired_quickbooks():
    workspaces = [{"workspace_id": "ws_qb", "quickbooks_tokens": {"sealed": True}}]

    class Cursor:
        async def to_list(self, _n):
            return workspaces

    fake_db = MagicMock()
    fake_db.workspaces.find = MagicMock(return_value=Cursor())

    with (
        patch.object(server, "db", fake_db),
        patch.object(server.cred_crypto, "credentials_present", return_value=True),
        patch.object(
            server,
            "_run_quickbooks_sync_for_workspace",
            side_effect=server.qb_sync.QuickBooksAuthError("expired"),
        ),
        patch.object(server, "_store_integration_tokens", new_callable=AsyncMock) as store,
    ):
        stats = asyncio.run(server.run_accounting_auto_sync())

    assert stats["quickbooks_auth_errors"] == 1
    store.assert_awaited_once()
    assert store.await_args.args[0] == "ws_qb"
    assert store.await_args.args[1] == "quickbooks_tokens"
    assert store.await_args.args[2] is None


def test_accounting_sync_endpoint_requires_cron_secret():
    with patch.object(server, "INTERNAL_CRON_SECRET", "cron-secret-test"):
        client = TestClient(server.app)
        assert client.post("/api/internal/run-accounting-sync").status_code == 401
        assert client.post(
            "/api/internal/run-accounting-sync",
            headers={"X-Trenston-Cron-Secret": "wrong"},
        ).status_code == 401


def test_accounting_sync_endpoint_runs_with_cron_header():
    with (
        patch.object(server, "INTERNAL_CRON_SECRET", "cron-secret-test"),
        patch.object(
            server,
            "run_accounting_auto_sync",
            new=AsyncMock(return_value={"workspaces_scanned": 0, "transactions_synced": 0}),
        ),
    ):
        client = TestClient(server.app)
        res = client.post(
            "/api/internal/run-accounting-sync",
            headers={"X-Trenston-Cron-Secret": "cron-secret-test"},
        )
    assert res.status_code == 200
    assert res.json()["workspaces_scanned"] == 0


def test_accounting_auto_sync_skips_workspaces_whose_plan_dropped_the_provider():
    workspaces = [
        {"workspace_id": "ws_free", "plan": "free", "quickbooks_tokens": {"sealed": True},
         "quickbooks_tokens_connected_by": "user_a"},
        {"workspace_id": "ws_cancel", "plan": "starter", "subscription_status": "canceled",
         "quickbooks_tokens": {"sealed": True}, "quickbooks_tokens_connected_by": "user_b"},
        {"workspace_id": "ws_ok", "plan": "starter", "subscription_status": "active",
         "quickbooks_tokens": {"sealed": True}, "quickbooks_tokens_connected_by": "user_c"},
        {"workspace_id": "ws_sap_starter", "plan": "starter", "subscription_status": "active",
         "sap_b1_credentials": {"sealed": True}, "sap_b1_credentials_connected_by": "user_d"},
    ]

    class Cursor:
        async def to_list(self, _n):
            return workspaces

    fake_db = MagicMock()
    fake_db.workspaces.find = MagicMock(return_value=Cursor())
    synced = []

    async def fake_qb(c, principal, *, source="quickbooks_sync"):
        synced.append(c["workspace_id"])
        return {"synced_count": 1}

    sap = AsyncMock(return_value={"synced_count": 1})
    with (
        patch.object(server, "BILLING_ENFORCED", True),
        patch.object(server, "db", fake_db),
        patch.object(server.cred_crypto, "credentials_present", side_effect=lambda v: bool(v)),
        patch.object(server, "_run_quickbooks_sync_for_workspace", side_effect=fake_qb),
        patch.object(server, "_run_sap_b1_sync_for_workspace", sap),
    ):
        stats = asyncio.run(server.run_accounting_auto_sync())

    assert synced == ["ws_ok"]
    assert stats["quickbooks_skipped"] == 2
    sap.assert_not_awaited()
    assert stats["sap_b1_skipped"] == 1
