"""Null-vs-zero for MRR/runway: expense-only ≠ $0 MRR; profitable ≠ missing runway."""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_financials_null_vs_zero")

import server  # noqa: E402


def _entries_cursor(rows):
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=rows)
    return cursor


def _run_compute(entries, settings):
    import simple_cache
    simple_cache.clear()
    mock_db = MagicMock()
    mock_db.workspaces.find_one = AsyncMock(
        return_value={"financial_settings": settings},
    )
    mock_db.financial_entries.find = MagicMock(return_value=_entries_cursor(entries))
    with patch.object(server, "db", mock_db):
        return asyncio.run(server.compute_financials("ws_test", bypass_cache=True))


def test_format_runway_display_states():
    assert server.format_runway_display({"runway_months": 12.5}) == "12.5 months"
    assert server.format_runway_display({"runway_months": 0}) == "0 months"
    assert server.format_runway_display({"runway_months": None, "runway_no_burn": True}) == (
        server.RUNWAY_NO_BURN_LABEL
    )
    assert server.format_runway_display({"runway_months": None}) == "Add data"
    assert server.format_runway_display({"runway_months": None}, missing="—") == "—"


def test_one_time_revenue_does_not_confirm_zero_mrr():
    """One-time sales are not MRR — must not render as confirmed $0."""
    fin = _run_compute(
        [
            {
                "type": "revenue",
                "category": "Project",
                "amount": 15000,
                "month": "2026-09",
                "recurring": False,
            },
            {
                "type": "expense",
                "category": "Ops",
                "amount": 3000,
                "month": "2026-09",
                "recurring": True,
            },
        ],
        {"cash": 50000, "currency": "usd", "cash_entered": True},
    )
    assert fin["mrr_known"] is False
    assert fin["mrr_state"] == server.FIGURE_NOT_ENTERED
    assert fin["mrr"] == "—"
    assert fin["mrr_value"] is None
    assert server.format_mrr_display(fin) == "Add data"


def test_confirmed_zero_recurring_mrr_shows_zero():
    fin = _run_compute(
        [
            {
                "type": "revenue",
                "category": "Subscriptions",
                "amount": 0,
                "month": "2026-09",
                "recurring": True,
            },
        ],
        {"cash": 10000, "currency": "usd", "cash_entered": True},
    )
    assert fin["mrr_known"] is True
    assert fin["mrr_state"] == server.FIGURE_ZERO_CONFIRMED
    assert fin["mrr_value"] == 0
    assert server.format_mrr_display(fin) == fin["mrr"]
    assert "$0" in fin["mrr"] or fin["mrr"].endswith("0")


def test_empty_workspace_finance_displays_are_add_data():
    fin = _run_compute([], {})
    assert fin["mrr_known"] is False
    assert fin["burn_known"] is False
    assert fin["cash_entered"] is False
    assert fin["runway_state"] == server.FIGURE_NOT_ENTERED
    assert server.format_mrr_display(fin) == "Add data"
    assert server.format_runway_display(fin) == "Add data"
    assert server.format_burn_display(fin) == "Add data"


def test_briefing_missing_metrics_link_to_add_data():
    fin = _run_compute([], {})
    metrics = {m["label"]: m for m in server._briefing_finance_metrics(fin)}
    assert metrics["MRR"]["missing"] is True
    assert metrics["MRR"]["href"] == "/app/financials#log-mrr"
    assert metrics["Burn"]["href"] == "/app/financials#log-entry"
    assert metrics["Runway"]["href"] == "/app/financials#cash"

    with_cash = _run_compute([], {"cash": 10000, "currency": "usd"})
    runway = next(m for m in server._briefing_finance_metrics(with_cash) if m["label"] == "Runway")
    assert runway["missing"] is True
    assert runway["href"] == "/app/financials#log-entry"


def test_report_money_card_uses_add_data_not_dash():
    fin = {
        "mrr": "—",
        "mrr_known": False,
        "mrr_value": None,
        "burn": "—",
        "burn_known": False,
        "burn_value": None,
        "runway_months": None,
        "runway_no_burn": False,
        "currency": "usd",
    }
    cards = server._computed_report_cards({}, fin, [], [], 1, prior=None, include_financials=True)
    money = next(c for c in cards if c["id"] == "auto_fin")
    values = {m["label"]: m["value"] for m in money["metrics"]}
    assert values["Monthly recurring revenue"] == "Add data"
    assert values["Cash runway"] == "Add data"
    assert values["Net burn this month"] == "Add data"


