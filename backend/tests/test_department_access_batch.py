"""Batched department membership lookup matches per-type results."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_dept_access_batch")

import department_access as access  # noqa: E402
import departments_catalog as catalog  # noqa: E402


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _n):
        return list(self.rows)


class _Coll:
    def __init__(self, rows):
        self.rows = list(rows)

    def find(self, query, projection=None):
        matched = []
        for row in self.rows:
            ok = True
            for k, v in query.items():
                if isinstance(v, dict) and "$in" in v:
                    if row.get(k) not in v["$in"]:
                        ok = False
                        break
                elif row.get(k) != v:
                    ok = False
                    break
            if ok:
                matched.append(dict(row))
        return _Cursor(matched)


@pytest.fixture(autouse=True)
def _clear_memo():
    access.clear_access_ids_cache()
    yield
    access.clear_access_ids_cache()


def _mock_db(departments, members):
    db = MagicMock()
    db.departments = _Coll(departments)
    db.department_members = _Coll(members)
    return db


@pytest.mark.asyncio
async def test_batched_accessible_ids_match_per_type_for_member():
    types = (
        catalog.TYPE_SALES,
        catalog.TYPE_HR,
        catalog.TYPE_PRODUCTION,
        catalog.TYPE_PROCUREMENT,
        catalog.TYPE_LEGAL,
        catalog.TYPE_ENGINEERING_MAINTENANCE,
    )
    departments = [
        {"department_id": "d_sales", "workspace_id": "ws1", "type": catalog.TYPE_SALES, "enabled": True},
        {"department_id": "d_hr", "workspace_id": "ws1", "type": catalog.TYPE_HR, "enabled": True},
        {"department_id": "d_prod", "workspace_id": "ws1", "type": catalog.TYPE_PRODUCTION, "enabled": True},
        {"department_id": "d_legal", "workspace_id": "ws1", "type": catalog.TYPE_LEGAL, "enabled": True},
        # procurement enabled but user not a member
        {"department_id": "d_proc", "workspace_id": "ws1", "type": catalog.TYPE_PROCUREMENT, "enabled": True},
        # maintenance not enabled
        {"department_id": "d_maint", "workspace_id": "ws1", "type": catalog.TYPE_ENGINEERING_MAINTENANCE, "enabled": False},
    ]
    members = [
        {"department_id": "d_sales", "user_id": "u1"},
        {"department_id": "d_hr", "user_id": "u1"},
        {"department_id": "d_prod", "user_id": "u1"},
        {"department_id": "d_legal", "user_id": "u1"},
    ]
    db = _mock_db(departments, members)
    principal = {
        "user_id": "u1",
        "workspace_id": "ws1",
        "pack": "member",
        "role": "member",
    }

    access.clear_access_ids_cache()
    per_type = {
        t: await access.accessible_department_ids(db, principal, t) for t in types
    }
    access.clear_access_ids_cache()
    batched = await access.accessible_department_ids_by_type(db, principal, types)
    assert batched == per_type
    assert batched[catalog.TYPE_SALES] == ["d_sales"]
    assert batched[catalog.TYPE_PROCUREMENT] == []
    assert batched[catalog.TYPE_ENGINEERING_MAINTENANCE] == []


@pytest.mark.asyncio
async def test_batched_accessible_ids_ceo_bypass_is_none():
    types = (catalog.TYPE_SALES, catalog.TYPE_PRODUCTION)
    db = _mock_db(
        [{"department_id": "d_sales", "workspace_id": "ws1", "type": catalog.TYPE_SALES, "enabled": True}],
        [],
    )
    principal = {"user_id": "ceo", "workspace_id": "ws1", "pack": "owner", "role": "owner"}
    batched = await access.accessible_department_ids_by_type(db, principal, types)
    assert batched[catalog.TYPE_SALES] is None
    assert batched[catalog.TYPE_PRODUCTION] is None
    # Memoized: single-type call must not re-query
    db.departments.find = MagicMock(side_effect=AssertionError("should use memo"))
    assert await access.accessible_department_ids(db, principal, catalog.TYPE_SALES) is None


@pytest.mark.asyncio
async def test_accessible_department_ids_memoizes_within_request():
    db = _mock_db(
        [{"department_id": "d1", "workspace_id": "ws1", "type": catalog.TYPE_SALES, "enabled": True}],
        [{"department_id": "d1", "user_id": "u1"}],
    )
    principal = {"user_id": "u1", "workspace_id": "ws1", "pack": "member", "role": "member"}
    first = await access.accessible_department_ids(db, principal, catalog.TYPE_SALES)
    # Break find so a second query would fail
    db.departments.find = MagicMock(side_effect=AssertionError("memo miss"))
    second = await access.accessible_department_ids(db, principal, catalog.TYPE_SALES)
    assert first == second == ["d1"]


@pytest.mark.asyncio
async def test_can_access_department_rejects_foreign_workspace():
    """CEO/exec/pack must not short-circuit past a mismatched workspace_id."""
    db = _mock_db([], [])
    foreign = {
        "department_id": "d_other",
        "workspace_id": "ws_other",
        "type": catalog.TYPE_HR,
        "enabled": True,
    }
    ceo = {"user_id": "ceo", "workspace_id": "ws1", "pack": "owner", "role": "owner"}
    hr_pack = {"user_id": "hr", "workspace_id": "ws1", "pack": "hr", "role": "member"}
    assert await access.can_access_department(db, ceo, foreign) is False
    assert await access.can_access_department(db, hr_pack, foreign) is False
    same = {**foreign, "workspace_id": "ws1"}
    assert await access.can_access_department(db, ceo, same) is True
    assert await access.can_access_department(db, hr_pack, same) is True
