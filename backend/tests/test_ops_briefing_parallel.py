"""Ops briefing sections must run concurrently and isolate per-section failures."""
from __future__ import annotations

import asyncio
import inspect
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import ops_briefing as ob
import departments_catalog as dept_catalog


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    async def to_list(self, _n):
        return list(self._rows)


@pytest.mark.asyncio
async def test_assemble_ops_runs_enabled_sections_concurrently():
    started = asyncio.Event()
    order: list[str] = []

    async def slow_proc(*_a, **_k):
        order.append("proc_start")
        started.set()
        await asyncio.sleep(0.04)
        order.append("proc_done")
        return {"enabled": True, "awaiting_approval_count": 0, "lead_time": {}, "spend": {}}

    async def slow_sales(*_a, **_k):
        await started.wait()
        order.append("sales_start")
        await asyncio.sleep(0.04)
        order.append("sales_done")
        return {
            "enabled": True,
            "month": "2026-09",
            "summary": {"confirmed_this_month": 0},
            "target_vs_actual": {},
        }

    depts = {
        dept_catalog.TYPE_PROCUREMENT: {"department_id": "d_proc"},
        dept_catalog.TYPE_SALES: {"department_id": "d_sales"},
    }
    fake_db = MagicMock()
    fake_db.workspaces.find_one = AsyncMock(return_value={"timezone": "UTC"})

    with (
        patch.object(ob.dept_migrate, "get_enabled_departments_by_type", AsyncMock(return_value=depts)),
        patch.object(ob, "_section_procurement", side_effect=slow_proc),
        patch.object(ob, "_section_sales", side_effect=slow_sales),
        patch.object(ob, "_section_production", AsyncMock(return_value=None)),
        patch.object(ob, "_section_maintenance", AsyncMock(return_value=None)),
        patch.object(ob.tz_utils, "workspace_today", return_value=date(2026, 9, 19)),
        patch.object(ob.sales_ob, "current_month", return_value="2026-09"),
    ):
        t0 = asyncio.get_event_loop().time()
        data = await ob.assemble_ops_briefing_data(fake_db, "ws_1")
        elapsed = asyncio.get_event_loop().time() - t0

    assert data["has_content"] is True
    assert data["sections"]["procurement"]["enabled"] is True
    assert data["sections"]["sales"]["enabled"] is True
    # Overlap: sales started before procurement finished.
    assert order.index("sales_start") < order.index("proc_done")
    assert elapsed < 0.075


@pytest.mark.asyncio
async def test_assemble_ops_reuses_workspace_skips_tz_read():
    fake_db = MagicMock()
    fake_db.workspaces.find_one = AsyncMock()

    with (
        patch.object(
            ob.dept_migrate,
            "get_enabled_departments_by_type",
            AsyncMock(return_value={}),
        ),
        patch.object(ob.tz_utils, "workspace_today", return_value=date(2026, 9, 19)),
        patch.object(ob.sales_ob, "current_month", return_value="2026-09"),
    ):
        data = await ob.assemble_ops_briefing_data(
            fake_db,
            "ws_1",
            workspace={"workspace_id": "ws_1", "timezone": "Asia/Manila"},
        )

    assert data["has_content"] is False
    fake_db.workspaces.find_one.assert_not_called()


@pytest.mark.asyncio
async def test_section_failure_isolates_to_none():
    """One section raising still returns others."""
    depts = {
        dept_catalog.TYPE_PROCUREMENT: {"department_id": "d_proc"},
        dept_catalog.TYPE_SALES: {"department_id": "d_sales"},
    }
    fake_db = MagicMock()
    # Procurement find blows up via the real section helper.
    bad = MagicMock()
    bad.find = MagicMock(side_effect=RuntimeError("db down"))
    fake_db.procurement_requests = bad
    fake_db.sales_order_book.find = MagicMock(return_value=_Cursor([]))
    fake_db.sales_targets.find_one = AsyncMock(return_value=None)
    fake_db.workspaces.find_one = AsyncMock(return_value={"timezone": "UTC"})

    with (
        patch.object(ob.dept_migrate, "get_enabled_departments_by_type", AsyncMock(return_value=depts)),
        patch.object(ob.tz_utils, "workspace_today", return_value=date(2026, 9, 19)),
        patch.object(ob.sales_ob, "current_month", return_value="2026-09"),
        patch.object(
            ob.sales_ob,
            "order_book_summary",
            return_value={"confirmed_this_month": 0, "line_count": 0},
        ),
        patch.object(
            ob.sales_ob,
            "target_vs_actual",
            return_value={"target_entered": False, "actual": 0},
        ),
    ):
        data = await ob.assemble_ops_briefing_data(fake_db, "ws_iso")

    assert data["sections"]["procurement"] is None
    assert data["sections"]["sales"] is not None
    assert data["has_content"] is True


def test_assemble_ops_source_uses_gather():
    src = inspect.getsource(ob.assemble_ops_briefing_data)
    assert "asyncio.gather" in src
    assert "_section_procurement" in src
    assert "_section_maintenance" in src


@pytest.mark.asyncio
async def test_maintenance_section_month_key_is_local_not_utc_instant():
    """Manila Oct 1 → UTC Sep 30; ledger month must stay 2026-10."""
    from datetime import datetime, timezone

    maint = {"department_id": "d_maint", "monthly_budget": None, "monthly_budget_entered": False}
    local_today = date(2026, 10, 1)
    # UTC bounds for Manila October start before UTC midnight Oct 1.
    month_start = datetime(2026, 9, 30, 16, 0, tzinfo=timezone.utc)
    month_end = datetime(2026, 10, 31, 16, 0, tzinfo=timezone.utc)

    cost_queries: list[dict] = []

    class _Find:
        def __init__(self, rows):
            self._rows = rows

        def find(self, query, *_a, **_k):
            if "month" in query:
                cost_queries.append(dict(query))
            return _Cursor(self._rows)

    fake_db = MagicMock()
    fake_db.maintenance_spares = _Find([])
    fake_db.maintenance_schedules = _Find([])
    fake_db.maintenance_contracts = _Find([])
    fake_db.maintenance_tickets = _Find([])
    fake_db.maintenance_costs = _Find([])

    with (
        patch.object(ob.tz_utils, "month_bounds_utc", return_value=(month_start, month_end)),
        patch.object(ob.sales_ob, "current_month", return_value="2026-10") as cm,
    ):
        out = await ob._section_maintenance(
            fake_db, "ws_1", maint, {"timezone": "Asia/Manila"}, local_today,
        )

    assert out is not None
    assert out["overhead"]["period"] == "2026-10"
    assert out["overhead"]["period_label"] == "October 2026"
    cm.assert_called_with(local_today)
    assert cost_queries and cost_queries[0].get("month") == "2026-10"
    # Regress: must not key costs off UTC strftime of month_start (2026-09).
    assert all(q.get("month") != "2026-09" for q in cost_queries)
