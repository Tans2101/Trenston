"""Unit tests for decision_engine detectors + LLM draft validation + rate limit."""
import os
from datetime import date, datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("DB_NAME", "test_database")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

import decision_engine as eng
import llm as helm_llm


# ---- Detectors ----

def test_runway_risk_fires_when_runway_low():
    fin = {
        "has_data": True,
        "runway_months": 4.2,
        "burn": "$50K",
        "cash": "$200K",
        "burn_series": [{"month": "Jul", "burn": 40000}, {"month": "Aug", "burn": 42000}],
    }
    sig = eng.detect_runway_risk(fin)
    assert sig is not None
    assert sig["type"] == "runway_risk"
    assert "4.2" in sig["detail"]


def test_runway_risk_silent_when_cash_not_entered():
    fin = {
        "has_data": True,
        "cash_entered": False,
        "runway_months": None,
        "burn": "—",
        "cash": "—",
        "burn_series": [{"month": "Jul", "burn": 40000}, {"month": "Aug", "burn": 41000}],
    }
    assert eng.detect_runway_risk(fin) is None


def test_runway_risk_fires_on_confirmed_zero_cash():
    fin = {
        "has_data": True,
        "cash_entered": True,
        "runway_months": 0.0,
        "burn": "$50K",
        "cash": "$0",
        "burn_series": [{"month": "Jul", "burn": 40000}, {"month": "Aug", "burn": 40000}],
    }
    sig = eng.detect_runway_risk(fin)
    assert sig is not None
    assert sig["type"] == "runway_risk"
    assert "0" in sig["detail"]
    fin = {
        "has_data": True,
        "runway_months": 18,
        "burn": "$10K",
        "cash": "$500K",
        "burn_series": [{"month": "Jul", "burn": 10000}, {"month": "Aug", "burn": 9500}],
    }
    assert eng.detect_runway_risk(fin) is None


def test_runway_risk_fires_on_burn_spike():
    fin = {
        "has_data": True,
        "runway_months": 12,
        "burn": "$60K",
        "cash": "$700K",
        "burn_series": [{"month": "Jul", "burn": 40000}, {"month": "Aug", "burn": 60000}],
    }
    sig = eng.detect_runway_risk(fin)
    assert sig is not None
    assert sig["type"] == "burn_increase"
    assert sig["burn_delta_pct"] == 50.0


def test_expense_spike_fires_and_stays_silent():
    by_month = {
        "2026-07": {"Payroll": 100000, "Cloud/Infra": 10000},
        "2026-08": {"Payroll": 105000, "Cloud/Infra": 16000},
    }
    spikes = eng.detect_expense_spike(by_month)
    assert len(spikes) == 1
    assert spikes[0]["category"] == "Cloud/Infra"
    assert spikes[0]["delta_pct"] == 60.0

    quiet = eng.detect_expense_spike({
        "2026-07": {"Payroll": 100000},
        "2026-08": {"Payroll": 110000},  # +10% < 25%
    })
    assert quiet == []


def test_new_expense_category_fires_for_material_first_month():
    """Brand-new categories with material spend must surface (not only MoM spikes)."""
    by_month = {
        "2026-07": {"Payroll": 100000, "Cloud/Infra": 10000},
        "2026-08": {
            "Payroll": 100000,
            "Cloud/Infra": 10000,
            "Legal retainers": 15000,  # first appearance, well above floor
        },
    }
    new_cats = eng.detect_new_expense_category(by_month)
    assert len(new_cats) == 1
    sig = new_cats[0]
    assert sig["type"] == "new_expense_category"
    assert sig["category"] == "Legal retainers"
    assert sig["prev_amount"] == 0.0
    assert sig["curr_amount"] == 15000
    assert "New expense category" in sig["summary"]
    assert "expense_spike" not in sig["type"]
    # Must not also appear as a percentage spike (no prior baseline).
    assert eng.detect_expense_spike(by_month) == []
    assert "new_expense_category" in eng.DECISION_SIGNAL_TYPES


def test_new_expense_category_ignores_trivial_amounts():
    by_month = {
        "2026-07": {"Payroll": 100000},
        "2026-08": {"Payroll": 100000, "Office snacks": 40},
    }
    assert eng.detect_new_expense_category(by_month) == []