def test_profitable_company_runway_is_not_add_data():
    fin = _run_compute(
        [
            {
                "type": "revenue",
                "category": "Subscriptions",
                "amount": 20000,
                "month": "2026-07",
                "recurring": True,
            },
            {
                "type": "revenue",
                "category": "Subscriptions",
                "amount": 20000,
                "month": "2026-08",
                "recurring": True,
            },
            {
                "type": "revenue",
                "category": "Subscriptions",
                "amount": 20000,
                "month": "2026-09",
                "recurring": True,
            },
            {
                "type": "expense",
                "category": "Ops",
                "amount": 8000,
                "month": "2026-07",
                "recurring": True,
            },
            {
                "type": "expense",
                "category": "Ops",
                "amount": 8000,
                "month": "2026-08",
                "recurring": True,
            },
            {
                "type": "expense",
                "category": "Ops",
                "amount": 8000,
                "month": "2026-09",
                "recurring": True,
            },
        ],
        {"cash": 250000, "currency": "usd"},
    )
    assert fin["runway_months"] is None
    assert fin["runway_no_burn"] is True
    assert fin["runway_state"] == server.FIGURE_ZERO_CONFIRMED
    assert server.format_runway_display(fin) == server.RUNWAY_NO_BURN_LABEL
    assert fin["mrr_known"] is True
    assert fin["mrr_state"] == server.FIGURE_COMPUTED


def test_empty_ledger_runway_still_missing():
    fin = _run_compute([], {"cash": 250000, "currency": "usd"})
    assert fin["runway_months"] is None
    assert fin["runway_no_burn"] is False
    assert fin["mrr_known"] is False
    assert server.format_runway_display(fin) == "Add data"


def test_synthesis_skips_runway_unknown_when_no_burn():
    payload = server.financials_for_synthesis(
        {
            "cash_entered": True,
            "cash_value": 250000,
            "mrr_known": True,
            "mrr_value": 20000,
            "burn_known": True,
            "burn_value": -12000,
            "runway_months": None,
            "runway_no_burn": True,
            "currency": "usd",
        }
    )
    assert "runway_not_computable" not in payload["unknown_fields"]
    assert payload["runway_no_burn"] is True
    assert "cash is growing" in payload["instructions_for_missing_data"]


def test_synthesis_marks_revenue_not_entered():
    payload = server.financials_for_synthesis(
        {
            "cash_entered": True,
            "cash_value": 100000,
            "mrr_known": False,
            "mrr_value": None,
            "burn_known": True,
            "burn_value": 5000,
            "runway_months": 20.0,
            "runway_no_burn": False,
            "currency": "usd",
        }
    )
    assert "revenue_not_entered" in payload["unknown_fields"]
    assert payload["mrr"] is None


def test_compute_financials_cache_hit_skips_second_db_read():
    import simple_cache
    simple_cache.clear()
    entries = [
        {
            "type": "revenue",
            "category": "Subscriptions",
            "amount": 1000,
            "month": "2026-09",
            "recurring": True,
        },
    ]
    mock_db = MagicMock()
    mock_db.workspaces.find_one = AsyncMock(
        return_value={"financial_settings": {"cash": 50000, "currency": "usd"}},
    )
    find_mock = MagicMock(return_value=_entries_cursor(entries))
    mock_db.financial_entries.find = find_mock
    with patch.object(server, "db", mock_db):
        first = asyncio.run(server.compute_financials("ws_cache"))
        second = asyncio.run(server.compute_financials("ws_cache"))
    assert first["mrr_known"] is True
    assert second["mrr"] == first["mrr"]
    assert find_mock.call_count == 1
    assert simple_cache.stats()["hits"] >= 1


def test_invalidate_financials_cache_forces_recompute():
    import simple_cache
    simple_cache.clear()
    entries = [
        {
            "type": "expense",
            "category": "Cloud",
            "amount": 100,
            "month": "2026-09",
            "recurring": True,
        },
    ]
    mock_db = MagicMock()
    mock_db.workspaces.find_one = AsyncMock(
        return_value={"financial_settings": {"cash": 1000, "currency": "usd"}},
    )
    find_mock = MagicMock(return_value=_entries_cursor(entries))
    mock_db.financial_entries.find = find_mock
    with patch.object(server, "db", mock_db):
        asyncio.run(server.compute_financials("ws_inv"))
        server.invalidate_financials_cache("ws_inv")
        asyncio.run(server.compute_financials("ws_inv"))
    assert find_mock.call_count == 2


def test_compute_financials_return_entries_reused_by_live_signals():
    import simple_cache
    simple_cache.clear()
    entries = [
        {
            "type": "expense",
            "category": "Cloud",
            "amount": 250,
            "month": "2026-09",
            "recurring": True,
        },
    ]
    mock_db = MagicMock()
    mock_db.workspaces.find_one = AsyncMock(
        return_value={"financial_settings": {"cash": 10000, "currency": "usd"}},
    )
    find_mock = MagicMock(return_value=_entries_cursor(entries))
    mock_db.financial_entries.find = find_mock
    mock_db.deals.find = MagicMock(return_value=_entries_cursor([]))

    async def _run():
        with patch.object(server, "db", mock_db), \
             patch.object(server, "get_ws", new=AsyncMock(return_value={
                 "workspace_id": "ws_sig", "tasks": {"items": []}, "people": {"people": []},
             })), \
             patch.object(server, "_recent_updates", new=AsyncMock(return_value=[])), \
             patch.object(server, "_department_signal_inputs", new=AsyncMock(return_value=[])):
            await server._workspace_live_signals("ws_sig")

    asyncio.run(_run())
    # One financial_entries read inside compute_financials — not a second for signals.
    assert find_mock.call_count == 1
