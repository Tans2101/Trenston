"""HR per-hire onboarding API tests."""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_hr_onboarding")

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

HR_DEPT = {
    "department_id": "dept_hr",
    "workspace_id": "ws_test",
    "type": "hr",
    "name": "HR",
    "enabled": True,
}


class CollStore:
    def __init__(self):
        self.rows = []

    async def find_one(self, query, projection=None):
        for r in self.rows:
            if all(r.get(k) == v for k, v in query.items()):
                return {k: v for k, v in r.items() if k != "_id"}
        return None

    def find(self, query, projection=None):
        matched = [dict(r) for r in self.rows if all(r.get(k) == v for k, v in query.items())]

        class C:
            async def to_list(self, n):
                return matched[:n]

            def sort(self, *a, **k):
                return self

        return C()

    async def insert_one(self, doc):
        self.rows.append(dict(doc))

    async def update_one(self, query, update):
        for r in self.rows:
            if all(r.get(k) == v for k, v in query.items()):
                r.update(update.get("$set") or {})
                return MagicMock(matched_count=1)
        return MagicMock(matched_count=0)

    async def delete_one(self, query):
        before = len(self.rows)
        self.rows = [r for r in self.rows if not all(r.get(k) == v for k, v in query.items())]
        return MagicMock(deleted_count=before - len(self.rows))


@pytest.fixture
def hr_api():
    templates = CollStore()
    instances = CollStore()
    employees = CollStore()
    off_templates = CollStore()
    off_instances = CollStore()
    depts = MagicMock()
    depts.find_one = AsyncMock(return_value=dict(HR_DEPT))
    members = MagicMock()

    async def member_find_one(query, projection=None):
        uid = query.get("user_id")
        roles = {"u_mem": "member", "u_lead": "lead"}
        if uid in roles:
            return {"department_id": "dept_hr", "user_id": uid, "role": roles[uid]}
        return None

    members.find_one = AsyncMock(side_effect=member_find_one)
    users = MagicMock()
    users.find_one = AsyncMock(return_value={"name": "Mem", "email": "mem@acme.com"})
    attach_users_in_find(users)

    mock_db = MagicMock()
    mock_db.departments = depts
    mock_db.department_members = members
    mock_db.hr_onboarding_template = templates
    mock_db.hr_onboarding_instances = instances
    mock_db.hr_employees = employees
    mock_db.hr_offboarding_template = off_templates
    mock_db.hr_offboarding_instances = off_instances
    mock_db.users = users
    memberships = CollStore()
    for uid, email, name in (
        ("u_ceo", "ceo@acme.com", "CEO"),
        ("u_lead", "lead@acme.com", "Lead"),
        ("u_mem", "mem@acme.com", "Mem"),
    ):
        memberships.rows.append({
            "membership_id": f"mem_{uid}",
            "workspace_id": "ws_test",
            "user_id": uid,
            "email": email,
            "name": name,
            "role": "owner" if uid == "u_ceo" else "member",
            "pack": "owner" if uid == "u_ceo" else "member",
            "status": "active",
        })
    mock_db.memberships = memberships

    async def as_ceo():
        return CEO

    async def as_member():
        return MEMBER

    async def as_lead():
        return LEAD

    async def as_outsider():
        return OUTSIDER

    server.app.dependency_overrides[server.get_principal] = as_lead
    with patch.object(server, "db", mock_db), \
         patch.object(server, "BILLING_ENFORCED", False):
        client = TestClient(server.app)
        yield client, templates, instances, as_ceo, as_member, as_lead, as_outsider, depts, {
            "employees": employees,
            "off_templates": off_templates,
            "off_instances": off_instances,
        }
    server.app.dependency_overrides.clear()


def test_hr_not_placeholder():
    assert catalog.TYPE_HR not in catalog.PLACEHOLDER_SHELL_TYPES
    assert catalog.PLACEHOLDER_SHELL_TYPES == frozenset()


def test_outsider_403(hr_api):
    client, templates, instances, as_ceo, as_member, as_lead, as_outsider, depts, *_ = hr_api
    server.app.dependency_overrides[server.get_principal] = as_outsider
    assert client.get("/api/hr/template").status_code == 403
    assert client.get("/api/hr/onboarding").status_code == 403
    assert client.post("/api/hr/onboarding", json={"hire_name": "Ada"}).status_code == 403


def test_default_template_created_on_get(hr_api):
    client, templates, instances, *_ = hr_api
    r = client.get("/api/hr/template")
    assert r.status_code == 200, r.text
    steps = r.json()["template"]["steps"]
    assert [s["name"] for s in sorted(steps, key=lambda x: x["order"])] == [
        "Offer", "Paperwork", "Orientation", "Active",
    ]
    assert len(templates.rows) == 1


