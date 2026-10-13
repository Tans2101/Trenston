"""Automations: rule validation, firing + dedupe, anomaly detection, owner-only API."""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_automations")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import automations as au  # noqa: E402
import server  # noqa: E402
from tests.mongo_mocks import FakeCollection  # noqa: E402

NOW = datetime(2026, 10, 13, 9, 0, tzinfo=timezone.utc)
TODAY = date(2026, 10, 13)
MEMBERS = {"u_own", "u_ann"}


def run(coro):
    return asyncio.run(coro)


class _Coll(FakeCollection):
    """FakeCollection plus the $inc / $push / distinct the automation code uses."""

    async def update_one(self, flt, update, upsert=False):
        res = await super().update_one(flt, update, upsert)
        for d in self.docs:
            if all(d.get(k) == v for k, v in (flt or {}).items() if not isinstance(v, dict)):
                for k, v in ((update or {}).get("$inc") or {}).items():
                    d[k] = d.get(k, 0) + v
                for k, v in ((update or {}).get("$push") or {}).items():
                    node = d
                    *parents, leaf = k.split(".")
                    for part in parents:
                        node = node.setdefault(part, {})
                    node.setdefault(leaf, []).append(v)
                break
        return res

    async def distinct(self, key, flt=None):
        from tests.mongo_mocks import match_filter
        return sorted({d[key] for d in self.docs if key in d and match_filter(d, flt or {})})


class DB(SimpleNamespace):
    def __getitem__(self, name):
        return getattr(self, name)


def new_db():
    return DB(**{n: _Coll() for n in (
        "automation_rules", "automation_events", "anomaly_alerts", "memberships", "users", "workspaces",
    )})


def task_rule(**over):
    rule = {
        "id": "rule_1", "workspace_id": "ws1", "name": "Late work orders", "enabled": True,
        "trigger": {"type": "signal", "signal_type": "overdue_work_order", "min_severity": "low"},
        "action": {"type": "create_task", "title": "Chase: {summary}", "priority": "High",
                   "due_in_days": 1, "assignee_user_id": "u_ann"},
        "created_by": "u_own",
    }
    rule.update(over)
    return rule


def sig(type_="overdue_work_order", related="wo1", severity="medium", summary="WO-1 is late"):
    return {"type": type_, "severity": severity, "summary": summary, "detail": "d", "related_id": related}


# ------------------------------------------------------------------ validation

def test_valid_rule_is_normalised_and_extra_keys_dropped():
    rule = au.normalize_rule({
        "name": "  Late   work orders ", "enabled": True, "evil": "x",
        "trigger": {"type": "signal", "signal_type": "overdue_work_order", "extra": 1},
        "action": {"type": "create_task", "title": "Chase {summary}", "priority": "High",
                   "due_in_days": "3", "assignee_user_id": "u_ann", "webhook": "http://x"},
    }, MEMBERS)
    assert rule["name"] == "Late work orders"
    assert rule["trigger"] == {"type": "signal", "signal_type": "overdue_work_order", "min_severity": "low"}
    assert rule["action"] == {"type": "create_task", "title": "Chase {summary}", "priority": "High",
                              "due_in_days": 3, "assignee_user_id": "u_ann"}
    assert "evil" not in rule


@pytest.mark.parametrize("body", [
    {"name": "", "trigger": {"type": "signal", "signal_type": "overdue_task"}, "action": {"type": "alert"}},
    {"name": "x", "trigger": {"type": "signal", "signal_type": "nope"}, "action": {"type": "alert"}},
    {"name": "x", "trigger": {"type": "signal", "signal_type": "overdue_task", "min_severity": "extreme"},
     "action": {"type": "alert"}},
    {"name": "x", "trigger": {"type": "metric", "metric": "runway_months_below", "value": 0},
     "action": {"type": "alert"}},
    {"name": "x", "trigger": {"type": "metric", "metric": "runway_months_below", "value": "abc"},
     "action": {"type": "alert"}},
    {"name": "x", "trigger": {"type": "metric", "metric": "runway_months_below", "value": float("nan")},
     "action": {"type": "alert"}},
    {"name": "x", "trigger": {"type": "signal", "signal_type": "overdue_task"}, "action": {"type": "email"}},
    {"name": "x", "trigger": {"type": "signal", "signal_type": "overdue_task"},
     "action": {"type": "create_task", "priority": "Urgent"}},
    {"name": "x", "trigger": {"type": "signal", "signal_type": "overdue_task"},
     "action": {"type": "create_task", "due_in_days": 400}},
    {"name": "x", "trigger": {"type": "signal", "signal_type": "overdue_task"},
     "action": {"type": "create_task", "assignee_user_id": "u_stranger"}},
    {"name": "x", "trigger": "overdue", "action": {"type": "alert"}},
])
def test_bad_rules_are_rejected(body):
    with pytest.raises(au.RuleError):
        au.normalize_rule(body, MEMBERS)


