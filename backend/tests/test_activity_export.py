"""Activity log CSV export — owner/admin only."""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DB_NAME", "test_database")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402


@pytest.fixture
def owner_client():
    async def principal():
        return {
            "user_id": "u_own", "name": "Owner", "email": "o@x.com",
            "workspace_id": "ws1", "pack": "owner", "role": "owner",
        }
    server.app.dependency_overrides[server.get_principal] = principal
    mock_db = MagicMock()
    mock_db.activities = MagicMock()
    mock_db.workspaces.find_one = AsyncMock(return_value={"timezone": "UTC"})

    class Cursor:
        def __init__(self, rows):
            self._rows = rows
        def sort(self, *a, **k):
            return self
        async def to_list(self, n):
            return self._rows

    rows = [
        {
            "created_at": "2026-03-10T12:00:00+00:00",
            "actor_name": "Owner",
            "module": "sales",
            "action": "deal.create",
            "summary": "New deal",
        },
        {
            "created_at": "2026-03-12T09:00:00+00:00",
            "actor_name": "Owner",
            "module": "financials",
            "action": "entry.add",
            "summary": "Logged expense",
        },
    ]
    mock_db.activities.find = MagicMock(return_value=Cursor(rows))
    with patch.object(server, "db", mock_db):
        yield TestClient(server.app)
    server.app.dependency_overrides.clear()


@pytest.fixture
def member_client():
    async def principal():
        return {
            "user_id": "u_mem", "name": "Member", "email": "m@x.com",
            "workspace_id": "ws1", "pack": "member", "role": "member",
        }
    server.app.dependency_overrides[server.get_principal] = principal
    with patch.object(server, "db", MagicMock(workspaces=MagicMock(find_one=AsyncMock(return_value=None)))):
        yield TestClient(server.app)
    server.app.dependency_overrides.clear()


def test_activity_export_csv_for_owner(owner_client):
    r = owner_client.get("/api/activities/export", params={"start": "2026-03-01", "end": "2026-03-31", "format": "csv"})
    assert r.status_code == 200, r.text
    assert "text/csv" in r.headers.get("content-type", "")
    lines = [ln for ln in r.text.strip().splitlines() if ln]
    assert lines[0] == "timestamp,actor_name,area,action,message"
    assert len(lines) == 3
    assert "New deal" in lines[1]
    assert "Logged expense" in lines[2]


def test_activity_export_forbidden_for_member(member_client):
    r = member_client.get("/api/activities/export", params={"start": "2026-03-01", "end": "2026-03-31"})
    assert r.status_code == 403
