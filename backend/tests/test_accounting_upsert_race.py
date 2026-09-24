"""Regression: accounting sync insert races on qb_txn_id unique index."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pymongo.errors import DuplicateKeyError

import server


@pytest.mark.asyncio
async def test_upsert_accounting_sync_handles_duplicate_key():
    insert = AsyncMock(side_effect=DuplicateKeyError("E11000"))
    update = AsyncMock()
    delete_many = AsyncMock()
    find = MagicMock()
    find.to_list = AsyncMock(return_value=[])  # no pre-existing rows

    class Cursor:
        def to_list(self, _n):
            return find.to_list(_n)

    mock_db = MagicMock()
    mock_db.financial_entries.find = MagicMock(return_value=Cursor())
    mock_db.financial_entries.insert_one = insert
    mock_db.financial_entries.update_one = update
    mock_db.financial_entries.delete_many = delete_many
    mock_db.financial_entries.delete_one = AsyncMock()
    mock_db.workspaces.find_one = AsyncMock(return_value={"financial_settings": {"currency": "usd"}})

    txns = [{
        "qb_txn_id": "qb_purchase_1",
        "type": "expense",
        "category": "Cloud",
        "name": "AWS",
        "amount": 10.0,
        "month": "2026-01",
        "note": "",
        "recurring": False,
    }]
    with (
        patch.object(server, "db", mock_db),
        patch.object(server.dept_migrate, "finance_department_id", AsyncMock(return_value=None)),
        patch.object(server, "invalidate_financials_cache"),
    ):
        n = await server._upsert_accounting_sync_entries(
            ws_id="ws1",
            principal={"user_id": "u1"},
            txns=txns,
            source="quickbooks_sync",
        )
    assert n == 1
    insert.assert_awaited_once()
    update.assert_awaited_once()
    # Safety net: also deletes dated legacy ids that rewrite to this stable id.
    assert delete_many.await_count >= 1
    filt, payload = update.await_args.args
    assert filt == {"workspace_id": "ws1", "qb_txn_id": "qb_purchase_1"}
    assert payload["$set"]["amount"] == 10.0
