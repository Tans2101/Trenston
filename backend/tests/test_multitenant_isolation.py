"""Workspace isolation, role gates, and auth guards (replaces legacy live Kalun suites)."""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_multitenant_isolation")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import server  # noqa: E402
from mongo_mocks import attach_users_in_find  # noqa: E402

OWNER_A = {
    "user_id": "u_owner_a",
    "email": "owner-a@acme.com",
    "name": "Owner A",
    "workspace_id": "ws_a",
    "role": "owner",
    "pack": "owner",
}

OWNER_B = {
    "user_id": "u_owner_b",
    "email": "owner-b@other.com",
    "name": "Owner B",
    "workspace_id": "ws_b",
    "role": "owner",
    "pack": "owner",
}

MEMBER_A = {
    "user_id": "u_member_a",
    "email": "member-a@acme.com",
    "name": "Member A",
    "workspace_id": "ws_a",
    "role": "member",
    "pack": "member",
}

WS_A = {
    "workspace_id": "ws_a",
    "name": "Acme",
    "plan": "pro",
    "stage": "Established, growing",
    "employees": 5,
    "founded": "2020",
    "mission": "Ship",
    "industry": "SaaS",
    "founder_title": "CEO",
    "onboarding_done": True,
    "company_setup_done": True,
    "template": "blank",
    "people": {"people": []},
    "integrations": {},
}

WS_B = {
    **WS_A,
    "workspace_id": "ws_b",
    "name": "Other Co",
}

READ_ENDPOINTS = [
    "/api/company",
    "/api/briefing",
    "/api/decisions",
    "/api/telemetry",
    "/api/financials",
    "/api/tasks",
    "/api/reports",
    "/api/calendar",
    "/api/people",
    "/api/integrations",
    "/api/ask/history",
    "/api/billing/plans",
]


def _empty_cursor(rows=None):
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=list(rows or []))
    return cursor


def _ws_for(principal):
    return dict(WS_A if principal["workspace_id"] == "ws_a" else WS_B)


@pytest.fixture
def isolation_api():
    chat_rows = []
    memberships = [
        {
            "membership_id": "mem_owner_a",
            "workspace_id": "ws_a",
            "user_id": "u_owner_a",
            "email": "owner-a@acme.com",
            "role": "owner",
            "pack": "owner",
            "status": "active",
            "section_grants": [],
        },
        {
            "membership_id": "mem_member_a",
            "workspace_id": "ws_a",
            "user_id": "u_member_a",
            "email": "member-a@acme.com",
            "role": "member",
            "pack": "member",
            "status": "active",
            "section_grants": [],
        },
    ]
    principal_holder = {"current": OWNER_A}

    async def mock_principal():
        return principal_holder["current"]

    async def get_ws(wid):
        if wid == "ws_a":
            return dict(WS_A)
        if wid == "ws_b":
            return dict(WS_B)
        return None

    async def mem_find_one(query, projection=None):
        for m in memberships:
            if all(m.get(k) == v for k, v in query.items()):
                return dict(m)
        return None

    def mem_find(query, projection=None):
        matched = [
            dict(m) for m in memberships
            if all(m.get(k) == v for k, v in (query or {}).items())
        ]
        return _empty_cursor(matched)

    def chat_find(query, projection=None):
        matched = [
            dict(r) for r in chat_rows
            if all(r.get(k) == v for k, v in (query or {}).items())
        ]
        return _empty_cursor(matched)

    mock_db = MagicMock()
    mock_db.memberships.find_one = AsyncMock(side_effect=mem_find_one)
    mock_db.memberships.find = MagicMock(side_effect=mem_find)
    mock_db.memberships.insert_one = AsyncMock()
    mock_db.memberships.update_one = AsyncMock()
    mock_db.memberships.delete_one = AsyncMock()
    mock_db.users.find_one = AsyncMock(return_value=None)
    attach_users_in_find(mock_db.users)
    mock_db.chat_messages.find = MagicMock(side_effect=chat_find)
    mock_db.chat_messages.insert_one = AsyncMock(
        side_effect=lambda doc: chat_rows.append(dict(doc))
    )
    mock_db.workspaces.find_one = AsyncMock(
        side_effect=lambda q, p=None: get_ws(q.get("workspace_id") or "ws_a")
    )
    mock_db.workspaces.update_one = AsyncMock()
    mock_db.departments.find = MagicMock(return_value=_empty_cursor())
    mock_db.departments.find_one = AsyncMock(return_value=None)
    mock_db.department_members.find = MagicMock(return_value=_empty_cursor())
    mock_db.department_members.find_one = AsyncMock(return_value=None)
    for coll in (
        "production_work_orders", "legal_matters", "maintenance_tickets",
        "hr_onboarding_instances", "hr_offboarding_instances", "deals",
        "hr_employees", "procurement_requests", "decisions", "tasks",
        "financial_entries", "user_google_tokens",
    ):
        getattr(mock_db, coll).find = MagicMock(return_value=_empty_cursor())
        getattr(mock_db, coll).find_one = AsyncMock(return_value=None)

    server.app.dependency_overrides[server.get_principal] = mock_principal
    server.simple_cache.clear()

    with patch.object(server, "db", mock_db), \
         patch.object(server, "get_ws", new=AsyncMock(side_effect=get_ws)), \
         patch.object(server, "BILLING_ENFORCED", False), \
         patch.object(server, "log_activity", new=AsyncMock()), \
         patch.object(server, "_enforce_seat_available", new=AsyncMock()), \
         patch.object(server, "send_invite_email", new=AsyncMock(return_value={"sent": True})), \
         patch.object(server, "ensure_person_for_membership", new=AsyncMock()), \
         patch.object(server, "_release_seat_reservation", new=AsyncMock()), \
         patch.object(server, "unlink_person_membership", new=AsyncMock()), \
         patch.object(server, "invalidate_workspace_list_cache", MagicMock()), \
         patch.object(server, "_user_google_row", new=AsyncMock(return_value=None)), \
         patch.object(
             server.dept_access, "department_names_by_user_id",
             new=AsyncMock(return_value={}),
         ), \
         patch.object(
             server.dept_access, "list_enabled_departments",
             new=AsyncMock(return_value=[]),
         ):
        client = TestClient(server.app)
        yield {
            "client": client,
            "principal_holder": principal_holder,
            "memberships": memberships,
            "chat_rows": chat_rows,
            "mock_db": mock_db,
        }

    server.app.dependency_overrides.clear()
    server.simple_cache.clear()


