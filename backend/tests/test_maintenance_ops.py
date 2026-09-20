"""Engineering & Maintenance ops panels API tests (spares, schedules, AMCs, costs, settings)."""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_maintenance_ops")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import server  # noqa: E402
import departments_catalog as catalog  # noqa: E402

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

OUTSIDER = {
    "user_id": "u_out",
    "email": "out@acme.com",
    "name": "Out",
    "workspace_id": "ws_test",
    "role": "member",
    "pack": "member",
}

MAINT_DEPT = {
    "department_id": "dept_maint",
    "workspace_id": "ws_test",
    "type": "engineering_maintenance",
    "name": "Engineering & Maintenance",
    "enabled": True,
    "monthly_budget": None,
    "monthly_budget_entered": False,
}


class DocStore:
    def __init__(self):
        self.rows = []

    async def find_one(self, query, projection=None):
        for r in self.rows:
            if _match_query(r, query):
                return {k: v for k, v in r.items() if k != "_id"}
        return None

    def find(self, query, projection=None):
        matched = [dict(r) for r in self.rows if _match_query(r, query or {})]
        state = {"sort": None}

        class C:
            def sort(self, field, direction=1):
                state["sort"] = (field, direction)
                return self

            async def to_list(self, n):
                items = list(matched)
                if state["sort"]:
                    field, direction = state["sort"]
                    items.sort(
                        key=lambda x: x.get(field) or "",
                        reverse=direction == -1,
                    )
                return items[:n]

        return C()

    async def insert_one(self, doc):
        self.rows.append(dict(doc))

    async def update_one(self, query, update):
        for r in self.rows:
            if _match_query(r, query):
                r.update(update.get("$set") or {})
                return MagicMock(matched_count=1)
        return MagicMock(matched_count=0)

    async def update_many(self, query, update):
        n = 0
        for r in self.rows:
            if _match_query(r, query):
                r.update(update.get("$set") or {})
                n += 1
        return MagicMock(matched_count=n)

    async def delete_one(self, query):
        before = len(self.rows)
        self.rows = [r for r in self.rows if not _match_query(r, query)]
        return MagicMock(deleted_count=before - len(self.rows))


def _match_query(doc: dict, query: dict) -> bool:
    if not query:
        return True
    for k, v in query.items():
        if k == "$or":
            if not any(_match_query(doc, clause) for clause in v):
                return False
            continue
        actual = doc.get(k)
        if isinstance(v, dict):
            if "$in" in v:
                if actual not in v["$in"]:
                    return False
            elif "$gte" in v or "$lt" in v or "$exists" in v:
                # Minimal range/exists support for overhead queries
                if "$exists" in v:
                    exists = k in doc
                    if bool(v["$exists"]) != exists:
                        return False
                if "$gte" in v and str(actual or "") < str(v["$gte"]):
                    return False
                if "$lt" in v and str(actual or "") >= str(v["$lt"]):
                    return False
            else:
                return False
        elif actual != v:
            return False
    return True


@pytest.fixture
def ops_api():
    spares = DocStore()
    schedules = DocStore()
    contracts = DocStore()
    costs = DocStore()
    tickets = DocStore()
    dept_row = dict(MAINT_DEPT)
    depts = MagicMock()

    async def dept_find_one(query, projection=None):
        if query.get("department_id") == "dept_maint" or (
            query.get("workspace_id") == "ws_test"
            and query.get("type") == "engineering_maintenance"
            and query.get("enabled") is True
        ):
            return dict(dept_row)
        return None

    async def dept_update_one(query, update):
        if query.get("department_id") == "dept_maint":
            dept_row.update(update.get("$set") or {})
            return MagicMock(matched_count=1)
        return MagicMock(matched_count=0)

    depts.find_one = AsyncMock(side_effect=dept_find_one)
    depts.update_one = AsyncMock(side_effect=dept_update_one)

    members = MagicMock()

    async def member_find_one(query, projection=None):
        uid = query.get("user_id")
        if uid == "u_mem":
            return {"department_id": "dept_maint", "user_id": "u_mem", "role": "member"}
        if uid == "u_lead":
            return {"department_id": "dept_maint", "user_id": "u_lead", "role": "lead"}
        return None

    members.find_one = AsyncMock(side_effect=member_find_one)

    mock_db = MagicMock()
    mock_db.departments = depts
    mock_db.department_members = members
    mock_db.maintenance_spares = spares
    mock_db.maintenance_schedules = schedules
    mock_db.maintenance_contracts = contracts
    mock_db.maintenance_costs = costs
    mock_db.maintenance_tickets = tickets

    async def as_ceo():
        return CEO

    async def as_member():
        return MEMBER

    async def as_lead():
        return LEAD

    async def as_outsider():
        return OUTSIDER

    server.app.dependency_overrides[server.get_principal] = as_member
    with patch.object(server, "db", mock_db), \
         patch.object(server, "BILLING_ENFORCED", False):
        client = TestClient(server.app)
        yield {
            "client": client,
            "spares": spares,
            "schedules": schedules,
            "contracts": contracts,
            "costs": costs,
            "tickets": tickets,
            "dept_row": dept_row,
            "depts": depts,
            "as_ceo": as_ceo,
            "as_member": as_member,
            "as_lead": as_lead,
            "as_outsider": as_outsider,
        }
    server.app.dependency_overrides.clear()


