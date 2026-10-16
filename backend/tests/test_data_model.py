"""One definition per metric: Financials, the Model page and the reserve forecast
agree on burn and runway; cross-source double counting is caught; synced rows
carry their mapper version. See docs/DATA_MODEL.md."""
import asyncio
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_data_model")

import accounting_map as amap  # noqa: E402
import automations  # noqa: E402
import metric_definitions as md  # noqa: E402
import modeling  # noqa: E402
import risk_forecast  # noqa: E402
import server  # noqa: E402
import simple_cache  # noqa: E402

MID_OCT = datetime(2026, 10, 16, tzinfo=timezone.utc)


def _row(month, rev, exp):
    return {"month": month, "revenue": float(rev), "expenses": float(exp)}


# ---------------------------------------------------------------- definitions

def test_burn_basis_uses_completed_months_only():
    rows = [_row("2026-07", 0, 10000), _row("2026-08", 0, 10000),
            _row("2026-09", 0, 10000), _row("2026-10", 0, 1000)]
    basis = md.burn_basis(rows, "2026-10")
    assert basis["months"] == ["2026-07", "2026-08", "2026-09"]
    assert basis["net_burn"] == 10000
    assert basis["includes_current_month"] is False


def test_burn_basis_falls_back_to_current_month_for_brand_new_workspaces():
    basis = md.burn_basis([_row("2026-10", 0, 4000)], "2026-10")
    assert basis["months"] == ["2026-10"]
    assert basis["net_burn"] == 4000
    assert basis["includes_current_month"] is True
    assert "early estimate" in md.runway_basis_text(basis)


def test_profitable_months_offset_burn_months():
    rows = [_row("2026-07", 0, 10000), _row("2026-08", 15000, 10000), _row("2026-09", 0, 10000)]
    basis = md.burn_basis(rows, "2026-10")
    assert round(basis["net_burn"], 2) == round((10000 - 5000 + 10000) / 3, 2)


def test_runway_rules():
    assert md.runway_months(60000, 10000) == 6.0
    assert md.runway_months(None, 10000) is None          # cash never entered
    assert md.runway_months(60000, None) is None          # no ledger
    assert md.runway_months(60000, 0) is None             # no burn: no limit
    assert md.runway_months(60000, -500) is None          # cash growing
    assert md.runway_months(-100, 10000) == 0.0           # overdrawn and burning
    assert md.is_cash_growing(60000, -500) is True
    assert md.is_cash_growing(None, -500) is False


def test_definitions_cover_every_headline_metric():
    keys = {d["key"] for d in md.definitions()}
    assert {"cash", "net_burn", "average_net_burn", "runway", "mrr", "arr", "gross_margin"} <= keys
    for d in md.definitions():
        assert d["definition"] and d["formula"] and d["when_unknown"]


def test_basis_text_names_the_window():
    basis = md.burn_basis([_row("2026-07", 0, 1), _row("2026-08", 0, 1), _row("2026-09", 0, 1)], "2026-10")
    assert md.runway_basis_text(basis) == "Based on average net burn over Jul 2026 to Sep 2026."
    assert md.runway_basis_text(md.burn_basis([], "2026-10")) == ""


# ---------------------------------------------------- compute_financials

def _cursor(rows):
    cur = MagicMock()
    cur.to_list = AsyncMock(return_value=rows)
    return cur


def _fin(entries, cash=60000):
    simple_cache.clear()
    db = MagicMock()
    db.workspaces.find_one = AsyncMock(return_value={
        "financial_settings": {"cash": cash, "cash_entered": True, "currency": "usd"},
    })
    db.financial_entries.find = MagicMock(return_value=_cursor(entries))
    db.financial_entries.count_documents = AsyncMock(return_value=len(entries))
    with patch.object(server, "db", db), \
            patch.object(server.tz_utils, "workspace_now", lambda ws=None: MID_OCT):
        return asyncio.run(server.compute_financials("ws_dm", bypass_cache=True))


def _exp(i, month, amount):
    return {"id": f"e{i}", "type": "expense", "category": "Ops", "name": f"Exp {i}",
            "amount": amount, "month": month, "recurring": False}


