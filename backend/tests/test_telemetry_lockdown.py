"""Telemetry helpers: optional targets + risk suggestions from signals."""
import os
import sys
from pathlib import Path

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_telemetry_lockdown")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import (  # noqa: E402
    _normalize_telemetry_targets,
    _resolve_telemetry_funnel_and_risks,
    _revenue_trend_with_targets,
    _telemetry_risk_suggestions_from_signals,
)
import seed_data  # noqa: E402


def test_targets_default_off_and_clamp_pct():
    assert _normalize_telemetry_targets(None) == {"enabled": False, "monthly_growth_pct": 0.0}
    assert _normalize_telemetry_targets({"enabled": True, "monthly_growth_pct": 5})["enabled"] is True
    assert _normalize_telemetry_targets({"enabled": True, "monthly_growth_pct": 5})["monthly_growth_pct"] == 5.0
    assert _normalize_telemetry_targets({"enabled": True, "monthly_growth_pct": 99999})["monthly_growth_pct"] == 1000.0
    assert _normalize_telemetry_targets({"enabled": True, "monthly_growth_pct": -200})["monthly_growth_pct"] == -100.0


def test_revenue_trend_omits_target_when_disabled():
    series = [{"month": "Jan", "revenue": 100}, {"month": "Feb", "revenue": 110}]
    out = _revenue_trend_with_targets(series, {"enabled": False, "monthly_growth_pct": 3})
    # `revenue` is the real field (total revenue); `mrr` stays as an alias for old clients.
    assert out == [
        {"month": "Jan", "revenue": 100, "mrr": 100},
        {"month": "Feb", "revenue": 110, "mrr": 110},
    ]
    assert all("target" not in p for p in out)


def test_revenue_trend_compounds_from_prior_actual():
    series = [
        {"month": "Jan", "revenue": 100},
        {"month": "Feb", "revenue": 120},
        {"month": "Mar", "revenue": 130},
    ]
    out = _revenue_trend_with_targets(series, {"enabled": True, "monthly_growth_pct": 10})
    assert out[0]["target"] == 100  # first month = own actual
    assert out[1]["target"] == round(100 * 1.10)  # prior actual × (1+g)
    assert out[2]["target"] == round(120 * 1.10)
    # Not lockstep with same-month actual * 1.03
    assert out[1]["target"] != round(120 * 1.03)


def test_risk_suggestions_dedupe_by_type_and_cap():
    signals = [
        {"type": "recurring_blocker", "summary": "Ada blocked again"},
        {"type": "recurring_blocker", "summary": "Bob blocked again"},
        {"type": "overdue_work_order", "summary": "WO-1 overdue"},
        {"type": "runway_risk", "summary": "Runway under 6 months"},
        {"type": "stalled_deal", "summary": "should be ignored"},
    ]
    out = _telemetry_risk_suggestions_from_signals(signals, cap=5)
    types = [s["source_signal"] for s in out]
    assert types.count("recurring_blocker") == 1
    assert "stalled_deal" not in types
    assert "runway_risk" in types
    rb = next(s for s in out if s["source_signal"] == "recurring_blocker")
    assert rb["category"] == "People"
    assert "2 teammates" in rb["name"]


def test_empty_workspace_seed_has_no_funnel_or_risks():
    empty = seed_data.build_workspace("ws_empty", "Acme", "u1", empty=True)
    assert empty["template"] == "empty"
    assert empty["telemetry"]["funnel"] == []
    assert empty["telemetry"]["risks"] == []


def test_sample_workspace_seed_has_funnel_and_risks():
    sample = seed_data.build_workspace("ws_sample", "Northwind", "u1", empty=False)
    assert sample["template"] == "sample"
    assert len(sample["telemetry"]["funnel"]) >= 1
    assert len(sample["telemetry"]["risks"]) >= 1


def test_non_sample_never_inherits_seed_funnel_or_risks():
    sample = seed_data.build_workspace("ws_sample", "Northwind", "u1", empty=False)
    tel = sample["telemetry"]
    funnel, funnel_is_sample, risks, risks_is_sample = _resolve_telemetry_funnel_and_risks(
        template="empty",
        tel=tel,
        manual={},
        metrics=None,
    )
    assert funnel == []
    assert funnel_is_sample is False
    assert risks == []
    assert risks_is_sample is False

    # Missing template must not fall back to serving seed as live data.
    funnel2, f2, risks2, r2 = _resolve_telemetry_funnel_and_risks(
        template=None, tel=tel, manual={}, metrics=None,
    )
    assert funnel2 == [] and f2 is False and risks2 == [] and r2 is False


def test_sample_template_serves_seed_with_sample_flags():
    sample = seed_data.build_workspace("ws_sample", "Northwind", "u1", empty=False)
    tel = sample["telemetry"]
    funnel, funnel_is_sample, risks, risks_is_sample = _resolve_telemetry_funnel_and_risks(
        template="sample",
        tel=tel,
        manual={},
        metrics=None,
    )
    assert funnel == tel["funnel"]
    assert funnel_is_sample is True
    assert risks == tel["risks"]
    assert risks_is_sample is True


def test_manual_risks_override_seed_even_on_sample():
    sample = seed_data.build_workspace("ws_sample", "Northwind", "u1", empty=False)
    manual = {"risks": [{"id": "mine", "name": "Real risk", "likelihood": 2, "impact": 2, "category": "Ops"}]}
    _funnel, _fis, risks, risks_is_sample = _resolve_telemetry_funnel_and_risks(
        template="sample",
        tel=sample["telemetry"],
        manual=manual,
        metrics=None,
    )
    assert risks == manual["risks"]
    assert risks_is_sample is False


def test_live_deal_metrics_override_sample_funnel():
    sample = seed_data.build_workspace("ws_sample", "Northwind", "u1", empty=False)
    metrics = {"by_stage": [{"label": "Qualified", "count": 3}, {"label": "Empty", "count": 0}]}
    funnel, funnel_is_sample, _risks, _ris = _resolve_telemetry_funnel_and_risks(
        template="sample",
        tel=sample["telemetry"],
        manual={},
        metrics=metrics,
    )
    assert funnel == [{"stage": "Qualified", "value": 3}]
    assert funnel_is_sample is False
