"""Living company map: built only from real records, no model, owner-only."""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_company_map")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import company_map as cm  # noqa: E402

TODAY = date(2026, 10, 13)  # a Tuesday
ME = {"user_id": "u_me", "name": "Tansher"}
ANN = {"user_id": "u_ann", "name": "Ann"}

FIN = {
    "currency_symbol": "$", "current_month": "2026-10", "cash_entered": True, "cash_value": 42000,
    "runway_months": 7.0, "runway_no_burn": False,
    "ledger_months": [{"month": "2026-09", "revenue": 9000, "expenses": 8000},
                      {"month": "2026-10", "revenue": 6000, "expenses": 8000}],
}


def entry(kind, month, amount, category="", name=""):
    return {"id": f"{kind}{month}{amount}{category}", "type": kind, "month": month, "amount": amount,
            "category": category, "name": name}


ENTRIES = [
    entry("revenue", "2026-10", 5000, "Retainers"), entry("revenue", "2026-10", 1000, "Courses"),
    entry("expense", "2026-10", 5000, "Salaries"), entry("expense", "2026-10", 2000, "Software"),
    entry("expense", "2026-10", 1000, "Rent"),
    entry("revenue", "2026-09", 9000, "Old stuff"),
]


def build(**over):
    args = dict(fin=FIN, entries=ENTRIES, signals=[], deals=[], tasks=[], decisions=[],
                members=[ME], today=TODAY, can_see_finance=True)
    args.update(over)
    return cm.build_company_map(**args)


def by_id(m):
    return {n["id"]: n for n in m["nodes"]}


def test_nothing_entered_means_not_ready_and_says_what_to_add():
    m = build(fin={}, entries=[], can_see_finance=True)
    assert m["ready"] is False
    assert {x["label"] for x in m["missing"]} >= {"Your cash balance", "Tasks and deadlines", "Deals you're chasing"}
    assert all(n["kind"] in ("cash", "hub") for n in m["nodes"])


def test_money_view_uses_the_latest_month_with_real_numbers():
    m = build()
    n = by_id(m)
    assert m["ready"] and m["mode"] == "solo"
    assert n["cash"]["sub"] == "$42,000 · 7 months of runway" and n["cash"]["tone"] == "ok"
    assert [n[f"in:{i}"]["label"] for i in range(2)] == ["Retainers", "Courses"]
    assert n["in:0"]["amount"] == 5000
    assert n["out:0"]["label"] == "Salaries" and n["out:0"]["sub"] == "$5,000"
    assert "Old stuff" not in {x["label"] for x in m["nodes"]}  # last month's income is not this month's


def test_short_runway_turns_the_cash_node_red():
    m = build(fin={**FIN, "runway_months": 2.0})
    assert by_id(m)["cash"]["tone"] == "bad"


def test_cash_not_entered_is_a_placeholder_never_zero():
    m = build(fin={**FIN, "cash_entered": False, "cash_value": None, "runway_months": None})
    cash = by_id(m)["cash"]
    assert cash.get("placeholder") and "0" not in cash["sub"]
    assert any(x["label"] == "Your cash balance" for x in m["missing"])


def test_top_expenses_are_capped_and_the_rest_is_grouped():
    many = [entry("expense", "2026-10", 100 + i, f"Cat{i}") for i in range(9)]
    m = build(entries=many)
    labels = [n["label"] for n in m["nodes"] if n["kind"] == "expense"]
    assert len(labels) == cm.MAX_EXPENSE + 1 and labels[-1] == "Everything else"


def test_no_finance_access_hides_all_money():
    m = build(can_see_finance=False, tasks=[{"id": "t1", "title": "Call", "due": "2026-10-14", "column": "todo"}],
              signals=[{"type": "runway_risk", "severity": "high", "summary": "Runway short", "detail": "$1"},
                       {"type": "overdue_task", "severity": "high", "summary": "Late", "detail": "x"}])
    kinds = {n["kind"] for n in m["nodes"]}
    assert not kinds & {"cash", "income", "expense"} and "cash" not in by_id(m)
    assert "Runway short" not in {n["label"] for n in m["nodes"]}
    assert "Late" in {n["label"] for n in m["nodes"]}


def test_promises_come_from_tasks_decisions_and_legal_dates():
    tasks = [
        {"id": "t_late", "title": "Pay supplier", "due": "2026-10-10", "column": "todo", "assignee": "Tansher"},
        {"id": "t_soon", "title": "Send deck", "due": "2026-10-15", "column": "doing"},
        {"id": "t_far", "title": "Far away", "due": "2026-12-01", "column": "todo"},
        {"id": "t_done", "title": "Finished", "due": "2026-10-11", "column": "done"},
        {"id": "t_free", "title": "No date", "due": "Soon", "column": "todo"},
    ]
    m = build(tasks=tasks, decisions=[{"id": "d1", "title": "Hire?", "status": "pending", "due": "2026-10-20"},
                                      {"id": "d2", "title": "Done one", "status": "approved"}],
              signals=[{"type": "upcoming_legal_deadline", "severity": "medium", "summary": "Tax filing due",
                        "detail": "", "related_id": "L1"}])
    n = by_id(m)
    assert n["task:t_late"]["sub"] == "3 days late" and n["task:t_late"]["tone"] == "bad"
    assert n["task:t_soon"]["sub"] == "Due in 2 days" and n["task:t_soon"]["tone"] == "warn"
    assert not {"task:t_far", "task:t_done", "task:t_free"} & set(n)
    assert n["decision:d1"]["sub"] == "Waiting on you · due 2026-10-20" and "decision:d2" not in n
    assert n["legal:L1"]["label"] == "Tax filing due"
    assert n["task:t_late"]["sub"].count("Tansher") == 0  # solo: no names


