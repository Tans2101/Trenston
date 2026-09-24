"""Procurement request queue API tests."""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_procurement_queue")

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

OUTSIDER = {
    "user_id": "u_out",
    "email": "out@acme.com",
    "name": "Out",
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
}


class RequestStore:
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
            else:
                return False
        elif actual != v:
            return False
    return True


@pytest.fixture
def proc_api():
    store = RequestStore()
    work_orders = RequestStore()
    depts = MagicMock()
    depts.find_one = AsyncMock(return_value=dict(PROC_DEPT))
    members = MagicMock()

    async def member_find_one(query, projection=None):
        uid = query.get("user_id")
        if uid == "u_mem":
            return {"department_id": "dept_proc", "user_id": "u_mem", "role": "member"}
        if uid == "u_lead":
            return {"department_id": "dept_proc", "user_id": "u_lead", "role": "lead"}
        if uid == "u_ceo":
            return None  # CEO bypasses membership
        return None

    members.find_one = AsyncMock(side_effect=member_find_one)
    users = MagicMock()
    users.find_one = AsyncMock(return_value={"name": "Mem", "email": "mem@acme.com"})
    attach_users_in_find(users)

    mock_db = MagicMock()
    mock_db.workspaces.find_one = AsyncMock(return_value={"timezone": "Asia/Manila"})
    mock_db.departments = depts
    mock_db.department_members = members
    mock_db.procurement_requests = store
    mock_db.production_work_orders = work_orders
    mock_db.users = users

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
        yield client, store, work_orders, as_ceo, as_member, as_lead, as_outsider, depts
    server.app.dependency_overrides.clear()


def test_procurement_not_placeholder():
    assert catalog.TYPE_PROCUREMENT not in catalog.PLACEHOLDER_SHELL_TYPES


def test_outsider_gets_403(proc_api):
    client, store, work_orders, as_ceo, as_member, as_lead, as_outsider, depts = proc_api
    server.app.dependency_overrides[server.get_principal] = as_outsider
    assert client.get("/api/procurement/requests").status_code == 403
    assert client.post("/api/procurement/requests", json={"item": "Bolts", "quantity": 10}).status_code == 403


def test_member_creates_with_server_requested_by(proc_api):
    client, store, work_orders, as_ceo, as_member, as_lead, as_outsider, depts = proc_api
    r = client.post("/api/procurement/requests", json={
        "item": "Steel plate",
        "quantity": 4,
        "vendor_name": "Acme Metals",
        "requested_by": "u_hacker",  # ignored — not on model
    })
    assert r.status_code == 200, r.text
    body = r.json()["request"]
    assert body["requested_by"] == "u_mem"
    assert body["status"] == "requested"
    assert body["item"] == "Steel plate"
    assert store.rows[0]["requested_by"] == "u_mem"


def test_member_cannot_approve(proc_api):
    client, store, work_orders, as_ceo, as_member, as_lead, as_outsider, depts = proc_api
    client.post("/api/procurement/requests", json={"item": "Widget", "quantity": 1})
    rid = store.rows[0]["id"]
    r = client.patch(f"/api/procurement/requests/{rid}", json={"status": "approved"})
    assert r.status_code == 403
    assert store.rows[0]["status"] == "requested"


def test_member_can_edit_own_requested(proc_api):
    client, store, work_orders, as_ceo, as_member, as_lead, as_outsider, depts = proc_api
    client.post("/api/procurement/requests", json={"item": "Widget", "quantity": 1})
    rid = store.rows[0]["id"]
    r = client.patch(f"/api/procurement/requests/{rid}", json={
        "item": "Widget v2", "quantity": 3, "vendor_name": "V", "notes": "rush",
    })
    assert r.status_code == 200, r.text
    assert store.rows[0]["item"] == "Widget v2"
    assert store.rows[0]["quantity"] == 3.0


