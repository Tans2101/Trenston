"""Ask Trenston context respects department membership for every department type."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_ask_department_scope")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import departments_catalog as dept_catalog  # noqa: E402
import server
from tests.mongo_mocks import FakeCollection  # noqa: E402
from server import ask_context_for_synthesis  # noqa: E402


def _company():
    return {
        "name": "Acme",
        "stage": "Seed",
        "employees": 2,
        "people": {"people": [{"id": "p1"}]},
        "decisions": [{"title": "Hire", "status": "pending"}],
        "telemetry_manual": {"risks": []},
        "workspace_id": "ws_ask",
        "plan": "starter",
    }


def _deals():
    return [
        {"id": "d1", "stage": "negotiation", "value": 50000, "title": "Big Deal"},
        {"id": "d2", "stage": "won", "value": 10000, "title": "Won Deal"},
    ]


def _onboarding():
    return [
        {"id": "o1", "hire_name": "Alex", "overall_status": "in_progress"},
    ]


def _production():
    return [
        {"id": "wo1", "status": "in_production", "title": "Secret WO"},
        {"id": "wo2", "status": "completed", "title": "Done WO"},
    ]


def _procurement():
    return [
        {"id": "pr1", "status": "requested", "item": "Secret Parts"},
        {"id": "pr2", "status": "delivered", "item": "Arrived"},
    ]


def _legal():
    return [
        {"id": "lm1", "status": "draft", "title": "Secret Contract"},
        {"id": "lm2", "status": "signed", "title": "Done Contract"},
    ]


def _maintenance():
    return [
        {"id": "mt1", "status": "reported", "equipment_name": "Secret Press"},
        {"id": "mt2", "status": "resolved", "equipment_name": "Fixed Press"},
    ]


def test_ask_context_restricts_all_departments_when_not_visible():
    ctx = ask_context_for_synthesis(
        _company(),
        {},
        deals=_deals(),
        sales_tracked=True,
        onboarding_instances=_onboarding(),
        hr_tracked=True,
        financials_visible=False,
        sales_visible=False,
        hr_visible=False,
        sales_enabled=True,
        hr_enabled=True,
        production_rows=_production(),
        production_enabled=True,
        production_visible=False,
        procurement_rows=_procurement(),
        procurement_enabled=True,
        procurement_visible=False,
        legal_rows=_legal(),
        legal_enabled=True,
        legal_visible=False,
        maintenance_rows=_maintenance(),
        maintenance_enabled=True,
        maintenance_visible=False,
    )
    assert ctx["pipeline"]["access"] == "restricted"
    assert "50000" not in str(ctx["pipeline"])
    assert "Big Deal" not in str(ctx["pipeline"])
    assert ctx["onboarding"]["access"] == "restricted"
    assert "Alex" not in str(ctx["onboarding"])
    assert ctx["production"]["access"] == "restricted"
    assert "Secret WO" not in str(ctx["production"])
    assert ctx["procurement"]["access"] == "restricted"
    assert "Secret Parts" not in str(ctx["procurement"])
    assert ctx["legal"]["access"] == "restricted"
    assert "Secret Contract" not in str(ctx["legal"])
    assert ctx["maintenance"]["access"] == "restricted"
    assert "Secret Press" not in str(ctx["maintenance"])
    assert ctx["financials"]["access"] == "restricted"


def test_ask_context_includes_departments_when_visible():
    ctx = ask_context_for_synthesis(
        _company(),
        {},
        deals=_deals(),
        sales_tracked=True,
        onboarding_instances=_onboarding(),
        hr_tracked=True,
        financials_visible=False,
        sales_visible=True,
        hr_visible=True,
        sales_enabled=True,
        hr_enabled=True,
        production_rows=_production(),
        production_enabled=True,
        production_visible=True,
        procurement_rows=_procurement(),
        procurement_enabled=True,
        procurement_visible=True,
        legal_rows=_legal(),
        legal_enabled=True,
        legal_visible=True,
        maintenance_rows=_maintenance(),
        maintenance_enabled=True,
        maintenance_visible=True,
    )
    assert ctx["pipeline"].get("access") != "restricted"
    assert ctx["pipeline"]["tracked"] is True
    assert ctx["pipeline"]["deal_count"] >= 1
    assert ctx["onboarding"].get("access") != "restricted"
    assert ctx["onboarding"]["instance_count"] == 1
    assert ctx["production"].get("access") != "restricted"
    assert ctx["production"]["open_count"] == 1
    assert ctx["production"]["by_status"]["in_production"] == 1
    assert "possibly_stale_count" in ctx["production"]
    assert ctx["procurement"]["open_count"] == 1
    assert ctx["legal"]["open_count"] == 1
    assert ctx["maintenance"]["open_count"] == 1
    # Aggregate only — raw titles/items are not copied into the snapshot.
    assert "Secret WO" not in str(ctx["production"])
    assert "Secret Parts" not in str(ctx["procurement"])



def test_ask_context_disabled_department_is_not_tracked_not_restricted():
    ctx = ask_context_for_synthesis(
        _company(),
        {},
        financials_visible=False,
        sales_enabled=False,
        sales_visible=False,
        hr_enabled=False,
        hr_visible=False,
        production_enabled=False,
        production_visible=False,
        procurement_enabled=False,
        procurement_visible=False,
        legal_enabled=False,
        legal_visible=False,
        maintenance_enabled=False,
        maintenance_visible=False,
    )
    assert ctx["pipeline"].get("tracked") is False
    assert ctx["pipeline"].get("access") != "restricted"
    assert ctx["production"].get("tracked") is False
    assert ctx["production"].get("access") != "restricted"
    assert ctx["legal"].get("tracked") is False


def _mock_coll(rows):
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=rows)
    find = MagicMock(return_value=cursor)
    return find, cursor


_ASK_TYPES = (
    dept_catalog.TYPE_SALES,
    dept_catalog.TYPE_HR,
    dept_catalog.TYPE_PRODUCTION,
    dept_catalog.TYPE_PROCUREMENT,
    dept_catalog.TYPE_LEGAL,
    dept_catalog.TYPE_ENGINEERING_MAINTENANCE,
)


def _enabled_by_type(types=_ASK_TYPES):
    return {t: {"department_id": f"dept_{t}", "type": t, "enabled": True} for t in types}


def _access_by_type(member_types=(), *, ceo=False, types=_ASK_TYPES):
    if ceo:
        return {t: None for t in types}
    return {t: ([f"dept_{t}"] if t in member_types else []) for t in types}



def _system_text(system) -> str:
    """Flatten ask_helm system prompt (str or Anthropic content-block list) for assertions."""
    if isinstance(system, list):
        parts = []
        for block in system:
            if isinstance(block, dict):
                parts.append(block.get("text") or "")
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return system or ""


def _ask_period():
    return {
        "key": "2026-09-01",
        "start": __import__("datetime").datetime(2026, 9, 1, tzinfo=__import__("datetime").timezone.utc),
        "end": __import__("datetime").datetime(2026, 10, 1, tzinfo=__import__("datetime").timezone.utc),
    }


@pytest.mark.asyncio
async def test_ask_helm_scopes_each_department_by_membership():
    """Sales member: sales data in prompt; every other dept restricted; no raw foreign rows."""
    principal = {
        "user_id": "u_sales",
        "workspace_id": "ws_ask",
        "pack": "member",
        "role": "member",
        "email": "sales@example.com",
        "name": "Sales",
    }
    ws = _company()
    mock_db = MagicMock()
    mock_db.chat_messages.insert_one = AsyncMock(return_value=None)
    mock_db.chat_messages.find = FakeCollection().find

    deals_find, _ = _mock_coll([
        {"id": "d1", "stage": "negotiation", "value": 12000, "department_id": "dept_sales"},
    ])
    mock_db.deals.find = deals_find
    for attr, rows in (
        ("hr_onboarding_instances", []),
        ("production_work_orders", [{"id": "wo1", "status": "in_production", "title": "LEAK"}]),
        ("procurement_requests", [{"id": "pr1", "status": "requested", "item": "LEAK"}]),
        ("legal_matters", [{"id": "lm1", "status": "draft", "title": "LEAK"}]),
        ("maintenance_tickets", [{"id": "mt1", "status": "reported", "equipment_name": "LEAK"}]),
    ):
        find, _ = _mock_coll(rows)
        setattr(mock_db, attr, MagicMock(find=find))

    captured = {}

    async def _capture_stream(system, message=None, **kwargs):
        captured["system"] = _system_text(system)
        captured["max_tokens"] = kwargs.get("max_tokens")
        yield "ok"

    async def _slice(principal, dept_type, collection_attr, *, enabled_dept=None, access_ids=None):
        # Replicate membership: only Sales visible.
        if dept_type == dept_catalog.TYPE_SALES:
            return (
                [{"id": "d1", "stage": "negotiation", "value": 12000, "department_id": "dept_sales"}],
                True,
                True,
            )
        return [], True, False

    with patch.object(server, "get_ws", new=AsyncMock(return_value=ws)), \
            patch.object(server, "can_access_financials", new=AsyncMock(return_value=False)), \
            patch.object(server, "db", mock_db), \
            patch.object(server, "_product_event", new=AsyncMock()), \
            patch.object(server.helm_llm, "anthropic_configured", return_value=True), \
            patch.object(server.helm_llm, "stream_text", side_effect=_capture_stream), \
            patch.object(server.plan_usage, "acquire_period_ask_slot", new=AsyncMock(return_value=True)), \
            patch.object(server.plan_usage, "current_usage_period", return_value=_ask_period()), \
            patch.object(server, "BILLING_ENFORCED", False), \
            patch.object(
                server.dept_access, "accessible_department_ids_by_type",
                new=AsyncMock(return_value=_access_by_type({dept_catalog.TYPE_SALES})),
            ), \
            patch.object(
                server.dept_migrate, "get_enabled_departments_by_type",
                new=AsyncMock(return_value=_enabled_by_type()),
            ), \
            patch.object(server, "_ask_helm_department_slice", new=AsyncMock(side_effect=_slice)):
        resp = await server.ask_helm(
            server.AskInput(message="How is the pipeline looking?"),
            principal,
        )
        chunks = []
        async for chunk in resp.body_iterator:
            chunks.append(chunk if isinstance(chunk, str) else chunk.decode())

    assert "".join(chunks) == "ok"
    system = captured["system"]
    assert "12000" in system or "deal_count" in system
    assert "HR onboarding data is not shared" in system
    assert "Production data is not shared" in system
    assert "Procurement data is not shared" in system
    assert "Legal data is not shared" in system
    assert "Engineering & Maintenance data is not shared" in system
    assert "LEAK" not in system
    assert "Financial figures are not shared" in system


@pytest.mark.asyncio
async def test_ask_helm_member_of_production_gets_production_counts():
    principal = {
        "user_id": "u_prod",
        "workspace_id": "ws_ask",
        "pack": "member",
        "role": "member",
        "email": "prod@example.com",
        "name": "Prod",
    }
    ws = _company()
    mock_db = MagicMock()
    mock_db.chat_messages.insert_one = AsyncMock(return_value=None)
    mock_db.chat_messages.find = FakeCollection().find
    captured = {}

    async def _capture_stream(system, message=None, **kwargs):
        captured["system"] = _system_text(system)
        captured["max_tokens"] = kwargs.get("max_tokens")
        yield "prod-ok"

    async def _slice(principal, dept_type, collection_attr, *, enabled_dept=None, access_ids=None):
        if dept_type == dept_catalog.TYPE_PRODUCTION:
            return _production(), True, True
        return [], True, False

    with patch.object(server, "get_ws", new=AsyncMock(return_value=ws)), \
            patch.object(server, "can_access_financials", new=AsyncMock(return_value=False)), \
            patch.object(server, "db", mock_db), \
            patch.object(server, "_product_event", new=AsyncMock()), \
            patch.object(server.helm_llm, "anthropic_configured", return_value=True), \
            patch.object(server.helm_llm, "stream_text", side_effect=_capture_stream), \
            patch.object(server.plan_usage, "acquire_period_ask_slot", new=AsyncMock(return_value=True)), \
            patch.object(server.plan_usage, "current_usage_period", return_value=_ask_period()), \
            patch.object(server, "BILLING_ENFORCED", False), \
            patch.object(
                server.dept_access, "accessible_department_ids_by_type",
                new=AsyncMock(return_value=_access_by_type({dept_catalog.TYPE_PRODUCTION})),
            ), \
            patch.object(
                server.dept_migrate, "get_enabled_departments_by_type",
                new=AsyncMock(return_value=_enabled_by_type()),
            ), \
            patch.object(server, "_ask_helm_department_slice", new=AsyncMock(side_effect=_slice)):
        resp = await server.ask_helm(
            server.AskInput(message="How many open work orders?"),
            principal,
        )
        async for _ in resp.body_iterator:
            pass

    system = captured["system"]
    assert '"open_count":1' in system or '"open_count": 1' in system
    assert "Production data is not shared" not in system
    assert "Sales pipeline is not shared" in system
    assert "Secret WO" not in system


@pytest.mark.asyncio
async def test_ask_helm_ceo_sees_all_department_slices_unfiltered():
    principal = {
        "user_id": "u_ceo",
        "workspace_id": "ws_ask",
        "pack": "owner",
        "role": "owner",
        "email": "ceo@example.com",
        "name": "CEO",
    }
    ws = _company()
    mock_db = MagicMock()
    mock_db.chat_messages.insert_one = AsyncMock(return_value=None)
    mock_db.chat_messages.find = FakeCollection().find

    slice_calls = []

    async def _slice(principal, dept_type, collection_attr, *, enabled_dept=None, access_ids=None):
        slice_calls.append(dept_type)
        if dept_type == dept_catalog.TYPE_SALES:
            return _deals(), True, True
        if dept_type == dept_catalog.TYPE_HR:
            return _onboarding(), True, True
        if dept_type == dept_catalog.TYPE_PRODUCTION:
            return _production(), True, True
        if dept_type == dept_catalog.TYPE_PROCUREMENT:
            return _procurement(), True, True
        if dept_type == dept_catalog.TYPE_LEGAL:
            return _legal(), True, True
        if dept_type == dept_catalog.TYPE_ENGINEERING_MAINTENANCE:
            return _maintenance(), True, True
        return [], False, False

    captured = {}

    async def _capture_stream(system, message=None, **kwargs):
        captured["system"] = _system_text(system)
        captured["max_tokens"] = kwargs.get("max_tokens")
        yield "ceo-ok"

    with patch.object(server, "get_ws", new=AsyncMock(return_value=ws)), \
            patch.object(server, "can_access_financials", new=AsyncMock(return_value=True)), \
            patch.object(server, "compute_financials", new=AsyncMock(return_value={
                "mrr_value": 1, "burn_value": 1, "cash_entered": False,
                "mrr_known": False, "burn_known": False, "currency": "usd",
            })), \
            patch.object(server, "db", mock_db), \
            patch.object(server, "_product_event", new=AsyncMock()), \
            patch.object(server.helm_llm, "anthropic_configured", return_value=True), \
            patch.object(server.helm_llm, "stream_text", side_effect=_capture_stream), \
            patch.object(server.plan_usage, "acquire_period_ask_slot", new=AsyncMock(return_value=True)), \
            patch.object(server.plan_usage, "current_usage_period", return_value=_ask_period()), \
            patch.object(server, "BILLING_ENFORCED", False), \
            patch.object(
                server.dept_access, "accessible_department_ids_by_type",
                new=AsyncMock(return_value=_access_by_type(ceo=True)),
            ), \
            patch.object(
                server.dept_migrate, "get_enabled_departments_by_type",
                new=AsyncMock(return_value=_enabled_by_type()),
            ), \
            patch.object(server, "_ask_helm_department_slice", new=AsyncMock(side_effect=_slice)):
        resp = await server.ask_helm(
            server.AskInput(message="Give me a company pulse"),
            principal,
        )
        async for _ in resp.body_iterator:
            pass

    system = captured["system"]
    for phrase in (
        "Sales pipeline is not shared",
        "HR onboarding data is not shared",
        "Production data is not shared",
        "Procurement data is not shared",
        "Legal data is not shared",
        "Engineering & Maintenance data is not shared",
        "Financial figures are not shared",
    ):
        assert phrase not in system
    assert dept_catalog.TYPE_SALES in slice_calls
    assert dept_catalog.TYPE_PRODUCTION in slice_calls
    assert dept_catalog.TYPE_LEGAL in slice_calls
    assert dept_catalog.TYPE_ENGINEERING_MAINTENANCE in slice_calls
    assert '"open_count":1' in system or '"open_count": 1' in system


@pytest.mark.asyncio
async def test_ask_helm_department_slice_uses_accessible_department_ids():
    """Integration with real helper: non-member gets no rows; filter applied for member."""
    principal = {
        "user_id": "u1",
        "workspace_id": "ws_ask",
        "pack": "member",
        "role": "member",
    }
    mock_db = MagicMock()
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[{"id": "wo1", "status": "in_production"}])
    mock_db.production_work_orders.find = MagicMock(return_value=cursor)

    with patch.object(server, "db", mock_db), \
            patch.object(server.dept_migrate, "get_enabled_department", new=AsyncMock(return_value={
                "department_id": "dept_prod", "type": dept_catalog.TYPE_PRODUCTION,
            })), \
            patch.object(server.dept_access, "accessible_department_ids", new=AsyncMock(return_value=["dept_prod"])):
        rows, enabled, visible = await server._ask_helm_department_slice(
            principal, dept_catalog.TYPE_PRODUCTION, "production_work_orders",
        )
    assert enabled and visible
    assert rows[0]["id"] == "wo1"
    filt = mock_db.production_work_orders.find.call_args[0][0]
    assert filt["department_id"] == {"$in": ["dept_prod"]}

    with patch.object(server, "db", mock_db), \
            patch.object(server.dept_migrate, "get_enabled_department", new=AsyncMock(return_value={
                "department_id": "dept_prod", "type": dept_catalog.TYPE_PRODUCTION,
            })), \
            patch.object(server.dept_access, "accessible_department_ids", new=AsyncMock(return_value=[])):
        rows, enabled, visible = await server._ask_helm_department_slice(
            principal, dept_catalog.TYPE_PRODUCTION, "production_work_orders",
        )
    assert enabled and not visible
    assert rows == []

    ceo = {**principal, "pack": "owner", "role": "owner"}
    with patch.object(server, "db", mock_db), \
            patch.object(server.dept_migrate, "get_enabled_department", new=AsyncMock(return_value={
                "department_id": "dept_prod", "type": dept_catalog.TYPE_PRODUCTION,
            })), \
            patch.object(server.dept_access, "accessible_department_ids", new=AsyncMock(return_value=None)):
        rows, enabled, visible = await server._ask_helm_department_slice(
            ceo, dept_catalog.TYPE_PRODUCTION, "production_work_orders",
        )
    assert enabled and visible
    filt = mock_db.production_work_orders.find.call_args[0][0]
    assert "department_id" not in filt


# Catalog coverage: every department type Ask Trenston can surface must be membership-gated
# (Accounting/Finance uses the Financials section grant, not department membership alone).
_ASK_DEPT_SLICES = (
    (dept_catalog.TYPE_SALES, "deals", "pipeline"),
    (dept_catalog.TYPE_HR, "hr_onboarding_instances", "onboarding"),
    (dept_catalog.TYPE_PRODUCTION, "production_work_orders", "production"),
    (dept_catalog.TYPE_PROCUREMENT, "procurement_requests", "procurement"),
    (dept_catalog.TYPE_LEGAL, "legal_matters", "legal"),
    (dept_catalog.TYPE_ENGINEERING_MAINTENANCE, "maintenance_tickets", "maintenance"),
)


def test_ask_scopes_every_non_finance_catalog_department():
    """No department queue is left as an unconditional Ask Trenston exception."""
    catalog_types = {d["type"] for d in dept_catalog.DEPARTMENT_CATALOG}
    sliced = {t for t, _c, _k in _ASK_DEPT_SLICES}
    assert dept_catalog.TYPE_ACCOUNTING_FINANCE in catalog_types
    assert sliced | {dept_catalog.TYPE_ACCOUNTING_FINANCE} == catalog_types
    for _type, _coll, ctx_key in _ASK_DEPT_SLICES:
        assert ctx_key in (
            "pipeline", "onboarding", "production", "procurement", "legal", "maintenance",
        )


@pytest.mark.asyncio
async def test_ask_helm_calls_membership_slice_for_every_non_finance_dept():
    """Batched membership once, then a slice for each non-finance dept type."""
    principal = {
        "user_id": "u_member",
        "workspace_id": "ws_ask",
        "pack": "member",
        "role": "member",
        "email": "m@example.com",
        "name": "Member",
    }
    ws = _company()
    mock_db = MagicMock()
    mock_db.chat_messages.insert_one = AsyncMock(return_value=None)
    mock_db.chat_messages.find = FakeCollection().find
    called = []
    access_mock = AsyncMock(return_value=_access_by_type())
    enabled_mock = AsyncMock(return_value=_enabled_by_type())

    async def _slice(principal, dept_type, collection_attr, *, enabled_dept=None, access_ids=None):
        called.append((dept_type, collection_attr))
        return [], True, False

    captured = {}

    async def _capture_stream(system, message=None, **kwargs):
        captured["system"] = _system_text(system)
        captured["max_tokens"] = kwargs.get("max_tokens")
        yield "ok"

    with patch.object(server, "get_ws", new=AsyncMock(return_value=ws)), \
            patch.object(server, "can_access_financials", new=AsyncMock(return_value=False)), \
            patch.object(server, "db", mock_db), \
            patch.object(server, "_product_event", new=AsyncMock()), \
            patch.object(server.helm_llm, "anthropic_configured", return_value=True), \
            patch.object(server.helm_llm, "stream_text", side_effect=_capture_stream), \
            patch.object(server.plan_usage, "acquire_period_ask_slot", new=AsyncMock(return_value=True)), \
            patch.object(server.plan_usage, "current_usage_period", return_value=_ask_period()), \
            patch.object(server, "BILLING_ENFORCED", False), \
            patch.object(server.dept_access, "accessible_department_ids_by_type", new=access_mock), \
            patch.object(server.dept_migrate, "get_enabled_departments_by_type", new=enabled_mock), \
            patch.object(server, "_ask_helm_department_slice", new=AsyncMock(side_effect=_slice)), \
            patch.object(server.helm_freshness, "resolve_workspace_data_as_of", new=AsyncMock(return_value={
                "data_as_of": None, "sources": {},
            })):
        resp = await server.ask_helm(
            server.AskInput(message="What is happening in production?"),
            principal,
        )
        async for _ in resp.body_iterator:
            pass

    expected = {(t, c) for t, c, _k in _ASK_DEPT_SLICES}
    assert set(called) == expected
    assert access_mock.await_count == 1
    assert enabled_mock.await_count == 1
    batch_types = set(access_mock.await_args.args[2])
    assert batch_types == {t for t, _c, _k in _ASK_DEPT_SLICES}
    system = captured["system"]
    for note_frag in (
        "Sales pipeline is not shared",
        "HR onboarding data is not shared",
        "Production data is not shared",
        "Procurement data is not shared",
        "Legal data is not shared",
        "Engineering & Maintenance data is not shared",
        "Financial figures are not shared",
    ):
        assert note_frag in system