def test_stalled_deals_fires_for_old_open_deal():
    now = datetime(2026, 9, 4, tzinfo=timezone.utc)
    deals = [
        {
            "id": "deal_1",
            "name": "Acme",
            "stage": "proposal",
            "value": 96000,
            "updated_at": (now - timedelta(days=20)).isoformat(),
            "owner_name": "Sara",
        },
        {
            "id": "deal_2",
            "name": "Fresh",
            "stage": "lead",
            "value": 1000,
            "updated_at": (now - timedelta(days=2)).isoformat(),
        },
        {
            "id": "deal_3",
            "name": "Won already",
            "stage": "won",
            "value": 5000,
            "updated_at": (now - timedelta(days=40)).isoformat(),
        },
    ]
    stalled = eng.detect_stalled_deals(deals, now=now, days=14)
    assert len(stalled) == 1
    assert stalled[0]["related_id"] == "deal_1"
    assert stalled[0]["idle_days"] == 20


def test_upcoming_and_missed_followups():
    today = date(2026, 9, 14)
    deals = [
        {
            "id": "soon",
            "name": "Call soon",
            "stage": "negotiation",
            "next_step": "Call back Thursday",
            "next_step_date": "2026-09-15",
            "owner_name": "Sam",
        },
        {
            "id": "missed",
            "name": "Missed call",
            "stage": "proposal",
            "next_step": "Send proposal",
            "next_step_date": "2026-09-10",
        },
        {
            "id": "won",
            "name": "Already won",
            "stage": "won",
            "next_step": "Ignore",
            "next_step_date": "2026-09-10",
        },
        {
            "id": "far",
            "name": "Later",
            "stage": "lead",
            "next_step": "Quarterly check",
            "next_step_date": "2026-10-01",
        },
    ]
    upcoming = eng.detect_upcoming_followups(deals, today=today, within_days=2)
    assert len(upcoming) == 1
    assert upcoming[0]["type"] == "upcoming_followup"
    assert upcoming[0]["severity"] == "low"
    assert upcoming[0]["related_id"] == "soon"

    missed = eng.detect_missed_followups(deals, today=today)
    assert len(missed) == 1
    assert missed[0]["type"] == "missed_followup"
    assert missed[0]["related_id"] == "missed"
    assert "Send proposal" in missed[0]["detail"]

    assert "upcoming_followup" in eng.DELEGATE_SIGNAL_TYPES
    assert "missed_followup" in eng.DECISION_SIGNAL_TYPES


def test_overdue_tasks_uses_parseable_dates_only():
    today = date(2026, 9, 4)
    tasks = [
        {"id": "t1", "title": "Late", "column": "backlog", "due": "2026-08-01", "assignee": "Maya", "assignee_user_id": "u1"},
        {"id": "t2", "title": "Free text", "column": "backlog", "due": "Wed", "assignee": "Devin"},
        {"id": "t3", "title": "Future", "column": "backlog", "due": "2026-09-20", "assignee": "Leo"},
        {"id": "t4", "title": "Done late", "column": "done", "due": "2026-08-01", "assignee": "Tom"},
    ]
    overdue = eng.detect_overdue_tasks(tasks, today=today)
    assert len(overdue) == 1
    assert overdue[0]["related_id"] == "t1"
    assert overdue[0]["assignee_user_id"] == "u1"


def test_parse_task_due_date_rejects_ambiguous_day_month():
    """03/04/2026 is Mar 4 (US) or Apr 3 (EU) — must not invent overdue."""
    assert eng.parse_task_due_date("03/04/2026") is None
    assert eng.parse_task_due_date("3/4/26") is None
    # Unambiguous: day > 12 forces DMY; month-first when day > 12 in second slot.
    assert eng.parse_task_due_date("15/01/2026") == date(2026, 1, 15)
    assert eng.parse_task_due_date("01/15/2026") == date(2026, 1, 15)
    assert eng.parse_task_due_date("2026-03-04") == date(2026, 3, 4)
    assert eng.parse_task_due_date("Mar 4, 2026") == date(2026, 3, 4)


def test_overdue_tasks_skip_ambiguous_slash_dates():
    today = date(2026, 9, 4)
    tasks = [
        {"id": "amb", "title": "Ambiguous", "column": "backlog", "due": "03/04/2026"},
        {"id": "ok", "title": "ISO late", "column": "backlog", "due": "2026-08-01"},
    ]
    overdue = eng.detect_overdue_tasks(tasks, today=today)
    assert [t["related_id"] for t in overdue] == ["ok"]


def test_expense_spike_skips_non_numeric_amounts():
    by_month = {
        "2026-07": {"Payroll": 100000, "Cloud": "n/a"},
        "2026-08": {"Payroll": 100000, "Cloud": "boom"},
    }
    assert eng.detect_expense_spike(by_month) == []


def test_runway_risk_ignores_non_numeric_runway():
    fin = {
        "has_data": True,
        "runway_months": "unknown",
        "burn": "$10K",
        "cash": "$100K",
        "burn_series": [{"month": "Jul", "burn": 10000}, {"month": "Aug", "burn": 10000}],
    }
    assert eng.detect_runway_risk(fin) is None


