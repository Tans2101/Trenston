"""Retention pass: setup checklist, decision edits, briefing links, work-item
deep links, workspace-local month boundaries, sample apply profile, calendar hrefs."""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_retention_connected")

import finance_recurrence as fr  # noqa: E402
import retention  # noqa: E402
import server  # noqa: E402
import work_items  # noqa: E402
from seed_data import build_workspace  # noqa: E402

PRINCIPAL = {
    "user_id": "u_owner",
    "email": "owner@example.com",
    "name": "Owner",
    "workspace_id": "ws1",
    "role": "owner",
    "pack": "owner",
}


# ---------------- Win-back nudge gate (item 2) ----------------

def test_inactivity_nudge_reaches_founders_who_bounced_at_template_screen():
    now = datetime(2026, 9, 28, tzinfo=timezone.utc)
    ws = {
        "onboarding_done": False,
        "company_setup_done": True,
        "last_active_at": (now - timedelta(days=10)).isoformat(),
    }
    assert retention.inactivity_nudge_due(ws, now=now) is True
    ws["company_setup_done"] = False
    assert retention.inactivity_nudge_due(ws, now=now) is False


# ---------------- Setup checklist (item 3) ----------------

def _checklist_db(*, updates_count=0):
    mock_db = MagicMock()
    mock_db.financial_entries.count_documents = AsyncMock(return_value=0)
    mock_db.memberships.count_documents = AsyncMock(return_value=1)
    captured = {}

    async def updates_count_documents(flt, *a, **k):
        captured["filter"] = flt
        return updates_count

    mock_db.updates.count_documents = updates_count_documents
    return mock_db, captured


def _run_checklist(ws, mock_db):
    with patch.object(server, "get_ws", AsyncMock(return_value=ws)), \
         patch.object(server, "db", mock_db), \
         patch.object(server.helm_analytics, "log_event_once", AsyncMock()):
        return asyncio.run(server.onboarding_checklist(PRINCIPAL))


def test_checklist_status_update_stays_done_after_first_day():
    ws = {"workspace_id": "ws1", "people": {"people": []}, "has_team": True}
    mock_db, captured = _checklist_db(updates_count=1)
    out = _run_checklist(ws, mock_db)
    step = next(s for s in out["steps"] if s["id"] == "update")
    assert step["done"] is True
    # Any past update counts — no "day" filter.
    assert "day" not in captured["filter"]
    assert captured["filter"]["user_id"] == "u_owner"


def test_checklist_omits_team_steps_for_solo_founder():
    ws = {"workspace_id": "ws1", "people": {"people": []}, "has_team": False}
    mock_db, _ = _checklist_db(updates_count=1)
    mock_db.financial_entries.count_documents = AsyncMock(return_value=3)
    out = _run_checklist(ws, mock_db)
    ids = [s["id"] for s in out["steps"]]
    assert ids == ["financials", "update"]
    assert out["complete"] is True


def test_checklist_keeps_team_steps_when_has_team():
    ws = {"workspace_id": "ws1", "people": {"people": []}, "has_team": True}
    mock_db, _ = _checklist_db()
    out = _run_checklist(ws, mock_db)
    assert [s["id"] for s in out["steps"]] == ["financials", "people", "invite", "update"]


# ---------------- Decision PATCH keeps confidence (item 4) ----------------

def _patch_decision(payload: dict):
    update = AsyncMock(return_value=MagicMock(matched_count=1))
    mock_db = MagicMock()
    mock_db.workspaces.update_one = update
    ws = {"workspace_id": "ws1", "decisions": [{"id": "d1", "confidence": 81}]}
    with patch.object(server, "get_ws", AsyncMock(return_value=ws)), \
         patch.object(server, "db", mock_db), \
         patch.object(server, "invalidate_workspace_list_cache"):
        asyncio.run(server.edit_decision("d1", server.DecisionInput(**payload), PRINCIPAL))
    args, kwargs = update.await_args
    assert kwargs.get("array_filters") == [{"d.id": "d1"}]
    return args[1]["$set"]