@pytest.mark.parametrize("path", READ_ENDPOINTS)
def test_unauthenticated_read_returns_401(path):
    server.app.dependency_overrides.clear()
    with patch.object(server.clerk_auth, "clerk_configured", return_value=True):
        client = TestClient(server.app)
        r = client.get(path)
    assert r.status_code == 401, f"{path} expected 401, got {r.status_code}: {r.text[:200]}"


def test_company_scoped_to_principal_workspace_ignores_query(isolation_api):
    client = isolation_api["client"]
    holder = isolation_api["principal_holder"]

    holder["current"] = OWNER_A
    a = client.get("/api/company?workspace_id=ws_b")
    assert a.status_code == 200, a.text
    assert a.json()["workspace_id"] == "ws_a"
    assert a.json()["name"] == "Acme"

    holder["current"] = OWNER_B
    b = client.get("/api/company?workspace_id=ws_a")
    assert b.status_code == 200, b.text
    assert b.json()["workspace_id"] == "ws_b"
    assert b.json()["name"] == "Other Co"


def test_ask_history_isolated_per_user_and_workspace(isolation_api):
    client = isolation_api["client"]
    holder = isolation_api["principal_holder"]
    chats = isolation_api["chat_rows"]

    chats.extend([
        {
            "workspace_id": "ws_a", "user_id": "u_owner_a", "role": "user",
            "content": "OWNER_ONLY_MSG",
        },
        {
            "workspace_id": "ws_a", "user_id": "u_member_a", "role": "user",
            "content": "MEMBER_ONLY_MSG",
        },
        {
            "workspace_id": "ws_b", "user_id": "u_owner_b", "role": "user",
            "content": "OTHER_WS_MSG",
        },
    ])

    holder["current"] = OWNER_A
    owner_msgs = client.get("/api/ask/history").json()["messages"]
    owner_texts = [m["content"] for m in owner_msgs]
    assert "OWNER_ONLY_MSG" in owner_texts
    assert "MEMBER_ONLY_MSG" not in owner_texts
    assert "OTHER_WS_MSG" not in owner_texts

    holder["current"] = MEMBER_A
    member_msgs = client.get("/api/ask/history").json()["messages"]
    member_texts = [m["content"] for m in member_msgs]
    assert "MEMBER_ONLY_MSG" in member_texts
    assert "OWNER_ONLY_MSG" not in member_texts
    assert "OTHER_WS_MSG" not in member_texts


def test_integrations_can_manage_owner_vs_member(isolation_api):
    client = isolation_api["client"]
    holder = isolation_api["principal_holder"]

    holder["current"] = OWNER_A
    assert client.get("/api/integrations").json()["can_manage"] is True

    holder["current"] = MEMBER_A
    assert client.get("/api/integrations").json()["can_manage"] is False


def test_member_forbidden_on_invite(isolation_api):
    client = isolation_api["client"]
    isolation_api["principal_holder"]["current"] = MEMBER_A
    r = client.post("/api/members/invite", json={"email": "new@acme.com"})
    assert r.status_code == 403, r.text


def test_owner_cannot_change_own_role(isolation_api):
    client = isolation_api["client"]
    isolation_api["principal_holder"]["current"] = OWNER_A
    r = client.patch("/api/members/mem_owner_a", json={"pack": "member"})
    assert r.status_code == 400
    assert "own" in r.json()["detail"].lower()


def test_owner_cannot_remove_self(isolation_api):
    client = isolation_api["client"]
    isolation_api["principal_holder"]["current"] = OWNER_A
    r = client.delete("/api/members/mem_owner_a")
    assert r.status_code == 400
    assert "yourself" in r.json()["detail"].lower()


def test_invite_existing_user_auto_joins(isolation_api):
    client = isolation_api["client"]
    mock_db = isolation_api["mock_db"]
    isolation_api["principal_holder"]["current"] = OWNER_A
    mock_db.users.find_one = AsyncMock(
        return_value={"user_id": "u_joiner", "email": "joiner@acme.com", "name": "Joiner"}
    )
    r = client.post("/api/members/invite", json={"email": "joiner@acme.com"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["auto_joined"] is True
    inserted = mock_db.memberships.insert_one.await_args.args[0]
    assert inserted["status"] == "active"
    assert inserted["user_id"] == "u_joiner"


def test_invite_unregistered_email_creates_pending(isolation_api):
    client = isolation_api["client"]
    mock_db = isolation_api["mock_db"]
    isolation_api["principal_holder"]["current"] = OWNER_A
    mock_db.users.find_one = AsyncMock(return_value=None)
    r = client.post("/api/members/invite", json={"email": "pending@acme.com"})
    assert r.status_code == 200, r.text
    assert r.json()["auto_joined"] is False
    inserted = mock_db.memberships.insert_one.await_args.args[0]
    assert inserted["status"] == "invited"
    assert inserted["user_id"] is None