def test_lead_approves_sets_approved_by(proc_api):
    client, store, work_orders, as_ceo, as_member, as_lead, as_outsider, depts = proc_api
    client.post("/api/procurement/requests", json={"item": "Cable", "quantity": 2})
    rid = store.rows[0]["id"]
    server.app.dependency_overrides[server.get_principal] = as_lead
    r = client.patch(f"/api/procurement/requests/{rid}", json={"status": "approved"})
    assert r.status_code == 200, r.text
    assert store.rows[0]["status"] == "approved"
    assert store.rows[0]["approved_by"] == "u_lead"


def test_ceo_can_reject(proc_api):
    client, store, work_orders, as_ceo, as_member, as_lead, as_outsider, depts = proc_api
    client.post("/api/procurement/requests", json={"item": "Cable", "quantity": 2})
    rid = store.rows[0]["id"]
    server.app.dependency_overrides[server.get_principal] = as_ceo
    r = client.patch(f"/api/procurement/requests/{rid}", json={"status": "rejected"})
    assert r.status_code == 200
    assert store.rows[0]["status"] == "rejected"


def test_independent_statuses(proc_api):
    client, store, work_orders, as_ceo, as_member, as_lead, as_outsider, depts = proc_api
    client.post("/api/procurement/requests", json={"item": "A", "quantity": 1})
    client.post("/api/procurement/requests", json={"item": "B", "quantity": 1})
    a, b = store.rows[0]["id"], store.rows[1]["id"]
    server.app.dependency_overrides[server.get_principal] = as_lead
    client.patch(f"/api/procurement/requests/{a}", json={"status": "approved"})
    assert store.rows[0]["status"] == "approved"
    assert store.rows[1]["status"] == "requested"


def test_list_filter_by_status(proc_api):
    client, store, work_orders, as_ceo, as_member, as_lead, as_outsider, depts = proc_api
    client.post("/api/procurement/requests", json={"item": "A", "quantity": 1})
    client.post("/api/procurement/requests", json={"item": "B", "quantity": 1})
    store.rows[0]["status"] = "delivered"
    r = client.get("/api/procurement/requests?status=delivered")
    assert r.status_code == 200
    assert len(r.json()["requests"]) == 1
    assert r.json()["requests"][0]["item"] == "A"


def test_member_delete_own_requested(proc_api):
    client, store, work_orders, as_ceo, as_member, as_lead, as_outsider, depts = proc_api
    client.post("/api/procurement/requests", json={"item": "Temp", "quantity": 1})
    rid = store.rows[0]["id"]
    r = client.delete(f"/api/procurement/requests/{rid}")
    assert r.status_code == 200
    assert store.rows == []


def test_member_cannot_delete_after_approve(proc_api):
    client, store, work_orders, as_ceo, as_member, as_lead, as_outsider, depts = proc_api
    client.post("/api/procurement/requests", json={"item": "Temp", "quantity": 1})
    rid = store.rows[0]["id"]
    store.rows[0]["status"] = "approved"
    r = client.delete(f"/api/procurement/requests/{rid}")
    assert r.status_code == 403
    assert len(store.rows) == 1


def test_dept_disabled_404(proc_api):
    client, store, work_orders, as_ceo, as_member, as_lead, as_outsider, depts = proc_api
    depts.find_one = AsyncMock(return_value=None)
    assert client.get("/api/procurement/requests").status_code == 404


