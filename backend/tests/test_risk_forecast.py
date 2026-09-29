"""Predictive risk alerts: detectors, dedupe, and no financial leaks to
users without Financials access."""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_risk_forecast")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import alert_notify as an  # noqa: E402
import decision_engine as de  # noqa: E402
import retention  # noqa: E402
import risk_forecast as rf  # noqa: E402
import server  # noqa: E402

TODAY = date(2026, 9, 29)


def fin_with(burns=None, revs=None, *, cash=100000.0, reserve=40000.0, cash_entered=True, current="2026-09"):
    """Ledger months ending the month before `current`, plus a partial current month."""
    burns = burns or []
    revs = revs or [0.0] * len(burns)
    n = len(burns)
    months = []
    y, m = int(current[:4]), int(current[5:])
    for i in range(n, 0, -1):
        idx = y * 12 + (m - 1) - i
        months.append(f"{idx // 12:04d}-{idx % 12 + 1:02d}")
    ledger = [
        {"month": mo, "revenue": float(r), "expenses": float(r + b)}
        for mo, b, r in zip(months, burns, revs)
    ]
    # In-progress month with tiny numbers: must be ignored by every detector.
    ledger.append({"month": current, "revenue": 1.0, "expenses": 2.0})
    return {
        "ledger_months": ledger, "current_month": current, "cash_entered": cash_entered,
        "cash_value": cash if cash_entered else None, "min_cash_reserve": reserve,
        "currency": "usd", "has_data": True,
    }


# ------------------------------------------------------------ cash runway forecast

def test_forecast_fires_with_date_and_cut_suggestion():
    sig = rf.detect_cash_runway_forecast(fin_with([15000, 15000, 15000]), today=TODAY)
    assert sig and sig["type"] == "cash_runway_forecast"
    # 60k above reserve / 15k a month = 4 months.
    assert sig["days_until_reserve"] == round(4 * rf.DAYS_PER_MONTH)
    assert sig["severity"] == "medium"
    f = sig["forecast"]
    assert f["projected_date"] == (TODAY + timedelta(days=sig["days_until_reserve"])).isoformat()
    assert f["cut_amount"] == pytest.approx(1500)
    assert f["projected_days_after_cut"] > sig["days_until_reserve"]
    assert "Cutting burn by $1,500 a month" in sig["what_would_change"]
    assert "At your current burn you reach your minimum cash reserve of $40,000" in sig["detail"]
    assert f["confidence"] == "medium" and f["data_points"] == 3


def test_forecast_high_severity_inside_60_days():
    sig = rf.detect_cash_runway_forecast(fin_with([35000, 35000, 35000]), today=TODAY)
    assert sig["days_until_reserve"] <= rf.RESERVE_HIGH_SEVERITY_DAYS
    assert sig["severity"] == "high"


def test_forecast_silent_beyond_horizon_days():
    # 60k / 10k = 6 months ≈ 183 days > 180.
    assert rf.detect_cash_runway_forecast(fin_with([10000, 10000, 10000]), today=TODAY) is None


def test_forecast_horizon_boundary():
    # Exactly 180 days away fires; a hair beyond does not.
    per_month = 60000 / (rf.RESERVE_ALERT_HORIZON_DAYS / rf.DAYS_PER_MONTH)
    assert rf.detect_cash_runway_forecast(fin_with([per_month] * 3), today=TODAY) is not None
    assert rf.detect_cash_runway_forecast(fin_with([per_month * 0.99] * 3), today=TODAY) is None


@pytest.mark.parametrize("kwargs", [
    {"cash_entered": False},
    {"reserve": None},
])
def test_forecast_needs_cash_and_reserve(kwargs):
    assert rf.detect_cash_runway_forecast(fin_with([20000] * 3, **kwargs), today=TODAY) is None


def test_forecast_needs_two_complete_months():
    assert rf.detect_cash_runway_forecast(fin_with([30000]), today=TODAY) is None
    assert rf.detect_cash_runway_forecast(fin_with([30000, 30000]), today=TODAY) is not None


def test_forecast_silent_when_profitable_or_zero_burn():
    assert rf.detect_cash_runway_forecast(fin_with([-5000, -5000, -5000]), today=TODAY) is None
    assert rf.detect_cash_runway_forecast(fin_with([0, 0, 0]), today=TODAY) is None


