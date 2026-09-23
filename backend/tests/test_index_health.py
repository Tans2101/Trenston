"""Critical index ensure status surfaces on health / setup probes."""
import os
from unittest.mock import patch

import pytest
from fastapi.responses import JSONResponse

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_index_health")

import server


@pytest.mark.asyncio
async def test_health_503_when_critical_indexes_failed_in_production():
    server._index_ensure_state["done"] = True
    server._index_ensure_state["critical_ok"] = False
    server._index_ensure_state["errors"] = ["users.email: boom"]
    with (
        patch.object(server, "ENVIRONMENT", "production"),
        patch.object(server, "_mongo_ping", return_value=True),
    ):
        out = await server.health()
    assert isinstance(out, JSONResponse)
    assert out.status_code == 503
    # reset
    server._index_ensure_state["done"] = False
    server._index_ensure_state["critical_ok"] = True
    server._index_ensure_state["errors"] = []


@pytest.mark.asyncio
async def test_health_ok_when_indexes_pending_or_healthy():
    server._index_ensure_state["done"] = False
    server._index_ensure_state["critical_ok"] = True
    with patch.object(server, "_mongo_ping", return_value=True):
        out = await server.health()
    assert out["status"] == "ok"
    assert out["indexes_ok"] is None