def test_blocking_production_orders_enrichment_and_sort(proc_api):
    """Requests linked to awaiting/blocked work orders float to the top with badges."""
    client, store, work_orders, as_ceo, as_member, as_lead, as_outsider, depts = proc_api
    # Create three requests; the middle one will be linked as blocking.
    for item in ("Restock A", "Steel for WO", "Restock B"):
        r = client.post("/api/procurement/requests", json={"item": item, "quantity": 1})
        assert r.status_code == 200, r.text
    ids = [row["id"] for row in store.rows]
    assert len(ids) == 3
    blocking_req_id = ids[1]

    work_orders.rows.append({
        "id": "pwo_block1",
        "workspace_id": "ws_test",
        "reference": "Order #245",
        "due_date": "2026-09-20",
        "status": "awaiting_materials",
        "blocked": False,
        "linked_procurement_request_id": blocking_req_id,
    })
    # Completed linked order must NOT appear as blocking.
    work_orders.rows.append({
        "id": "pwo_done",
        "workspace_id": "ws_test",
        "reference": "Order #100",
        "due_date": "2026-01-01",
        "status": "completed",
        "blocked": False,
        "linked_procurement_request_id": ids[0],
    })
    # Blocked (any status) still counts.
    work_orders.rows.append({
        "id": "pwo_blocked",
        "workspace_id": "ws_test",
        "reference": "Order #300",
        "due_date": "",
        "status": "in_production",
        "blocked": True,
        "linked_procurement_request_id": blocking_req_id,
    })

    listed = client.get("/api/procurement/requests")
    assert listed.status_code == 200, listed.text
    requests = listed.json()["requests"]
    assert [r["item"] for r in requests][0] == "Steel for WO"
    assert all(r["item"] != "Steel for WO" or i == 0 for i, r in enumerate(requests))

    steel = requests[0]
    assert len(steel["blocking_production_orders"]) == 2
    refs = {e["reference"] for e in steel["blocking_production_orders"]}
    assert refs == {"Order #245", "Order #300"}
    by_ref = {e["reference"]: e for e in steel["blocking_production_orders"]}
    assert by_ref["Order #245"]["work_order_id"] == "pwo_block1"
    assert by_ref["Order #245"]["due_date"] == "2026-09-20"
    assert by_ref["Order #300"]["due_date"] == ""

    # Non-blocking requests get an empty array (live field always present).
    for r in requests[1:]:
        assert r["blocking_production_orders"] == []


def test_blocking_badge_clears_when_link_removed_or_completed(proc_api):
    client, store, work_orders, as_ceo, as_member, as_lead, as_outsider, depts = proc_api
    client.post("/api/procurement/requests", json={"item": "Widget", "quantity": 2})
    client.post("/api/procurement/requests", json={"item": "Other", "quantity": 1})
    rid = store.rows[0]["id"]
    work_orders.rows.append({
        "id": "pwo_live",
        "workspace_id": "ws_test",
        "reference": "WO-9",
        "due_date": "2026-10-01",
        "status": "awaiting_materials",
        "blocked": False,
        "linked_procurement_request_id": rid,
    })
    first = client.get("/api/procurement/requests").json()["requests"]
    assert first[0]["id"] == rid
    assert first[0]["blocking_production_orders"][0]["reference"] == "WO-9"

    # Completing the work order clears the badge on next fetch.
    work_orders.rows[0]["status"] = "completed"
    mid = client.get("/api/procurement/requests").json()["requests"]
    widget = next(r for r in mid if r["id"] == rid)
    assert widget["blocking_production_orders"] == []

    # Re-block via blocked flag, then unlink — badge disappears again.
    work_orders.rows[0]["status"] = "in_production"
    work_orders.rows[0]["blocked"] = True
    again = client.get("/api/procurement/requests").json()["requests"]
    assert again[0]["id"] == rid
    assert again[0]["blocking_production_orders"][0]["reference"] == "WO-9"

    work_orders.rows[0]["linked_procurement_request_id"] = None
    final = client.get("/api/procurement/requests").json()["requests"]
    widget = next(r for r in final if r["id"] == rid)
    assert widget["blocking_production_orders"] == []



def test_expected_delivery_date_create_and_patch(proc_api):
    client, store, work_orders, as_ceo, as_member, as_lead, as_outsider, depts = proc_api
    r = client.post("/api/procurement/requests", json={
        "item": "Bearings",
        "quantity": 4,
        "expected_delivery_date": "2026-04-01",
    })
    assert r.status_code == 200, r.text
    body = r.json()["request"]
    assert body["expected_delivery_date"] == "2026-04-01"
    rid = body["id"]

    bad = client.patch(f"/api/procurement/requests/{rid}", json={"expected_delivery_date": "not-a-date"})
    assert bad.status_code == 400

    server.app.dependency_overrides[server.get_principal] = as_lead
    ok = client.patch(f"/api/procurement/requests/{rid}", json={
        "status": "ordered",
        "expected_delivery_date": "2026-04-15",
    })
    assert ok.status_code == 200, ok.text
    assert ok.json()["request"]["status"] == "ordered"
    assert ok.json()["request"]["expected_delivery_date"] == "2026-04-15"
    assert store.rows[0]["expected_delivery_date"] == "2026-04-15"


