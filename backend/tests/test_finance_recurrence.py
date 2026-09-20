"""Unit tests for recurring expense expansion (monthly / annual)."""
from datetime import datetime, timezone

import finance_recurrence as fr


def test_normalize_recurrence():
    assert fr.normalize_recurrence(False, "monthly", "expense") is None
    assert fr.normalize_recurrence(True, "annual", "expense") == "annual"
    assert fr.normalize_recurrence(True, None, "expense") == "monthly"
    assert fr.normalize_recurrence(True, "weekly", "expense") == "monthly"
    assert fr.normalize_recurrence(True, "annual", "revenue") == "monthly"


def test_is_valid_month():
    assert fr.is_valid_month("2026-03")
    assert not fr.is_valid_month("2026-13")
    assert not fr.is_valid_month("2026-00")
    assert not fr.is_valid_month("bad")


def test_months_inclusive():
    assert fr.months_inclusive("2026-01", "2026-03") == ["2026-01", "2026-02", "2026-03"]
    assert fr.months_inclusive("2026-03", "2026-01") == []


def test_monthly_expense_expands_each_month():
    entry = {
        "type": "expense",
        "amount": 1000,
        "month": "2026-01",
        "recurring": True,
        "recurrence": "monthly",
        "category": "Cloud/Infra",
    }
    amounts = dict(fr.iter_expense_month_amounts(entry, "2026-03"))
    assert amounts == {"2026-01": 1000, "2026-02": 1000, "2026-03": 1000}


def test_annual_expense_is_monthlyized():
    entry = {
        "type": "expense",
        "amount": 12000,
        "month": "2026-01",
        "recurring": True,
        "recurrence": "annual",
        "category": "G&A",
    }
    amounts = dict(fr.iter_expense_month_amounts(entry, "2026-03"))
    assert amounts == {"2026-01": 1000.0, "2026-02": 1000.0, "2026-03": 1000.0}


def test_one_time_expense_only_start_month():
    entry = {
        "type": "expense",
        "amount": 500,
        "month": "2026-02",
        "recurring": False,
        "category": "Other",
    }
    amounts = dict(fr.iter_expense_month_amounts(entry, "2026-03"))
    assert amounts == {"2026-02": 500}


def test_monthly_logged_recurring_does_not_triple_count():
    """Payroll logged as recurring each month must not stack expansions."""
    entries = [
        {"id": "a", "type": "expense", "amount": 10000, "month": "2026-01",
         "recurring": True, "recurrence": "monthly", "category": "Payroll"},
        {"id": "b", "type": "expense", "amount": 10000, "month": "2026-02",
         "recurring": True, "recurrence": "monthly", "category": "Payroll"},
        {"id": "c", "type": "expense", "amount": 10000, "month": "2026-03",
         "recurring": True, "recurrence": "monthly", "category": "Payroll"},
    ]
    by = fr.expand_entries_by_month(entries, entry_type="expense", horizon_end="2026-03")
    assert by["2026-01"] == 10000
    assert by["2026-02"] == 10000
    assert by["2026-03"] == 10000


def test_recurring_rate_change_uses_new_amount_from_start():
    entries = [
        {"id": "a", "type": "expense", "amount": 10000, "month": "2026-01",
         "recurring": True, "recurrence": "monthly", "category": "Payroll"},
        {"id": "b", "type": "expense", "amount": 12000, "month": "2026-03",
         "recurring": True, "recurrence": "monthly", "category": "Payroll"},
    ]
    by = fr.expand_entries_by_month(entries, entry_type="expense", horizon_end="2026-04")
    assert by["2026-01"] == 10000
    assert by["2026-02"] == 10000
    assert by["2026-03"] == 12000
    assert by["2026-04"] == 12000

    # Line items for March must show only the $12k rate — not both commitments.
    march = fr.line_items_for_period(entries, "2026-03", "2026-04")
    assert len(march) == 1
    assert march[0]["amount"] == 12000
    assert march[0]["id"] == "b"
    feb = fr.line_items_for_period(entries, "2026-02", "2026-04")
    assert len(feb) == 1
    assert feb[0]["amount"] == 10000


def test_expense_totals_by_month_category_expands(monkeypatch):
    import decision_engine as eng

    monkeypatch.setattr(fr, "current_month", lambda now=None: "2026-03")
    entries = [
        {
            "type": "expense",
            "amount": 1200,
            "month": "2026-01",
            "recurring": True,
            "recurrence": "monthly",
            "category": "Payroll",
            "id": "only",
        }
    ]
    out = eng.expense_totals_by_month_category(entries)
    assert out["2026-01"]["Payroll"] == 1200
    assert out["2026-02"]["Payroll"] == 1200
    assert out["2026-03"]["Payroll"] == 1200


def test_fmt_money_rounding():
    from money_fmt import fmt_money
    assert fmt_money(1500) == "$1.5K"
    assert fmt_money(1499) == "$1.5K"
    assert fmt_money(1000) == "$1K"
    assert fmt_money(999999) == "$1.00M"
    assert "M" in fmt_money(1_000_000)