def test_forecast_already_below_reserve():
    sig = rf.detect_cash_runway_forecast(fin_with([1000] * 3, cash=30000), today=TODAY)
    assert sig["days_until_reserve"] == 0 and sig["severity"] == "high"
    assert sig["summary"] == "Cash is below your minimum reserve"


def test_forecast_uses_trend_not_just_average():
    rising = fin_with([5000, 10000, 15000, 20000, 25000, 30000])
    flat = fin_with([25000] * 6)
    s_rising = rf.detect_cash_runway_forecast(rising, today=TODAY)
    s_flat = rf.detect_cash_runway_forecast(flat, today=TODAY)
    assert s_rising["forecast"]["burn_trend_per_month"] > 0
    assert s_rising["forecast"]["confidence"] == "high"
    assert s_rising["days_until_reserve"] <= s_flat["days_until_reserve"] + 1


def test_forecast_huge_numbers_stay_finite():
    sig = rf.detect_cash_runway_forecast(fin_with([4e11] * 3, cash=1e12, reserve=1e11), today=TODAY)
    assert sig and isinstance(sig["days_until_reserve"], int)


def test_forecast_rejects_nan_cash():
    assert rf.detect_cash_runway_forecast(fin_with([20000] * 3, cash=float("nan")), today=TODAY) is None


# ------------------------------------------------------------ burn acceleration

def test_burn_acceleration_fires_on_two_consecutive_rises():
    sig = rf.detect_burn_acceleration(fin_with([10000, 12000, 13000]))
    assert sig["type"] == "burn_acceleration" and sig["severity"] == "medium"
    assert sig["burn_delta_pct"] == 30.0
    assert sig["forecast"]["prior_value"] == 10000 and sig["forecast"]["current_value"] == 13000


def test_burn_acceleration_boundaries():
    assert rf.detect_burn_acceleration(fin_with([10000, 11000, 12400])) is None  # 24%
    assert rf.detect_burn_acceleration(fin_with([10000, 11000, 12500])) is not None  # 25%
    assert rf.detect_burn_acceleration(fin_with([10000, 20000, 30000]))["severity"] == "high"


@pytest.mark.parametrize("burns", [
    [10000, 14000, 13000],   # not monotonic
    [0, 5000, 9000],         # no positive base
    [-2000, 3000, 9000],     # was profitable
    [10000, 15000],          # only two months
])
def test_burn_acceleration_silent(burns):
    assert rf.detect_burn_acceleration(fin_with(burns)) is None


def test_burn_acceleration_ignores_partial_current_month():
    # Last complete months flat; only the (ignored) current month would differ.
    assert rf.detect_burn_acceleration(fin_with([10000, 10000, 10000])) is None


# ------------------------------------------------------------ revenue decline

def test_revenue_decline_two_months_below_trailing_average():
    revs = [10000, 10000, 10000, 8000, 7000]
    sig = rf.detect_revenue_decline(fin_with([0] * 5, revs))
    assert sig and sig["type"] == "revenue_decline"
    # Trailing for last month = avg(10000, 10000, 8000) = 9333; 7000 is 25% below.
    assert sig["forecast"]["prior_value"] == pytest.approx(28000 / 3)
    assert sig["severity"] == "medium"


@pytest.mark.parametrize("revs", [
    [10000, 10000, 10000, 10000, 10000],   # flat
    [10000, 10000, 10000, 10000, 7000],    # only one bad month
    [10000, 10000, 8000, 7000],            # only 4 months
    [0, 0, 0, 0, 0],                       # no revenue
])
def test_revenue_decline_silent(revs):
    assert rf.detect_revenue_decline(fin_with([0] * len(revs), revs)) is None


def test_revenue_decline_high_severity():
    sig = rf.detect_revenue_decline(fin_with([0] * 5, [10000, 10000, 10000, 6000, 4000]))
    assert sig["severity"] == "high"


# ------------------------------------------------------------ team output

def _done(days_ago, **extra):
    at = datetime.combine(TODAY, datetime.min.time(), tzinfo=timezone.utc) - timedelta(days=days_ago)
    return {"column": "done", "done_at": at.isoformat(), **extra}