def test_every_starter_template_is_a_valid_rule():
    templates = au.starter_templates()
    assert len({t["id"] for t in templates}) == len(templates)
    for t in templates:
        au.normalize_rule({"name": t["name"], "trigger": t["trigger"], "action": t["action"]}, MEMBERS)


def test_financial_triggers_are_flagged():
    assert au.trigger_is_financial({"type": "metric", "metric": "cash_below", "value": 1})
    assert au.trigger_is_financial({"type": "signal", "signal_type": "runway_risk"})
    assert not au.trigger_is_financial({"type": "signal", "signal_type": "overdue_task"})


def test_title_template_is_plain_replace_not_format():
    firing = {"summary": "WO-1 late", "detail": "2 days"}
    assert au.render_title("Chase {summary} / {detail}", firing) == "Chase WO-1 late / 2 days"
    # Braces from user text must never be interpreted as format fields.
    assert au.render_title("{0} {summary.__class__} {summary}", firing) == "{0} {summary.__class__} WO-1 late"
    assert au.render_title("   ", firing) == "WO-1 late"
    assert len(au.render_title("x" * 500, firing)) == au.MAX_TITLE


# ------------------------------------------------------------------ matching

def test_signal_rule_matches_type_and_severity():
    rule = task_rule(trigger={"type": "signal", "signal_type": "overdue_work_order", "min_severity": "medium"})
    signals = [sig(severity="low", related="a"), sig(severity="high", related="b"), sig("overdue_task", "c")]
    keys = [f["dedupe_key"] for f in au.rule_firings(rule, signals, {})]
    assert keys == ["signal:overdue_work_order:b"]


def test_metric_rules_need_real_data():
    runway = task_rule(trigger={"type": "metric", "metric": "runway_months_below", "value": 6})
    assert au.rule_firings(runway, [], {"has_data": True, "cash_entered": True, "runway_months": 4.2})
    assert not au.rule_firings(runway, [], {"has_data": True, "cash_entered": True, "runway_months": 9})
    # Cash not entered is "unknown", never "zero runway".
    assert not au.rule_firings(runway, [], {"has_data": True, "cash_entered": False, "runway_months": 0})
    assert not au.rule_firings(runway, [], {"has_data": False, "runway_months": 1})
    cash = task_rule(trigger={"type": "metric", "metric": "cash_below", "value": 1000})
    assert au.rule_firings(cash, [], {"has_data": True, "cash_entered": True, "cash_value": 400})
    assert not au.rule_firings(cash, [], {"has_data": True, "cash_entered": False, "cash_value": 400})


# ------------------------------------------------------------------ running rules

def _runner(db, rules, signals, fin=None, assignee=True, pushed=None, fail_first=False, calls=None):
    pushed = pushed if pushed is not None else []
    calls = calls if calls is not None else {"n": 0}

    async def resolve(rule):
        return {"user_id": "u_ann", "name": "Ann"} if assignee else None

    async def push(rule, task, who):
        calls["n"] += 1
        if fail_first and calls["n"] == 1:
            raise RuntimeError("db down")
        pushed.append(task)

    return run(au.run_rules(
        db, "ws1", rules=rules, signals=signals, fin=fin or {}, today=TODAY, now=NOW,
        resolve_assignee=resolve, push_task=push,
    ))


