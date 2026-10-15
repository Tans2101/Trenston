"""How each access pack sees Trenston: Executive reads everything but edits less,
People / HR leads the HR department, and no money figure reaches anyone who
can't open Financials."""
import asyncio
import os
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DB_NAME", "test_database")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

import departments_catalog as dept_catalog
import department_access as dept_access
import server


def run(coro):
    return asyncio.run(coro)


class _Coll:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.calls = 0

    async def find_one(self, flt, _proj=None):
        self.calls += 1
        for row in self.rows:
            if all(row.get(k) == v for k, v in flt.items()):
                return dict(row)
        return None


class _Db:
    def __init__(self, departments=(), members=()):
        self.departments = _Coll(departments)
        self.department_members = _Coll(members)


HR = {"department_id": "dept_hr", "workspace_id": "ws1", "type": dept_catalog.TYPE_HR}
LEGAL = {"department_id": "dept_legal", "workspace_id": "ws1", "type": dept_catalog.TYPE_LEGAL}


def principal(pack, uid="u1", role="member"):
    return {"user_id": uid, "workspace_id": "ws1", "pack": pack, "role": role}


def setup_function(_fn):
    dept_access.clear_access_ids_cache()
    dept_access.set_current_principal(None)


def teardown_function(_fn):
    # The current-person marker is process-wide in tests; never leak it.
    dept_access.clear_access_ids_cache()
    dept_access.set_current_principal(None)


# ---------------- Departments ----------------

def test_owner_and_executive_read_every_department():
    db = _Db()
    for p in (principal("owner", role="owner"), principal("exec")):
        assert dept_access.can_read_all_departments(p)
        assert run(dept_access.can_access_department(db, p, LEGAL))
        assert run(dept_access.accessible_department_ids(db, p, dept_catalog.TYPE_LEGAL)) is None
    assert not dept_access.can_read_all_departments(principal("member"))
    assert not run(dept_access.can_access_department(db, principal("member"), LEGAL))


def test_executive_is_not_a_department_lead():
    db = _Db(departments=[LEGAL])
    exec_p = principal("exec")
    dept_access.set_current_principal(exec_p)
    assert run(dept_access.get_department_membership(db, "dept_legal", "u1")) is None
    assert not run(dept_access.can_manage_department_members(db, exec_p, "dept_legal"))


def test_people_hr_pack_leads_the_hr_department_only():
    db = _Db(departments=[HR, LEGAL])
    hr_p = principal("hr")
    dept_access.set_current_principal(hr_p)
    assert run(dept_access.can_access_department(db, hr_p, HR))
    row = run(dept_access.get_department_membership(db, "dept_hr", "u1"))
    assert row["role"] == "lead" and row["implied_by_pack"] == "hr"
    assert run(dept_access.can_manage_department_members(db, hr_p, "dept_hr"))
    # Not Legal, and not someone else's membership.
    assert not run(dept_access.can_access_department(db, hr_p, LEGAL))
    assert run(dept_access.get_department_membership(db, "dept_legal", "u1")) is None
    assert run(dept_access.get_department_membership(db, "dept_hr", "someone_else")) is None


def test_hr_pack_role_never_crosses_workspaces():
    other = {**HR, "workspace_id": "ws_other"}
    db = _Db(departments=[other])
    dept_access.set_current_principal(principal("hr"))
    assert run(dept_access.get_department_membership(db, "dept_hr", "u1")) is None


def test_plain_members_cost_no_extra_queries():
    db = _Db(departments=[HR], members=[{"department_id": "dept_hr", "user_id": "u1", "role": "member"}])
    dept_access.set_current_principal(principal("member"))
    row = run(dept_access.get_department_membership(db, "dept_hr", "u1"))
    assert row["role"] == "member"
    assert db.departments.calls == 0


# ---------------- Money ----------------

def test_executive_views_financials_but_cannot_edit_them():
    exec_p = principal("exec")
    assert run(server.can_access_financials(exec_p, membership={}, workspace={}))
    assert not run(server.can_edit_financials(exec_p, membership={}, workspace={}))
    fin_p = principal("finance")
    assert run(server.can_access_financials(fin_p, membership={}, workspace={}))
    assert run(server.can_edit_financials(fin_p, membership={}, workspace={}))
    for pack in ("member", "ops", "hr", "sales"):
        assert not run(server.can_access_financials(principal(pack), membership={}, workspace={}))


def test_financial_reads_use_view_gate_and_writes_use_edit_gate():
    routes = {(r.path, tuple(sorted(r.methods))): r for r in server.app.routes if hasattr(r, "methods")}

    def deps(path, method):
        route = routes[(path, (method,))]
        return {getattr(d.call, "__name__", "") for d in route.dependant.dependencies}

    for path in ("/api/financials", "/api/reports/financial-export"):
        assert "require_financials_view" in deps(path, "GET")
    for path in ("/api/reports/financial-export/pdf", "/api/reports/financial-export/xlsx"):
        assert "require_financials_view" in deps(path, "POST")
    for path in ("/api/financials/entries",):
        assert "require_financials_view" not in deps(path, "POST")


def test_scope_ops_metrics_hides_departments_you_are_not_in():
    cards = [
        {"label": "Procurement spend", "section": "procurement"},
        {"label": "Maint overhead", "section": "maintenance"},
        {"label": "Sales confirmed", "section": "sales"},
        {"label": "Unsectioned", "section": None},
    ]
    access = {
        dept_catalog.TYPE_PROCUREMENT: ["dept_p"],
        dept_catalog.TYPE_ENGINEERING_MAINTENANCE: [],
        dept_catalog.TYPE_SALES: ["dept_s"],
        dept_catalog.TYPE_PRODUCTION: [],
    }
    with patch.object(server.dept_access, "accessible_department_ids_by_type", new=AsyncMock(return_value=access)):
        shown = run(server._scope_ops_metrics(principal("member"), cards))
    assert [c["label"] for c in shown] == ["Procurement spend", "Sales confirmed", "Unsectioned"]
    # Owner and Executives see every card.
    assert len(run(server._scope_ops_metrics(principal("exec"), cards))) == 4