def test_decision_edit_with_null_confidence_keeps_ai_confidence():
    # Exactly what the Decisions edit form sends.
    set_fields = _patch_decision({
        "title": "Hire a PM", "category": "Hiring", "description": "d",
        "recommendation": "r", "due": "2026-10-01", "impact": "High", "confidence": None,
    })
    assert "decisions.$[d].confidence" not in set_fields
    assert set_fields["decisions.$[d].title"] == "Hire a PM"
    assert set_fields["decisions.$[d].impact"] == "High"
    assert set_fields["decisions.$[d].due"] == "2026-10-01"
    assert set_fields["decisions.$[d].description"] == "d"


def test_decision_edit_only_writes_sent_fields():
    set_fields = _patch_decision({"title": "Renamed"})
    assert set_fields == {"decisions.$[d].title": "Renamed"}


def test_decision_edit_explicit_confidence_still_updates():
    set_fields = _patch_decision({"title": "T", "confidence": 140})
    assert set_fields["decisions.$[d].confidence"] == 100


# ---------------- Accepting a suggestion keeps its signal (item 6) ----------------

SIGNAL = {
    "type": "overdue_legal_deadline",
    "severity": "high",
    "summary": "NDA overdue",
    "detail": "",
    "related_id": "lm_1",
    "department_type": "legal",
    "employee_id": "emp_9",
}


def test_approve_suggestion_copies_signal():
    ws = {
        "workspace_id": "ws1",
        "decisions": [],
        "decision_suggestions": [{
            "id": "s1", "status": "suggested", "title": "Chase NDA",
            "signal_type": "overdue_legal_deadline", "signal": dict(SIGNAL),
            "confidence": 70, "impact": "High",
        }],
    }
    update = AsyncMock()
    mock_db = MagicMock()
    mock_db.workspaces.update_one = update
    with patch.object(server, "get_ws", AsyncMock(return_value=ws)), \
         patch.object(server, "db", mock_db), \
         patch.object(server, "log_activity", AsyncMock()), \
         patch.object(server, "invalidate_workspace_list_cache"):
        out = asyncio.run(server.approve_decision_suggestion("s1", PRINCIPAL))
    d = out["decision"]
    assert d["signal_type"] == "overdue_legal_deadline"
    assert d["signal"] == SIGNAL
    assert d["confidence"] == 70
    stored = update.await_args.args[1]["$set"]["decisions"][0]
    assert stored["signal"]["related_id"] == "lm_1"
    assert stored["signal"]["department_type"] == "legal"
    # GET /decisions returns stored decisions as-is → signal comes through.
    ws_after = {**ws, "decisions": [stored], "decision_suggestions": []}
    with patch.object(server, "get_ws", AsyncMock(return_value=ws_after)), \
         patch.object(server, "can_section_write", AsyncMock(return_value=True)):
        listed = asyncio.run(server.decisions(PRINCIPAL))
    assert listed["decisions"][0]["signal"]["employee_id"] == "emp_9"


# ---------------- GET /briefing links (item 5) ----------------

@pytest.fixture
def briefing_client():
    # No context manager: skip startup hooks (they try to reach Mongo).
    app = server.app
    app.dependency_overrides[server.get_principal] = lambda: PRINCIPAL
    yield TestClient(app)
    app.dependency_overrides.pop(server.get_principal, None)


def _briefing_ws():
    decisions = [
        {"id": f"d{i}", "title": f"Decision {i}", "status": "pending", "impact": "Medium",
         "due": f"2026-10-0{i}"}
        for i in range(1, 7)
    ]
    decisions[0].update({
        "impact": "High", "signal_type": "overdue_legal_deadline", "signal": dict(SIGNAL),
    })
    return {
        "workspace_id": "ws1",
        "name": "Acme",
        "plan": "free",
        "briefing": {"headline": "Hi", "what_changed": []},
        "tasks": {"items": []},
        "people": {"people": []},
        "has_team": True,
        "decisions": decisions,
        "decision_suggestions": [{
            "id": "s1", "status": "suggested", "title": "Suggested", "impact": "Low",
            "signal": {"type": "hr_leave_pending", "related_id": "lr_1",
                       "department_type": "hr", "employee_id": "emp_2"},
        }],
        "delegate_suggestions": [{
            "id": "del1", "status": "suggested", "title": "Follow up WO",
            "signal_type": "overdue_work_order",
            "signal": {"type": "overdue_work_order", "related_id": "pwo_1",
                       "department_type": "production"},
        }],
    }


