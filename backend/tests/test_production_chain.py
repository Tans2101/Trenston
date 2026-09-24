"""Production work-order queue API tests (fixed statuses, no stages)."""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_production_chain")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import server  # noqa: E402
from mongo_mocks import attach_users_in_find  # noqa: E402

CEO = {
    "user_id": "u_ceo",
    "email": "ceo@acme.com",
    "name": "CEO",
    "workspace_id": "ws_test",
    "role": "owner",
    "pack": "owner",
}

OUTSIDER = {
    "user_id": "u_out",
    "email": "out@acme.com",
    "name": "Out",
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

LEAD = {
    "user_id": "u_lead",
    "email": "lead@acme.com",
    "name": "Lead",
    "workspace_id": "ws_test",
    "role": "member",
    "pack": "member",
}

PROD_DEPT = {
    "department_id": "dept_prod",
    "workspace_id": "ws_test",
    "type": "production",
    "name": "Production",
    "enabled": True,
}


def _match(doc: dict, query: dict) -> bool:
    if not query:
        return True
    for k, v in query.items():
        if k == "$or":
            if not any(_match(doc, clause) for clause in v):
                return False
            continue
        actual = doc.get(k)
        if isinstance(v, dict):
            if "$in" in v:
                if actual not in v["$in"]:
                    return False
            elif "$gt" in v:
                if not (actual is not None and actual > v["$gt"]):
                    return False
            else:
                return False
        elif actual != v:
            return False
    return True


class DocStore:
    def __init__(self):
        self.rows = []

    async def find_one(self, query, projection=None):
        for r in self.rows:
            if _match(r, query):
                return {k: v for k, v in r.items() if k != "_id"}
        return None

    def find(self, query, projection=None):
        matched = [dict(r) for r in self.rows if _match(r, query or {})]
        state = {"sort": None}

        class C:
            def sort(self, field, direction=1):
                state["sort"] = (field, direction)
                return self

            async def to_list(self, n):
                items = list(matched)
                if state["sort"]:
                    field, direction = state["sort"]
                    items.sort(key=lambda x: x.get(field) or 0, reverse=direction == -1)
                return items[:n]

        return C()

    async def insert_one(self, doc):
        self.rows.append(dict(doc))

    async def update_one(self, query, update):
        for r in self.rows:
            if _match(r, query):
                r.update(update.get("$set") or {})
                return MagicMock(matched_count=1, modified_count=1)
        return MagicMock(matched_count=0, modified_count=0)

    async def delete_one(self, query):
        before = len(self.rows)
        self.rows = [r for r in self.rows if not _match(r, query)]
        return MagicMock(deleted_count=before - len(self.rows))

    async def delete_many(self, query):
        before = len(self.rows)
        self.rows = [r for r in self.rows if not _match(r, query)]
        return MagicMock(deleted_count=before - len(self.rows))


@pytest.fixture
def prod_api():
    orders = DocStore()
    procurement = DocStore()
    maintenance = DocStore()
    daily_logs = DocStore()
    dept_members = [
        {"department_id": "dept_prod", "user_id": "u_mem", "role": "member"},
        {"department_id": "dept_prod", "user_id": "u_lead", "role": "lead"},
    ]

    async def dept_find_one(query, projection=None):
        if query.get("type") == "production" or query.get("department_id") == "dept_prod":
            if query.get("workspace_id") in (None, "ws_test"):
                return dict(PROD_DEPT)
        return None

    async def mem_find_one(query, projection=None):
        for m in dept_members:
            if all(m.get(k) == v for k, v in query.items()):
                return dict(m)
        return None

    mock_db = MagicMock()
    mock_db.workspaces.find_one = AsyncMock(return_value={"timezone": "Asia/Manila"})
    mock_db.departments.find_one = AsyncMock(side_effect=dept_find_one)
    mock_db.department_members.find_one = AsyncMock(side_effect=mem_find_one)
    mock_db.production_work_orders = orders
    mock_db.procurement_requests = procurement
    mock_db.maintenance_tickets = maintenance
    mock_db.production_daily_logs = daily_logs
    mock_db.users.find_one = AsyncMock(
        return_value={"name": "Mem", "email": "mem@acme.com", "picture": None},
    )
    attach_users_in_find(mock_db.users)

    async def as_ceo():
        return CEO

    async def as_outsider():
        return OUTSIDER

    async def as_member():
        return MEMBER

    async def as_lead():
        return LEAD

    server.app.dependency_overrides[server.get_principal] = as_ceo
    with patch.object(server, "db", mock_db):
        client = TestClient(server.app)
        yield client, orders, procurement, maintenance, as_ceo, as_outsider, as_member, as_lead
    server.app.dependency_overrides.clear()


def test_outsider_gets_403(prod_api):
    client, orders, procurement, maintenance, as_ceo, as_outsider, as_member, as_lead = prod_api
    server.app.dependency_overrides[server.get_principal] = as_outsider
    assert client.get("/api/production/work-orders").status_code == 403
    assert client.post("/api/production/work-orders", json={"reference": "X"}).status_code == 403


def test_create_work_order_without_setup(prod_api):
    client, *_ = prod_api
    r = client.post("/api/production/work-orders", json={"reference": "WO-1", "product": "Frame"})
    assert r.status_code == 200, r.text
    wo = r.json()["work_order"]
    assert wo["reference"] == "WO-1"
    assert wo["status"] == "in_production"
    assert wo["blocked"] is False
    assert wo["quantity_produced"] is None
    assert "current_stage_id" not in wo
    assert "current_progress" not in wo


def test_create_with_open_procurement_sets_awaiting_materials(prod_api):
    client, orders, procurement, *_ = prod_api
    procurement.rows.append({
        "id": "preq_1",
        "workspace_id": "ws_test",
        "item": "Steel",
        "status": "ordered",
        "quantity": 5,
    })
    r = client.post(
        "/api/production/work-orders",
        json={"reference": "WO-mat", "linked_procurement_request_id": "preq_1"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["work_order"]["status"] == "awaiting_materials"
    assert r.json()["work_order"]["linked_procurement_request_id"] == "preq_1"


def test_stages_endpoints_removed(prod_api):
    client, *_ = prod_api
    assert client.get("/api/production/stages").status_code == 404
    assert client.post("/api/production/stages", json={"name": "Cut"}).status_code == 404


def test_member_can_update_status_and_notes(prod_api):
    client, orders, procurement, maintenance, as_ceo, as_outsider, as_member, as_lead = prod_api
    wo = client.post("/api/production/work-orders", json={"reference": "Order #1"}).json()["work_order"]

    server.app.dependency_overrides[server.get_principal] = as_member
    ok = client.patch(
        f"/api/production/work-orders/{wo['id']}",
        json={"status": "quality_check", "notes": "Ready for QC"},
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()["work_order"]
    assert body["status"] == "quality_check"
    assert body["notes"] == "Ready for QC"


def test_status_only_fixed_values(prod_api):
    client, *_ = prod_api
    wo = client.post("/api/production/work-orders", json={"reference": "S"}).json()["work_order"]
    bad = client.patch(f"/api/production/work-orders/{wo['id']}", json={"status": "assembly"})
    assert bad.status_code == 400
    for st in ("awaiting_materials", "in_production", "quality_check"):
        r = client.patch(f"/api/production/work-orders/{wo['id']}", json={"status": st})
        assert r.status_code == 200, r.text
        assert r.json()["work_order"]["status"] == st


def test_blocked_requires_category(prod_api):
    client, *_ = prod_api
    wo = client.post("/api/production/work-orders", json={"reference": "Block me"}).json()["work_order"]

    bad = client.patch(f"/api/production/work-orders/{wo['id']}", json={"blocked": True})
    assert bad.status_code == 400
    assert "blocked_reason" in bad.json()["detail"]

    bad2 = client.patch(
        f"/api/production/work-orders/{wo['id']}",
        json={"blocked": True, "blocked_reason": {"detail": "no parts"}},
    )
    assert bad2.status_code == 400

    ok = client.patch(
        f"/api/production/work-orders/{wo['id']}",
        json={
            "blocked": True,
            "blocked_reason": {"category": "material", "detail": "Waiting on steel"},
            "status": "in_production",
        },
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()["work_order"]
    assert body["blocked"] is True
    assert body["status"] == "in_production"
    assert body["blocked_reason"]["category"] == "material"


def test_complete_requires_quantity_produced(prod_api):
    client, *_ = prod_api
    wo = client.post(
        "/api/production/work-orders",
        json={"reference": "Finish", "quantity_planned": 10},
    ).json()["work_order"]

    bad = client.patch(f"/api/production/work-orders/{wo['id']}", json={"status": "completed"})
    assert bad.status_code == 400
    assert "quantity_produced" in bad.json()["detail"]

    ok = client.patch(
        f"/api/production/work-orders/{wo['id']}",
        json={"status": "completed", "quantity_produced": 9},
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()["work_order"]
    assert body["status"] == "completed"
    assert body["quantity_produced"] == 9
    assert body["completed_at"]


def test_patch_work_order_fields(prod_api):
    client, *_ = prod_api
    wo = client.post(
        "/api/production/work-orders",
        json={"reference": "Order #9", "priority": "high", "customer": "Acme"},
    ).json()["work_order"]
    assert wo["priority"] == "high"

    patched = client.patch(
        f"/api/production/work-orders/{wo['id']}",
        json={"product": "Widget", "quantity_planned": 12, "due_date": "2026-10-01"},
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()["work_order"]
    assert body["product"] == "Widget"
    assert body["quantity_planned"] == 12
    assert body["due_date"] == "2026-10-01"


def test_list_filter_by_status(prod_api):
    client, *_ = prod_api
    client.post("/api/production/work-orders", json={"reference": "A"})
    b = client.post("/api/production/work-orders", json={"reference": "B"}).json()["work_order"]
    client.patch(
        f"/api/production/work-orders/{b['id']}",
        json={"status": "completed", "quantity_produced": 1},
    )
    open_list = client.get("/api/production/work-orders?status=in_production").json()["work_orders"]
    assert len(open_list) == 1
    assert open_list[0]["reference"] == "A"
    done = client.get("/api/production/work-orders?status=completed").json()["work_orders"]
    assert len(done) == 1
    assert done[0]["reference"] == "B"


def test_delete_work_order(prod_api):
    client, orders, _procurement, _maintenance, as_ceo, as_outsider, as_member, as_lead = prod_api
    wo = client.post("/api/production/work-orders", json={"reference": "Drop me"}).json()["work_order"]
    wid = wo["id"]

    server.app.dependency_overrides[server.get_principal] = as_outsider
    denied = client.delete(f"/api/production/work-orders/{wid}")
    assert denied.status_code in (403, 404)

    server.app.dependency_overrides[server.get_principal] = as_member
    # Unassigned → members can update/delete
    ok_member = client.delete(f"/api/production/work-orders/{wid}")
    assert ok_member.status_code == 200, ok_member.text
    assert ok_member.json()["ok"] is True
    assert not any(o.get("id") == wid for o in orders.rows)

    server.app.dependency_overrides[server.get_principal] = as_ceo
    missing = client.delete(f"/api/production/work-orders/{wid}")
    assert missing.status_code == 404

    wo2 = client.post(
        "/api/production/work-orders",
        json={"reference": "Assigned", "assigned_user_ids": ["u_ceo"]},
    ).json()["work_order"]
    server.app.dependency_overrides[server.get_principal] = as_member
    blocked = client.delete(f"/api/production/work-orders/{wo2['id']}")
    assert blocked.status_code == 403

    server.app.dependency_overrides[server.get_principal] = as_ceo
    ok_ceo = client.delete(f"/api/production/work-orders/{wo2['id']}")
    assert ok_ceo.status_code == 200, ok_ceo.text


def test_member_cannot_set_assignees_on_create_or_patch(prod_api):
    client, orders, _procurement, _maintenance, as_ceo, as_outsider, as_member, as_lead = prod_api

    server.app.dependency_overrides[server.get_principal] = as_member
    create_denied = client.post(
        "/api/production/work-orders",
        json={"reference": "Hijack", "assigned_user_ids": ["u_mem"]},
    )
    assert create_denied.status_code == 403, create_denied.text
    assert "assign" in create_denied.json()["detail"].lower()

    # Empty assignees still allowed for members
    create_ok = client.post("/api/production/work-orders", json={"reference": "Open seat"})
    assert create_ok.status_code == 200, create_ok.text
    wid = create_ok.json()["work_order"]["id"]

    patch_denied = client.patch(
        f"/api/production/work-orders/{wid}",
        json={"assigned_user_ids": ["u_mem", "u_ceo"]},
    )
    assert patch_denied.status_code == 403, patch_denied.text
    assert "assign" in patch_denied.json()["detail"].lower()

    # Lead can assign on create and reassign on patch
    server.app.dependency_overrides[server.get_principal] = as_lead
    lead_create = client.post(
        "/api/production/work-orders",
        json={"reference": "Lead assigns", "assigned_user_ids": ["u_mem"]},
    )
    assert lead_create.status_code == 200, lead_create.text
    assert lead_create.json()["work_order"]["assigned_user_ids"] == ["u_mem"]
    lead_id = lead_create.json()["work_order"]["id"]

    lead_patch = client.patch(
        f"/api/production/work-orders/{lead_id}",
        json={"assigned_user_ids": ["u_ceo"]},
    )
    assert lead_patch.status_code == 200, lead_patch.text
    assert lead_patch.json()["work_order"]["assigned_user_ids"] == ["u_ceo"]

    # CEO can still assign
    server.app.dependency_overrides[server.get_principal] = as_ceo
    ceo_create = client.post(
        "/api/production/work-orders",
        json={"reference": "CEO assigns", "assigned_user_ids": ["u_lead"]},
    )
    assert ceo_create.status_code == 200, ceo_create.text
    assert ceo_create.json()["work_order"]["assigned_user_ids"] == ["u_lead"]


def test_patch_link_sets_awaiting_materials_and_unlink_resumes(prod_api):
    client, orders, procurement, *_ = prod_api
    procurement.rows.append({
        "id": "preq_open",
        "workspace_id": "ws_test",
        "item": "Bolts",
        "status": "approved",
        "quantity": 2,
    })
    wo = client.post("/api/production/work-orders", json={"reference": "Link later"}).json()["work_order"]
    assert wo["status"] == "in_production"

    linked = client.patch(
        f"/api/production/work-orders/{wo['id']}",
        json={"linked_procurement_request_id": "preq_open"},
    )
    assert linked.status_code == 200, linked.text
    body = linked.json()["work_order"]
    assert body["linked_procurement_request_id"] == "preq_open"
    assert body["status"] == "awaiting_materials"

    cleared = client.patch(
        f"/api/production/work-orders/{wo['id']}",
        json={"linked_procurement_request_id": ""},
    )
    assert cleared.status_code == 200, cleared.text
    body = cleared.json()["work_order"]
    assert body["linked_procurement_request_id"] in (None, "")
    assert body["status"] == "in_production"


def test_cannot_link_delivered_or_rejected_procurement(prod_api):
    client, orders, procurement, *_ = prod_api
    procurement.rows.append({
        "id": "preq_done",
        "workspace_id": "ws_test",
        "item": "Done",
        "status": "delivered",
    })
    bad_create = client.post(
        "/api/production/work-orders",
        json={"reference": "Bad link", "linked_procurement_request_id": "preq_done"},
    )
    assert bad_create.status_code == 400

    wo = client.post("/api/production/work-orders", json={"reference": "Ok"}).json()["work_order"]
    bad_patch = client.patch(
        f"/api/production/work-orders/{wo['id']}",
        json={"linked_procurement_request_id": "preq_done"},
    )
    assert bad_patch.status_code == 400


def test_link_open_maintenance_ticket_and_list_open(prod_api):
    client, orders, procurement, maintenance, *_ = prod_api
    maintenance.rows.append({
        "id": "mtkt_open",
        "workspace_id": "ws_test",
        "equipment_name": "CNC #3",
        "status": "in_repair",
        "priority": "high",
    })
    maintenance.rows.append({
        "id": "mtkt_done",
        "workspace_id": "ws_test",
        "equipment_name": "Lathe",
        "status": "resolved",
        "priority": "low",
    })

    listed = client.get("/api/production/work-orders")
    assert listed.status_code == 200
    open_ids = {t["id"] for t in listed.json()["open_maintenance_tickets"]}
    assert "mtkt_open" in open_ids
    assert "mtkt_done" not in open_ids

    wo = client.post(
        "/api/production/work-orders",
        json={
            "reference": "Order #245",
            "blocked": True,
            "blocked_reason": {"category": "machine", "detail": "Spindle down"},
            "linked_maintenance_ticket_id": "mtkt_open",
        },
    )
    assert wo.status_code == 200, wo.text
    body = wo.json()["work_order"]
    assert body["linked_maintenance_ticket_id"] == "mtkt_open"
    assert body["linked_maintenance"]["equipment_name"] == "CNC #3"
    assert body["blocked"] is True

    cleared = client.patch(
        f"/api/production/work-orders/{body['id']}",
        json={"linked_maintenance_ticket_id": ""},
    )
    assert cleared.status_code == 200
    assert cleared.json()["work_order"]["linked_maintenance_ticket_id"] in (None, "")
    assert cleared.json()["work_order"]["linked_maintenance"] is None

    bad = client.patch(
        f"/api/production/work-orders/{body['id']}",
        json={"linked_maintenance_ticket_id": "mtkt_done"},
    )
    assert bad.status_code == 400
