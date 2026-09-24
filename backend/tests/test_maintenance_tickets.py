"""Engineering & Maintenance ticket queue API tests."""
import os
import re
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_maintenance_tickets")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import server  # noqa: E402
import departments_catalog as catalog  # noqa: E402
from mongo_mocks import attach_users_in_find  # noqa: E402

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

TECH = {
    "user_id": "u_tech",
    "email": "tech@acme.com",
    "name": "Tech",
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
}


class TicketStore:
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
            elif "$regex" in v:
                flags = re.IGNORECASE if "i" in str(v.get("$options") or "") else 0
                if not re.search(str(v["$regex"]), str(actual or ""), flags):
                    return False
            else:
                return False
        elif actual != v:
            return False
    return True


@pytest.fixture
def maint_api():
    store = TicketStore()
    work_orders = TicketStore()
    depts = MagicMock()
    depts.find_one = AsyncMock(return_value=dict(MAINT_DEPT))
    members = MagicMock()

    async def member_find_one(query, projection=None):
        uid = query.get("user_id")
        roles = {"u_mem": "member", "u_tech": "member", "u_lead": "lead"}
        if uid in roles:
            return {"department_id": "dept_maint", "user_id": uid, "role": roles[uid]}
        return None

    members.find_one = AsyncMock(side_effect=member_find_one)
    users = MagicMock()
    users.find_one = AsyncMock(return_value={"name": "Mem", "email": "mem@acme.com"})
    attach_users_in_find(users)

    mock_db = MagicMock()
    mock_db.departments = depts
    mock_db.department_members = members
    mock_db.maintenance_tickets = store
    mock_db.production_work_orders = work_orders
    mock_db.users = users
    # list_maintenance_tickets also rolls up spares/schedules/contracts/overhead
    # inline — empty stores so those awaited find(...).to_list(...) calls succeed.
    mock_db.maintenance_spares = TicketStore()
    mock_db.maintenance_schedules = TicketStore()
    mock_db.maintenance_contracts = TicketStore()
    mock_db.maintenance_costs = TicketStore()
    mock_db.workspaces.find_one = AsyncMock(return_value={
        "timezone": "Asia/Manila", "financial_settings": {"currency": "usd"},
    })

    async def as_ceo():
        return CEO

    async def as_member():
        return MEMBER

    async def as_tech():
        return TECH

    async def as_lead():
        return LEAD

    async def as_outsider():
        return OUTSIDER

    server.app.dependency_overrides[server.get_principal] = as_member
    with patch.object(server, "db", mock_db), \
         patch.object(server, "BILLING_ENFORCED", False):
        client = TestClient(server.app)
        yield client, store, work_orders, as_ceo, as_member, as_tech, as_lead, as_outsider, depts
    server.app.dependency_overrides.clear()


def test_maint_not_placeholder():
    assert catalog.TYPE_ENGINEERING_MAINTENANCE not in catalog.PLACEHOLDER_SHELL_TYPES


def test_outsider_403(maint_api):
    client, store, work_orders, as_ceo, as_member, as_tech, as_lead, as_outsider, depts = maint_api
    server.app.dependency_overrides[server.get_principal] = as_outsider
    assert client.get("/api/maintenance/tickets").status_code == 403
    assert client.post("/api/maintenance/tickets", json={"equipment_name": "Pump"}).status_code == 403


def test_create_sets_reported_by_unassigned(maint_api):
    client, store, *_ = maint_api
    r = client.post("/api/maintenance/tickets", json={
        "equipment_name": "CNC #3",
        "description": "Bearing noise",
        "priority": "high",
        "reported_by": "u_hacker",
        "assigned_technician": "u_tech",
    })
    assert r.status_code == 200, r.text
    body = r.json()["ticket"]
    assert body["reported_by"] == "u_mem"
    assert body["assigned_technician"] is None
    assert body["status"] == "reported"
    assert body["priority"] == "high"
    assert body["blocking_production_orders"] == []


def test_member_cannot_assign(maint_api):
    client, store, work_orders, as_ceo, as_member, as_tech, as_lead, as_outsider, depts = maint_api
    client.post("/api/maintenance/tickets", json={"equipment_name": "Lathe"})
    tid = store.rows[0]["id"]
    r = client.patch(f"/api/maintenance/tickets/{tid}", json={"assigned_technician": "u_tech"})
    assert r.status_code == 403