def _get_briefing(client, ws, *, can_act=True, acts=None):
    with patch.object(server, "get_ws", new=AsyncMock(return_value=ws)), \
         patch.object(server, "can_access_financials", new=AsyncMock(return_value=False)), \
         patch.object(server, "can_section_write", new=AsyncMock(return_value=can_act)), \
         patch.object(server, "_insights_stale", return_value=False), \
         patch.object(server, "_briefing_ops_metrics", new=AsyncMock(return_value=[])), \
         patch.object(server.helm_freshness, "resolve_workspace_data_as_of", new=AsyncMock(return_value={
             "data_as_of": None, "sources": {},
         })), \
         patch.object(server, "_briefing_gmail_swr", new=AsyncMock(return_value=([], {
             "connected": False, "needs_reconnect": False, "compose": False,
         }))), \
         patch.object(server.db, "activities", MagicMock()), \
         patch.object(server.db, "updates", MagicMock()), \
         patch.object(server.db, "workspaces", MagicMock()):
        server.db.activities.find.return_value.sort.return_value.to_list = AsyncMock(return_value=acts or [])
        server.db.updates.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
        server.db.workspaces.update_one = AsyncMock(return_value=None)
        r = client.get("/api/briefing")
    assert r.status_code == 200, r.text
    return r.json()


def test_briefing_exposes_can_act_and_total(briefing_client):
    body = _get_briefing(briefing_client, _briefing_ws(), can_act=False)
    assert body["can_act"] is False
    assert len(body["what_to_decide"]) == 5
    assert body["what_to_decide_total"] == 7
    body = _get_briefing(briefing_client, _briefing_ws(), can_act=True)
    assert body["can_act"] is True


def test_briefing_items_carry_link_fields(briefing_client):
    acts = [{
        "summary": "New decision: X", "actor_name": "Owner",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "module": "decisions", "related_id": "d1",
    }, {
        "summary": "Deal moved", "actor_name": "Owner",
        "created_at": datetime.now(timezone.utc).isoformat(), "module": "sales",
    }]
    body = _get_briefing(briefing_client, _briefing_ws(), acts=acts)
    top = body["what_to_decide"][0]
    assert top["id"] == "d1"
    assert top["signal_type"] == "overdue_legal_deadline"
    assert top["related_id"] == "lm_1"
    assert top["department_type"] == "legal"
    assert top["employee_id"] == "emp_9"
    # Existing keys intact.
    for key in ("title", "detail", "urgency", "impact", "due", "source", "confidence"):
        assert key in top
    plain = next(i for i in body["what_to_decide"] if i["id"] == "d2")
    assert "related_id" not in plain
    delegate = body["what_to_delegate"][0]
    assert delegate["signal_type"] == "overdue_work_order"
    assert delegate["related_id"] == "pwo_1"
    assert delegate["department_type"] == "production"
    changed = body["what_changed"]
    assert changed[0]["module"] == "decisions"
    assert changed[0]["related_id"] == "d1"
    assert changed[1]["module"] == "sales"
    assert "related_id" not in changed[1]


def test_what_to_decide_suggestion_link_fields_from_signal():
    items = server._briefing_what_to_decide_all(_briefing_ws())
    sug = next(i for i in items if i["id"] == "s1")
    assert sug["signal_type"] == "hr_leave_pending"
    assert sug["related_id"] == "lr_1"
    assert sug["employee_id"] == "emp_2"


# ---------------- Work item deep links (item 7) ----------------

def test_work_item_urls_deep_link():
    today = datetime(2026, 9, 28).date()

    def url(dtype, item_id):
        return work_items.work_row(
            item_id=item_id, department_type=dtype, title="x", due_raw=None,
            status="", today=today,
        )["url"]

    assert url("production", "pwo_1") == "/app/departments/production?item=pwo_1"
    assert url("procurement", "pr_1") == "/app/departments/procurement?item=pr_1"
    assert url("legal", "lm_1") == "/app/departments/legal?item=lm_1"
    assert url("engineering_maintenance", "mt_1") == "/app/departments/engineering_maintenance?item=mt_1"
    assert url("hr", "inst_1:step_2") == "/app/departments/hr?item=inst_1%3Astep_2"
    assert url("sales", "deal_1") == "/app/sales?deal=deal_1"
    assert work_items.task_url("t_1") == "/app/tasks?task=t_1"
    assert work_items.hr_leave_request_url("lr_1") == "/app/departments/hr?tab=leave&request=lr_1"
    assert work_items.decision_url("d_1") == "/app/decisions?focus=d_1"