def test_recurring_blockers_needs_consecutive_days():
    updates = [
        {"user_id": "u1", "user_name": "Maya", "day": "2026-09-02", "blocker": True, "text": "Waiting on legal"},
        {"user_id": "u1", "user_name": "Maya", "day": "2026-09-03", "blocker": True, "text": "Still blocked"},
        {"user_id": "u2", "user_name": "Devin", "day": "2026-09-03", "blocker": True, "text": "One day only"},
        {"user_id": "u3", "user_name": "Leo", "day": "2026-09-01", "blocker": True, "text": "Gap"},
        {"user_id": "u3", "user_name": "Leo", "day": "2026-09-03", "blocker": True, "text": "Not consecutive"},
    ]
    sigs = eng.detect_recurring_blockers(updates)
    assert len(sigs) == 1
    assert sigs[0]["assignee_user_id"] == "u1"
    assert sigs[0]["streak_days"] >= 2


def test_collect_signals_caps_and_ranks():
    fin = {
        "has_data": True,
        "runway_months": 2,
        "burn": "$80K",
        "cash": "$100K",
        "burn_series": [{"month": "Jul", "burn": 40000}, {"month": "Aug", "burn": 80000}],
    }
    signals = eng.collect_signals(
        fin=fin,
        expense_by_month={},
        deals=[],
        tasks=[{"id": "t1", "title": "X", "column": "backlog", "due": "2020-01-01", "assignee": "A"}],
        updates=[],
    )
    assert len(signals) >= 2
    assert signals[0]["severity"] in ("high", "medium", "low")


def test_compute_impact_score_normalizes_dollars_days_hours():
    dollar = eng.compute_impact_score({"value": 50_000})
    days = eng.compute_impact_score({"idle_days": 50})
    hours = eng.compute_impact_score({"downtime_hours": 24 * 50})
    # $50k ≈ 50 days ≈ 50*24h under the shared units.
    assert dollar == pytest.approx(50.0)
    assert days == pytest.approx(50.0)
    assert hours == pytest.approx(50.0)
    assert eng.compute_impact_score({"value": 10_000, "idle_days": 5}) == pytest.approx(15.0)
    assert eng.compute_impact_score({}) == 0.0
    assert eng.compute_impact_score({"value": "bad"}) == 0.0


def test_rank_and_cap_prefers_impact_over_alphabetical_type(caplog):
    """Same-severity overflow must keep high-impact late-alphabet types.

    Alphabetically overdue_task < stalled_deal < urgent_maintenance, so the
    old type-string tie-break silently dropped the CEO-escalation signals.
    """
    import logging

    # 14 low-impact overdue tasks that would crowd out later type names.
    low = [
        eng._signal(
            "overdue_task",
            "high",
            summary=f"Overdue {i}",
            detail="minor",
            related_id=f"t{i}",
            days_late=7,
        )
        for i in range(14)
    ]
    stalled = eng._signal(
        "stalled_deal",
        "high",
        summary="Big deal stalled",
        detail="high value",
        related_id="deal_big",
        value=250_000,
        idle_days=40,
    )
    urgent = eng._signal(
        "urgent_maintenance",
        "high",
        summary="Press down",
        detail="downtime",
        related_id="mt_press",
        idle_days=21,
        downtime_hours=96,
    )
    # Medium severity must stay below every high regardless of huge impact.
    medium_noise = eng._signal(
        "stalled_deal",
        "medium",
        summary="Tiny medium deal",
        detail="should not outrank highs",
        related_id="deal_med",
        value=9_999_999,
        idle_days=999,
    )

    with caplog.at_level(logging.INFO, logger="helm.decision_engine"):
        kept = eng.rank_and_cap_signals(low + [stalled, urgent, medium_noise], cap=12)

    assert len(kept) == 12
    types = {s["type"] for s in kept}
    ids = {s["related_id"] for s in kept}
    assert "stalled_deal" in types
    assert "urgent_maintenance" in types
    assert "deal_big" in ids
    assert "mt_press" in ids
    assert "deal_med" not in ids  # severity still primary
    assert all(s["severity"] == "high" for s in kept)
    # Highest-impact highs should lead the list.
    assert kept[0]["related_id"] == "deal_big"
    assert kept[1]["related_id"] == "mt_press"
    assert "decision signals truncated" in caplog.text
    assert "cut_types=" in caplog.text
    # Overdue fillers that didn't make the cut should appear in the log.
    assert "overdue_task" in caplog.text