def test_lead_assigns_then_tech_updates(maint_api):
    client, store, work_orders, as_ceo, as_member, as_tech, as_lead, as_outsider, depts = maint_api
    client.post("/api/maintenance/tickets", json={"equipment_name": "Lathe", "priority": "medium"})
    tid = store.rows[0]["id"]
    server.app.dependency_overrides[server.get_principal] = as_lead
    r = client.patch(f"/api/maintenance/tickets/{tid}", json={"assigned_technician": "u_tech"})
    assert r.status_code == 200
    assert store.rows[0]["assigned_technician"] == "u_tech"

    server.app.dependency_overrides[server.get_principal] = as_tech
    r2 = client.patch(f"/api/maintenance/tickets/{tid}", json={
        "status": "in_repair",
        "notes": "Parts ordered",
    })
    assert r2.status_code == 200, r2.text
    assert store.rows[0]["status"] == "in_repair"
    assert store.rows[0]["notes"] == "Parts ordered"


def test_non_assignee_cannot_update(maint_api):
    client, store, work_orders, as_ceo, as_member, as_tech, as_lead, as_outsider, depts = maint_api
    client.post("/api/maintenance/tickets", json={"equipment_name": "Lathe"})
    store.rows[0]["assigned_technician"] = "u_tech"
    tid = store.rows[0]["id"]
    r = client.patch(f"/api/maintenance/tickets/{tid}", json={"notes": "nope"})
    assert r.status_code == 403


def test_sort_open_high_first(maint_api):
    client, store, *_ = maint_api
    store.rows = [
        {"id": "1", "department_id": "dept_maint", "workspace_id": "ws_test", "equipment_name": "A", "priority": "low",
         "status": "reported", "created_at": "2026-01-03"},
        {"id": "2", "department_id": "dept_maint", "workspace_id": "ws_test", "equipment_name": "B", "priority": "high",
         "status": "resolved", "created_at": "2026-01-04"},
        {"id": "3", "department_id": "dept_maint", "workspace_id": "ws_test", "equipment_name": "C", "priority": "high",
         "status": "reported", "created_at": "2026-01-01"},
        {"id": "4", "department_id": "dept_maint", "workspace_id": "ws_test", "equipment_name": "D", "priority": "medium",
         "status": "diagnosed", "created_at": "2026-01-02"},
    ]
    r = client.get("/api/maintenance/tickets")
    assert r.status_code == 200
    names = [t["equipment_name"] for t in r.json()["tickets"]]
    # unresolved first: C (high), D (medium), A (low), then resolved B
    assert names == ["C", "D", "A", "B"]


def test_blocking_production_orders_enrichment_and_sort(maint_api):
    """Tickets linked to blocked work orders float to the top with badges."""
    client, store, work_orders, *_ = maint_api
    for name, pri, created in (
        ("Pump A", "high", "2026-01-01T00:00:00+00:00"),
        ("CNC Mill", "low", "2026-01-02T00:00:00+00:00"),
        ("Conveyor", "medium", "2026-01-03T00:00:00+00:00"),
    ):
        r = client.post("/api/maintenance/tickets", json={
            "equipment_name": name,
            "priority": pri,
        })
        assert r.status_code == 200, r.text
        store.rows[-1]["created_at"] = created
    ids = [row["id"] for row in store.rows]
    blocking_id = ids[1]

    work_orders.rows.append({
        "id": "pwo_block1",
        "workspace_id": "ws_test",
        "reference": "Order #245",
        "due_date": "2026-09-20",
        "status": "in_production",
        "blocked": True,
        "linked_maintenance_ticket_id": blocking_id,
    })
    # Linked but not blocked must NOT appear.
    work_orders.rows.append({
        "id": "pwo_ok",
        "workspace_id": "ws_test",
        "reference": "Order #100",
        "due_date": "2026-01-01",
        "status": "in_production",
        "blocked": False,
        "linked_maintenance_ticket_id": ids[0],
    })
    work_orders.rows.append({
        "id": "pwo_block2",
        "workspace_id": "ws_test",
        "reference": "Order #300",
        "due_date": "",
        "status": "quality_check",
        "blocked": True,
        "linked_maintenance_ticket_id": blocking_id,
    })

    listed = client.get("/api/maintenance/tickets")
    assert listed.status_code == 200, listed.text
    tickets = listed.json()["tickets"]
    assert tickets[0]["equipment_name"] == "CNC Mill"
    assert tickets[0]["id"] == blocking_id

    cnc = tickets[0]
    assert len(cnc["blocking_production_orders"]) == 2
    refs = {e["reference"] for e in cnc["blocking_production_orders"]}
    assert refs == {"Order #245", "Order #300"}
    by_ref = {e["reference"]: e for e in cnc["blocking_production_orders"]}
    assert by_ref["Order #245"]["work_order_id"] == "pwo_block1"
    assert by_ref["Order #245"]["due_date"] == "2026-09-20"

    for t in tickets[1:]:
        assert t["blocking_production_orders"] == []