# ---------------- Workspace-local month boundary (item 10) ----------------

# 2026-09-30 20:00 UTC == 2026-10-01 04:00 in Manila.
UTC_NOW = datetime(2026, 9, 30, 20, 0, tzinfo=timezone.utc)
MANILA_NOW = UTC_NOW.astimezone(ZoneInfo("Asia/Manila"))


def test_is_future_month_respects_local_now():
    assert fr.is_future_month("2026-10", UTC_NOW) is True
    assert fr.is_future_month("2026-10", MANILA_NOW) is False


def test_reject_future_month_uses_workspace_now():
    server._reject_future_fin_month("2026-10", MANILA_NOW)  # no raise
    with pytest.raises(HTTPException):
        server._reject_future_fin_month("2026-10", UTC_NOW)


def test_compute_financials_month_boundary_in_workspace_tz():
    import simple_cache
    simple_cache.clear()
    rows = [
        {"type": "expense", "category": "Ops", "amount": 500, "month": "2026-10", "recurring": False},
    ]
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=rows)
    mock_db = MagicMock()
    mock_db.workspaces.find_one = AsyncMock(return_value={
        "timezone": "Asia/Manila",
        "financial_settings": {"currency": "usd"},
    })
    mock_db.financial_entries.find = MagicMock(return_value=cursor)

    def fake_workspace_now(ws):
        return UTC_NOW.astimezone(server.tz_utils.workspace_tz(ws))

    with patch.object(server, "db", mock_db), \
         patch.object(server.tz_utils, "workspace_now", fake_workspace_now):
        fin = asyncio.run(server.compute_financials("ws_tz", bypass_cache=True))
    assert fin["scheduled_count"] == 0
    assert fin["horizon_month"] == "2026-10"


# ---------------- Sample apply preserves CompanySetup profile (item 11) ----------------

def _apply_sample(ws):
    ws_update = AsyncMock()
    mock_db = MagicMock()
    mock_db.workspaces.update_one = ws_update
    mock_db.financial_entries.delete_many = AsyncMock()
    mock_db.financial_entries.insert_many = AsyncMock()
    mock_db.financial_entries.count_documents = AsyncMock(return_value=0)
    mock_db.financial_entries.find_one = AsyncMock(return_value=None)
    with patch.object(server, "get_ws", AsyncMock(return_value=ws)), \
         patch.object(server, "db", mock_db), \
         patch.object(server.dept_migrate, "migrate_workspace_sales_finance", AsyncMock()), \
         patch.object(server.dept_migrate, "finance_department_id", AsyncMock(return_value=None)), \
         patch.object(server, "invalidate_financials_cache"):
        asyncio.run(server.apply_template(
            server.TemplateInput(template="sample"),
            {"user_id": "u1", "workspace_id": "ws1", "pack": "owner"},
        ))
    return ws_update.await_args.args[1]["$set"]


def test_sample_apply_keeps_company_setup_profile():
    ws = build_workspace("ws1", "Rice Mill Co", "u1", empty=True)
    ws.update({
        "company_setup_done": True, "industry": "Agriculture", "stage": "Growth",
        "mission": "Feed Manila", "founded": "2019", "employees": 12, "has_team": False,
    })
    update = _apply_sample(ws)
    assert update["industry"] == "Agriculture"
    assert update["stage"] == "Growth"
    assert update["mission"] == "Feed Manila"
    assert update["founded"] == "2019"
    assert update["employees"] == 12
    assert update["has_team"] is False
    assert update["company_setup_done"] is True
    # Sample content is still loaded.
    assert update["template"] == "sample"


def test_sample_apply_before_company_setup_uses_sample_profile():
    ws = build_workspace("ws1", "Fresh Co", "u1", empty=True)
    assert not ws.get("company_setup_done")
    update = _apply_sample(ws)
    assert update["industry"] == "Industrial Robotics"


# ---------------- Calendar deadline hrefs (item 13) ----------------