def test_member_cannot_edit_template_or_create(hr_api):
    client, templates, instances, as_ceo, as_member, as_lead, as_outsider, depts, *_ = hr_api
    client.get("/api/hr/template")
    server.app.dependency_overrides[server.get_principal] = as_member
    r = client.patch("/api/hr/template", json={"steps": [{"name": "Only"}]})
    assert r.status_code == 403
    r2 = client.post("/api/hr/onboarding", json={"hire_name": "Ada"})
    assert r2.status_code == 403


def test_create_copies_template_independently(hr_api):
    client, templates, instances, as_ceo, as_member, as_lead, as_outsider, depts, *_ = hr_api
    client.get("/api/hr/template")
    r1 = client.post("/api/hr/onboarding", json={"hire_name": "Ada", "hire_email": "ada@x.com"})
    r2 = client.post("/api/hr/onboarding", json={"hire_name": "Bob"})
    assert r1.status_code == 200 and r2.status_code == 200
    a, b = instances.rows[0], instances.rows[1]
    assert a["overall_status"] == "in_progress"
    assert len(a["steps"]) == 4
    assert a["steps"][0]["status"] == "not_started"
    # Different step ids (copied, not shared)
    assert {s["id"] for s in a["steps"]}.isdisjoint({s["id"] for s in b["steps"]})

    # Edit template after create — instances unchanged
    client.patch("/api/hr/template", json={"steps": [{"name": "Only Offer"}, {"name": "Done"}]})
    assert len(templates.rows[0]["steps"]) == 2
    assert len(instances.rows[0]["steps"]) == 4
    assert instances.rows[0]["steps"][0]["name"] == "Offer"


def test_assignee_updates_own_step_not_others(hr_api):
    client, templates, instances, as_ceo, as_member, as_lead, as_outsider, depts, *_ = hr_api
    client.post("/api/hr/onboarding", json={"hire_name": "Ada"})
    inst = instances.rows[0]
    step0 = inst["steps"][0]
    step1 = inst["steps"][1]
    step0["assigned_to"] = "u_mem"
    step1["assigned_to"] = "u_lead"

    server.app.dependency_overrides[server.get_principal] = as_member
    r = client.patch(f"/api/hr/onboarding/{inst['id']}", json={
        "step_id": step0["id"], "status": "in_progress",
    })
    assert r.status_code == 200, r.text
    assert instances.rows[0]["steps"][0]["status"] == "in_progress"

    r2 = client.patch(f"/api/hr/onboarding/{inst['id']}", json={
        "step_id": step1["id"], "status": "done",
    })
    assert r2.status_code == 403


def test_overall_status_active_when_all_done(hr_api):
    client, templates, instances, *_ = hr_api
    client.post("/api/hr/onboarding", json={"hire_name": "Ada"})
    inst = instances.rows[0]
    for step in inst["steps"]:
        r = client.patch(f"/api/hr/onboarding/{inst['id']}", json={
            "step_id": step["id"], "status": "done",
        })
        assert r.status_code == 200
    assert instances.rows[0]["overall_status"] == "active"
    assert r.json()["instance"]["overall_status"] == "active"


def test_completing_onboarding_creates_one_employee(hr_api):
    client, templates, instances, as_ceo, as_member, as_lead, as_outsider, depts, stores = hr_api
    employees = stores["employees"]
    client.post("/api/hr/onboarding", json={"hire_name": "Ada Lovelace"})
    inst = instances.rows[0]
    # Mid-progress — no employee yet
    client.patch(f"/api/hr/onboarding/{inst['id']}", json={
        "step_id": inst["steps"][0]["id"], "status": "done",
    })
    assert employees.rows == []

    for step in inst["steps"]:
        client.patch(f"/api/hr/onboarding/{inst['id']}", json={
            "step_id": step["id"], "status": "done",
        })
    assert len(employees.rows) == 1
    emp = employees.rows[0]
    assert emp["name"] == "Ada Lovelace"
    assert emp["status"] == "active"
    assert emp["source_onboarding_instance_id"] == inst["id"]
    # Sensitive fields must never exist on the record
    for banned in ("salary", "compensation", "ssn", "medical", "race", "religion", "immigration"):
        assert banned not in emp

    # Completing again / re-patching must not duplicate
    client.patch(f"/api/hr/onboarding/{inst['id']}", json={
        "step_id": inst["steps"][0]["id"], "status": "done",
    })
    assert len(employees.rows) == 1

    listed = client.get("/api/hr/employees")
    assert listed.status_code == 200
    rows = listed.json()["employees"]
    names = {e["name"] for e in rows}
    # Onboarding hire stays listed; Team & Access members are mirrored in too.
    assert "Ada Lovelace" in names
    assert len(rows) >= 4
    onboarded = [e for e in rows if e.get("source_onboarding_instance_id") == inst["id"]]
    assert len(onboarded) == 1
    linked = [e for e in rows if e.get("linked_user_id")]
    assert len(linked) >= 3

    filtered = client.get("/api/hr/employees", params={"status": "active"})
    assert len(filtered.json()["employees"]) >= 1
    assert any(e["name"] == "Ada Lovelace" for e in filtered.json()["employees"])
    empty = client.get("/api/hr/employees", params={"status": "departed"})
    assert empty.json()["employees"] == []


