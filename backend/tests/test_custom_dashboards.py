"""Custom dashboards: inquiry form, operator tools, approved emails, client view."""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_custom_dashboards")

import custom_dashboards as cd  # noqa: E402
import server  # noqa: E402

OPERATOR_EMAIL = "operator@trenston.com"
OPERATOR = {
    "user_id": "u_operator", "email": OPERATOR_EMAIL, "name": "Operator",
    "workspace_id": "ws_operator", "role": "owner", "pack": "owner",
}
STRANGER = {
    "user_id": "u_stranger", "email": "someone@else.com", "name": "Someone",
    "workspace_id": "ws_other", "role": "owner", "pack": "owner",
}

INQUIRY = {
    "name": "Dana Cruz",
    "email": "Dana@BigCo.com",
    "company": "BigCo Manufacturing",
    "role": "COO",
    "company_size": "201_1000",
    "tools": "SAP, Excel",
    "needs": "Daily output per line, cash, overdue orders.",
    "budget_range": "5k_10k",
}


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def env(monkeypatch):
    db = AsyncMongoMockClient()["test_custom_dashboards"]
    _run(db.users.insert_one({"user_id": "u_operator", "email": OPERATOR_EMAIL, "email_verified": True}))
    monkeypatch.setattr(server, "ANALYTICS_ADMIN_EMAIL", OPERATOR_EMAIL)
    sent = AsyncMock(return_value={"sent": True})
    invites = AsyncMock(return_value={"sent": True})
    with patch.object(server, "db", db), \
         patch.object(server, "send_resend_email", sent), \
         patch.object(server, "send_invite_email", invites):
        yield db, sent, invites
    server.app.dependency_overrides.clear()


def _as(principal):
    async def dep():
        return dict(principal)
    server.app.dependency_overrides[server.get_principal] = dep
    return TestClient(server.app)


# ------------------------------------------------------------- inquiry

def test_inquiry_is_stored_and_emailed(env):
    db, sent, _ = env
    client = TestClient(server.app)
    r = client.post("/api/custom-dashboards/inquiry", json=INQUIRY)
    assert r.status_code == 200, r.text
    row = _run(db.custom_inquiries.find_one({}))
    assert row["email"] == "dana@bigco.com"
    assert row["status"] == "new"
    assert row["budget_range"] == "5k_10k"
    sent.assert_awaited_once()
    kwargs = sent.await_args.kwargs
    assert kwargs["to"] == [OPERATOR_EMAIL]
    assert kwargs["reply_to"] == "dana@bigco.com"
    assert "BigCo" in kwargs["subject"]


def test_inquiry_validation_and_honeypot(env):
    db, sent, _ = env
    client = TestClient(server.app)
    bad = client.post("/api/custom-dashboards/inquiry", json={**INQUIRY, "email": "nope"})
    assert bad.status_code == 400
    missing = client.post("/api/custom-dashboards/inquiry", json={**INQUIRY, "needs": ""})
    assert missing.status_code == 400
    bot = client.post("/api/custom-dashboards/inquiry", json={**INQUIRY, "website": "http://spam"})
    assert bot.status_code == 200
    assert _run(db.custom_inquiries.count_documents({})) == 0
    sent.assert_not_awaited()


def test_inquiry_is_rate_limited(env):
    client = TestClient(server.app)
    codes = [client.post("/api/custom-dashboards/inquiry", json=INQUIRY).status_code for _ in range(7)]
    assert codes[:5] == [200] * 5
    assert 429 in codes[5:]


# ------------------------------------------------------------- operator gate

def test_admin_routes_need_the_operator(env):
    client = _as(STRANGER)
    assert client.get("/api/admin/custom/inquiries").status_code == 403
    assert client.post("/api/admin/custom/workspaces", json={
        "company_name": "X", "owner_email": "x@x.com",
    }).status_code == 403


def test_unverified_operator_is_refused(env):
    db, _, _ = env
    _run(db.users.update_one({"user_id": "u_operator"}, {"$set": {"email_verified": False}}))
    assert _as(OPERATOR).get("/api/admin/custom/catalog").status_code == 403


# ------------------------------------------------------------- full client flow

