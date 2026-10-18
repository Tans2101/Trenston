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


# ---- emails to the people working in the department ----
import pytest
import server


@pytest.fixture
def mail(monkeypatch):
    sent = []

    async def fake_send(*, to, subject, html, **_k):
        sent.append({"to": to, "subject": subject, "html": html})
        return {"sent": True}

    monkeypatch.setattr(server, "send_resend_email", fake_send)
    return sent


async def _nudge_setup(monkeypatch):
    db = await _setup()
    monkeypatch.setattr(server, "db", db)
    await db.workspaces.insert_one({"workspace_id": WS, "name": "Acme"})
    await db.users.update_one({"user_id": "u_priya"}, {"$set": {"email": "priya@example.com"}})
    await db.users.insert_one({"user_id": "u_sam", "name": "Sam Lee", "email": "sam@example.com"})
    await db.users.insert_one({"user_id": "u_gone", "name": "Gone", "email": "gone@example.com"})
    await db.department_members.insert_many([
        {"department_id": "d_sales", "user_id": "u_sam", "role": "member"},
        {"department_id": "d_sales", "user_id": "u_gone", "role": "member"},
        {"department_id": "d_prod", "user_id": "u_sam", "role": "member"},
    ])
    for uid in ("u_priya", "u_sam"):
        await db.memberships.insert_one({"workspace_id": WS, "user_id": uid, "status": "active"})
    await db.memberships.insert_one({"workspace_id": WS, "user_id": "u_gone", "status": "revoked"})
    return db


def test_everyone_in_the_quiet_department_gets_a_personal_email(monkeypatch, mail):
    async def go():
        await _nudge_setup(monkeypatch)
        stats = await server.run_stale_department_nudges(now=NOW)
        assert stats["departments_nudged"] == 1 and stats["emails_sent"] == 2
        by_to = {m["to"][0]: m for m in mail}
        assert set(by_to) == {"priya@example.com", "sam@example.com"}  # revoked member skipped
        assert "Hi Priya," in by_to["priya@example.com"]["html"]
        assert "Hi Sam," in by_to["sam@example.com"]["html"]
        assert "Sales department hasn't been updated in 20 days" in by_to["sam@example.com"]["html"]
        assert by_to["sam@example.com"]["subject"] == "Sales has not been updated in 20 days"

    run(go())


def test_a_department_is_not_nudged_again_within_the_cooldown(monkeypatch, mail):
    async def go():
        await _nudge_setup(monkeypatch)
        await server.run_stale_department_nudges(now=NOW)
        mail.clear()
        again = await server.run_stale_department_nudges(now=NOW + timedelta(days=2))
        assert again["emails_sent"] == 0 and again["skipped_cooldown"] == 1
        later = await server.run_stale_department_nudges(now=NOW + timedelta(days=8))
        assert later["emails_sent"] == 2

    run(go())


def test_a_failed_send_does_not_start_the_cooldown(monkeypatch):
    async def go():
        await _nudge_setup(monkeypatch)

        async def fail(**_k):
            return {"sent": False}

        monkeypatch.setattr(server, "send_resend_email", fail)
        stats = await server.run_stale_department_nudges(now=NOW)
        assert stats["send_failed"] == 1
        sent = []

        async def ok(*, to, **_k):
            sent.append(to)
            return {"sent": True}

        monkeypatch.setattr(server, "send_resend_email", ok)
        retry = await server.run_stale_department_nudges(now=NOW)
        assert retry["emails_sent"] == 2

    run(go())