def test_team_output_trend_fires_and_counts_overdue():
    tasks = [_done(40) for _ in range(10)] + [_done(5) for _ in range(5)]
    tasks.append({"column": "doing", "due": (TODAY - timedelta(days=3)).isoformat(), "created_at": "2026-08-01T00:00:00+00:00"})
    sig = rf.detect_team_output_trend(tasks, today=TODAY)
    assert sig["summary"] == "Tasks completed have dropped 50% over four weeks"
    assert sig["severity"] == "medium"
    assert sig["forecast"]["overdue_now"] == 1
    assert sig["forecast"]["overdue_four_weeks_ago"] == 0
    assert "velocity" not in sig["summary"].lower()


def test_team_output_trend_needs_minimum_prior_tasks():
    tasks = [_done(40) for _ in range(rf.TEAM_TREND_MIN_TASKS - 1)]
    assert rf.detect_team_output_trend(tasks, today=TODAY) is None


def test_team_output_trend_small_drop_and_high_drop():
    small = [_done(40) for _ in range(10)] + [_done(5) for _ in range(8)]
    assert rf.detect_team_output_trend(small, today=TODAY) is None
    big = [_done(40) for _ in range(10)] + [_done(5) for _ in range(2)]
    assert rf.detect_team_output_trend(big, today=TODAY)["severity"] == "high"