def test_filter_status_priority(maint_api):
    client, store, *_ = maint_api
    client.post("/api/maintenance/tickets", json={"equipment_name": "A", "priority": "high"})
    client.post("/api/maintenance/tickets", json={"equipment_name": "B", "priority": "low"})
    store.rows[0]["status"] = "resolved"
    r = client.get("/api/maintenance/tickets?status=resolved&priority=high")
    assert r.status_code == 200
    assert len(r.json()["tickets"]) == 1
    assert r.json()["tickets"][0]["equipment_name"] == "A"


def test_independent_tickets(maint_api):
    client, store, work_orders, as_ceo, as_member, as_tech, as_lead, as_outsider, depts = maint_api
    client.post("/api/maintenance/tickets", json={"equipment_name": "A"})
    client.post("/api/maintenance/tickets", json={"equipment_name": "B"})
    store.rows[0]["assigned_technician"] = "u_mem"
    store.rows[1]["assigned_technician"] = "u_mem"
    a, b = store.rows[0]["id"], store.rows[1]["id"]
    client.patch(f"/api/maintenance/tickets/{a}", json={"status": "diagnosed"})
    assert store.rows[0]["status"] == "diagnosed"
    assert store.rows[1]["status"] == "reported"


def test_delete_lead_only(maint_api):
    client, store, work_orders, as_ceo, as_member, as_tech, as_lead, as_outsider, depts = maint_api
    client.post("/api/maintenance/tickets", json={"equipment_name": "A"})
    tid = store.rows[0]["id"]
    assert client.delete(f"/api/maintenance/tickets/{tid}").status_code == 403
    server.app.dependency_overrides[server.get_principal] = as_lead
    assert client.delete(f"/api/maintenance/tickets/{tid}").status_code == 200
    assert store.rows == []


def test_lead_can_assign_on_create(maint_api):
    client, store, work_orders, as_ceo, as_member, as_tech, as_lead, as_outsider, depts = maint_api
    server.app.dependency_overrides[server.get_principal] = as_lead
    r = client.post("/api/maintenance/tickets", json={
        "equipment_name": "Press",
        "assigned_technician": "u_tech",
    })
    assert r.status_code == 200
    assert store.rows[0]["assigned_technician"] == "u_tech"
    assert store.rows[0]["reported_by"] == "u_lead"


def test_equipment_history_and_chronic_badge_on_list(maint_api):
    client, store, work_orders, *_ = maint_api
    now = __import__("datetime").datetime(2026, 9, 14, tzinfo=__import__("datetime").timezone.utc)
    for i in range(3):
        r = client.post("/api/maintenance/tickets", json={
            "equipment_name": "CNC Mill #3",
            "description": f"Failure {i}",
            "priority": "medium",
        })
        assert r.status_code == 200, r.text
        store.rows[-1]["created_at"] = (now - __import__("datetime").timedelta(days=10 - i)).isoformat()
    # Different equipment should not inflate the count
    client.post("/api/maintenance/tickets", json={"equipment_name": "Lathe", "priority": "low"})

    hist = client.get("/api/maintenance/equipment-history", params={"equipment_name": "cnc mill #3"})
    assert hist.status_code == 200, hist.text
    body = hist.json()
    assert body["ticket_count"] == 3
    assert body["ticket_count_90d"] == 3
    assert body["equipment_name"].lower() == "cnc mill #3"

    listed = client.get("/api/maintenance/tickets")
    assert listed.status_code == 200
    payload = listed.json()
    assert "downtime_summary" in payload
    summary = payload["downtime_summary"]
    assert summary["metric_label"]
    assert "open" in summary["metric_label"].lower()
    assert "machine-down" not in summary["metric_label"].lower()
    assert "by_equipment" in summary
    by_name = {r["equipment_name"]: r for r in summary["by_equipment"]}
    assert "CNC Mill #3" in by_name
    assert by_name["CNC Mill #3"]["ticket_count"] >= 3
    cnc = [t for t in payload["tickets"] if t["equipment_name"] == "CNC Mill #3"]
    assert cnc
    assert cnc[0]["is_chronic_equipment"] is True
    assert cnc[0]["recent_repairs_90d"] == 3
    lathe = next(t for t in payload["tickets"] if t["equipment_name"] == "Lathe")
    assert lathe["is_chronic_equipment"] is False
    assert lathe["recent_repairs_90d"] == 1