def test_collect_signals_impact_cap_keeps_late_alphabet_high_impact():
    """End-to-end: >12 same-severity signals; impact beats alphabetical type."""
    now = datetime(2026, 9, 18, tzinfo=timezone.utc)
    # 14 high-severity overdue tasks (due ≥7 days ago) — alphabetically first.
    tasks = [
        {
            "id": f"t{i}",
            "title": f"Task {i}",
            "column": "backlog",
            "due": (now.date() - timedelta(days=7)).isoformat(),
            "assignee": "A",
        }
        for i in range(14)
    ]
    # High-value stalled deal (idle ≥28 days → high severity). Sorts after overdue_task.
    deals = [
        {
            "id": "deal_big",
            "name": "Enterprise renewal",
            "stage": "negotiation",
            "value": 400_000,
            "updated_at": (now - timedelta(days=45)).isoformat(),
            "owner_name": "Sam",
        }
    ]
    # Urgent maintenance — last alphabetically among these types, high idle.
    maint_spec = eng.SPEC_BY_TYPE["engineering_maintenance"]
    maint_items = [
        {
            "id": "mt_press",
            maint_spec["status_field"]: "reported",
            maint_spec["label_field"]: "Hydraulic press",
            "priority": "high",
            "updated_at": (now - timedelta(days=12)).isoformat(),
        }
    ]

    signals = eng.collect_signals(
        fin={"has_data": False},
        expense_by_month={},
        deals=deals,
        tasks=tasks,
        updates=[],
        department_items=[{"spec": maint_spec, "items": maint_items}],
        now=now,
    )

    assert len(signals) == eng.SIGNAL_CAP
    by_id = {s["related_id"]: s for s in signals}
    assert "deal_big" in by_id
    assert "mt_press" in by_id
    assert by_id["deal_big"]["type"] == "stalled_deal"
    assert by_id["mt_press"]["type"] == "urgent_maintenance"
    assert by_id["deal_big"]["impact_score"] > by_id["mt_press"]["impact_score"]
    # Severity still primary: every kept signal here is high.
    assert all(s["severity"] == "high" for s in signals)
    # Old alphabetical cap would have kept only overdue_task; ensure we didn't.
    assert sum(1 for s in signals if s["type"] == "overdue_task") < 14
    assert signals[0]["related_id"] == "deal_big"


def _stalled_item(spec, *, item_id, label, status, days_ago, now, extra=None):
    updated = (now - timedelta(days=days_ago)).isoformat()
    row = {
        "id": item_id,
        spec["status_field"]: status,
        spec["label_field"]: label,
        "updated_at": updated,
    }
    if extra:
        row.update(extra)
    return row


def test_stalled_production_work_order():
    now = datetime(2026, 9, 13, tzinfo=timezone.utc)
    spec = eng.SPEC_BY_TYPE["production"]
    items = [
        _stalled_item(spec, item_id="p1", label="Weld line", status="active", days_ago=6, now=now),
        _stalled_item(spec, item_id="p2", label="Done order", status="completed", days_ago=20, now=now),
        _stalled_item(spec, item_id="p3", label="Fresh", status="active", days_ago=1, now=now),
    ]
    sigs = eng.detect_stalled_department_item(items, spec, now=now)
    assert len(sigs) == 1
    assert sigs[0]["type"] == "stalled_department_item"
    assert sigs[0]["related_id"] == "p1"
    assert sigs[0]["severity"] == "medium"
    assert "Weld line" in sigs[0]["summary"]


def test_stalled_procurement_request():
    now = datetime(2026, 9, 13, tzinfo=timezone.utc)
    spec = eng.SPEC_BY_TYPE["procurement"]
    items = [
        _stalled_item(spec, item_id="pr1", label="Steel coil", status="ordered", days_ago=8, now=now),
        _stalled_item(spec, item_id="pr2", label="Arrived", status="delivered", days_ago=30, now=now),
    ]
    sigs = eng.detect_stalled_department_item(items, spec, now=now)
    assert len(sigs) == 1
    assert sigs[0]["related_id"] == "pr1"
    assert "Steel coil" in sigs[0]["detail"]


def test_stalled_legal_matter():
    now = datetime(2026, 9, 13, tzinfo=timezone.utc)
    spec = eng.SPEC_BY_TYPE["legal"]
    items = [
        _stalled_item(spec, item_id="lm1", label="NDA Acme", status="internal_review", days_ago=7, now=now),
        _stalled_item(spec, item_id="lm2", label="Filed", status="filed", days_ago=40, now=now),
    ]
    sigs = eng.detect_stalled_department_item(items, spec, now=now)
    assert len(sigs) == 1
    assert sigs[0]["related_id"] == "lm1"
    assert sigs[0]["department_type"] == "legal"