def test_maint_type_exists():
    assert catalog.TYPE_ENGINEERING_MAINTENANCE == "engineering_maintenance"


def test_routes_registered():
    paths = {getattr(r, "path", None) for r in server.app.routes}
    for p in (
        "/api/maintenance/spares",
        "/api/maintenance/schedules",
        "/api/maintenance/contracts",
        "/api/maintenance/costs",
        "/api/maintenance/settings",
    ):
        assert p in paths


def test_outsider_403(ops_api):
    client = ops_api["client"]
    server.app.dependency_overrides[server.get_principal] = ops_api["as_outsider"]
    assert client.get("/api/maintenance/spares").status_code == 403
    assert client.post("/api/maintenance/spares", json={"part_name": "Seal"}).status_code == 403
    assert client.get("/api/maintenance/schedules").status_code == 403
    assert client.get("/api/maintenance/contracts").status_code == 403
    assert client.get("/api/maintenance/settings").status_code == 403


def test_disabled_dept_404(ops_api):
    client = ops_api["client"]
    ops_api["depts"].find_one = AsyncMock(return_value=None)
    assert client.get("/api/maintenance/spares").status_code == 404


def test_member_can_list_but_not_create_spare(ops_api):
    client = ops_api["client"]
    listed = client.get("/api/maintenance/spares")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["spares"] == []
    assert body["below_threshold_count"] == 0
    assert body["is_lead"] is False
    assert body["is_ceo"] is False

    r = client.post("/api/maintenance/spares", json={
        "part_name": "Bearing",
        "equipment_name": "Pump-1",
        "quantity_on_hand": 2,
        "minimum_threshold": 5,
        "unit": "pcs",
    })
    assert r.status_code == 403


def test_lead_creates_and_lists_spare(ops_api):
    client = ops_api["client"]
    server.app.dependency_overrides[server.get_principal] = ops_api["as_lead"]
    r = client.post("/api/maintenance/spares", json={
        "part_name": "Bearing",
        "equipment_name": "Pump-1",
        "quantity_on_hand": 2,
        "minimum_threshold": 5,
        "unit": "pcs",
    })
    assert r.status_code == 200, r.text
    spare = r.json()["spare"]
    assert spare["part_name"] == "Bearing"
    assert spare["equipment_name"] == "Pump-1"
    assert spare["equipment_names"] == ["Pump-1"]
    assert spare["quantity_on_hand"] == 2.0
    assert spare["minimum_threshold"] == 5.0
    assert spare["is_below_threshold"] is True
    assert spare["workspace_id"] == "ws_test"
    assert spare["department_id"] == "dept_maint"
    assert spare["id"].startswith("msp_")
    assert len(ops_api["spares"].rows) == 1

    listed = client.get("/api/maintenance/spares")
    assert listed.status_code == 200
    body = listed.json()
    assert len(body["spares"]) == 1
    assert body["below_threshold_count"] == 1
    assert body["is_lead"] is True


def test_lead_schedule_create_and_mark_done(ops_api):
    client = ops_api["client"]
    server.app.dependency_overrides[server.get_principal] = ops_api["as_lead"]
    r = client.post("/api/maintenance/schedules", json={
        "equipment_name": "CNC #3",
        "task": "Grease ways",
        "frequency_days": 30,
    })
    assert r.status_code == 200, r.text
    sched = r.json()["schedule"]
    assert sched["equipment_name"] == "CNC #3"
    assert sched["task"] == "Grease ways"
    assert sched["frequency_days"] == 30
    assert sched["last_done_at"] is None
    assert sched["next_due_at"] is None
    assert sched["schedule_established"] is False
    assert sched["is_overdue"] is False
    sid = sched["id"]

    listed = client.get("/api/maintenance/schedules")
    assert listed.status_code == 200
    assert len(listed.json()["schedules"]) == 1

    marked = client.patch(f"/api/maintenance/schedules/{sid}", json={"mark_done": True})
    assert marked.status_code == 200, marked.text
    updated = marked.json()["schedule"]
    assert updated["last_done_at"]
    assert updated["schedule_established"] is True
    assert updated["next_due_at"]
    assert ops_api["schedules"].rows[0]["last_done_at"]


