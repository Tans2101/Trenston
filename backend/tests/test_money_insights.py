import json
import os

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_money_insights")

import money_insights as mi  # noqa: E402


def _e(kind, cat, name, amount, month, recurring=False):
    return {"id": f"{kind}-{name}-{month}", "type": kind, "category": cat, "name": name,
            "amount": amount, "month": month, "recurring": recurring}


ENTRIES = [
    _e("revenue", "Subscriptions", "Plans", 5000, "2026-08"),
    _e("revenue", "Subscriptions", "Plans", 6000, "2026-09"),
    _e("revenue", "Services", "Setup fees", 1000, "2026-09"),
    _e("expense", "Payroll", "Salaries", 4000, "2026-08"),
    _e("expense", "Payroll", "Salaries", 4000, "2026-09"),
    _e("expense", "Cloud/Infra", "Render", 300, "2026-08"),
    _e("expense", "Cloud/Infra", "Render", 900, "2026-09"),
]


def _facts(entries=ENTRIES):
    return mi.build_facts(entries, current_month="2026-10", horizon="2026-10", currency="usd")


def test_bad_amount_does_not_crash_facts():
    entries = [_e("revenue", "X", "Y", "not-a-number", "2026-09")]
    f = mi.build_facts(entries, current_month="2026-10", horizon="2026-10", currency="usd")
    assert f["revenue"]["has_data"] is True
    assert f["revenue"]["total_value"] == 0.0


def test_facts_use_last_finished_month_and_compare_to_previous():
    f = _facts()
    assert f["period"] == "2026-09" and f["period_label"] == "September 2026"
    assert f["month_so_far"] is False
    top = f["revenue"]["by_category"][0]
    assert top["category"] == "Subscriptions"
    assert top["change_vs_previous_month_pct"] == 20
    assert f["revenue"]["by_category"][1].get("new_this_month") is True
    inc = f["expenses"]["biggest_increases"][0]
    assert inc["category"] == "Cloud/Infra"
    assert f["net_direction"] == "profit"


def test_no_rows_means_no_data_not_a_zero_month():
    f = _facts([])
    assert f["has_data"] is False
    t = mi.template_sections(f)
    assert "No revenue is logged" in t["making_money"]
    assert "No expenses are logged" in t["losing_money"]
    assert "$0" not in json.dumps(t)


def test_only_current_month_is_marked_so_far():
    f = mi.build_facts([_e("expense", "Payroll", "Pay", 100, "2026-10")],
                       current_month="2026-10", horizon="2026-10")
    assert f["month_so_far"] is True and f["period"] == "2026-10"
    assert f["revenue"]["has_data"] is False


def test_template_mentions_runway_only_when_cash_entered():
    f = _facts()
    with_cash = mi.template_sections(f, {"cash_entered": True, "runway_months": 4.9, "runway_basis": "based on Jun to Aug"})
    assert "Runway is 4.9 months" in with_cash["why_it_matters"]
    without = mi.template_sections(f, {"cash_entered": False, "runway_months": None})
    assert "Add your cash balance" in without["why_it_matters"]


def test_ai_output_with_invented_figure_is_rejected():
    ctx = json.dumps({"facts": mi._strip_values(_facts())})
    good = json.dumps({
        "making_money": "Subscriptions brought in $6,000, up 20% from the month before.",
        "losing_money": "Payroll is the biggest cost at $4,000.",
        "why_it_matters": "You made a profit. Keep an eye on Cloud/Infra.",
    })
    assert mi.parse_sections(good, ctx) is not None
    bad = json.dumps({
        "making_money": "Subscriptions brought in $9,999.",
        "losing_money": "Payroll is large.",
        "why_it_matters": "Fine.",
    })
    assert mi.parse_sections(bad, ctx) is None
    assert mi.parse_sections("not json", ctx) is None
    assert mi.parse_sections(json.dumps({"making_money": "x"}), ctx) is None


def test_hash_changes_only_when_facts_change():
    a = mi.context_hash({"facts": mi._strip_values(_facts())})
    b = mi.context_hash({"facts": mi._strip_values(_facts())})
    c = mi.context_hash({"facts": mi._strip_values(_facts(ENTRIES[:-1]))})
    assert a == b and a != c


# ------------------------------------------------------------------ endpoint

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import anthropic
import httpx
import pytest
from fastapi import HTTPException

import server


class _Ws:
    def __init__(self):
        self.doc = {"workspace_id": "w", "financial_insights": {}}

    async def update_one(self, _flt, upd):
        for path, val in upd["$set"].items():
            node = self.doc
            *parents, leaf = path.split(".")
            for part in parents:
                node = node.setdefault(part, {})
            node[leaf] = val