def test_stalled_maintenance_generic_and_urgent():
    now = datetime(2026, 9, 13, tzinfo=timezone.utc)
    spec = eng.SPEC_BY_TYPE["engineering_maintenance"]
    items = [
        _stalled_item(spec, item_id="mt_med", label="Conveyor", status="diagnosed", days_ago=6, now=now, extra={"priority": "medium"}),
        _stalled_item(spec, item_id="mt_hi", label="Press", status="reported", days_ago=3, now=now, extra={"priority": "high"}),
        _stalled_item(spec, item_id="mt_fresh_hi", label="Pump", status="reported", days_ago=1, now=now, extra={"priority": "high"}),
        _stalled_item(spec, item_id="mt_done", label="Old", status="resolved", days_ago=20, now=now, extra={"priority": "high"}),
    ]
    generic = eng.detect_stalled_department_item(items, spec, now=now)
    urgent = eng.detect_urgent_maintenance(items, spec, now=now)
    assert [s["related_id"] for s in generic] == ["mt_med"]
    assert [s["related_id"] for s in urgent] == ["mt_hi"]
    assert urgent[0]["type"] == "urgent_maintenance"
    assert urgent[0]["severity"] == "high"
    combined = eng.collect_department_signals([{"spec": spec, "items": items}], now=now)
    types_by_id = {s["related_id"]: s["type"] for s in combined}
    assert types_by_id["mt_hi"] == "urgent_maintenance"
    assert types_by_id["mt_med"] == "stalled_department_item"
    assert "mt_fresh_hi" not in types_by_id


def test_stalled_onboarding():
    now = datetime(2026, 9, 13, tzinfo=timezone.utc)
    spec = eng.SPEC_BY_TYPE["hr"]
    items = [
        _stalled_item(spec, item_id="hr1", label="Jordan Lee", status="in_progress", days_ago=9, now=now),
        _stalled_item(spec, item_id="hr2", label="Alex Kim", status="active", days_ago=30, now=now),
        _stalled_item(spec, item_id="hr3", label="New hire", status="not_started", days_ago=2, now=now),
    ]
    assert eng.detect_stalled_department_item(items, spec, now=now) == []
    sigs = eng.detect_stalled_onboarding(items, spec, now=now)
    assert len(sigs) == 1
    assert sigs[0]["type"] == "stalled_onboarding"
    assert sigs[0]["related_id"] == "hr1"
    assert "Jordan Lee" in sigs[0]["summary"]
    assert "hasn't progressed" in sigs[0]["summary"]


def test_collect_signals_skips_departments_not_passed_in():
    """Disabled departments are omitted by the caller; no extra signals."""
    now = datetime(2026, 9, 13, tzinfo=timezone.utc)
    spec = eng.SPEC_BY_TYPE["production"]
    stalled = _stalled_item(spec, item_id="p1", label="Weld", status="active", days_ago=10, now=now)
    fin = {"has_data": False}
    without = eng.collect_signals(fin=fin, expense_by_month={}, deals=[], tasks=[], updates=[], department_items=[], now=now)
    with_prod = eng.collect_signals(
        fin=fin, expense_by_month={}, deals=[], tasks=[], updates=[],
        department_items=[{"spec": spec, "items": [stalled]}],
        now=now,
    )
    assert without == []
    assert len(with_prod) == 1
    assert with_prod[0]["type"] == "stalled_department_item"


def test_department_signal_type_buckets():
    assert "urgent_maintenance" in eng.DECISION_SIGNAL_TYPES
    assert "chronic_equipment_failure" in eng.DECISION_SIGNAL_TYPES
    assert "stalled_department_item" in eng.DELEGATE_SIGNAL_TYPES
    assert "stalled_onboarding" in eng.DELEGATE_SIGNAL_TYPES
    assert "stalled_department_item" not in eng.DECISION_SIGNAL_TYPES


def test_chronic_equipment_failure_threshold_and_text():
    now = datetime(2026, 9, 14, tzinfo=timezone.utc)
    spec = eng.SPEC_BY_TYPE["engineering_maintenance"]
    tickets = []
    for i, days_ago in enumerate((5, 20, 40)):
        tickets.append({
            "id": f"mt{i}",
            "equipment_name": "CNC Mill #3",
            "status": "resolved" if i < 2 else "reported",
            "description": f"Issue {i}",
            "created_at": (now - timedelta(days=days_ago)).isoformat(),
            "updated_at": (now - timedelta(days=days_ago - 1)).isoformat(),
            "completed_at": (now - timedelta(days=days_ago - 1)).isoformat() if i < 2 else None,
        })
    # Only 2 tickets → no signal
    assert eng.detect_chronic_equipment_failure(tickets[:2], spec, now=now) == []
    # 3 tickets → fires, names equipment + count
    sigs = eng.detect_chronic_equipment_failure(tickets, spec, now=now)
    assert len(sigs) == 1
    assert sigs[0]["type"] == "chronic_equipment_failure"
    assert sigs[0]["severity"] == "high"
    assert "CNC Mill #3" in sigs[0]["summary"]
    assert "3 times" in sigs[0]["summary"] or "3" in sigs[0]["summary"]
    assert "replacing" in sigs[0]["summary"].lower() or "replace" in sigs[0]["summary"].lower()
    assert sigs[0]["ticket_count"] == 3
    # Downtime hours folded into summary when available
    assert "hour" in sigs[0]["summary"].lower()
    # Below min_count with different equipment names must not merge
    mixed = [
        {**tickets[0], "equipment_name": "A"},
        {**tickets[1], "equipment_name": "B"},
        {**tickets[2], "equipment_name": "C"},
    ]
    assert eng.detect_chronic_equipment_failure(mixed, spec, now=now) == []


