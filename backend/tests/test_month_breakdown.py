"""The click-a-month view must add up to the same numbers the Financials charts use."""
import finance_recurrence as fr


def _e(id, name, month, amount, *, type="expense", recurring=False, category="Software", recurrence=None, **extra):
    return {"id": id, "name": name, "month": month, "amount": amount, "type": type,
            "recurring": recurring, "recurrence": recurrence, "category": category, **extra}


CURSOR = _e("c1", "Cursor Pro", "2026-07", 20, recurring=True, recurrence="monthly")


def test_recurring_expense_shows_in_every_month_since_it_started():
    for month in ("2026-07", "2026-08", "2026-09", "2026-10"):
        out = fr.month_breakdown([CURSOR], month, "2026-10")
        assert [r["name"] for r in out["counted"]] == ["Cursor Pro"]
        row = out["counted"][0]
        assert row["recurring"] is True and row["cadence"] == "monthly" and row["month"] == "2026-07"
        assert out["expense_total"] == 20
    assert fr.month_breakdown([CURSOR], "2026-06", "2026-10")["counted"] == []


def test_totals_match_the_chart_expansion():
    entries = [
        CURSOR,
        _e("o1", "Domain", "2026-08", 12),
        _e("r1", "Retainer", "2026-07", 500, type="revenue", recurring=True, category="Subscriptions"),
        _e("r2", "One-off sale", "2026-09", 90, type="revenue", category="Sales"),
        _e("a1", "Annual tool", "2026-07", 120, recurring=True, recurrence="annual", category="Tools"),
        _e("x1", "Refund", "2026-09", 5, is_credit=True),
    ]
    rev = fr.expand_entries_by_month(entries, entry_type="revenue", horizon_end="2026-10")
    exp = fr.expand_entries_by_month(entries, entry_type="expense", horizon_end="2026-10")
    for month in fr.months_inclusive("2026-07", "2026-10"):
        out = fr.month_breakdown(entries, month, "2026-10")
        assert out["revenue_total"] == round(rev.get(month, 0), 2), month
        assert out["expense_total"] == round(exp.get(month, 0), 2), month
        assert out["net"] == round(out["revenue_total"] - out["expense_total"], 2)


def test_annual_plan_is_shown_as_a_twelfth_with_its_cadence():
    entries = [_e("a1", "Annual tool", "2026-07", 120, recurring=True, recurrence="annual", category="Tools")]
    row = fr.month_breakdown(entries, "2026-09", "2026-10")["counted"][0]
    assert row["amount"] == 10 and row["cadence"] == "annual"


def test_two_different_subscriptions_in_one_category_both_count():
    claude = _e("c2", "Claude Max", "2026-09", 100, recurring=True, recurrence="monthly")
    aug = fr.month_breakdown([CURSOR, claude], "2026-08", "2026-10")
    assert [r["name"] for r in aug["counted"]] == ["Cursor Pro"]
    for month in ("2026-09", "2026-10"):
        out = fr.month_breakdown([CURSOR, claude], month, "2026-10")
        assert sorted(r["name"] for r in out["counted"]) == ["Claude Max", "Cursor Pro"]
        assert out["expense_total"] == 120 and out["not_counted"] == []
    exp = fr.expand_entries_by_month([CURSOR, claude], entry_type="expense", horizon_end="2026-10")
    assert exp["2026-08"] == 20 and exp["2026-09"] == 120 and exp["2026-10"] == 120
    cats = fr.expand_expense_category_totals([CURSOR, claude], "2026-10")
    assert cats["2026-10"]["Software"] == 120


def test_a_price_change_with_the_same_name_replaces_the_old_rate():
    raised = _e("c2", "cursor  pro", "2026-09", 40, recurring=True, recurrence="monthly")
    aug = fr.month_breakdown([CURSOR, raised], "2026-08", "2026-10")
    assert aug["expense_total"] == 20
    sep = fr.month_breakdown([CURSOR, raised], "2026-09", "2026-10")
    assert [r["amount"] for r in sep["counted"]] == [40] and sep["expense_total"] == 40
    gone = sep["not_counted"]
    assert len(gone) == 1 and gone[0]["id"] == "c1" and gone[0]["replaced_from"] == "2026-09"


def test_unnamed_rows_in_one_category_still_replace_each_other():
    a = _e("u1", "", "2026-07", 10, recurring=True)
    b = _e("u2", None, "2026-09", 30, recurring=True)
    assert fr.month_breakdown([a, b], "2026-10", "2026-10")["expense_total"] == 30


def test_different_categories_do_not_replace_each_other():
    other = _e("c2", "Claude Max", "2026-09", 100, recurring=True, category="AI tools")
    out = fr.month_breakdown([CURSOR, other], "2026-10", "2026-10")
    assert sorted(r["name"] for r in out["counted"]) == ["Claude Max", "Cursor Pro"]
    assert out["not_counted"] == []


def test_empty_ledger_and_bad_month():
    assert fr.month_breakdown([], "2026-07", "2026-10")["counted"] == []
    assert fr.month_breakdown([CURSOR], "nope", "2026-10")["counted"] == []


def test_endpoint_lists_cursor_pro_in_each_month(monkeypatch):
    import asyncio
    import os
    from datetime import datetime, timezone

    os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
    os.environ.setdefault("DB_NAME", "test_month_breakdown")
    import server

    async def fake_fin(ws_id, department_ids=None, **kw):
        return {"entries": [dict(CURSOR), _e("f1", "Next year", "2027-03", 9)], "currency": "usd"}

    async def fake_now(ws_id):
        return datetime(2026, 10, 17, tzinfo=timezone.utc)

    async def fake_ids(*a, **k):
        return None

    monkeypatch.setattr(server, "compute_financials", fake_fin)
    monkeypatch.setattr(server, "_workspace_now", fake_now)
    monkeypatch.setattr(server.dept_access, "accessible_department_ids", fake_ids)
    principal = {"workspace_id": "ws_x"}

    got = asyncio.run(server.financials_month("2026-08", principal))
    assert [r["name"] for r in got["counted"]] == ["Cursor Pro"]
    assert got["expense_total"] == 20 and got["first_month"] == "2026-07" and got["future"] is False

    future = asyncio.run(server.financials_month("2027-03", principal))
    assert future["future"] is True and future["counted"] == []

    try:
        asyncio.run(server.financials_month("2026-13", principal))
        raise AssertionError("expected 400")
    except server.HTTPException as exc:
        assert exc.status_code == 400