def test_half_finished_month_no_longer_inflates_runway():
    # Three full months at 10k burn, then 1k so far this month.
    entries = [_exp(1, "2026-07", 10000), _exp(2, "2026-08", 10000),
               _exp(3, "2026-09", 10000), _exp(4, "2026-10", 1000)]
    fin = _fin(entries)
    # Old rule averaged Aug, Sep and partial Oct: 60000 / 7000 = 8.6 months.
    assert fin["runway_months"] == 6.0
    assert fin["avg_burn_value"] == 10000
    assert fin["burn_window"] == ["2026-07", "2026-08", "2026-09"]
    assert fin["burn_window_includes_current"] is False
    assert "Jul 2026 to Sep 2026" in fin["runway_basis"]


def test_financials_runway_matches_model_page_baseline():
    entries = [_exp(1, "2026-07", 8000), _exp(2, "2026-08", 12000),
               _exp(3, "2026-09", 10000), _exp(4, "2026-10", 500),
               {"id": "r1", "type": "revenue", "category": "Sales", "name": "Sale",
                "amount": 3000, "month": "2026-08", "recurring": False}]
    fin = _fin(entries)
    avg = modeling.average_recent(fin["ledger_months"], fin["current_month"])
    projection = modeling.project_cash(
        modeling.baseline_inputs({}),
        {"cash": fin["cash_value"], "revenue": avg["revenue"], "expenses": avg["expenses"],
         "start_month": fin["current_month"]},
    )
    # Same basis: the model's no-change runway equals the headline runway.
    assert round(projection["runway_months"], 1) == fin["runway_months"]


def test_reserve_forecast_uses_same_burn_as_headline():
    entries = [_exp(1, "2026-06", 9000), _exp(2, "2026-07", 9000),
               _exp(3, "2026-08", 9000), _exp(4, "2026-09", 9000), _exp(5, "2026-10", 200)]
    fin = _fin(entries, cash=30000)
    fin["min_cash_reserve"] = 20000
    sig = risk_forecast.detect_cash_runway_forecast(fin, today=MID_OCT.date())
    assert sig is not None
    assert sig["forecast"]["window"] == "2026-07 to 2026-09"
    assert fin["avg_burn_value"] == 9000


def test_cash_growing_is_not_missing_runway():
    entries = [_exp(1, "2026-09", 1000),
               {"id": "r1", "type": "revenue", "category": "Sales", "name": "Sale",
                "amount": 5000, "month": "2026-09", "recurring": False}]
    fin = _fin(entries)
    assert fin["runway_months"] is None
    assert fin["runway_no_burn"] is True
    assert fin["runway_state"] == server.FIGURE_ZERO_CONFIRMED


def test_synthesis_carries_runway_basis():
    fin = _fin([_exp(1, "2026-08", 5000), _exp(2, "2026-09", 5000)])
    payload = server.financials_for_synthesis(fin)
    assert payload["runway_basis"].startswith("Based on average net burn over Aug 2026 to Sep 2026")


# ------------------------------------------------- cross-source duplicates

def _synced(i, month, amount, name="Office rent - Bill", etype="expense", source="quickbooks_sync"):
    return {"id": f"s{i}", "type": etype, "category": "Rent", "name": name, "amount": amount,
            "month": month, "recurring": False, "qb_txn_id": f"qb_bill_{i}", "source": source}


def test_flags_hand_entry_matching_synced_row():
    entries = [
        {"id": "m1", "type": "expense", "category": "Rent", "name": "Rent", "amount": 2500,
         "month": "2026-09", "recurring": False, "source": "manual"},
        _synced(1, "2026-09", 2500),
    ]
    found = automations.detect_cross_source_duplicates(entries, "2026-10", "$")
    assert len(found) == 1
    f = found[0]
    assert f["kind"] == "cross_source_duplicate"
    assert f["entry_ids"] == ["m1", "s1"]
    assert "QuickBooks" in f["detail"] and "Rent" in f["title"]


def test_recurring_hand_entry_vs_monthly_synced_bills():
    entries = [
        {"id": "m1", "type": "expense", "category": "Rent", "name": "Rent", "amount": 2500,
         "month": "2026-07", "recurring": True, "source": "manual"},
        _synced(1, "2026-07", 2500, source="xero_sync"),
        _synced(2, "2026-08", 2500, source="xero_sync"),
        _synced(3, "2026-09", 2500, source="xero_sync"),
    ]
    found = automations.detect_cross_source_duplicates(entries, "2026-10", "")
    assert len(found) == 1
    assert found[0]["severity"] == "medium"
    assert found[0]["entry_ids"] == ["m1", "s1", "s2", "s3"]
    assert "Xero" in found[0]["detail"] and "Review" in found[0]["detail"]


