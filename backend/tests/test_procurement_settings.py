"""Procurement monthly budget settings API tests (PUT /procurement/settings)."""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_procurement_settings")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import server  # noqa: E402

CEO = {
    "user_id": "u_ceo",
    "email": "ceo@acme.com",
    "name": "CEO",
    "workspace_id": "ws_test",
    "role": "owner",
    "pack": "owner",
}

LEAD = {
    "user_id": "u_lead",
    "email": "lead@acme.com",
    "name": "Lead",
    "workspace_id": "ws_test",
    "role": "member",
    "pack": "member",
}

MEMBER = {
    "user_id": "u_mem",
    "email": "mem@acme.com",
    "name": "Mem",
    "workspace_id": "ws_test",
    "role": "member",
    "pack": "member",
}

PROC_DEPT = {
    "department_id": "dept_proc",
    "workspace_id": "ws_test",
    "type": "procurement",
    "name": "Procurement",
    "enabled": True,
    "monthly_budget": None,
    "monthly_budget_entered": False,
}


class RequestStore:
    def __init__(self):
        self.rows = []

    def find(self, query, projection=None):
        class C:
            def sort(self, *a, **k):
                return self

            async def to_list(self, n):
                return []

        return C()

    async def insert_one(self, doc):
        self.rows.append(dict(doc))


@pytest.fixture
def settings_api():
    dept_row = dict(PROC_DEPT)
    depts = MagicMock()

    async def dept_find_one(query, projection=None):
        if query.get("department_id") == "dept_proc" or (
            query.get("workspace_id") == "ws_test"
            and query.get("type") == "procurement"
            and query.get("enabled") is True
        ):
            return dict(dept_row)
        return None

    async def dept_update_one(query, update):
        if query.get("department_id") == "dept_proc":
            dept_row.update(update.get("$set") or {})
            return MagicMock(matched_count=1)
        return MagicMock(matched_count=0)

    depts.find_one = AsyncMock(side_effect=dept_find_one)
    depts.update_one = AsyncMock(side_effect=dept_update_one)

    members = MagicMock()

    async def member_find_one(query, projection=None):
        uid = query.get("user_id")
        if uid == "u_mem":
            return {"department_id": "dept_proc", "user_id": "u_mem", "role": "member"}
        if uid == "u_lead":
            return {"department_id": "dept_proc", "user_id": "u_lead", "role": "lead"}
        return None

    members.find_one = AsyncMock(side_effect=member_find_one)

    mock_db = MagicMock()
    mock_db.departments = depts
    mock_db.department_members = members
    mock_db.procurement_requests = RequestStore()

    async def as_ceo():
        return CEO

    async def as_member():
        return MEMBER

    async def as_lead():
        return LEAD

    server.app.dependency_overrides[server.get_principal] = as_member
    with patch.object(server, "db", mock_db), \
         patch.object(server, "BILLING_ENFORCED", False):
        client = TestClient(server.app)
        yield client, dept_row, as_ceo, as_member, as_lead, depts
    server.app.dependency_overrides.clear()


def test_procurement_settings_route_registered():
    paths = {
        (getattr(r, "path", None), frozenset(getattr(r, "methods", None) or []))
        for r in server.app.routes
    }
    assert ("/api/procurement/settings", frozenset({"PUT"})) in paths
    assert ("/api/procurement/settings", frozenset({"GET"})) in paths


def test_member_cannot_set_or_clear_budget(settings_api):
    client, dept_row, as_ceo, as_member, as_lead, depts = settings_api
    assert client.put("/api/procurement/settings", json={"monthly_budget": 50000}).status_code == 403
    assert client.put("/api/procurement/settings", json={"clear_budget": True}).status_code == 403
    assert dept_row["monthly_budget_entered"] is False


def test_lead_sets_and_clears_budget(settings_api):
    client, dept_row, as_ceo, as_member, as_lead, depts = settings_api
    server.app.dependency_overrides[server.get_principal] = as_lead

    # Matches Procurement.jsx saveProcurementBudget payload
    set_r = client.put("/api/procurement/settings", json={"monthly_budget": 50000})
    assert set_r.status_code == 200, set_r.text
    body = set_r.json()
    assert body["ok"] is True
    assert body["monthly_budget"] == 50000.0
    assert body["monthly_budget_entered"] is True
    assert dept_row["monthly_budget"] == 50000.0
    assert dept_row["monthly_budget_entered"] is True
    depts.update_one.assert_called()

    # Matches Procurement.jsx clearProcurementBudget payload
    clear_r = client.put("/api/procurement/settings", json={"clear_budget": True})
    assert clear_r.status_code == 200, clear_r.text
    cleared = clear_r.json()
    assert cleared["ok"] is True
    assert cleared["monthly_budget"] is None
    assert cleared["monthly_budget_entered"] is False
    assert dept_row["monthly_budget"] is None
    assert dept_row["monthly_budget_entered"] is False


def test_ceo_can_set_budget(settings_api):
    client, dept_row, as_ceo, as_member, as_lead, depts = settings_api
    server.app.dependency_overrides[server.get_principal] = as_ceo
    r = client.put("/api/procurement/settings", json={"monthly_budget": 1200.5})
    assert r.status_code == 200, r.text
    assert r.json()["monthly_budget"] == 1200.5
    assert dept_row["monthly_budget"] == 1200.5


def test_negative_budget_rejected(settings_api):
    client, dept_row, as_ceo, as_member, as_lead, depts = settings_api
    server.app.dependency_overrides[server.get_principal] = as_lead
    r = client.put("/api/procurement/settings", json={"monthly_budget": -1})
    assert r.status_code == 400
    assert dept_row["monthly_budget_entered"] is False
