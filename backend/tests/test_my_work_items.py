"""GET /api/me/work-items — cross-department personal work feed."""
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_my_work_items")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import server  # noqa: E402

WS = "ws_work"
MEMBER = {
    "user_id": "u_mem",
    "email": "mem@acme.com",
    "name": "Mem",
    "workspace_id": WS,
    "role": "member",
    "pack": "member",
}
CEO = {
    "user_id": "u_ceo",
    "email": "ceo@acme.com",
    "name": "CEO",
    "workspace_id": WS,
    "role": "owner",
    "pack": "owner",
}

PROD = {
    "department_id": "dept_prod",
    "workspace_id": WS,
    "type": "production",
    "name": "Production",
    "enabled": True,
}
LEGAL = {
    "department_id": "dept_legal",
    "workspace_id": WS,
    "type": "legal",
    "name": "Legal",
    "enabled": True,
}
PROC = {
    "department_id": "dept_proc",
    "workspace_id": WS,
    "type": "procurement",
    "name": "Procurement",
    "enabled": True,
}
SALES = {
    "department_id": "dept_sales",
    "workspace_id": WS,
    "type": "sales",
    "name": "Sales",
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
        if k == "$and":
            if not all(_match(doc, clause) for clause in v):
                return False
            continue
        actual = doc.get(k)
        if isinstance(v, dict):
            if "$in" in v:
                allowed = list(v["$in"])
                if isinstance(actual, list):
                    if not any(x in allowed for x in actual):
                        return False
                elif actual not in allowed:
                    return False
            elif "$nin" in v:
                blocked = list(v["$nin"])
                if isinstance(actual, list):
                    if any(x in blocked for x in actual):
                        return False
                elif actual in blocked:
                    return False
            elif "$ne" in v:
                if actual == v["$ne"]:
                    return False
            elif "$elemMatch" in v:
                if not isinstance(actual, list):
                    return False
                if not any(_match(el if isinstance(el, dict) else {}, v["$elemMatch"]) for el in actual):
                    return False
            elif "$gt" in v:
                if not (actual is not None and actual > v["$gt"]):
                    return False
            else:
                return False
        else:
            # Mongo: scalar match against array field → membership
            if isinstance(actual, list):
                if v not in actual:
                    return False
            elif actual != v:
                return False
    return True


class DocStore:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    async def find_one(self, query, projection=None):
        for r in self.rows:
            if _match(r, query or {}):
                return {k: v for k, v in r.items() if k != "_id"}
        return None

    def find(self, query, projection=None):
        matched = [dict(r) for r in self.rows if _match(r, query or {})]

        class C:
            def sort(self, field, direction=1):
                return self

            async def to_list(self, n):
                return matched[:n]

        return C()

    async def insert_one(self, doc):
        self.rows.append(dict(doc))


@pytest.fixture
def work_api():
    departments = DocStore([PROD, LEGAL, PROC, SALES])
    # Member is ONLY in Production — not Legal / Procurement / Sales.
    members = DocStore([
        {"department_id": "dept_prod", "user_id": "u_mem", "role": "member"},
        {"department_id": "dept_prod", "user_id": "u_ceo", "role": "lead"},
        {"department_id": "dept_legal", "user_id": "u_ceo", "role": "lead"},
        {"department_id": "dept_proc", "user_id": "u_ceo", "role": "lead"},
        {"department_id": "dept_sales", "user_id": "u_ceo", "role": "lead"},
    ])

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    next_week = (date.today() + timedelta(days=7)).isoformat()

    production = DocStore([
        {
            "id": "pwo_mine_open",
            "workspace_id": WS,
            "department_id": "dept_prod",
            "reference": "WO-MINE",
            "assigned_user_ids": ["u_mem"],
            "status": "in_production",
            "due_date": tomorrow,
        },
        {
            "id": "pwo_mine_done",
            "workspace_id": WS,
            "department_id": "dept_prod",
            "reference": "WO-DONE",
            "assigned_user_ids": ["u_mem"],
            "status": "completed",
            "due_date": yesterday,
        },
        {
            "id": "pwo_ceo_only",
            "workspace_id": WS,
            "department_id": "dept_prod",
            "reference": "WO-CEO",
            "assigned_user_ids": ["u_ceo"],
            "status": "quality_check",
            "due_date": next_week,
        },
    ])

    # Hypothetically assigned to member in a dept they cannot access.
    legal = DocStore([
        {
            "id": "lmat_leak",
            "workspace_id": WS,
            "department_id": "dept_legal",
            "title": "Secret matter",
            "assigned_to": "u_mem",
            "status": "draft",
            "due_date": tomorrow,
        },
        {
            "id": "lmat_ceo",
            "workspace_id": WS,
            "department_id": "dept_legal",
            "title": "CEO matter",
            "assigned_to": "u_ceo",
            "status": "draft",
            "due_date": yesterday,
        },
    ])

    procurement = DocStore([
        {
            "id": "preq_mem",
            "workspace_id": WS,
            "department_id": "dept_proc",
            "item": "Bolts",
            "requested_by": "u_mem",
            "status": "requested",
            "expected_delivery_date": next_week,
        },
        {
            "id": "preq_ceo",
            "workspace_id": WS,
            "department_id": "dept_proc",
            "item": "Steel",
            "requested_by": "u_ceo",
            "status": "ordered",
            "expected_delivery_date": yesterday,
        },
    ])

    deals = DocStore([
        {
            "id": "deal_ceo",
            "workspace_id": WS,
            "department_id": "dept_sales",
            "name": "Acme deal",
            "owner_user_id": "u_ceo",
            "stage": "proposal",
            "next_step_date": tomorrow,
        },
    ])

    maintenance = DocStore([])
    hr_onb = DocStore([])
    hr_off = DocStore([])

    mock_db = MagicMock()
    mock_db.workspaces.find_one = AsyncMock(return_value={"timezone": "Asia/Manila"})
    mock_db.departments = departments
    mock_db.department_members = members
    mock_db.production_work_orders = production
    mock_db.legal_matters = legal
    mock_db.procurement_requests = procurement
    mock_db.deals = deals
    mock_db.maintenance_tickets = maintenance
    mock_db.hr_onboarding_instances = hr_onb
    mock_db.hr_offboarding_instances = hr_off

    principal = {"current": MEMBER}

    def as_principal():
        return principal["current"]

    server.app.dependency_overrides[server.get_principal] = as_principal

    with patch.object(server, "db", mock_db), patch.object(server, "BILLING_ENFORCED", False):
        client = TestClient(server.app)
        yield {
            "client": client,
            "principal": principal,
            "members": members,
            "yesterday": yesterday,
            "tomorrow": tomorrow,
            "next_week": next_week,
        }

    server.app.dependency_overrides.clear()


def test_accessible_assigned_item_appears(work_api):
    r = work_api["client"].get("/api/me/work-items")
    assert r.status_code == 200
    items = r.json()["items"]
    ids = [i["id"] for i in items]
    assert "pwo_mine_open" in ids
    assert "pwo_mine_done" not in ids
    mine = next(i for i in items if i["id"] == "pwo_mine_open")
    assert mine["department_type"] == "production"
    assert mine["relationship"] == "assigned_to_me"
    assert mine["url"] == "/app/departments/production"
    assert mine["due_date"] == work_api["tomorrow"]
    assert mine["overdue"] is False


def test_inaccessible_department_assignment_hidden(work_api):
    """Member is assigned on a Legal matter but is not a Legal member — must not appear."""
    r = work_api["client"].get("/api/me/work-items")
    assert r.status_code == 200
    ids = [i["id"] for i in r.json()["items"]]
    assert "lmat_leak" not in ids
    assert "preq_mem" not in ids  # not a procurement member either
    assert "deal_ceo" not in ids


def test_procurement_requested_by_me_label(work_api):
    work_api["members"].rows.append(
        {"department_id": "dept_proc", "user_id": "u_mem", "role": "member"},
    )
    r = work_api["client"].get("/api/me/work-items")
    assert r.status_code == 200
    items = r.json()["items"]
    proc = next(i for i in items if i["id"] == "preq_mem")
    assert proc["relationship"] == "requested_by_me"
    assert proc["department_type"] == "procurement"
    assert proc["title"] == "Bolts"
    assert "pwo_mine_open" in [i["id"] for i in items]


def test_ceo_sees_only_own_assignments_not_company_wide(work_api):
    work_api["principal"]["current"] = CEO
    r = work_api["client"].get("/api/me/work-items")
    assert r.status_code == 200
    ids = [i["id"] for i in r.json()["items"]]
    assert "pwo_ceo_only" in ids
    assert "lmat_ceo" in ids
    assert "preq_ceo" in ids
    assert "deal_ceo" in ids
    # Not the member's items
    assert "pwo_mine_open" not in ids
    assert "lmat_leak" not in ids
    assert "preq_mem" not in ids


def test_overdue_sort_and_flag(work_api):
    work_api["principal"]["current"] = CEO
    r = work_api["client"].get("/api/me/work-items")
    items = r.json()["items"]
    assert items, "expected CEO work items"
    # All overdue items must come before non-overdue dated items.
    seen_non_overdue = False
    for it in items:
        if it.get("overdue"):
            assert not seen_non_overdue
            assert it.get("due_date")
        elif it.get("due_date"):
            seen_non_overdue = True
    overdue = [i for i in items if i["overdue"]]
    assert any(i["id"] == "lmat_ceo" for i in overdue)
    assert any(i["id"] == "preq_ceo" for i in overdue)
    # Within overdue group, sooner due first
    overdue_dates = [i["due_date"] for i in overdue]
    assert overdue_dates == sorted(overdue_dates)
