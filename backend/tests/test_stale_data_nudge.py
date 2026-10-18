"""Quiet departments are flagged to the owner, in the Briefing and the daily email."""
import asyncio
import os

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_db")
from datetime import datetime, timedelta, timezone

from mongomock_motor import AsyncMongoMockClient

import data_freshness as df
import ops_briefing as ob

WS = "ws_stale"
NOW = datetime(2026, 10, 18, 8, 0, tzinfo=timezone.utc)


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _iso(days_ago):
    return (NOW - timedelta(days=days_ago)).isoformat()


async def _setup():
    db = AsyncMongoMockClient()["stale_nudge"]
    await db.departments.insert_many([
        {"workspace_id": WS, "department_id": "d_sales", "type": "sales", "name": "Sales", "enabled": True},
        {"workspace_id": WS, "department_id": "d_prod", "type": "production", "name": "Production", "enabled": True},
        {"workspace_id": WS, "department_id": "d_hr", "type": "hr", "name": "HR", "enabled": True},
        {"workspace_id": WS, "department_id": "d_leg", "type": "legal", "name": "Legal", "enabled": False},
    ])
    await db.users.insert_one({"user_id": "u_priya", "name": "Priya"})
    await db.department_members.insert_one({"department_id": "d_sales", "user_id": "u_priya", "role": "lead"})
    await db.sales_order_book.insert_one({"department_id": "d_sales", "created_at": _iso(20)})
    await db.production_work_orders.insert_one({"department_id": "d_prod", "updated_at": _iso(2)})
    await db.legal_matters.insert_one({"department_id": "d_leg", "created_at": _iso(90)})
    return db


def test_only_quiet_used_departments_are_flagged_with_their_lead():
    async def go():
        db = await _setup()
        alerts = await df.stale_department_alerts(db, WS, now=NOW)
        assert [a["type"] for a in alerts] == ["sales"]  # fresh, unused and disabled are skipped
        assert alerts[0]["days_since_update"] == 20
        assert alerts[0]["lead_name"] == "Priya"

    run(go())


def test_a_recent_deal_keeps_sales_fresh():
    async def go():
        db = await _setup()
        await db.deals.insert_one({"department_id": "d_sales", "updated_at": _iso(1)})
        assert await df.stale_department_alerts(db, WS, now=NOW) == []

    run(go())


def test_email_names_the_department_and_lead():
    html = ob.daily_briefing_email_html(
        workspace_name="Acme", app_url="https://x.test",
        data={"sections": {}, "stale_data": [
            {"name": "Sales", "days_since_update": 20, "lead_name": "Priya"},
            {"name": "HR", "days_since_update": 15, "lead_name": None},
        ]},
    )
    assert "Data may be out of date" in html
    assert "No update in 20 days. Ask Priya." in html
    assert "No update in 15 days." in html


def test_email_without_stale_data_has_no_warning():
    html = ob.daily_briefing_email_html(workspace_name="Acme", app_url="https://x.test", data={"sections": {}})
    assert "Data may be out of date" not in html
