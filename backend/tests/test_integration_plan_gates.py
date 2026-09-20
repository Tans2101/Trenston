"""Per-provider plan gates on OAuth connect and sync dependencies."""
import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_integration_plan_gates")

import server


OWNER = {
    "user_id": "u_owner",
    "workspace_id": "ws_1",
    "pack": "owner",
    "role": "owner",
}


@pytest.mark.asyncio
async def test_connect_free_blocks_quickbooks_allows_google():
    dep_connect = None  # call endpoint helpers via workspace_allows_provider

    with patch.object(server, "BILLING_ENFORCED", True):
        assert server.workspace_allows_provider({"plan": "free"}, "google") is True
        assert server.workspace_allows_provider({"plan": "free"}, "quickbooks") is False
        assert server.workspace_allows_provider({"plan": "starter"}, "quickbooks") is True
        assert server.workspace_allows_provider({"plan": "starter"}, "hubspot") is False
        assert server.workspace_allows_provider({"plan": "growth"}, "hubspot") is True
        assert server.workspace_allows_provider({"plan": "growth"}, "slack") is True


@pytest.mark.asyncio
async def test_require_integration_provider_plan_reason():
    dep = server.require_integration_provider("hubspot")
    with patch.object(server, "BILLING_ENFORCED", True), \
         patch.object(server, "get_ws", new=AsyncMock(return_value={"plan": "starter", "workspace_id": "ws_1"})):
        with pytest.raises(HTTPException) as ei:
            await dep(OWNER)
        assert ei.value.status_code == 403
        assert ei.value.detail["reason"] == "plan"
        assert ei.value.detail["provider"] == "hubspot"
        assert "HubSpot" in ei.value.detail["message"]


@pytest.mark.asyncio
async def test_require_integration_provider_allows_starter_quickbooks():
    dep = server.require_integration_provider("quickbooks")
    with patch.object(server, "BILLING_ENFORCED", True), \
         patch.object(server, "get_ws", new=AsyncMock(return_value={"plan": "starter", "workspace_id": "ws_1"})):
        out = await dep(OWNER)
        assert out is OWNER


@pytest.mark.asyncio
async def test_integration_connect_free_plan_403_for_xero():
    async def as_owner():
        return OWNER

    server.app.dependency_overrides[server.get_principal] = as_owner
    try:
        with patch.object(server, "BILLING_ENFORCED", True), \
             patch.object(server, "get_ws", new=AsyncMock(return_value={"plan": "free", "workspace_id": "ws_1"})):
            from fastapi.testclient import TestClient
            client = TestClient(server.app)
            r = client.get("/api/integrations/xero/connect")
        assert r.status_code == 403
        body = r.json()["detail"]
        assert body["reason"] == "plan"
        assert body["provider"] == "xero"
    finally:
        server.app.dependency_overrides.clear()