def test_rule_creates_one_task_and_never_repeats():
    db, pushed = new_db(), []
    rule = task_rule()
    db.automation_rules.docs.append(dict(rule))
    first = _runner(db, [rule], [sig()], pushed=pushed)
    second = _runner(db, [rule], [sig()], pushed=pushed)
    assert first["tasks"] == 1 and second["tasks"] == 0
    assert len(pushed) == 1
    task = pushed[0]
    assert task["title"] == "Chase: WO-1 is late"
    assert task["assignee_user_id"] == "u_ann" and task["priority"] == "High"
    assert task["due"] == "2026-10-14" and task["source"] == "automation" and task["column"] == "backlog"
    assert len(db.automation_events.docs) == 1
    assert db.automation_events.docs[0]["task_id"] == task["id"]
    assert db.automation_rules.docs[0]["fire_count"] == 1


def test_new_matching_signal_fires_again():
    db, pushed = new_db(), []
    rule = task_rule()
    _runner(db, [rule], [sig(related="a")], pushed=pushed)
    _runner(db, [rule], [sig(related="a"), sig(related="b")], pushed=pushed)
    assert len(pushed) == 2


def test_alert_only_rule_logs_an_event_without_a_task():
    db, pushed = new_db(), []
    rule = task_rule(action={"type": "alert"})
    out = _runner(db, [rule], [sig()], pushed=pushed)
    assert out["fired"] == 1 and out["tasks"] == 0 and pushed == []
    assert db.automation_events.docs[0]["action"] == "alert"


def test_disabled_rules_do_nothing():
    db, pushed = new_db(), []
    out = _runner(db, [task_rule(enabled=False)], [sig()], pushed=pushed)
    assert out["rules"] == 0 and pushed == [] and db.automation_events.docs == []


def test_a_rule_cannot_flood_the_task_board():
    db, pushed = new_db(), []
    signals = [sig(related=f"wo{i}") for i in range(40)]
    _runner(db, [task_rule()], signals, pushed=pushed)
    assert len(pushed) == au.MAX_FIRINGS_PER_RULE_RUN
    _runner(db, [task_rule()], signals, pushed=pushed)  # next run picks up more
    assert len(pushed) == 2 * au.MAX_FIRINGS_PER_RULE_RUN


def test_failed_action_releases_the_claim_so_it_retries():
    db, pushed = new_db(), []
    rule = task_rule()
    calls = {"n": 0}  # shared, so only the very first push attempt fails
    first = _runner(db, [rule], [sig()], pushed=pushed, fail_first=True, calls=calls)
    assert first["errors"] == 1 and first["tasks"] == 0 and db.automation_events.docs == []
    second = _runner(db, [rule], [sig()], pushed=pushed, fail_first=True, calls=calls)
    assert second["tasks"] == 1 and len(pushed) == 1


def test_no_assignee_means_no_task_and_no_stuck_claim():
    db, pushed = new_db(), []
    out = _runner(db, [task_rule()], [sig()], assignee=False, pushed=pushed)
    assert out["errors"] == 1 and pushed == [] and db.automation_events.docs == []


# ------------------------------------------------------------------ anomalies

def entry(i, type_="expense", month="2026-10", amount=1000.0, name="Rent", category="Rent", **extra):
    return {"id": f"e{i}", "type": type_, "month": month, "amount": amount, "name": name,
            "category": category, **extra}


def test_identical_entries_that_move_the_month_are_flagged():
    entries = [entry(1, amount=5000, name="Steel supplier"), entry(2, amount=5000, name="Steel  Supplier"),
               entry(3, amount=800, name="Other", category="Misc")]
    found = au.detect_duplicates(entries)
    assert len(found) == 1 and found[0]["kind"] == "duplicate_entry"
    assert found[0]["entry_ids"] == ["e1", "e2"]


def test_small_repeats_recurring_and_system_booked_rows_are_not_duplicates():
    big = entry(9, amount=100000, name="Payroll", category="Payroll")
    small = [entry(1, amount=10, name="Coffee"), entry(2, amount=10, name="Coffee"), big]
    assert au.detect_duplicates(small) == []
    recurring = [entry(1, amount=5000, recurring=True), entry(2, amount=5000, recurring=True)]
    assert au.detect_duplicates(recurring) == []
    booked = [entry(1, type_="revenue", amount=5000, source_deal_id="d1"),
              entry(2, type_="revenue", amount=5000, source_deal_id="d2")]
    assert au.detect_duplicates(booked) == []