def _wire(monkeypatch, complete):
    ws = _Ws()

    async def get_ws(_id):
        return ws.doc

    async def depts(*_a, **_k):
        return None

    async def fin(*_a, **_k):
        return {"currency": "usd", "entries": [dict(e) for e in ENTRIES]}

    async def now(_id):
        return datetime(2026, 10, 16, tzinfo=timezone.utc)

    async def slot(*_a, **_k):
        return True

    monkeypatch.setattr(server, "get_ws", get_ws)
    monkeypatch.setattr(server.dept_access, "accessible_department_ids", depts)
    monkeypatch.setattr(server, "compute_financials", fin)
    monkeypatch.setattr(server, "_workspace_now", now)
    monkeypatch.setattr(server.helm_llm, "anthropic_configured", lambda: True)
    monkeypatch.setattr(server.doc_rate_limit, "acquire_event_slot", slot)
    monkeypatch.setattr(server.helm_llm, "complete", complete)
    monkeypatch.setattr(server, "db", SimpleNamespace(workspaces=ws))
    return ws


def _run():
    return asyncio.run(server.generate_money_insights({"workspace_id": "w"}))


def _req():
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


@pytest.mark.parametrize("make_error", [
    lambda: anthropic.APIConnectionError(request=_req()),
    lambda: anthropic.BadRequestError(
        "Your credit balance is too low", response=httpx.Response(400, request=_req()), body=None),
    lambda: anthropic.AuthenticationError(
        "invalid x-api-key", response=httpx.Response(401, request=_req()), body=None),
])
def test_ai_failure_shows_maintenance_and_hides_the_reason(monkeypatch, make_error):
    async def boom(*_a, **_k):
        raise make_error()

    _wire(monkeypatch, boom)
    with pytest.raises(HTTPException) as ei:
        _run()
    assert ei.value.status_code == 503
    assert ei.value.detail["reason"] == "maintenance"
    assert "under maintenance" in ei.value.detail["message"]
    assert "credit" not in ei.value.detail["message"].lower()


def test_success_is_saved_uses_haiku_and_unchanged_data_is_not_paid_for_twice(monkeypatch):
    calls = []

    async def ok(system, user, **kw):
        calls.append(kw)
        return json.dumps({
            "making_money": "Subscriptions brought in $6,000, up 20% from the month before.",
            "losing_money": "Payroll is the biggest cost at $4,000.",
            "why_it_matters": "You made a profit of $2,100 in September 2026.",
        })

    ws = _wire(monkeypatch, ok)
    first = _run()["insight"]
    assert first["ai"] is True and first["cached"] is False
    assert calls[0]["model"] == server.helm_llm.ANTHROPIC_MODEL_FAST
    assert ws.doc["financial_insights"]["all"]["sections"]["making_money"].startswith("Subscriptions")
    second = _run()["insight"]
    assert second["cached"] is True and len(calls) == 1


def test_ungrounded_ai_text_falls_back_to_the_plain_template(monkeypatch):
    async def liar(*_a, **_k):
        return json.dumps({"making_money": "You earned $123,456.", "losing_money": "a", "why_it_matters": "b"})

    _wire(monkeypatch, liar)
    out = _run()["insight"]
    assert out["ai"] is False
    assert "123,456" not in json.dumps(out["sections"])
    assert "$7,000" in out["sections"]["making_money"]


def test_summaries_are_kept_per_department_scope(monkeypatch):
    async def ok(*_a, **_k):
        return json.dumps({
            "making_money": "Subscriptions brought in $6,000.",
            "losing_money": "Payroll costs $4,000.",
            "why_it_matters": "You made a profit.",
        })

    ws = _wire(monkeypatch, ok)
    _run()
    assert set(ws.doc["financial_insights"]) == {"all"}

    async def limited(*_a, **_k):
        return ["dept_fin_1"]

    monkeypatch.setattr(server.dept_access, "accessible_department_ids", limited)
    out = asyncio.run(server.get_money_insights({"workspace_id": "w", "pack": "finance"}))
    assert out["insight"] is None  # the full-ledger summary is not shown to a limited user
    assert server._money_insights_scope(["b", "a"]) == server._money_insights_scope(["a", "b"])
    assert server._money_insights_scope(None) == "all"


def test_every_new_summary_is_added_to_the_ai_history(monkeypatch):
    seen = []

    async def ok(*_a, **_k):
        return json.dumps({
            "making_money": "Subscriptions brought in $6,000.",
            "losing_money": "Payroll costs $4,000.",
            "why_it_matters": "You made a profit.",
        })

    async def fake_record(_db, ws_id, **kw):
        seen.append((ws_id, kw))

    _wire(monkeypatch, ok)
    monkeypatch.setattr(server.ai_audit, "record", fake_record)
    _run()
    _run()  # unchanged data: saved summary reused, nothing new to record
    assert len(seen) == 1
    ws_id, kw = seen[0]
    assert ws_id == "w" and kw["kind"] == "money_summary"
    assert kw["model"] == server.helm_llm.ANTHROPIC_MODEL_FAST
    assert kw["text"]["making_money"].startswith("Subscriptions")
