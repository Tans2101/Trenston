"""Department-scoped calendar read visibility (helm events + derived deadlines)."""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_calendar_visibility")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import department_access as dept_access  # noqa: E402
import server  # noqa: E402


CEO = {
    "user_id": "u_ceo",
    "email": "ceo@acme.com",
    "name": "CEO",
    "workspace_id": "ws_vis",
    "role": "owner",
    "pack": "owner",
}

FINANCE_MEMBER = {
    "user_id": "u_fin",
    "email": "fin@acme.com",
    "name": "Finance",
    "workspace_id": "ws_vis",
    "role": "member",
    "pack": "member",
}

PROC_MEMBER = {
    "user_id": "u_proc",
    "email": "proc@acme.com",
    "name": "Proc",
    "workspace_id": "ws_vis",
    "role": "member",
    "pack": "member",
}


def _match(doc: dict, query: dict) -> bool:
    if not query:
        return True
    for k, v in query.items():
        if k == "$or":
            if not any(_match(doc, clause) for clause in v):
                return False
            continue
        if isinstance(v, dict):
            if "$exists" in v:
                if v["$exists"] and k not in doc:
                    return False
                if (not v["$exists"]) and k in doc:
                    return False
            if "$nin" in v and doc.get(k) in v["$nin"]:
                return False
            if "$in" in v and doc.get(k) not in v["$in"]:
                return False
            continue
        if doc.get(k) != v:
            return False
    return True


class DocStore:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def find(self, query, projection=None):
        matched = [dict(r) for r in self.rows if _match(r, query or {})]

        class C:
            async def to_list(self, n):
                return matched[:n]

            def sort(self, *a, **k):
                return self

        return C()

    async def find_one(self, query, projection=None):
        for r in self.rows:
            if _match(r, query or {}):
                return dict(r)
        return None


@pytest.fixture
def vis_db():
    departments = DocStore([
        {
            "department_id": "dept_fin",
            "workspace_id": "ws_vis",
            "type": "accounting_finance",
            "name": "Finance",
            "enabled": True,
        },
        {
            "department_id": "dept_proc",
            "workspace_id": "ws_vis",
            "type": "procurement",
            "name": "Procurement",
            "enabled": True,
        },
    ])
    members = DocStore([
        {"department_id": "dept_fin", "user_id": "u_fin", "role": "member"},
        {"department_id": "dept_proc", "user_id": "u_proc", "role": "member"},
    ])
    procurement = DocStore([
        {
            "id": "preq_1",
            "workspace_id": "ws_vis",
            "department_id": "dept_proc",
            "item": "Steel plate",
            "expected_delivery_date": "2026-09-16",
            "status": "ordered",
        },
    ])
    mock_db = MagicMock()
    mock_db.departments = departments
    mock_db.department_members = members
    mock_db.procurement_requests = procurement
    mock_db.production_work_orders = DocStore()
    mock_db.legal_matters = DocStore()
    mock_db.hr_leave_requests = DocStore()
    return mock_db


def _ws_with_events(helm_events):
    return {
        "workspace_id": "ws_vis",
        "calendar": {"meetings": [], "helm_events": helm_events},
        "decisions": [],
        "tasks": {"items": []},
        "google_tokens": None,
    }


def _get_calendar(principal, mock_db, ws):
    async def as_principal():
        return principal

    server.simple_cache.clear()
    dept_access.clear_access_ids_cache()
    server.app.dependency_overrides[server.get_principal] = as_principal
    try:
        with patch.object(server, "db", mock_db), \
             patch.object(server, "get_ws", AsyncMock(return_value=ws)), \
             patch.object(server, "_google_calendar_snapshot", AsyncMock(return_value=None)), \
             patch.object(server, "_user_google_tokens_present", AsyncMock(return_value=False)), \
             patch.object(server, "_user_google_tokens", AsyncMock(return_value=None)), \
             patch.object(server, "can_section_write", AsyncMock(return_value=True)), \
             patch.object(server, "BILLING_ENFORCED", False):
            client = TestClient(server.app)
            return client.get("/api/calendar", params={"week_start": "2026-09-13"})
    finally:
        server.app.dependency_overrides.clear()
        dept_access.clear_access_ids_cache()
        server.simple_cache.clear()


