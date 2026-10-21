"""Regression tests for extreme-debug fixes on backend/server.py (Oct 2026)."""
from __future__ import annotations

import os
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_extreme_debug_server_oct2026")

import server  # noqa: E402

OWNER = {
    "user_id": "u_owner",
    "email": "owner@example.com",
    "name": "Owner",
    "workspace_id": "ws1",
    "role": "owner",
    "pack": "owner",
}

FINANCE_MEMBER = {
    "user_id": "u_fin",
    "email": "fin@example.com",
    "name": "Finance",
    "workspace_id": "ws1",
    "role": "member",
    "pack": "finance",
}


@pytest.mark.asyncio
async def test_compute_financials_for_principal_scopes_non_ceo():
    with patch.object(
        server.dept_access, "accessible_department_ids", new=AsyncMock(return_value=["dept_a"]),
    ), patch.object(
        server, "compute_financials", new=AsyncMock(return_value={"mrr_value": 1}),
    ) as compute:
        out = await server.compute_financials_for_principal(FINANCE_MEMBER, return_entries=True)
        assert out["mrr_value"] == 1
        compute.assert_awaited_once_with(
            "ws1", department_ids=["dept_a"], return_entries=True, bypass_cache=False,
        )


@pytest.mark.asyncio
async def test_compute_financials_for_principal_ceo_bypass():
    with patch.object(
        server.dept_access, "accessible_department_ids", new=AsyncMock(return_value=None),
    ), patch.object(
        server, "compute_financials", new=AsyncMock(return_value={"ok": True}),
    ) as compute:
        await server.compute_financials_for_principal(OWNER)
        compute.assert_awaited_once_with(
            "ws1", department_ids=None, return_entries=False, bypass_cache=False,
        )


@pytest.mark.asyncio
async def test_csv_confirm_rolls_back_receipt_when_insert_fails(monkeypatch):
    from tests.mongo_mocks import FakeCollection

    class _DB:
        def __init__(self):
            self.csv_import_receipts = FakeCollection()
            self.financial_entries = FakeCollection()

        async def boom_insert_many(self, docs):
            raise RuntimeError("boom")

    db = _DB()
    db.financial_entries.insert_many = db.boom_insert_many  # type: ignore[method-assign]
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server.dept_migrate, "finance_department_id", AsyncMock(return_value="fin_dept"))
    monkeypatch.setattr(server, "_workspace_currency", AsyncMock(return_value="usd"))
    monkeypatch.setattr(server, "_workspace_now", AsyncMock(return_value=datetime(2026, 3, 1)))
    monkeypatch.setattr(server, "invalidate_financials_cache", lambda *_: None)
    monkeypatch.setattr(server, "log_activity", AsyncMock())

    payload = server.CsvImportConfirmInput(entries=[
        {"type": "revenue", "amount": 100, "month": "2026-01", "category": "Sales", "name": "A"},
    ])
    with pytest.raises(HTTPException) as exc:
        await server.import_financials_csv_confirm(payload, OWNER)
    assert exc.value.status_code == 500
    assert await db.csv_import_receipts.find_one({"workspace_id": "ws1"}) is None


@pytest.mark.asyncio
async def test_delete_fin_entry_404_when_missing(monkeypatch):
    db = AsyncMongoMockClient()["del_fin"]
    monkeypatch.setattr(server, "db", db)
    with pytest.raises(HTTPException) as exc:
        await server.delete_fin_entry("fe_missing", OWNER)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_deal_404_when_missing(monkeypatch):
    db = AsyncMongoMockClient()["del_deal"]
    monkeypatch.setattr(server, "db", db)
    with pytest.raises(HTTPException) as exc:
        await server.delete_deal("deal_missing", OWNER)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_assemble_financial_export_refuses_over_cap(monkeypatch):
    db = AsyncMongoMockClient()["export_cap"]
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(
        server.dept_access, "accessible_department_ids", AsyncMock(return_value=None),
    )
    rows = [
        {"id": f"fe_{i}", "workspace_id": "ws1", "amount": 1, "type": "expense", "month": "2026-01"}
        for i in range(server._FINANCIAL_EXPORT_ROW_CAP + 1)
    ]
    await db.financial_entries.insert_many(rows)
    with pytest.raises(HTTPException) as exc:
        await server._assemble_financial_export_for(OWNER, None)
    assert exc.value.status_code == 400
    assert "more than" in str(exc.value.detail).lower()