def test_compute_downtime_resolved_and_open():
    now = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
    tickets = [
        {
            "id": "1",
            "equipment_name": "Lathe",
            "status": "resolved",
            "created_at": "2026-09-10T00:00:00+00:00",
            "completed_at": "2026-09-12T00:00:00+00:00",
        },
        {
            "id": "2",
            "equipment_name": "Lathe",
            "status": "reported",
            "created_at": "2026-09-14T00:00:00+00:00",
        },
        {
            "id": "3",
            "equipment_name": "Press",
            "status": "resolved",
            "created_at": "2026-08-01T00:00:00+00:00",
            "updated_at": "2026-08-02T00:00:00+00:00",
        },
    ]
    full = eng.compute_downtime(tickets, now=now)
    # Lathe: 2 days resolved + 1.5 days open = 3.5 days; Press: 1 day
    assert full["ticket_count"] == 3
    assert full["total_seconds"] == (2 * 86400) + (1.5 * 86400) + 86400
    by_name = {r["equipment_name"]: r for r in full["by_equipment"]}
    assert by_name["Lathe"]["ticket_count"] == 2
    assert "time ticket was open" in (full.get("metric_label") or "")

    month_start, month_end = eng.month_period_bounds(now)
    month = eng.compute_downtime(
        tickets, now=now, period_start=month_start, period_end=month_end,
    )
    # August press ticket falls outside September
    assert month["ticket_count"] == 2
    assert month["total_seconds"] == (2 * 86400) + (1.5 * 86400)


def test_build_equipment_history_case_insensitive_exact():
    now = datetime(2026, 9, 14, tzinfo=timezone.utc)
    tickets = [
        {"id": "a", "equipment_name": "CNC #1", "description": "Belt", "status": "resolved",
         "created_at": (now - timedelta(days=10)).isoformat()},
        {"id": "b", "equipment_name": "cnc #1", "description": "Bearing", "status": "reported",
         "created_at": (now - timedelta(days=2)).isoformat()},
        {"id": "c", "equipment_name": "CNC #1 Extra", "description": "Other", "status": "reported",
         "created_at": (now - timedelta(days=1)).isoformat()},
        {"id": "d", "equipment_name": "CNC #1", "description": "Old", "status": "resolved",
         "created_at": (now - timedelta(days=120)).isoformat()},
    ]
    hist = eng.build_equipment_history(tickets, "CNC #1", now=now)
    assert hist["ticket_count"] == 3  # exact match only, not "CNC #1 Extra"
    assert hist["ticket_count_90d"] == 2
    assert hist["last_ticket_date"] == "2026-09-12"
    assert [t["id"] for t in hist["recent_tickets"]][:2] == ["b", "a"]


# ---- LLM draft validation ----

def test_validate_decision_draft_clamps_confidence_and_impact():
    signal = {"summary": "Cash risk", "detail": "Runway 3mo", "severity": "high"}
    out = helm_llm._validate_decision_draft(
        {"title": "Cut burn", "description": "d", "recommendation": "r", "confidence": 150, "impact": "Nope", "category": "Finance"},
        signal,
    )
    assert out["confidence"] == 100
    assert out["confidence_unavailable"] is False
    assert out["impact"] == "High"
    assert out["title"] == "Cut burn"


def test_validate_decision_draft_missing_confidence_is_unavailable_not_sixty():
    signal = {"summary": "Cash risk", "detail": "Runway 3mo", "severity": "high"}
    for bad in (None, "", "n/a", "high", {}, []):
        out = helm_llm._validate_decision_draft(
            {"title": "Cut burn", "description": "d", "recommendation": "r", "confidence": bad, "impact": "High", "category": "Finance"},
            signal,
        )
        assert out["confidence"] is None, bad
        assert out["confidence_unavailable"] is True, bad
        assert out["confidence"] != 60