def test_outlier_expense_needs_history_and_a_big_jump():
    history = [entry(i, month=f"2026-0{i}", amount=100 + i, category="Travel", name=f"trip{i}") for i in range(1, 7)]
    spike = entry(50, month="2026-10", amount=5000, category="Travel", name="Conference")
    found = au.detect_outlier_expenses(history + [spike], "2026-10")
    assert [a["entry_ids"] for a in found] == [["e50"]]
    assert found[0]["severity"] == "high"
    normal = entry(51, month="2026-10", amount=130, category="Travel", name="Taxi")
    assert au.detect_outlier_expenses(history + [normal], "2026-10") == []
    # Too little history: no opinion.
    assert au.detect_outlier_expenses(history[:3] + [spike], "2026-10") == []
    # Old spikes are not re-announced.
    old = entry(52, month="2026-07", amount=5000, category="Travel", name="Old")
    assert au.detect_outlier_expenses(history + [old], "2026-10") == []


def months(*revenues, start=7):
    return [{"month": f"2026-{start + i:02d}", "revenue": r, "expenses": 100.0} for i, r in enumerate(revenues)]


def test_revenue_drop_and_stop():
    drop = au.detect_revenue_change(months(1000, 1000, 1000, 650), "2026-11")
    assert drop and drop[0]["kind"] == "revenue_drop" and drop[0]["severity"] == "medium"
    big = au.detect_revenue_change(months(1000, 1000, 1000, 200), "2026-11")
    assert big[0]["severity"] == "high"
    stopped = au.detect_revenue_change(months(1000, 1000, 1000, 0), "2026-11")
    assert stopped[0]["kind"] == "revenue_stopped" and stopped[0]["severity"] == "high"


def test_revenue_checks_stay_quiet_without_a_baseline():
    assert au.detect_revenue_change(months(1000, 400), "2026-11") == []          # too little history
    assert au.detect_revenue_change(months(0, 0, 1000, 0), "2026-11") == []      # baseline mostly empty
    assert au.detect_revenue_change(months(1000, 1000, 1000, 900), "2026-11") == []  # normal wobble
    # The in-progress month is never judged.
    assert au.detect_revenue_change(months(1000, 1000, 1000, 100), "2026-10") == []


def test_store_anomalies_inserts_once_resolves_gone_and_respects_dismissal():
    db = new_db()
    a = {"key": "dup:1", "kind": "duplicate_entry", "severity": "medium", "title": "t", "detail": "d",
         "entry_ids": ["e1"], "month": "2026-10"}
    assert run(au.store_anomalies(db, "ws1", [a], NOW)) == {"new": 1, "resolved": 0}
    assert run(au.store_anomalies(db, "ws1", [a], NOW)) == {"new": 0, "resolved": 0}
    assert len(db.anomaly_alerts.docs) == 1
    # User dismisses it: the same finding must not come back.
    db.anomaly_alerts.docs[0]["status"] = "dismissed"
    assert run(au.store_anomalies(db, "ws1", [a], NOW)) == {"new": 0, "resolved": 0}
    assert db.anomaly_alerts.docs[0]["status"] == "dismissed"
    # An open alert whose condition is gone is resolved.
    db.anomaly_alerts.docs[0]["status"] = "open"
    assert run(au.store_anomalies(db, "ws1", [], NOW)) == {"new": 0, "resolved": 1}
    assert db.anomaly_alerts.docs[0]["status"] == "resolved"


def test_store_anomalies_is_scoped_to_the_workspace():
    db = new_db()
    a = {"key": "k", "kind": "revenue_drop", "severity": "high", "title": "t", "detail": "d",
         "entry_ids": [], "month": "2026-09"}
    run(au.store_anomalies(db, "ws1", [a], NOW))
    assert run(au.store_anomalies(db, "ws2", [a], NOW))["new"] == 1
    run(au.store_anomalies(db, "ws2", [], NOW))
    assert {d["workspace_id"]: d["status"] for d in db.anomaly_alerts.docs} == {"ws1": "open", "ws2": "resolved"}


# ------------------------------------------------------------------ API