def test_finance_event_visible_to_finance_and_ceo_only(vis_db):
    helm = [
        {
            "id": "helm_fin",
            "source": "helm",
            "created_by": "u_other",
            "visibility": "department",
            "department_id": "dept_fin",
            "department_name": "Finance",
            "title": "Close books",
            "date": "2026-09-16",
            "time": "10:00",
            "duration": 30,
            "all_day": False,
            "type": "Internal",
            "start_at": "2026-09-16T10:00:00+00:00",
            "end_at": "2026-09-16T10:30:00+00:00",
        },
        {
            "id": "helm_personal_other",
            "source": "helm",
            "created_by": "u_other",
            "visibility": "personal",
            "title": "Dentist",
            "date": "2026-09-16",
            "time": "14:00",
            "duration": 30,
            "all_day": False,
            "type": "Internal",
            "start_at": "2026-09-16T14:00:00+00:00",
            "end_at": "2026-09-16T14:30:00+00:00",
        },
    ]
    ws = _ws_with_events(helm)

    r_ceo = _get_calendar(CEO, vis_db, ws)
    assert r_ceo.status_code == 200, r_ceo.text
    ceo_ids = {e["id"] for e in r_ceo.json()["events"] if e.get("source") == "helm"}
    assert "helm_fin" in ceo_ids
    assert "helm_personal_other" not in ceo_ids

    r_fin = _get_calendar(FINANCE_MEMBER, vis_db, ws)
    assert r_fin.status_code == 200
    fin_ids = {e["id"] for e in r_fin.json()["events"] if e.get("source") == "helm"}
    assert "helm_fin" in fin_ids
    assert "helm_personal_other" not in fin_ids

    r_proc = _get_calendar(PROC_MEMBER, vis_db, ws)
    assert r_proc.status_code == 200
    proc_ids = {e["id"] for e in r_proc.json()["events"] if e.get("source") == "helm"}
    assert "helm_fin" not in proc_ids


def test_procurement_deadline_scoped_to_procurement_and_ceo(vis_db):
    ws = _ws_with_events([])

    r_ceo = _get_calendar(CEO, vis_db, ws)
    assert r_ceo.status_code == 200
    upcoming_ceo = {u["id"] for u in r_ceo.json()["upcoming"]}
    assert "preq_1" in upcoming_ceo

    r_proc = _get_calendar(PROC_MEMBER, vis_db, ws)
    assert "preq_1" in {u["id"] for u in r_proc.json()["upcoming"]}

    r_fin = _get_calendar(FINANCE_MEMBER, vis_db, ws)
    assert "preq_1" not in {u["id"] for u in r_fin.json()["upcoming"]}


def test_legacy_event_without_visibility_is_personal(vis_db):
    helm = [
        {
            "id": "helm_legacy",
            "source": "helm",
            "created_by": "u_fin",
            "department_ids": ["dept_fin"],
            "department_id": "dept_fin",
            "title": "Old stamp",
            "date": "2026-09-16",
            "time": "09:00",
            "duration": 30,
            "all_day": False,
            "type": "Internal",
            "start_at": "2026-09-16T09:00:00+00:00",
            "end_at": "2026-09-16T09:30:00+00:00",
        },
    ]
    ws = _ws_with_events(helm)

    r_fin = _get_calendar(FINANCE_MEMBER, vis_db, ws)
    fin_ids = {e["id"] for e in r_fin.json()["events"] if e.get("source") == "helm"}
    assert "helm_legacy" in fin_ids

    r_ceo = _get_calendar(CEO, vis_db, ws)
    ceo_ids = {e["id"] for e in r_ceo.json()["events"] if e.get("source") == "helm"}
    assert "helm_legacy" not in ceo_ids

    r_proc = _get_calendar(PROC_MEMBER, vis_db, ws)
    proc_ids = {e["id"] for e in r_proc.json()["events"] if e.get("source") == "helm"}
    assert "helm_legacy" not in proc_ids


def test_member_two_departments_sees_both(vis_db):
    vis_db.department_members.rows.append(
        {"department_id": "dept_proc", "user_id": "u_fin", "role": "member"},
    )
    helm = [
        {
            "id": "helm_fin",
            "source": "helm",
            "created_by": "u_other",
            "visibility": "department",
            "department_id": "dept_fin",
            "title": "Finance sync",
            "date": "2026-09-16",
            "time": "10:00",
            "duration": 30,
            "all_day": False,
            "type": "Internal",
            "start_at": "2026-09-16T10:00:00+00:00",
            "end_at": "2026-09-16T10:30:00+00:00",
        },
        {
            "id": "helm_proc",
            "source": "helm",
            "created_by": "u_other",
            "visibility": "department",
            "department_id": "dept_proc",
            "title": "Vendor call",
            "date": "2026-09-16",
            "time": "11:00",
            "duration": 30,
            "all_day": False,
            "type": "Internal",
            "start_at": "2026-09-16T11:00:00+00:00",
            "end_at": "2026-09-16T11:30:00+00:00",
        },
    ]
    ws = _ws_with_events(helm)
    r = _get_calendar(FINANCE_MEMBER, vis_db, ws)
    ids = {e["id"] for e in r.json()["events"] if e.get("source") == "helm"}
    assert ids == {"helm_fin", "helm_proc"}
    assert "preq_1" in {u["id"] for u in r.json()["upcoming"]}