def test_problems_attach_to_what_they_are_about_with_a_next_step():
    tasks = [{"id": "t1", "title": "Pay supplier", "due": "2026-10-10", "column": "todo"}]
    signals = [
        {"type": "overdue_task", "severity": "high", "summary": "Task overdue: Pay supplier", "detail": "d", "related_id": "t1"},
        {"type": "runway_risk", "severity": "high", "summary": "Runway short", "detail": "d", "related_id": None},
        {"type": "expense_spike", "severity": "medium", "summary": "Software jumped", "detail": "d"},
        {"type": "overdue_task", "severity": "low", "summary": "ignored", "detail": ""},
    ]
    m = build(tasks=tasks, signals=signals)
    links = {(l["source"], l["target"]) for l in m["links"]}
    probs = {n["label"]: n for n in m["nodes"] if n["kind"] == "problem"}
    assert set(probs) == {"Task overdue: Pay supplier", "Runway short", "Software jumped"}
    assert (probs["Task overdue: Pay supplier"]["id"], "task:t1") in links
    assert (probs["Runway short"]["id"], "cash") in links
    assert (probs["Software jumped"]["id"], "out") in links
    assert probs["Runway short"]["tone"] == "bad" and probs["Software jumped"]["tone"] == "warn"
    assert all(p["action"] for p in probs.values())
    assert m["problem_count"] == 3


def test_problems_are_capped_worst_first():
    sigs = [{"type": "overdue_task", "severity": "medium" if i % 2 else "high", "summary": f"p{i}", "detail": ""}
            for i in range(20)]
    m = build(signals=sigs, tasks=[{"id": "x", "title": "t", "due": "2026-10-14", "column": "todo"}])
    probs = [n for n in m["nodes"] if n["kind"] == "problem"]
    assert len(probs) == cm.MAX_PROBLEMS and all(p["severity"] == "high" for p in probs)


def test_every_link_points_at_a_real_node():
    tasks = [{"id": "t1", "title": "a", "due": "2026-10-10", "column": "todo", "assignee_user_id": "u_ann"}]
    m = build(tasks=tasks, members=[ME, ANN], deals=[{"id": "x", "stage": "proposal", "value": 100}],
              signals=[{"type": "stalled_deal", "severity": "high", "summary": "s", "detail": "d", "related_id": "x"},
                       {"type": "pending_leave_request", "severity": "medium", "summary": "leave", "detail": ""}])
    ids = {n["id"] for n in m["nodes"]}
    assert len(ids) == len(m["nodes"])
    assert all(l["source"] in ids and l["target"] in ids for l in m["links"])


def test_pipeline_counts_only_open_deals_and_hides_value_without_finance_access():
    deals = [{"id": "a", "stage": "proposal", "value": 1000}, {"id": "b", "stage": "won", "value": 5000},
             {"id": "c", "stage": "lead", "value": 500}]
    m = build(deals=deals)
    assert by_id(m)["pipeline"]["sub"] == "2 open deals · $1,500"
    m2 = build(deals=deals, can_see_finance=False)
    assert by_id(m2)["pipeline"]["sub"] == "2 open deals"


def test_team_mode_shows_people_with_late_work():
    tasks = [
        {"id": "a", "title": "x", "due": "2026-10-01", "column": "todo", "assignee_user_id": "u_ann", "assignee": "Ann"},
        {"id": "b", "title": "y", "due": "2026-11-30", "column": "todo", "assignee_user_id": "u_ann"},
        {"id": "c", "title": "z", "due": "", "column": "todo", "assignee_user_id": "u_me"},
    ]
    m = build(tasks=tasks, members=[ME, ANN])
    n = by_id(m)
    assert m["mode"] == "team"
    assert n["person:u_ann"]["sub"] == "2 open · 1 late" and n["person:u_ann"]["tone"] == "bad"
    assert n["person:u_me"]["sub"] == "1 open"
    assert "Ann" in n["task:a"]["sub"]  # names appear on tasks only when there is a team


# ------------------------------------------------------------------ API
from unittest.mock import AsyncMock, patch  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402


@pytest.fixture
def client_for():
    def make(role):
        async def principal():
            return {"user_id": "u1", "name": "N", "email": "n@x.com", "workspace_id": "ws1",
                    "pack": "owner" if role == "owner" else "member", "role": role}
        server.app.dependency_overrides[server.get_principal] = principal
        return TestClient(server.app)
    yield make
    server.app.dependency_overrides.clear()


def test_endpoint_is_owner_only(client_for):
    assert client_for("member").get("/api/company-map").status_code == 403


def test_endpoint_returns_the_built_map(client_for):
    ws = {"workspace_id": "ws1", "tasks": {"items": [{"id": "t1", "title": "Call", "due": "2026-10-14", "column": "todo"}]},
          "decisions": []}

    class Deals:
        def find(self, *a, **k):
            return self

        async def to_list(self, n):
            return []

    fake_db = type("D", (), {"deals": Deals()})()
    members = {"u1": {"user_id": "u1", "name": "N", "role": "owner"}}
    with patch.object(server, "db", fake_db), \
            patch.object(server, "can_access_financials", AsyncMock(return_value=False)), \
            patch.object(server, "_automation_inputs", AsyncMock(return_value=(ws, {}, [], []))), \
            patch.object(server, "_active_member_ids", AsyncMock(return_value=members)), \
            patch.object(server.tz_utils, "workspace_today", return_value=TODAY):
        r = client_for("owner").get("/api/company-map")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] and body["mode"] == "solo" and body["can_see_finance"] is False
    assert "task:t1" in {n["id"] for n in body["nodes"]}