def test_create_client_then_owner_sees_dashboard(env):
    db, _, invites = env
    op = _as(OPERATOR)
    _run(db.custom_inquiries.insert_one({"inquiry_id": "inq_1", "status": "new", "created_at": "x"}))
    r = op.post("/api/admin/custom/workspaces", json={
        "company_name": "BigCo Manufacturing", "owner_email": "dana@bigco.com",
        "tier": "tailored", "inquiry_id": "inq_1",
    })
    assert r.status_code == 200, r.text
    ws_id = r.json()["workspace_id"]
    ws = _run(db.workspaces.find_one({"workspace_id": ws_id}))
    assert ws["billing_source"] == "custom"
    assert ws["plan"] == "business"
    assert ws["owner_user_id"] is None
    assert ws["custom_dashboard"]["approved_emails"] == ["dana@bigco.com"]
    mem = _run(db.memberships.find_one({"workspace_id": ws_id}))
    assert mem["status"] == "invited" and mem["pack"] == "owner"
    invites.assert_awaited_once()
    assert _run(db.custom_inquiries.find_one({"inquiry_id": "inq_1"}))["status"] == "won"

    # Operator lists and edits it.
    listed = op.get("/api/admin/custom/workspaces").json()["workspaces"]
    assert listed[0]["workspace_id"] == ws_id and listed[0]["tier"] == "tailored"
    save = op.put(f"/api/admin/custom/workspaces/{ws_id}/config", json={
        "title": "BigCo Control Room",
        "widgets": [
            {"type": "manual_kpi", "title": "Line 1 output", "params": {"value": "1,240 units", "tone": "positive"}},
            {"type": "tasks_summary", "params": {"limit": 3}},
            {"type": "financial_kpi", "params": {"metric": "cash"}},
            {"type": "custom", "params": {"component": "bigco-line-map", "props": {"lines": 3}}},
        ],
    })
    assert save.status_code == 200, save.text

    # The owner signs in: invite activation attaches them and claims ownership.
    _run(db.users.insert_one({"user_id": "u_dana", "email": "dana@bigco.com", "email_verified": True}))
    _run(server._activate_invites({"user_id": "u_dana", "email": "dana@bigco.com", "email_verified": True}))
    assert _run(db.workspaces.find_one({"workspace_id": ws_id}))["owner_user_id"] == "u_dana"

    owner = {"user_id": "u_dana", "email": "dana@bigco.com", "name": "Dana",
             "workspace_id": ws_id, "role": "owner", "pack": "owner"}
    client = _as(owner)
    status = client.get("/api/custom-dashboard/status").json()
    assert status == {"enabled": True, "title": "BigCo Control Room", "operator": False, "custom_billing": True}
    dash = client.get("/api/custom-dashboard")
    assert dash.status_code == 200, dash.text
    body = dash.json()
    assert body["title"] == "BigCo Control Room"
    assert "approved_emails" not in body
    by_type = {w["type"]: w for w in body["widgets"]}
    assert by_type["manual_kpi"]["params"]["value"] == "1,240 units"
    assert by_type["tasks_summary"]["data"]["state"] in ("ok", "error")
    assert by_type["financial_kpi"]["data"]["state"] != "restricted"
    assert by_type["custom"]["params"]["component"] == "bigco-line-map"

    # Self-serve plan changes are blocked for custom billing.
    blocked = client.post("/api/billing/schedule-plan", json={"plan": "free"})
    assert blocked.status_code == 400
    assert "custom agreement" in blocked.json()["detail"]


def test_approved_emails_invite_restrict_and_remove(env):
    db, _, invites = env
    op = _as(OPERATOR)
    ws_id = op.post("/api/admin/custom/workspaces", json={
        "company_name": "Acme", "owner_email": "boss@acme.com", "send_invite": False,
    }).json()["workspace_id"]
    invites.assert_not_awaited()

    add = op.post(f"/api/admin/custom/workspaces/{ws_id}/approved-emails", json={"email": "Ops@Acme.com", "pack": "ops"})
    assert add.status_code == 200, add.text
    assert add.json()["status"] == "invited"
    no_owner = op.post(f"/api/admin/custom/workspaces/{ws_id}/approved-emails", json={"email": "x@acme.com", "pack": "owner"})
    assert no_owner.status_code == 400

    op.put(f"/api/admin/custom/workspaces/{ws_id}/config", json={"restrict_to_approved": True})
    member = {"user_id": "u_m", "email": "other@acme.com", "workspace_id": ws_id, "role": "member", "pack": "member"}
    assert _as(member).get("/api/custom-dashboard").status_code == 404
    approved = {**member, "email": "ops@acme.com", "pack": "ops"}
    assert _as(approved).get("/api/custom-dashboard").status_code == 200

    op = _as(OPERATOR)
    rm = op.delete(f"/api/admin/custom/workspaces/{ws_id}/approved-emails/ops@acme.com")
    assert rm.status_code == 200 and rm.json()["removed_access"] is True
    assert _run(db.memberships.find_one({"workspace_id": ws_id, "email": "ops@acme.com"})) is None
    owner_rm = op.delete(f"/api/admin/custom/workspaces/{ws_id}/approved-emails/boss@acme.com")
    assert owner_rm.status_code == 400


def test_member_without_financials_sees_restricted_money(env):
    op = _as(OPERATOR)
    ws_id = op.post("/api/admin/custom/workspaces", json={
        "company_name": "Acme", "owner_email": "boss@acme.com", "send_invite": False,
    }).json()["workspace_id"]
    member = {"user_id": "u_m", "email": "m@acme.com", "workspace_id": ws_id, "role": "member", "pack": "member"}
    with patch.object(server, "can_access_financials", AsyncMock(return_value=False)):
        body = _as(member).get("/api/custom-dashboard").json()
    money = [w for w in body["widgets"] if w["type"] in ("financial_kpi", "revenue_expenses_chart")]
    assert money and all(w["data"]["state"] == "restricted" for w in money)