def test_no_flag_without_a_sync_or_for_small_or_different_amounts():
    manual = {"id": "m1", "type": "expense", "category": "Rent", "name": "Rent", "amount": 2500,
              "month": "2026-09", "recurring": False}
    assert automations.detect_cross_source_duplicates([manual], "2026-10") == []
    # Different amount.
    assert automations.detect_cross_source_duplicates([manual, _synced(1, "2026-09", 2600)], "2026-10") == []
    # Different month.
    assert automations.detect_cross_source_duplicates([manual, _synced(1, "2026-08", 2500)], "2026-10") == []
    # Immaterial: a 20 coffee next to 50k of synced spend.
    coffee = {"id": "m2", "type": "expense", "category": "Meals", "name": "Coffee", "amount": 20,
              "month": "2026-09", "recurring": False}
    big = _synced(2, "2026-09", 50000, name="Payroll")
    small = _synced(3, "2026-09", 20, name="Cafe")
    assert automations.detect_cross_source_duplicates([coffee, big, small], "2026-10") == []
    # Too old to matter.
    old = dict(manual, month="2025-01")
    assert automations.detect_cross_source_duplicates([old, _synced(4, "2025-01", 2500)], "2026-10") == []


def test_rounded_hand_entry_still_matches_and_each_synced_row_used_once():
    entries = [
        {"id": "m1", "type": "expense", "category": "Rent", "name": "Rent", "amount": 2500,
         "month": "2026-09", "recurring": False},
        {"id": "m2", "type": "expense", "category": "Rent", "name": "Rent again", "amount": 2500,
         "month": "2026-09", "recurring": False},
        _synced(1, "2026-09", 2498.75),
    ]
    found = automations.detect_cross_source_duplicates(entries, "2026-10")
    assert len(found) == 1 and found[0]["entry_ids"] == ["m1", "s1"]


def test_detect_anomalies_includes_cross_source():
    entries = [
        {"id": "m1", "type": "expense", "category": "Rent", "name": "Rent", "amount": 2500,
         "month": "2026-09", "recurring": False},
        _synced(1, "2026-09", 2500),
    ]
    kinds = {a["kind"] for a in automations.detect_anomalies(entries, {"currency_symbol": "$"}, "2026-10")}
    assert "cross_source_duplicate" in kinds
    assert "cross_source_duplicate" in automations.ANOMALY_KINDS


# ------------------------------------------------------------- lineage

def test_sync_does_full_repull_when_mapper_version_changes():
    c = {"qb_last_synced_at": "2026-10-01T00:00:00+00:00"}
    assert server._sync_since(c, "qb_last_synced_at", "qb_mapping_version") is None
    c["qb_mapping_version"] = "1999-01-01.0"
    assert server._sync_since(c, "qb_last_synced_at", "qb_mapping_version") is None
    c["qb_mapping_version"] = amap.MAPPING_VERSION
    assert server._sync_since(c, "qb_last_synced_at", "qb_mapping_version") == "2026-10-01T00:00:00+00:00"


def test_synced_rows_are_stamped_with_mapping_version():
    inserted = []
    db = MagicMock()
    db.financial_entries.find = MagicMock(return_value=_cursor([]))
    db.financial_entries.delete_many = AsyncMock()
    db.financial_entries.insert_one = AsyncMock(side_effect=lambda doc: inserted.append(doc))
    db.workspaces.find_one = AsyncMock(return_value={"financial_settings": {"currency": "usd"}})
    txn = {"qb_txn_id": "quickbooks_bill_9", "type": "expense", "category": "Rent",
           "name": "Office rent", "amount": 2500.0, "month": "2026-09"}
    with patch.object(server, "db", db), \
            patch.object(server.dept_migrate, "finance_department_id", AsyncMock(return_value="dept_fin")):
        db.financial_entries.bulk_write = AsyncMock(side_effect=lambda ops, ordered=False: (
            inserted.extend(
                (getattr(op, "_doc", None) or {})
                for op in ops if type(op).__name__ == "InsertOne"
            )
        ))
        n = asyncio.run(server._upsert_accounting_sync_entries(
            ws_id="ws_dm", principal={"user_id": "u1"}, txns=[txn], source="quickbooks_sync",
        ))
    assert n["synced_count"] == 1
    assert inserted[0]["mapping_version"] == amap.MAPPING_VERSION
    assert inserted[0]["source"] == "quickbooks_sync"
