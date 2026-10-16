"""Financial ledger item names — distinct from category."""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_finance_entry_name")

import finance_entry  # noqa: E402
import server  # noqa: E402


def test_normalize_falls_back_to_category():
    assert finance_entry.normalize_entry_name("", "Cloud Expense") == "Cloud Expense"
    assert finance_entry.normalize_entry_name(None, None) == "Other"
    assert finance_entry.normalize_entry_name("  MongoDB  ", "Cloud/Infra") == "MongoDB"


def test_require_entry_name_rejects_blank():
    with pytest.raises(ValueError, match="required"):
        finance_entry.require_entry_name("  ")
    assert finance_entry.require_entry_name("Render Hosting") == "Render Hosting"


def test_add_fin_entry_stores_name():
    mock_db = MagicMock()
    mock_db.financial_entries.insert_one = AsyncMock()
    payload = server.FinEntryInput(
        type="expense",
        category="Cloud/Infra",
        name="MongoDB Database Subscription",
        amount=57,
        month="2026-09",
    )
    principal = {
        "user_id": "u1",
        "workspace_id": "ws1",
        "email": "a@b.c",
        "name": "A",
        "role": "owner",
        "pack": "owner",
    }
    with patch.object(server, "db", mock_db), patch.object(
        server.dept_migrate, "finance_department_id", new=AsyncMock(return_value="dept_fin"),
    ), patch.object(
        server.dept_migrate, "ensure_department_member", new=AsyncMock(return_value=True),
    ), patch.object(
        server, "_workspace_currency", new=AsyncMock(return_value="usd"),
    ), patch.object(server, "log_activity", new=AsyncMock()):
        result = asyncio.run(server.add_fin_entry(payload, principal))
    assert result["entry"]["name"] == "MongoDB Database Subscription"
    assert result["entry"]["category"] == "Cloud/Infra"
    assert "qb_txn_id" not in result["entry"]
    assert "source_deal_id" not in result["entry"]
    assert "recurrence" not in result["entry"]  # non-recurring → omit null


def test_add_fin_entry_survives_activity_log_failure():
    mock_db = MagicMock()
    mock_db.financial_entries.insert_one = AsyncMock()
    payload = server.FinEntryInput(
        type="revenue",
        category="Subscriptions",
        name="Acme MRR",
        amount=100,
        month="2026-09",
        recurring=True,
    )
    principal = {
        "user_id": "u1",
        "workspace_id": "ws1",
        "email": "a@b.c",
        "name": "A",
        "role": "owner",
        "pack": "owner",
    }
    with patch.object(server, "db", mock_db), patch.object(
        server.dept_migrate, "finance_department_id", new=AsyncMock(return_value="dept_fin"),
    ), patch.object(
        server.dept_migrate, "ensure_department_member", new=AsyncMock(return_value=True),
    ), patch.object(
        server, "_workspace_currency", new=AsyncMock(return_value="usd"),
    ), patch.object(
        server, "log_activity", new=AsyncMock(side_effect=RuntimeError("activities down")),
    ):
        result = asyncio.run(server.add_fin_entry(payload, principal))
    assert result["ok"] is True
    assert result["entry"]["recurrence"] == "monthly"


def test_add_fin_entry_maps_duplicate_key_to_409():
    from pymongo.errors import DuplicateKeyError

    mock_db = MagicMock()
    mock_db.workspaces.find_one = AsyncMock(return_value={"financial_settings": {"currency": "usd"}})
    mock_db.financial_entries.insert_one = AsyncMock(side_effect=DuplicateKeyError("E11000"))
    payload = server.FinEntryInput(
        type="expense",
        category="Other",
        name="Printer ink",
        amount=12,
        month="2026-09",
    )
    principal = {
        "user_id": "u1",
        "workspace_id": "ws1",
        "email": "a@b.c",
        "name": "A",
        "role": "owner",
        "pack": "owner",
    }
    with patch.object(server, "db", mock_db), patch.object(
        server.dept_migrate, "finance_department_id", new=AsyncMock(return_value="dept_fin"),
    ), patch.object(
        server.dept_migrate, "ensure_department_member", new=AsyncMock(return_value=True),
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(server.add_fin_entry(payload, principal))
    assert exc.value.status_code == 409


def test_add_fin_entry_rejects_blank_name():
    payload = server.FinEntryInput(
        type="expense",
        category="Cloud/Infra",
        name="   ",
        amount=10,
        month="2026-09",
    )
    principal = {
        "user_id": "u1",
        "workspace_id": "ws1",
        "email": "a@b.c",
        "name": "A",
        "role": "owner",
        "pack": "owner",
    }
    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.add_fin_entry(payload, principal))
    assert exc.value.status_code == 400
    assert "name is required" in str(exc.value.detail)


class _Cursor:
    def __init__(self, rows):
        self.rows = list(rows)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.rows:
            raise StopAsyncIteration
        return self.rows.pop(0)


def test_backfill_sets_missing_name_to_category():
    rows = [
        {"_id": "a", "category": "Cloud Expense"},
        {"_id": "b", "category": "Payroll"},
    ]
    coll = MagicMock()
    coll.find = MagicMock(return_value=_Cursor(rows))
    coll.update_one = AsyncMock()
    fake_db = MagicMock()
    fake_db.financial_entries = coll
    with patch.object(server, "db", fake_db):
        asyncio.run(server._backfill_financial_entry_names())
    assert coll.update_one.await_count == 2
    names = [call.args[1]["$set"]["name"] for call in coll.update_one.await_args_list]
    assert names == ["Cloud Expense", "Payroll"]
