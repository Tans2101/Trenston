"""Financial Modeling: parity with the JS port, plan/permission gating,
scenario validation and tenant isolation."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_modeling")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import modeling  # noqa: E402
import plans  # noqa: E402
import server  # noqa: E402
from tests.mongo_mocks import FakeCollection  # noqa: E402

FIXTURE = json.loads((ROOT.parent / "shared" / "modeling-parity.json").read_text())


# ---------------------------------------------------------------- model / parity

def _close(a, b):
    if a is None or b is None:
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))
    return a == b


def _same(actual, expected, where="root"):
    if isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected), where
        for i, (x, y) in enumerate(zip(actual, expected)):
            _same(x, y, f"{where}[{i}]")
    elif isinstance(expected, dict):
        assert set(actual) == set(expected), where
        for k in expected:
            _same(actual[k], expected[k], f"{where}.{k}")
    else:
        assert _close(actual, expected), f"{where}: {actual!r} != {expected!r}"


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=[c["name"] for c in FIXTURE["cases"]])
def test_reference_model_matches_shared_fixture(case):
    """If this fails after editing modeling.py, regenerate the fixture AND fix modeling.js."""
    _same(modeling.sanitize_inputs(case["inputs"]), case["sanitized"], "sanitized")
    _same(modeling.project_cash(case["inputs"], case["baseline"]), case["expected"], "result")


def test_flat_burn_hand_check():
    r = modeling.project_cash(
        {"horizon": 12, "min_cash_reserve": 5000},
        {"cash": 10000, "revenue": 1000, "expenses": 3000, "start_month": "2026-09"},
    )
    assert [p["cash"] for p in r["points"][:6]] == [8000, 6000, 4000, 2000, 0, -2000]
    assert r["runway_months"] == 5.0
    assert r["cash_out_month"] == 6
    assert r["reserve_breach_month"] == 3
    assert r["points"][0]["month"] == "2026-10"


def test_interpolated_runway_inside_month():
    r = modeling.project_cash({"horizon": 12}, {"cash": 5000, "revenue": 0, "expenses": 2000, "start_month": "2026-09"})
    # 5000 -> 3000 -> 1000 -> -1000: crosses zero halfway through month 3.
    assert r["runway_months"] == pytest.approx(2.5)


def test_no_cash_keeps_curve_null_but_break_even_computable():
    r = modeling.project_cash(
        {"horizon": 24, "revenue_growth_pct": 10},
        {"cash": None, "revenue": 1000, "expenses": 2000, "start_month": "2026-09"},
    )
    assert r["runway_status"] == modeling.RUNWAY_NO_CASH
    assert r["runway_months"] is None and r["ending_cash"] is None
    assert all(p["cash"] is None for p in r["points"])
    assert r["break_even_month"] is not None


def test_baseline_inputs_strip_drivers():
    b = modeling.baseline_inputs({"revenue_growth_pct": 9, "hires": [{"monthly_cost": 1}], "horizon": 36, "min_cash_reserve": 5})
    assert b == {"revenue_growth_pct": 0.0, "expense_growth_pct": 0.0, "hires": [], "events": [],
                 "min_cash_reserve": 5.0, "horizon": 36}


def test_average_recent_skips_in_progress_month():
    months = [
        {"month": "2026-06", "revenue": 100, "expenses": 400},
        {"month": "2026-07", "revenue": 200, "expenses": 500},
        {"month": "2026-08", "revenue": 300, "expenses": 600},
        {"month": "2026-09", "revenue": 10, "expenses": 20},  # current, half done
    ]
    avg = modeling.average_recent(months, "2026-09")
    assert avg["months"] == ["2026-06", "2026-07", "2026-08"]
    assert avg["revenue"] == 200 and avg["expenses"] == 500
    only_current = modeling.average_recent(months[-1:], "2026-09")
    assert only_current["months"] == ["2026-09"]
    assert modeling.average_recent([], "2026-09") == {"revenue": None, "expenses": None, "months": []}


# ---------------------------------------------------------------- plan gating

@pytest.mark.parametrize("plan,allowed", [("free", False), ("starter", False), ("growth", True), ("business", True), ("pro", False)])
def test_plan_allows_financial_modeling(plan, allowed):
    assert plans.plan_allows(plan, plans.FEATURE_FINANCIAL_MODELING) is allowed
    # Billing off (dev) allows everything, same as every other feature.
    assert plans.plan_allows(plan, plans.FEATURE_FINANCIAL_MODELING, billing_enforced=False) is True


def test_growth_includes_mentions_modeling_and_starter_does_not():
    growth = " ".join(plans.PLANS["growth"]["includes"])
    starter = " ".join(plans.PLANS["starter"]["includes"])
    assert "Financial Modeling" in growth
    assert "Financial Modeling" not in starter


PRINCIPAL = {"user_id": "u1", "workspace_id": "ws_a", "pack": "owner", "role": "owner", "name": "T"}


def _ws(plan="growth", **extra):
    return {"workspace_id": "ws_a", "plan": plan, "name": "A", **extra}


async def _gate(ws, *, fin=True):
    with patch.object(server, "get_ws", new=AsyncMock(return_value=ws)), \
            patch.object(server, "can_access_financials", new=AsyncMock(return_value=fin)), \
            patch.object(server, "BILLING_ENFORCED", True):
        return await server.require_modeling(PRINCIPAL)


@pytest.mark.asyncio
async def test_gate_rejects_starter_with_plan_reason():
    with pytest.raises(HTTPException) as exc:
        await _gate(_ws("starter"))
    assert exc.value.status_code == 403
    assert exc.value.detail["reason"] == "plan"


@pytest.mark.asyncio
async def test_gate_rejects_missing_financials_with_permission_reason_even_on_growth():
    with pytest.raises(HTTPException) as exc:
        await _gate(_ws("growth"), fin=False)
    assert exc.value.detail["reason"] == "permission"


@pytest.mark.asyncio
async def test_gate_rejects_past_due_growth():
    with pytest.raises(HTTPException) as exc:
        await _gate(_ws("growth", subscription_status="past_due"))
    assert exc.value.detail["reason"] == "plan"


@pytest.mark.asyncio
async def test_gate_allows_growth_and_business():
    assert (await _gate(_ws("growth")))["user_id"] == "u1"
    assert (await _gate(_ws("business")))["user_id"] == "u1"


@pytest.mark.asyncio
async def test_access_endpoint_never_returns_figures():
    with patch.object(server, "get_ws", new=AsyncMock(return_value=_ws("starter"))), \
            patch.object(server, "can_access_financials", new=AsyncMock(return_value=True)), \
            patch.object(server, "BILLING_ENFORCED", True):
        out = await server.modeling_access(PRINCIPAL)
    assert out["allowed"] is False and out["reason"] == "plan"
    assert out["can_manage_billing"] is True
    assert not ({"cash", "revenue", "expenses", "runway_months"} & set(out))


# ---------------------------------------------------------------- baseline

def test_baseline_from_fin_keeps_nulls():
    fin = {"has_data": False, "ledger_months": [], "cash_entered": False, "cash_value": None,
           "current_month": "2026-09", "currency": "php", "currency_symbol": "₱"}
    b = server.modeling_baseline_from_fin(fin)
    assert b["cash"] is None and b["revenue"] is None and b["expenses"] is None
    assert b["cash_entered"] is False and b["months_used"] == []


def test_baseline_from_fin_averages_complete_months():
    fin = {
        "has_data": True, "cash_entered": True, "cash_value": 50000.0, "current_month": "2026-09",
        "ledger_months": [
            {"month": "2026-07", "revenue": 0.0, "expenses": 3000.0},
            {"month": "2026-08", "revenue": 0.0, "expenses": 5000.0},
            {"month": "2026-09", "revenue": 0.0, "expenses": 100.0},
        ],
        "min_cash_reserve": 10000.0, "currency": "usd", "currency_symbol": "$",
    }
    b = server.modeling_baseline_from_fin(fin)
    assert b["cash"] == 50000.0 and b["expenses"] == 4000.0 and b["revenue"] == 0.0
    assert b["revenue_known"] is False and b["expenses_known"] is True
    assert b["months_used"] == ["2026-07", "2026-08"]
    assert b["start_month"] == "2026-09" and b["min_cash_reserve"] == 10000.0


# ---------------------------------------------------------------- scenarios API

class _DB:
    def __init__(self):
        self.model_scenarios = FakeCollection()


def _client(db, principal):
    server.app.dependency_overrides[server.get_principal] = lambda: principal
    return TestClient(server.app)


@pytest.fixture
def api():
    db = _DB()
    ws = {"ws_a": _ws("growth"), "ws_b": {"workspace_id": "ws_b", "plan": "business", "name": "B"}}

    async def get_ws(wid):
        return ws[wid]

    with patch.object(server, "db", db), \
            patch.object(server, "get_ws", new=get_ws), \
            patch.object(server, "can_access_financials", new=AsyncMock(return_value=True)), \
            patch.object(server, "BILLING_ENFORCED", True):
        yield db
    server.app.dependency_overrides.clear()


GOOD = {"name": "Hire two engineers", "inputs": {
    "revenue_growth_pct": 5, "expense_growth_pct": 1, "horizon": 24, "min_cash_reserve": 20000,
    "hires": [{"label": "Eng", "monthly_cost": 4000, "start_month": 2}],
    "events": [{"label": "Seed", "amount": 250000, "month": 4}],
}}


def test_scenario_crud_roundtrip(api):
    c = _client(api, PRINCIPAL)
    r = c.post("/api/modeling/scenarios", json=GOOD)
    assert r.status_code == 200, r.text
    sid = r.json()["scenario_id"]
    assert r.json()["inputs"]["hires"][0]["monthly_cost"] == 4000
    listed = c.get("/api/modeling/scenarios").json()["scenarios"]
    assert [s["scenario_id"] for s in listed] == [sid]
    upd = c.put(f"/api/modeling/scenarios/{sid}", json={**GOOD, "name": "  Renamed   plan "})
    assert upd.status_code == 200 and upd.json()["name"] == "Renamed plan"
    assert c.delete(f"/api/modeling/scenarios/{sid}").status_code == 200
    assert c.delete(f"/api/modeling/scenarios/{sid}").status_code == 404


@pytest.mark.parametrize("bad", [
    {"revenue_growth_pct": 500},
    {"expense_growth_pct": -99},
    {"horizon": 18},
    {"min_cash_reserve": -1},
    {"hires": [{"monthly_cost": -5, "start_month": 1}]},
    {"hires": [{"monthly_cost": 5, "start_month": 30}], "horizon": 12},
    {"events": [{"amount": 1, "month": 40}]},
    {"hires": [{"monthly_cost": 1, "start_month": 1}] * 21},
])
def test_scenario_validation_rejects_out_of_bounds(api, bad):
    c = _client(api, PRINCIPAL)
    r = c.post("/api/modeling/scenarios", json={"name": "x", "inputs": bad})
    assert r.status_code == 422


def test_scenario_rejects_blank_and_long_names(api):
    c = _client(api, PRINCIPAL)
    assert c.post("/api/modeling/scenarios", json={"name": "", "inputs": {}}).status_code == 422
    assert c.post("/api/modeling/scenarios", json={"name": "x" * 61, "inputs": {}}).status_code == 422
    assert c.post("/api/modeling/scenarios", json={"name": "   ", "inputs": {}}).status_code == 400


def test_scenario_cap(api):
    c = _client(api, PRINCIPAL)
    for i in range(server.MODEL_SCENARIO_CAP):
        assert c.post("/api/modeling/scenarios", json={"name": f"s{i}", "inputs": {}}).status_code == 200
    r = c.post("/api/modeling/scenarios", json={"name": "one too many", "inputs": {}})
    assert r.status_code == 400


def test_tenant_isolation(api):
    a = _client(api, PRINCIPAL)
    sid = a.post("/api/modeling/scenarios", json=GOOD).json()["scenario_id"]
    b = _client(api, {**PRINCIPAL, "user_id": "u2", "workspace_id": "ws_b"})
    assert b.get("/api/modeling/scenarios").json()["scenarios"] == []
    assert b.put(f"/api/modeling/scenarios/{sid}", json=GOOD).status_code == 404
    assert b.delete(f"/api/modeling/scenarios/{sid}").status_code == 404
    # Still intact for its owner.
    assert len(_client(api, PRINCIPAL).get("/api/modeling/scenarios").json()["scenarios"]) == 1


def test_endpoints_blocked_for_starter(api):
    async def starter_ws(_wid):
        return _ws("starter")

    with patch.object(server, "get_ws", new=starter_ws):
        c = _client(api, PRINCIPAL)
        for method, path in [("get", "/api/modeling/baseline"), ("get", "/api/modeling/scenarios"),
                             ("post", "/api/modeling/scenarios")]:
            r = getattr(c, method)(path, **({"json": GOOD} if method == "post" else {}))
            assert r.status_code == 403
            assert r.json()["detail"]["reason"] == "plan"
    assert api.model_scenarios.docs == []


def test_scenarios_are_workspace_collections_for_delete_and_export():
    assert "model_scenarios" in server._WORKSPACE_COLLECTIONS