def test_member_cannot_mark_schedule_done(ops_api):
    client = ops_api["client"]
    server.app.dependency_overrides[server.get_principal] = ops_api["as_lead"]
    r = client.post("/api/maintenance/schedules", json={
        "equipment_name": "Lathe", "task": "Oil", "frequency_days": 14,
    })
    sid = r.json()["schedule"]["id"]
    server.app.dependency_overrides[server.get_principal] = ops_api["as_member"]
    assert client.patch(f"/api/maintenance/schedules/{sid}", json={"mark_done": True}).status_code == 403


def test_lead_creates_contract(ops_api):
    client = ops_api["client"]
    server.app.dependency_overrides[server.get_principal] = ops_api["as_lead"]
    r = client.post("/api/maintenance/contracts", json={
        "equipment_name": "Compressor",
        "vendor_name": "AMC Co",
        "coverage_start": "2026-01-01",
        "coverage_end": "2026-12-31",
        "cost": 12000,
        "scope_notes": "Annual visit",
    })
    assert r.status_code == 200, r.text
    contract = r.json()["contract"]
    assert contract["equipment_name"] == "Compressor"
    assert contract["vendor_name"] == "AMC Co"
    assert contract["coverage_start"] == "2026-01-01"
    assert contract["coverage_end"] == "2026-12-31"
    assert contract["renewal_date"] == "2026-12-31"
    assert contract["renewal_effective"] == "2026-12-31"
    assert contract["cost"] == 12000.0
    assert "expired" in contract
    assert "renewal_due_soon" in contract

    listed = client.get("/api/maintenance/contracts")
    assert listed.status_code == 200
    body = listed.json()
    assert len(body["contracts"]) == 1
    assert "needing_renewal_count" in body


def test_contract_requires_dates(ops_api):
    client = ops_api["client"]
    server.app.dependency_overrides[server.get_principal] = ops_api["as_lead"]
    r = client.post("/api/maintenance/contracts", json={
        "equipment_name": "Compressor",
        "vendor_name": "AMC Co",
        "coverage_start": "",
        "coverage_end": "2026-12-31",
    })
    assert r.status_code == 400


def test_ceo_settings_budget_and_cost(ops_api):
    client = ops_api["client"]
    server.app.dependency_overrides[server.get_principal] = ops_api["as_ceo"]

    settings = client.get("/api/maintenance/settings")
    assert settings.status_code == 200, settings.text
    body = settings.json()
    assert body["can_manage"] is True
    assert body["monthly_budget_entered"] is False
    assert "overhead" in body

    put = client.put("/api/maintenance/settings", json={"monthly_budget": 100000})
    assert put.status_code == 200, put.text
    assert put.json()["monthly_budget"] == 100000.0
    assert put.json()["monthly_budget_entered"] is True
    assert ops_api["dept_row"]["monthly_budget"] == 100000.0

    cost = client.post("/api/maintenance/costs", json={
        "amount": 2500,
        "description": "Emergency callout",
    })
    assert cost.status_code == 200, cost.text
    row = cost.json()["cost"]
    assert row["amount"] == 2500.0
    assert row["description"] == "Emergency callout"
    assert row["workspace_id"] == "ws_test"
    assert row["id"].startswith("mcost_")
    assert len(ops_api["costs"].rows) == 1

    settings2 = client.get("/api/maintenance/settings")
    overhead = settings2.json()["overhead"]
    assert overhead["budget_entered"] is True
    assert overhead["budget"] == 100000.0
    assert overhead["actual"] >= 2500.0


def test_member_cannot_set_budget_or_log_cost(ops_api):
    client = ops_api["client"]
    assert client.put("/api/maintenance/settings", json={"monthly_budget": 50}).status_code == 403
    assert client.post("/api/maintenance/costs", json={"amount": 10}).status_code == 403


def test_schedule_validation(ops_api):
    client = ops_api["client"]
    server.app.dependency_overrides[server.get_principal] = ops_api["as_lead"]
    assert client.post("/api/maintenance/schedules", json={
        "equipment_name": "", "task": "Oil", "frequency_days": 30,
    }).status_code == 400
    assert client.post("/api/maintenance/schedules", json={
        "equipment_name": "X", "task": "Oil", "frequency_days": 0,
    }).status_code == 400
