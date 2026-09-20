"""Delivered procurement request → automatic expense financial entry."""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DB_NAME", "test_proc_expense")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402

PRINCIPAL = {
    "user_id": "u_ceo",
    "name": "CEO",
    "email": "ceo@example.com",
    "workspace_id": "ws1",
    "pack": "owner",
    "role": "owner",
}


class FinStore:
    def __init__(self):
        self.rows = []

    async def find_one(self, query, projection=None):
        for r in self.rows:
            if all(r.get(k) == v for k, v in query.items()):
                return {k: v for k, v in r.items() if k != "_id"}
        return None

    async def insert_one(self, doc):
        sid = doc.get("source_procurement_request_id")
        if sid:
            for r in self.rows:
                if (
                    r.get("workspace_id") == doc.get("workspace_id")
                    and r.get("source_procurement_request_id") == sid
                ):
                    raise Exception("E11000 duplicate key error source_procurement_request_id")
        self.rows.append(dict(doc))
        return MagicMock()

    async def update_one(self, query, update):
        for r in self.rows:
            if all(r.get(k) == v for k, v in query.items()):
                r.update(update.get("$set") or {})
                return MagicMock(matched_count=1)
        return MagicMock(matched_count=0)


@pytest.mark.asyncio
async def test_delivered_priced_request_creates_expense():
    store = FinStore()
    req = {
        "id": "preq_abc",
        "item": "Steel bolts",
        "vendor_name": "Acme",
        "cost": 42.5,
        "status": "delivered",
        "actual_delivery_date": "2026-09-15",
    }
    with patch.object(server, "db", MagicMock(financial_entries=store)), \
         patch.object(server.dept_migrate, "finance_department_id", AsyncMock(return_value="dept_fin")), \
         patch.object(server, "invalidate_financials_cache"):
        entry, created = await server._ensure_procurement_expense_entry(req, PRINCIPAL)
    assert created is True
    assert entry["type"] == "expense"
    assert entry["category"] == "Procurement"
    assert entry["amount"] == 42.5
    assert entry["month"] == "2026-09"
    assert entry["source_procurement_request_id"] == "preq_abc"
    assert entry["name"] == "Steel bolts"
    assert "Acme" in entry["note"]


@pytest.mark.asyncio
async def test_skips_when_not_delivered_or_unpriced():
    store = FinStore()
    with patch.object(server, "db", MagicMock(financial_entries=store)), \
         patch.object(server.dept_migrate, "finance_department_id", AsyncMock(return_value="dept_fin")), \
         patch.object(server, "invalidate_financials_cache"):
        e1, c1 = await server._ensure_procurement_expense_entry(
            {"id": "preq_1", "item": "X", "cost": 10, "status": "ordered"}, PRINCIPAL,
        )
        e2, c2 = await server._ensure_procurement_expense_entry(
            {"id": "preq_2", "item": "Y", "cost": None, "status": "delivered"}, PRINCIPAL,
        )
    assert e1 is None and c1 is False
    assert e2 is None and c2 is False
    assert store.rows == []


@pytest.mark.asyncio
async def test_idempotent_then_updates_cost():
    store = FinStore()
    req = {
        "id": "preq_z",
        "item": "Oil",
        "vendor_name": "Other",
        "cost": 50,
        "status": "delivered",
        "actual_delivery_date": "2026-09-01",
    }
    with patch.object(server, "db", MagicMock(financial_entries=store)), \
         patch.object(server.dept_migrate, "finance_department_id", AsyncMock(return_value="dept_fin")), \
         patch.object(server, "invalidate_financials_cache"):
        first, created1 = await server._ensure_procurement_expense_entry(req, PRINCIPAL)
        second, created2 = await server._ensure_procurement_expense_entry(req, PRINCIPAL)
        req2 = {**req, "cost": 75}
        third, created3 = await server._ensure_procurement_expense_entry(req2, PRINCIPAL)
    assert created1 is True and created2 is False and created3 is False
    assert first["id"] == second["id"] == third["id"]
    assert len(store.rows) == 1
    assert store.rows[0]["amount"] == 75.0


def test_procurement_expense_month_prefers_delivery():
    assert server._procurement_expense_month({
        "actual_delivery_date": "2026-08-20",
        "ordered_at": "2026-07-01T00:00:00+00:00",
        "created_at": "2026-06-01T00:00:00+00:00",
    }) == "2026-08"
    assert server._procurement_expense_month({
        "ordered_at": "2026-07-15T12:00:00+00:00",
    }) == "2026-07"
