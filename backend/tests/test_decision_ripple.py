"""Decision ripple: saved money effects, Financials-only access, cleanup on delete."""
import asyncio
import os

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_decision_ripple")

import pytest  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

import server  # noqa: E402

OWNER = {"workspace_id": "w1", "user_id": "u1", "pack": "owner", "role": "owner"}


def _setup(monkeypatch, *, fin_access=True):
    db = AsyncMongoMockClient()["t"]
    monkeypatch.setattr(server, "db", db)

    async def access(_p):
        return fin_access

    async def fin(_ws):
        return {"current_month": "2026-10", "has_data": True, "cash_entered": True, "cash_value": 500000,
                "ledger_months": [{"month": "2026-09", "revenue": 100000, "expenses": 120000}],
                "currency": "php"}

    async def can_write(*a, **k):
        return True

    async def noop(*a, **k):
        return None

    monkeypatch.setattr(server, "can_access_financials", access)
    monkeypatch.setattr(server, "compute_financials", fin)
    monkeypatch.setattr(server, "can_section_write", can_write)
    monkeypatch.setattr(server, "log_activity", noop)
    return db


def test_save_read_and_clear_effect(monkeypatch):
    db = _setup(monkeypatch)

    async def run():
        await db.workspaces.insert_one({"workspace_id": "w1", "decisions": [{"id": "d1", "title": "Hire 2 devs"}]})
        body = server.DecisionRippleIn(direction="cost", cadence="monthly", amount=80000, start_offset=3)
        await server.save_decision_ripple("d1", body, OWNER)
        data = await server.decision_ripple_data(OWNER)
        assert data["baseline"]["cash"] == 500000
        assert data["effects"]["d1"]["amount"] == 80000 and data["effects"]["d1"]["start_offset"] == 3
        # Saving again updates the same row.
        await server.save_decision_ripple("d1", server.DecisionRippleIn(amount=50000), OWNER)
        assert await db.decision_effects.count_documents({}) == 1
        await server.clear_decision_ripple("d1", OWNER)
        assert await db.decision_effects.count_documents({}) == 0

    asyncio.run(run())


def test_unknown_decision_and_bad_input(monkeypatch):
    db = _setup(monkeypatch)

    async def run():
        await db.workspaces.insert_one({"workspace_id": "w1", "decisions": []})
        with pytest.raises(server.HTTPException) as exc:
            await server.save_decision_ripple("nope", server.DecisionRippleIn(amount=1), OWNER)
        assert exc.value.status_code == 404

    asyncio.run(run())
    with pytest.raises(Exception):
        server.DecisionRippleIn(amount=-5)
    with pytest.raises(Exception):
        server.DecisionRippleIn(amount=5, start_offset=40)


def test_no_financials_access_means_no_money(monkeypatch):
    _setup(monkeypatch, fin_access=False)

    async def run():
        with pytest.raises(server.HTTPException) as exc:
            await server.decision_ripple_data(OWNER)
        assert exc.value.status_code == 403

    asyncio.run(run())


def test_deleting_a_decision_removes_its_effect(monkeypatch):
    db = _setup(monkeypatch)

    async def run():
        await db.workspaces.insert_one({"workspace_id": "w1", "decisions": [{"id": "d1", "title": "X"}]})
        await server.save_decision_ripple("d1", server.DecisionRippleIn(amount=10), OWNER)
        await server.delete_decision("d1", OWNER)
        assert await db.decision_effects.count_documents({}) == 0

    asyncio.run(run())