def test_offboarding_sets_departed_only_when_complete(hr_api):
    client, templates, instances, as_ceo, as_member, as_lead, as_outsider, depts, stores = hr_api
    employees = stores["employees"]
    off_templates = stores["off_templates"]
    off_instances = stores["off_instances"]

    # Seed an active employee
    client.post("/api/hr/employees", json={"name": "Grace Hopper", "role": "Engineer"})
    assert len(employees.rows) == 1
    emp = employees.rows[0]
    assert emp["status"] == "active"

    r = client.get("/api/hr/offboarding/template")
    assert r.status_code == 200
    names = [s["name"] for s in sorted(r.json()["template"]["steps"], key=lambda x: x["order"])]
    assert names[0] == "Revoke Trenston/system access"
    assert "Update employee status to departed" in names
    assert len(off_templates.rows) == 1

    started = client.post("/api/hr/offboarding", json={"employee_id": emp["id"]})
    assert started.status_code == 200, started.text
    assert employees.rows[0]["status"] == "active"  # not departed yet
    assert employees.rows[0].get("departed_at") is None
    off = off_instances.rows[0]
    assert off["overall_status"] == "in_progress"
    assert off["employee_id"] == emp["id"]

    # Finish all but one step — still active
    for step in off["steps"][:-1]:
        client.patch(f"/api/hr/offboarding/{off['id']}", json={
            "step_id": step["id"], "status": "done",
        })
    assert employees.rows[0]["status"] == "active"
    assert off_instances.rows[0]["overall_status"] == "in_progress"

    # Complete last step → departed
    last = off["steps"][-1]
    done = client.patch(f"/api/hr/offboarding/{off['id']}", json={
        "step_id": last["id"], "status": "done",
    })
    assert done.status_code == 200
    assert off_instances.rows[0]["overall_status"] == "active"
    assert employees.rows[0]["status"] == "departed"
    assert employees.rows[0].get("departed_at")

    listed = client.get("/api/hr/employees", params={"status": "departed"})
    assert len(listed.json()["employees"]) == 1


def test_independent_progress(hr_api):
    client, templates, instances, *_ = hr_api
    client.post("/api/hr/onboarding", json={"hire_name": "Ada"})
    client.post("/api/hr/onboarding", json={"hire_name": "Bob"})
    a, b = instances.rows[0], instances.rows[1]
    client.patch(f"/api/hr/onboarding/{a['id']}", json={
        "step_id": a["steps"][0]["id"], "status": "done",
    })
    assert instances.rows[0]["steps"][0]["status"] == "done"
    assert instances.rows[1]["steps"][0]["status"] == "not_started"


def test_sort_in_progress_first(hr_api):
    client, templates, instances, *_ = hr_api
    instances.rows = [
        {"id": "1", "department_id": "dept_hr", "hire_name": "Done", "overall_status": "active",
         "steps": [], "created_at": "2026-01-02"},
        {"id": "2", "department_id": "dept_hr", "hire_name": "Open", "overall_status": "in_progress",
         "steps": [], "created_at": "2026-01-01"},
    ]
    r = client.get("/api/hr/onboarding")
    names = [i["hire_name"] for i in r.json()["instances"]]
    assert names == ["Open", "Done"]


def test_delete_lead_only(hr_api):
    client, templates, instances, as_ceo, as_member, as_lead, as_outsider, depts, *_ = hr_api
    client.post("/api/hr/onboarding", json={"hire_name": "Ada"})
    iid = instances.rows[0]["id"]
    server.app.dependency_overrides[server.get_principal] = as_member
    assert client.delete(f"/api/hr/onboarding/{iid}").status_code == 403
    server.app.dependency_overrides[server.get_principal] = as_lead
    assert client.delete(f"/api/hr/onboarding/{iid}").status_code == 200
    assert instances.rows == []


@pytest.mark.asyncio
async def test_ensure_template_idempotent(hr_api):
    client, templates, instances, *_ = hr_api
    mock = MagicMock()
    mock.hr_onboarding_template = templates
    with patch.object(server, "db", mock):
        doc = await server._ensure_hr_onboarding_template("ws_test", "dept_hr")
        assert [s["name"] for s in doc["steps"]] == [
            "Offer", "Paperwork", "Orientation", "Active",
        ]
        doc2 = await server._ensure_hr_onboarding_template("ws_test", "dept_hr")
        assert doc2["id"] == doc["id"]
        assert len(templates.rows) == 1