@pytest.fixture
def owner_client():
    async def principal():
        return {"user_id": "u_own", "name": "Owner", "email": "o@x.com",
                "workspace_id": "ws1", "pack": "owner", "role": "owner"}
    db = new_db()
    db.memberships.docs += [
        {"workspace_id": "ws1", "user_id": "u_own", "email": "o@x.com", "role": "owner", "status": "active"},
        {"workspace_id": "ws1", "user_id": "u_ann", "email": "a@x.com", "role": "member", "status": "active"},
        {"workspace_id": "ws2", "user_id": "u_zed", "email": "z@x.com", "role": "owner", "status": "active"},
    ]
    db.users.docs += [{"user_id": "u_own", "name": "Owner"}, {"user_id": "u_ann", "name": "Ann"}]
    server.app.dependency_overrides[server.get_principal] = principal
    with patch.object(server, "db", db), \
            patch.object(server, "can_access_financials", AsyncMock(return_value=True)):
        yield TestClient(server.app), db
    server.app.dependency_overrides.clear()


@pytest.fixture
def member_client():
    async def principal():
        return {"user_id": "u_ann", "name": "Ann", "email": "a@x.com",
                "workspace_id": "ws1", "pack": "member", "role": "member"}
    server.app.dependency_overrides[server.get_principal] = principal
    with patch.object(server, "db", new_db()):
        yield TestClient(server.app)
    server.app.dependency_overrides.clear()


def body(**over):
    b = {"name": "Late orders", "enabled": True,
         "trigger": {"type": "signal", "signal_type": "overdue_work_order", "min_severity": "low"},
         "action": {"type": "create_task", "title": "Chase {summary}", "priority": "High",
                    "due_in_days": 1, "assignee_user_id": "u_ann"}}
    b.update(over)
    return b


def test_only_the_owner_can_use_automations(member_client):
    assert member_client.get("/api/automations").status_code == 403
    assert member_client.post("/api/automations", json=body()).status_code == 403
    assert member_client.delete("/api/automations/rule_x").status_code == 403
    assert member_client.post("/api/automations/run").status_code == 403


def test_create_list_update_delete_flow(owner_client):
    client, db = owner_client
    created = client.post("/api/automations", json=body())
    assert created.status_code == 200
    rule = created.json()["rule"]
    assert rule["workspace_id"] == "ws1" and rule["created_by"] == "u_own" and rule["fire_count"] == 0

    listing = client.get("/api/automations").json()
    assert [r["id"] for r in listing["rules"]] == [rule["id"]]
    assert listing["max_rules"] == au.MAX_RULES and listing["templates"]
    assert {m["user_id"] for m in listing["members"]} == {"u_own", "u_ann"}

    patched = client.patch(f"/api/automations/{rule['id']}", json={"enabled": False})
    assert patched.status_code == 200 and patched.json()["rule"]["enabled"] is False
    assert db.automation_rules.docs[0]["enabled"] is False
    assert db.automation_rules.docs[0]["trigger"]["signal_type"] == "overdue_work_order"

    db.automation_events.docs.append({"workspace_id": "ws1", "rule_id": rule["id"], "id": "evt1"})
    assert client.delete(f"/api/automations/{rule['id']}").status_code == 200
    assert db.automation_rules.docs == [] and db.automation_events.docs == []
    assert client.delete(f"/api/automations/{rule['id']}").status_code == 404


def test_bad_rules_get_a_clear_422_and_strangers_cannot_be_assigned(owner_client):
    client, _ = owner_client
    bad = client.post("/api/automations", json=body(trigger={"type": "signal", "signal_type": "nope"}))
    assert bad.status_code == 422 and "trigger" in bad.json()["detail"].lower()
    stranger = body()
    stranger["action"]["assignee_user_id"] = "u_zed"  # member of another workspace
    assert client.post("/api/automations", json=stranger).status_code == 422


def test_rule_count_is_capped(owner_client):
    client, db = owner_client
    for i in range(au.MAX_RULES):
        db.automation_rules.docs.append({"id": f"r{i}", "workspace_id": "ws1"})
    assert client.post("/api/automations", json=body()).status_code == 403