def test_deadline_events_carry_href_and_all_day():
    upcoming = [
        {"id": "d1", "title": "Decide", "date": "2026-10-01", "type": "Decision",
         "source_type": "decision", "source_id": "d1"},
        {"id": "t1", "title": "Task", "date": "2026-10-02", "type": "Task",
         "source_type": "task", "source_id": "t1"},
        {"id": "lr1", "title": "Leave", "date": "2026-10-03", "end_date": "2026-10-05",
         "type": "Leave", "source_type": "hr_leave_request", "source_id": "lr1"},
        {"id": "pwo1", "title": "WO", "date": "2026-10-04", "type": "Production",
         "source_type": "production_work_order", "source_id": "pwo1"},
        {"id": "lm1", "title": "NDA", "date": "2026-10-04", "type": "Legal",
         "source_type": "legal_matter", "source_id": "lm1"},
        {"id": "pr1", "title": "Bolts", "date": "2026-10-04", "type": "Procurement",
         "source_type": "procurement_request", "source_id": "pr1"},
    ]
    events = {e["id"]: e for e in server._deadlines_as_events(upcoming)}
    for e in events.values():
        assert e["all_day"] is True
        assert len(e["date"]) == 10
    assert events["deadline_d1"]["href"] == "/app/decisions?focus=d1"
    assert events["deadline_t1"]["href"] == "/app/tasks?task=t1"
    assert events["deadline_lr1"]["href"] == "/app/departments/hr?tab=leave&request=lr1"
    assert events["deadline_pwo1"]["href"] == "/app/departments/production?item=pwo1"
    assert events["deadline_lm1"]["href"] == "/app/departments/legal?item=lm1"
    assert events["deadline_pr1"]["href"] == "/app/departments/procurement?item=pr1"


# ---------------- Tasks: atomic writes (item 12) ----------------

def _task_ws():
    return {
        "workspace_id": "ws1",
        "name": "Acme",
        "tasks": {"columns": [], "items": [
            {"id": "t1", "title": "Ship", "column": "in_progress", "progress": 40,
             "assignee_user_id": "u_owner", "assignee": "Owner"},
            {"id": "t2", "title": "Done one", "column": "done", "progress": 100,
             "done_at": "2026-09-01T00:00:00+00:00", "assignee_user_id": "u_owner"},
        ]},
    }


def _task_db():
    mock_db = MagicMock()
    mock_db.workspaces.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    return mock_db


def test_create_task_pushes_instead_of_rewriting_board():
    mock_db = _task_db()
    with patch.object(server, "get_ws", AsyncMock(return_value=_task_ws())), \
         patch.object(server, "db", mock_db), \
         patch.object(server, "notify_task_delegated", AsyncMock()), \
         patch.object(server, "invalidate_workspace_list_cache"):
        out = asyncio.run(server.create_task(server.TaskInput(title="New"), PRINCIPAL))
    update = mock_db.workspaces.update_one.await_args.args[1]
    assert update == {"$push": {"tasks.items": out["task"]}}


def test_move_task_sets_only_changed_fields_with_array_filters():
    mock_db = _task_db()
    with patch.object(server, "get_ws", AsyncMock(return_value=_task_ws())), \
         patch.object(server, "db", mock_db), \
         patch.object(server, "can_section_write", AsyncMock(return_value=True)), \
         patch.object(server, "invalidate_workspace_list_cache"):
        asyncio.run(server.patch_task("t1", server.TaskPatch(column="done"), PRINCIPAL))
    args, kwargs = mock_db.workspaces.update_one.await_args
    assert args[0] == {"workspace_id": "ws1", "tasks.items.id": "t1"}
    assert kwargs["array_filters"] == [{"t.id": "t1"}]
    sets = args[1]["$set"]
    assert sets["tasks.items.$[t].column"] == "done"
    assert sets["tasks.items.$[t].progress"] == 100
    assert "tasks.items.$[t].done_at" in sets
    assert "tasks.items.$[t].title" not in sets
    assert "tasks" not in sets


def test_move_task_out_of_done_unsets_done_at():
    mock_db = _task_db()
    with patch.object(server, "get_ws", AsyncMock(return_value=_task_ws())), \
         patch.object(server, "db", mock_db), \
         patch.object(server, "can_section_write", AsyncMock(return_value=True)), \
         patch.object(server, "invalidate_workspace_list_cache"):
        asyncio.run(server.patch_task("t2", server.TaskPatch(column="backlog"), PRINCIPAL))
    update = mock_db.workspaces.update_one.await_args.args[1]
    assert update["$unset"] == {"tasks.items.$[t].done_at": ""}
    assert update["$set"]["tasks.items.$[t].progress"] == 50