def test_vendor_suggestions_and_price_change_flag(proc_api):
    client, store, work_orders, as_ceo, as_member, as_lead, as_outsider, depts = proc_api
    # Stable price history
    for i, cost in enumerate((10.0, 10.5, 10.2)):
        store.rows.append({
            "id": f"preq_stable_{i}",
            "department_id": "dept_proc",
            "workspace_id": "ws_test",
            "item": "Steel plate",
            "vendor_name": "Acme Metals",
            "cost": cost,
            "status": "delivered",
            "created_at": f"2026-01-0{i+1}T00:00:00+00:00",
        })
    # Volatile vendor
    for i, cost in enumerate((20.0, 21.0, 30.0)):
        store.rows.append({
            "id": f"preq_vol_{i}",
            "department_id": "dept_proc",
            "workspace_id": "ws_test",
            "item": "Steel plate",
            "vendor_name": "Volatile Co",
            "cost": cost,
            "status": "delivered",
            "created_at": f"2026-02-0{i+1}T00:00:00+00:00",
        })
    r = client.get("/api/procurement/vendor-suggestions", params={"item": "steel"})
    assert r.status_code == 200, r.text
    suggestions = r.json()["suggestions"]
    by_vendor = {s["vendor_name"]: s for s in suggestions}
    assert "Acme Metals" in by_vendor
    assert "Volatile Co" in by_vendor
    assert by_vendor["Acme Metals"]["times_used"] == 3
    assert by_vendor["Acme Metals"]["price_changed"] is False
    assert by_vendor["Volatile Co"]["price_changed"] is True
    assert by_vendor["Volatile Co"]["last_cost"] == 30.0
    # Sort: more used first; both 3 so most recent vendor first
    assert suggestions[0]["times_used"] >= suggestions[1]["times_used"]

    empty = client.get("/api/procurement/vendor-suggestions", params={"item": "zzzz-nope"})
    assert empty.status_code == 200
    assert empty.json()["suggestions"] == []


def test_priority_and_unified_queue_sort(proc_api):
    client, store, work_orders, as_ceo, as_member, as_lead, as_outsider, depts = proc_api
    # Create four requests with explicit created_at ordering
    specs = [
        ("plain", "normal", None, False),
        ("high only", "high", None, False),
        ("blocking only", "normal", "awaiting_materials", False),
        ("blocking overdue", "low", "awaiting_materials", True),
    ]
    ids = []
    for i, (item, priority, wo_status, overdue) in enumerate(specs):
        r = client.post("/api/procurement/requests", json={
            "item": item,
            "quantity": 1,
            "priority": priority,
            "expected_delivery_date": "2020-01-01" if overdue else "",
        })
        assert r.status_code == 200, r.text
        rid = r.json()["request"]["id"]
        ids.append(rid)
        store.rows[-1]["created_at"] = f"2026-05-0{i+1}T12:00:00+00:00"
        if overdue:
            store.rows[-1]["status"] = "ordered"
            store.rows[-1]["expected_delivery_date"] = "2020-01-01"
        if wo_status:
            work_orders.rows.append({
                "id": f"pwo_sort_{i}",
                "workspace_id": "ws_test",
                "reference": f"WO-{i}",
                "due_date": "2026-06-01",
                "status": wo_status,
                "blocked": False,
                "linked_procurement_request_id": rid,
            })
    listed = client.get("/api/procurement/requests")
    assert listed.status_code == 200, listed.text
    items = [r["item"] for r in listed.json()["requests"]]
    # blocking+overdue, blocking only, high only, plain
    assert items[:4] == ["blocking overdue", "blocking only", "high only", "plain"]