@pytest.mark.parametrize("plan,limit", [("free", 2), ("starter", 5), ("growth", 15), ("business", 25)])
def test_rule_count_follows_the_plan(owner_client, plan, limit):
    client, db = owner_client
    db.workspaces.docs.append({"workspace_id": "ws1", "plan": plan})
    with patch.object(server, "BILLING_ENFORCED", True):
        assert client.get("/api/automations").json()["max_rules"] == limit
        for i in range(limit):
            db.automation_rules.docs.append({"id": f"r{i}", "workspace_id": "ws1"})
        over = client.post("/api/automations", json=body())
    assert over.status_code == 403 and f"up to {limit}" in over.json()["detail"]
    assert "upgrade" in over.json()["detail"].lower()


def test_plan_limits_only_grow():
    from plans import automation_rules_limit as lim
    vals = [lim(p) for p in ("free", "starter", "growth", "business")]
    assert vals == sorted(vals) and vals[0] >= 1 and vals[-1] <= au.MAX_RULES


def test_other_workspaces_rules_are_invisible_and_untouchable(owner_client):
    client, db = owner_client
    db.automation_rules.docs.append({**task_rule(id="rule_other", workspace_id="ws2")})
    assert client.get("/api/automations").json()["rules"] == []
    assert client.patch("/api/automations/rule_other", json={"enabled": False}).status_code == 404
    assert client.delete("/api/automations/rule_other").status_code == 404
    assert len(db.automation_rules.docs) == 1


def test_money_rules_need_financial_access(owner_client):
    client, _ = owner_client
    money = body(trigger={"type": "metric", "metric": "runway_months_below", "value": 6}, action={"type": "alert"})
    with patch.object(server, "can_access_financials", AsyncMock(return_value=False)):
        assert client.post("/api/automations", json=money).status_code == 403
        listing = client.get("/api/automations").json()
        assert listing["alerts"] == [] and not listing["can_see_finance"]
        assert all(not s["financial"] for s in listing["catalog"]["signals"])
        assert listing["catalog"]["metrics"] == []
    assert client.post("/api/automations", json=money).status_code == 200


def test_money_rules_cannot_hand_figures_to_someone_else(owner_client):
    client, _ = owner_client
    task_for_ann = body(
        trigger={"type": "metric", "metric": "cash_below", "value": 5000},
        action={"type": "create_task", "title": "{summary}", "assignee_user_id": "u_ann"},
    )
    refused = client.post("/api/automations", json=task_for_ann)
    assert refused.status_code == 422 and "only assign tasks to you" in refused.json()["detail"]
    mine = body(
        trigger={"type": "metric", "metric": "cash_below", "value": 5000},
        action={"type": "create_task", "title": "{summary}"},
    )
    assert client.post("/api/automations", json=mine).status_code == 200
    # Non-money rules may still go to a teammate.
    assert client.post("/api/automations", json=body()).status_code == 200


def test_dismiss_alert(owner_client):
    client, db = owner_client
    db.anomaly_alerts.docs += [
        {"id": "a1", "workspace_id": "ws1", "status": "open", "title": "t", "created_at": "2026-10-13"},
        {"id": "a2", "workspace_id": "ws2", "status": "open", "title": "t", "created_at": "2026-10-13"},
    ]
    assert [a["id"] for a in client.get("/api/automations").json()["alerts"]] == ["a1"]
    assert client.post("/api/automations/alerts/a2/dismiss").status_code == 404  # someone else's
    assert client.post("/api/automations/alerts/a1/dismiss").status_code == 200
    assert client.get("/api/automations").json()["alerts"] == []
    assert client.post("/api/automations/alerts/a1/dismiss").status_code == 404


def test_run_now_is_rate_limited(owner_client):
    client, _ = owner_client
    server._automation_last_run_now.clear()
    with patch.object(server, "run_workspace_automations", AsyncMock(return_value={"fired": 0})) as run_ws:
        assert client.post("/api/automations/run").status_code == 200
        assert client.post("/api/automations/run").status_code == 429
    assert run_ws.await_count == 1
    server._automation_last_run_now.clear()


# ------------------------------------------------------------------ server glue

def _glue_db():
    db = new_db()
    db.workspaces.docs.append({"workspace_id": "ws1", "name": "Acme", "tasks": {"items": []}})
    db.memberships.docs += [
        {"workspace_id": "ws1", "user_id": "u_own", "email": "o@x.com", "role": "owner", "status": "active"},
        {"workspace_id": "ws1", "user_id": "u_ann", "email": "a@x.com", "role": "member", "status": "active"},
    ]
    db.users.docs += [{"user_id": "u_own", "name": "Owner"}, {"user_id": "u_ann", "name": "Ann"}]
    db.automation_rules.docs.append(task_rule())
    return db