def test_enable_refuses_live_paddle_subscription(env):
    db, _, _ = env
    _run(db.workspaces.insert_one({
        "workspace_id": "ws_paying", "name": "Paying", "plan": "growth",
        "paddle_subscription_id": "sub_live", "subscription_status": "active",
    }))
    op = _as(OPERATOR)
    r = op.post("/api/admin/custom/workspaces/ws_paying/enable", json={"tier": "configured"})
    assert r.status_code == 409
    ok = op.post("/api/admin/custom/workspaces/ws_paying/enable", json={"tier": "configured", "custom_billing": False})
    assert ok.status_code == 200
    ws = _run(db.workspaces.find_one({"workspace_id": "ws_paying"}))
    assert ws["custom_dashboard"]["enabled"] is True
    assert ws["plan"] == "growth" and "billing_source" not in ws


def test_preview_uses_sample_data_only(env):
    op = _as(OPERATOR)
    r = op.post("/api/admin/custom/preview", json={"widgets": [
        {"type": "financial_kpi", "params": {"metric": "cash"}},
        {"type": "revenue_expenses_chart", "params": {"months": 3}},
    ]})
    assert r.status_code == 200, r.text
    widgets = r.json()["widgets"]
    assert widgets[0]["data"]["display"] == "$412,000"
    assert len(widgets[1]["data"]["months"]) == 3
    bad = op.post("/api/admin/custom/preview", json={"widgets": [{"type": "iframe"}]})
    assert bad.status_code == 400


# ------------------------------------------------------------- pure logic

def test_widget_validation_rules():
    with pytest.raises(cd.ConfigError):
        cd.clean_widget({"type": "financial_kpi", "params": {"metric": "profit"}})
    with pytest.raises(cd.ConfigError):
        cd.clean_widget({"type": "custom", "params": {"component": "../../etc"}})
    with pytest.raises(cd.ConfigError):
        cd.clean_widgets([{"type": "note", "params": {"body": "x"}}] * (cd.MAX_WIDGETS + 1))
    table = cd.clean_widget({"type": "manual_table", "params": {"columns": ["A", "B"], "rows": [["1"], ["1", "2", "3"]]}})
    assert table["params"]["rows"] == [["1", ""], ["1", "2"]]
    dup = cd.clean_widgets([
        {"id": "a", "type": "note", "params": {"body": "x"}},
        {"id": "a", "type": "note", "params": {"body": "y"}},
    ])
    assert dup[0]["id"] != dup[1]["id"]


def test_open_decisions_exclude_resolved():
    w = cd.resolve_widget(
        {"type": "decisions_open", "params": {"limit": 5}},
        {"decisions": [
            {"title": "A", "status": "pending"},
            {"title": "B", "status": "approved"},
            {"title": "C", "status": "rejected"},
            {"title": "D"},
        ], "errors": set()},
    )
    assert w["data"]["open"] == 2
    assert [i["title"] for i in w["data"]["items"]] == ["A", "D"]


def test_gross_margin_zero_is_entered_not_missing():
    """Numeric 0 used to be treated as falsy → not_entered."""
    sources = {
        "financials_access": True,
        "financials": {"gross_margin": 0, "currency": "USD"},
        "errors": set(),
    }
    w = cd.resolve_widget(
        {"type": "financial_kpi", "params": {"metric": "gross_margin"}, "title": "GM"},
        sources,
    )
    assert w["data"]["state"] == "ok"
    assert w["data"]["display"] == 0
    empty = cd.resolve_widget(
        {"type": "financial_kpi", "params": {"metric": "gross_margin"}, "title": "GM"},
        {"financials_access": True, "financials": {"gross_margin": None, "currency": "USD"}, "errors": set()},
    )
    assert empty["data"]["state"] == "not_entered"


def test_unverified_email_cannot_take_over_existing_account(env):
    db, _, _ = env
    _run(db.users.insert_one({"user_id": "u_victim", "email": "victim@co.com", "clerk_id": "clerk_victim"}))
    with pytest.raises(server.HTTPException) as exc:
        _run(server._upsert_clerk_user(
            email="victim@co.com", name="Attacker", picture=None,
            clerk_id="clerk_attacker", email_verified=False,
        ))
    assert exc.value.status_code == 403


def test_unverified_user_does_not_activate_invites(env):
    db, _, _ = env
    _run(db.memberships.insert_one({"membership_id": "m1", "workspace_id": "ws_x", "email": "a@b.com", "status": "invited"}))
    _run(server._activate_invites({"user_id": "u_a", "email": "a@b.com", "email_verified": False}))
    assert _run(db.memberships.find_one({"membership_id": "m1"}))["status"] == "invited"
