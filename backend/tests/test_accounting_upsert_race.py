"""Regression: accounting sync insert races on qb_txn_id unique index."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pymongo.errors import BulkWriteError

import server


@pytest.mark.asyncio
async def test_upsert_accounting_sync_handles_duplicate_key():
    update = AsyncMock()
    delete_many = AsyncMock()

    class Cursor:
        def to_list(self, _n):
            return AsyncMock(return_value=[])()

    async def _empty_list(_n):
        return []

    cursor = MagicMock()
    cursor.to_list = _empty_list

    mock_db = MagicMock()
    mock_db.financial_entries.find = MagicMock(return_value=cursor)
    mock_db.financial_entries.update_one = update
    mock_db.financial_entries.delete_many = delete_many
    mock_db.financial_entries.delete_one = AsyncMock()
    mock_db.workspaces.find_one = AsyncMock(return_value={"financial_settings": {"currency": "usd"}})

    async def _bulk_fail(ops, ordered=False):
        raise BulkWriteError({"writeErrors": [{"index": 0, "code": 11000, "errmsg": "E11000"}]})

    mock_db.financial_entries.bulk_write = AsyncMock(side_effect=_bulk_fail)

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
    assert n["synced_count"] == 1
    mock_db.financial_entries.bulk_write.assert_awaited_once()
    # Fallback path after BulkWriteError duplicate key.
    assert update.await_count >= 1
    assert delete_many.await_count >= 1
    filt, payload = update.await_args.args
    assert filt["workspace_id"] == "ws1"
    assert filt["qb_txn_id"] == "qb_purchase_1"
    assert payload["$set"]["amount"] == 10.0