def test_workspace_run_creates_tasks_alerts_and_stamps_the_scan():
    db = _glue_db()
    ledger = [entry(1, amount=5000, name="Steel"), entry(2, amount=5000, name="Steel")]
    inputs = (db.workspaces.docs[0], {"has_data": False, "currency_symbol": ""}, ledger, [sig()])
    with patch.object(server, "db", db), \
            patch.object(server, "_automation_inputs", AsyncMock(return_value=inputs)), \
            patch.object(server, "notify_task_delegated", AsyncMock(return_value={})) as notify, \
            patch.object(server, "invalidate_workspace_list_cache"):
        first = run(server.run_workspace_automations("ws1"))
        second = run(server.run_workspace_automations("ws1"))
    assert first["tasks"] == 1 and first["anomalies"]["new"] == 1
    assert second["tasks"] == 0 and second["anomalies"]["new"] == 0
    tasks = db.workspaces.docs[0]["tasks"]["items"]
    assert len(tasks) == 1 and tasks[0]["assignee_user_id"] == "u_ann" and tasks[0]["tag"] == "Automation"
    assert db.workspaces.docs[0]["automation_anomaly_scan_on"]
    notify.assert_awaited_once()  # Ann is told about her task once, not on the repeat run


def test_assignee_who_left_falls_back_to_the_owner():
    db = _glue_db()
    db.memberships.docs[1]["status"] = "removed"
    inputs = (db.workspaces.docs[0], {"has_data": False}, [], [sig()])
    with patch.object(server, "db", db), \
            patch.object(server, "_automation_inputs", AsyncMock(return_value=inputs)), \
            patch.object(server, "notify_task_delegated", AsyncMock(return_value={})), \
            patch.object(server, "invalidate_workspace_list_cache"):
        run(server.run_workspace_automations("ws1", anomalies=False))
    assert db.workspaces.docs[0]["tasks"]["items"][0]["assignee_user_id"] == "u_own"


def test_workspace_without_rules_skips_signal_work_when_only_scanning():
    db = new_db()
    db.workspaces.docs.append({"workspace_id": "ws1", "name": "Acme"})
    seen = {}

    async def inputs(wid, *, need_signals):
        seen["need_signals"] = need_signals
        return db.workspaces.docs[0], {"has_data": False}, [], []

    with patch.object(server, "db", db), patch.object(server, "_automation_inputs", inputs):
        run(server.run_workspace_automations("ws1", anomalies=True))
        assert seen["need_signals"] is False
        assert run(server.run_workspace_automations("ws1", anomalies=False))["rules"] == 0


def test_sweep_runs_rule_workspaces_always_and_scans_each_workspace_once_a_day():
    db = new_db()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    db.workspaces.docs += [
        {"workspace_id": "with_rules", "automation_anomaly_scan_on": today},
        {"workspace_id": "needs_scan"},
        {"workspace_id": "scanned_today", "automation_anomaly_scan_on": today},
    ]
    db.automation_rules.docs.append({"workspace_id": "with_rules", "enabled": True})
    db.automation_rules.docs.append({"workspace_id": "scanned_today", "enabled": False})
    calls = AsyncMock(return_value={})
    with patch.object(server, "db", db), patch.object(server, "run_workspace_automations", calls):
        run(server._automations_tick())
    got = {c.args[0]: c.kwargs["anomalies"] for c in calls.await_args_list}
    assert got == {"with_rules": False, "needs_scan": True}


def test_sweep_limits_daily_scans_per_tick_and_survives_a_failing_workspace():
    db = new_db()
    for i in range(server.AUTOMATION_SCANS_PER_TICK + 5):
        db.workspaces.docs.append({"workspace_id": f"ws{i}"})
    calls = AsyncMock(side_effect=RuntimeError("boom"))
    with patch.object(server, "db", db), patch.object(server, "run_workspace_automations", calls):
        run(server._automations_tick())
    assert calls.await_count == server.AUTOMATION_SCANS_PER_TICK