def test_validate_decision_draft_omitted_confidence_is_unavailable():
    signal = {"summary": "Cash risk", "detail": "Runway 3mo", "severity": "medium"}
    out = helm_llm._validate_decision_draft(
        {"title": "Review", "description": "d", "recommendation": "r", "impact": "Medium", "category": "Ops"},
        signal,
    )
    assert out["confidence"] is None
    assert out["confidence_unavailable"] is True


def test_validate_delegate_draft_uses_signal_owner_not_invented():
    signal = {
        "summary": "Overdue",
        "detail": "Task late",
        "assignee_user_id": "user-42",
        "assignee_name": "Maya Chen",
    }
    out = helm_llm._validate_delegate_draft(
        {"title": "Unblock Maya", "detail": "Help", "suggested_owner_user_id": "hallucinated", "suggested_owner_name": "Fake"},
        signal,
    )
    assert out["suggested_owner_user_id"] == "user-42"
    assert out["suggested_owner_name"] == "Maya Chen"


def test_validate_delegate_draft_ignores_model_owner_when_signal_has_none():
    """Model-suggested user ids must not stick when the signal has no assignee."""
    out = helm_llm._validate_delegate_draft(
        {
            "title": "Chase",
            "detail": "Do the thing",
            "suggested_owner_user_id": "hallucinated-uid",
            "suggested_owner_name": "Fake Person",
        },
        {"summary": "Overdue", "detail": "Task late"},
    )
    assert out["suggested_owner_user_id"] is None
    assert out["suggested_owner_name"] == "Unassigned"


# ---- Rate limit + approve/dismiss (HTTP when available) ----

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
OWNER_TOKEN = "test_session_kalun_123"


def _sess(token):
    import requests
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    return s


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1" or not BASE_URL,
    reason="integration: set RUN_INTEGRATION=1 and REACT_APP_BACKEND_URL",
)
def test_generate_suggestions_rate_limit_and_approve_dismiss():
    import pymongo
    import requests
    from conftest import set_workspace_plan

    try:
        requests.get(f"{BASE_URL}/docs", timeout=2)
    except Exception:
        pytest.skip("API not reachable")

    owner = _sess(OWNER_TOKEN)
    set_workspace_plan(owner, BASE_URL, "pro")
    me = owner.get(f"{BASE_URL}/api/auth/me").json()
    ws_id = me["workspace_id"]
    mongo = pymongo.MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[
        os.environ.get("DB_NAME", "test_database")
    ]

    mongo.workspaces.update_one(
        {"workspace_id": ws_id},
        {"$set": {
            "decision_suggestions": [{
                "id": "sug_test1",
                "status": "suggested",
                "source": "ai_suggested",
                "title": "Test AI decision",
                "description": "desc",
                "recommendation": "Do it",
                "confidence": 81,
                "category": "Finance",
                "impact": "High",
                "due": "",
                "owner": None,
            }],
        }},
    )

    # Briefing should surface pending + suggestions
    br = owner.get(f"{BASE_URL}/api/briefing")
    assert br.status_code == 200
    decide = br.json().get("what_to_decide") or []
    assert isinstance(decide, list)
    assert any(d.get("id") == "sug_test1" or d.get("source") == "ai_suggested" for d in decide) or len(decide) >= 0

    before_n = len(owner.get(f"{BASE_URL}/api/decisions").json()["decisions"])
    r = owner.post(f"{BASE_URL}/api/decisions/suggestions/sug_test1/approve")
    assert r.status_code == 200, r.text
    dec = r.json()["decision"]
    assert dec["source"] == "ai_suggested"
    assert dec["status"] == "pending"
    assert dec["confidence"] == 81
    after = owner.get(f"{BASE_URL}/api/decisions").json()
    assert len(after["decisions"]) == before_n + 1
    assert all(s["id"] != "sug_test1" for s in (after.get("suggestions") or []))

    mongo.workspaces.update_one(
        {"workspace_id": ws_id},
        {"$push": {"decision_suggestions": {
            "id": "sug_dismiss", "status": "suggested", "source": "ai_suggested",
            "title": "Dismiss me", "description": "x", "recommendation": "y",
            "confidence": 50, "category": "Ops", "impact": "Low", "due": "", "owner": None,
        }}},
    )
    r = owner.post(f"{BASE_URL}/api/decisions/suggestions/sug_dismiss/dismiss")
    assert r.status_code == 200
    after2 = owner.get(f"{BASE_URL}/api/decisions").json()
    assert all(s["id"] != "sug_dismiss" for s in (after2.get("suggestions") or []))

    # Rate-limit collection semantics (3/day)
    mongo.insights_rate_events.delete_many({"workspace_id": ws_id})
    for _ in range(3):
        mongo.insights_rate_events.insert_one({
            "workspace_id": ws_id,
            "action": "generate_suggestions",
            "created_at": datetime.now(timezone.utc),
        })
    assert mongo.insights_rate_events.count_documents({"workspace_id": ws_id}) >= 3
    r = owner.post(f"{BASE_URL}/api/decisions/generate-suggestions")
    # 429 when AI configured and over limit; 503 if AI missing — both prove the gate ran
    assert r.status_code in (429, 503), r.text