def test_task_overdue_on_respects_done_and_created():
    due = (TODAY - timedelta(days=10)).isoformat()
    finished_late = {"due": due, "done_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()}
    assert rf.task_overdue_on(finished_late, TODAY - timedelta(days=5)) is True
    created_later = {"due": due, "created_at": "2099-01-01T00:00:00+00:00"}
    assert rf.task_overdue_on(created_later, TODAY) is False


# ------------------------------------------------------------ pipeline coverage

def test_pipeline_coverage_silent_without_targets():
    assert rf.detect_pipeline_coverage([{"stage": "lead", "value": 1}], []) is None
    assert rf.detect_pipeline_coverage([{"stage": "lead", "value": 1}], None) is None


def test_pipeline_coverage_levels():
    targets = [{"month": "2026-09", "target": 50000}, {"month": "2026-10", "target": 50000}]
    deals = [{"stage": "proposal", "value": 40000}, {"stage": "won", "value": 90000}, {"stage": "lost", "value": 50000}]
    sig = rf.detect_pipeline_coverage(deals, targets)
    assert sig["summary"] == "Open pipeline covers 40% of your sales targets"
    assert sig["severity"] == "high"
    ok = rf.detect_pipeline_coverage([{"stage": "lead", "value": 120000}], targets)
    assert ok is None
    mid = rf.detect_pipeline_coverage([{"stage": "lead", "value": 70000}], targets)
    assert mid["severity"] == "medium"


# ------------------------------------------------------------ pipeline integration

def test_collect_signals_dedupes_overlapping_runway_cards():
    fin = fin_with([10000, 20000, 30000], cash=100000, reserve=40000)
    fin.update({"runway_months": 3.3, "burn_series": [{"month": "Jul", "burn": 20000}, {"month": "Aug", "burn": 30000}]})
    sigs = de.collect_signals(fin=fin, expense_by_month={}, deals=[], tasks=[], updates=[],
                              now=datetime(2026, 9, 29, tzinfo=timezone.utc))
    types = [s["type"] for s in sigs]
    assert "cash_runway_forecast" in types and "runway_risk" not in types
    assert "burn_acceleration" in types and "burn_increase" not in types


def test_new_types_are_decision_types_and_financial_classification():
    for t in rf.SIGNAL_TYPES:
        assert t in de.DECISION_SIGNAL_TYPES
    assert de.is_financial_signal({"type": "cash_runway_forecast"})
    assert de.is_financial_signal({"signal": {"type": "revenue_decline"}})
    assert de.is_financial_signal({"signal_type": "pipeline_coverage"})
    assert de.is_financial_signal({"financial": True})
    assert not de.is_financial_signal({"type": "team_output_trend"})
    assert not de.is_financial_signal({"signal": {"type": "overdue_task"}})


def test_notify_key_stable_across_days():
    a = rf.detect_cash_runway_forecast(fin_with([15000] * 3), today=TODAY)
    b = rf.detect_cash_runway_forecast(fin_with([15000] * 3, cash=99000), today=TODAY + timedelta(days=1))
    assert a["summary"] != b["summary"] or a["detail"] != b["detail"]
    assert an.signal_notify_key(a) == an.signal_notify_key(b)


def test_raw_card_uses_deterministic_recommendation():
    sig = rf.detect_burn_acceleration(fin_with([10000, 12000, 13000]))
    card = server._raw_decision_card_from_signal(sig, now="2026-09-29T00:00:00+00:00")
    assert card["recommendation"] == sig["what_would_change"]
    assert card["description"] == sig["detail"]


# ------------------------------------------------------------ no leaks

FIN_SUG = {"id": "s1", "status": "suggested", "title": "Cash reserve in 40 days", "signal_type": "cash_runway_forecast",
           "signal": {"type": "cash_runway_forecast", "severity": "high", "notify_key": "cash_runway_forecast:high"},
           "severity": "high", "impact": "High"}
TEAM_SUG = {"id": "s2", "status": "suggested", "title": "Tasks completed dropped", "signal_type": "team_output_trend",
            "signal": {"type": "team_output_trend", "severity": "high", "notify_key": "team_output_trend:high"},
            "severity": "high", "impact": "High"}
FIN_DECISION = {"id": "d1", "status": "pending", "title": "Burn is up", "financial": True}
PLAIN_DECISION = {"id": "d2", "status": "pending", "title": "Hire a PM"}
WS = {"workspace_id": "ws1", "name": "Acme", "decisions": [FIN_DECISION, PLAIN_DECISION],
      "decision_suggestions": [FIN_SUG, TEAM_SUG]}
PRINCIPAL = {"user_id": "u2", "workspace_id": "ws1", "pack": "member", "role": "member", "name": "M"}


@pytest.mark.asyncio
@pytest.mark.parametrize("has_fin,expect_ids", [(False, {"d2", "s2"}), (True, {"d1", "d2", "s1", "s2"})])
async def test_decisions_endpoint_hides_financial_items(has_fin, expect_ids):
    with patch.object(server, "get_ws", new=AsyncMock(return_value=dict(WS))), \
            patch.object(server, "can_access_financials", new=AsyncMock(return_value=has_fin)), \
            patch.object(server, "can_section_write", new=AsyncMock(return_value=False)):
        out = await server.decisions(PRINCIPAL)
    ids = {d["id"] for d in out["decisions"]} | {s["id"] for s in out["suggestions"]}
    assert ids == expect_ids


def test_briefing_decide_column_hides_financial_items():
    hidden = server._briefing_what_to_decide_all(WS, include_financial=False)
    shown = server._briefing_what_to_decide_all(WS, include_financial=True)
    assert {i["id"] for i in hidden} == {"d2", "s2"}
    assert {i["id"] for i in shown} == {"d1", "d2", "s1", "s2"}


def test_slack_text_redacts_financial_alerts():
    text = an.build_slack_text("Acme", [TEAM_SUG], "https://app", redacted_financial=1)
    assert "Cash reserve" not in text
    assert "1 financial alert" in text and "Financials access" in text


@pytest.mark.asyncio
async def test_alert_email_sends_financial_alerts_only_to_finance_recipients():
    sent = []

    async def fake_send(*, to, subject, html):
        sent.append((tuple(to), html))
        return {"sent": True}

    async def recipients(_wid, financial=False):
        return ["owner@x.com"] if financial else ["owner@x.com", "exec@x.com"]

    ws = {"workspace_id": "ws1", "name": "Acme", "notified_signal_ids": []}
    with patch.object(server, "send_resend_email", new=fake_send), \
            patch.object(server, "_alert_recipient_emails", new=recipients), \
            patch.object(server, "_slack_webhook_plaintext", return_value=None), \
            patch.object(server, "db") as mock_db:
        mock_db.workspaces.update_one = AsyncMock()
        await server._notify_high_severity_alerts("ws1", [FIN_SUG, TEAM_SUG], ws)
    by_to = {to: html for to, html in sent}
    assert "Cash reserve in 40 days" in by_to[("owner@x.com",)]
    assert "Cash reserve in 40 days" not in by_to[("exec@x.com",)]
    assert "Tasks completed dropped" in by_to[("exec@x.com",)]


def test_retention_email_bullets_exclude_financial_items():
    bullets = retention.collect_change_bullets(WS, deals=[], activities=[], now=datetime(2026, 9, 29, tzinfo=timezone.utc))
    text = " ".join(bullets)
    assert "Burn is up" not in text and "Cash reserve" not in text
    assert "Hire a PM" in text and "Tasks completed dropped" in text


def test_accepting_a_financial_suggestion_marks_the_decision():
    assert de.is_financial_signal(FIN_SUG) is True