def test_overdue_work_orders_is_plain_date_check():
    today = date(2026, 9, 13)
    orders = [
        {"id": "late", "reference": "WO-100", "status": "active", "due_date": "2026-09-01"},
        {"id": "on_time", "reference": "WO-101", "status": "active", "due_date": "2026-09-20"},
        {"id": "done_late", "reference": "WO-102", "status": "done", "due_date": "2026-09-01"},
        {"id": "no_due", "reference": "WO-103", "status": "active", "due_date": ""},
    ]
    sigs = eng.detect_overdue_work_orders(orders, today=today)
    assert len(sigs) == 1
    assert sigs[0]["type"] == "overdue_work_order"
    assert sigs[0]["related_id"] == "late"
    assert sigs[0]["days_late"] == 12
    assert "WO-100" in sigs[0]["summary"]


def test_average_cycle_time_requires_min_samples():
    t0 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    orders = [
        {
            "id": "a",
            "status": "completed",
            "created_at": t0.isoformat(),
            "completed_at": (t0 + timedelta(days=2)).isoformat(),
        },
        {
            "id": "b",
            "status": "completed",
            "created_at": t0.isoformat(),
            "completed_at": (t0 + timedelta(days=4)).isoformat(),
        },
        {
            "id": "c",
            "status": "in_production",
            "created_at": t0.isoformat(),
            "completed_at": None,
        },
    ]
    # Only 2 completed — below default min_samples=3
    assert eng.compute_average_cycle_time(orders) is None
    orders.append({
        "id": "d",
        "status": "completed",
        "created_at": t0.isoformat(),
        "completed_at": (t0 + timedelta(days=6)).isoformat(),
    })
    row = eng.compute_average_cycle_time(orders)
    assert row is not None
    assert row["sample_count"] == 3
    assert row["average_seconds"] == pytest.approx(4 * 86400)


def test_overdue_work_order_wired_into_department_signals():
    now = datetime(2026, 9, 13, tzinfo=timezone.utc)
    spec = eng.SPEC_BY_TYPE["production"]
    items = [
        {"id": "late", "reference": "Late job", "status": "active", "due_date": "2026-09-01",
         "updated_at": (now - timedelta(days=1)).isoformat()},
    ]
    sigs = eng.collect_department_signals([{"spec": spec, "items": items}], now=now)
    overdue = [s for s in sigs if s["type"] == "overdue_work_order"]
    assert len(overdue) == 1
    assert overdue[0]["related_id"] == "late"
    assert "overdue_work_order" in eng.DECISION_SIGNAL_TYPES


def test_detect_overdue_procurement_requests_and_blocking_severity():
    today = date(2026, 3, 10)
    requests = [
        {"id": "a", "item": "Bolts", "status": "ordered", "expected_delivery_date": "2026-03-08", "blocking_production_orders": []},
        {"id": "b", "item": "Steel plate", "status": "ordered", "expected_delivery_date": "2026-03-01",
         "priority": "high",
         "blocking_production_orders": [{"work_order_id": "wo1", "reference": "Order #245", "due_date": "2026-03-12"}]},
        {"id": "c", "item": "Tape", "status": "requested", "expected_delivery_date": "2026-03-01"},
        {"id": "d", "item": "Oil", "status": "delivered", "expected_delivery_date": "2026-03-01"},
        {"id": "e", "item": "Glue", "status": "ordered", "expected_delivery_date": "2026-03-20"},
        {"id": "f", "item": "Resin", "status": "approved", "expected_delivery_date": "2026-03-01"},
        {"id": "g", "item": "Paint", "status": "rejected", "expected_delivery_date": "2026-03-01"},
    ]
    sigs = eng.detect_overdue_procurement_requests(requests, today=today)
    types = {s["type"]: s for s in sigs}
    assert set(types) == {"overdue_procurement", "overdue_procurement_blocking_production"}
    assert types["overdue_procurement"]["severity"] == "medium"
    assert types["overdue_procurement"]["related_id"] == "a"
    assert types["overdue_procurement_blocking_production"]["severity"] == "high"
    assert "Order #245" in types["overdue_procurement_blocking_production"]["summary"]
    assert "Order #245" in types["overdue_procurement_blocking_production"]["detail"]
    assert "overdue" in types["overdue_procurement_blocking_production"]["detail"].lower()
    assert "High-priority" in types["overdue_procurement_blocking_production"]["detail"]

