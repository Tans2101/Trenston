"""Manage Access must honor section_access for Tasks and Decisions.

A member pack user without pack perms for decisions:act / tasks:assign should
still succeed when their department is granted via /api/access/sections, and
still get 403 when it is not.
"""
import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import pymongo
import requests

from conftest import set_workspace_plan

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
OWNER_TOKEN = "test_session_kalun_123"
MEMBER_TOKEN = "test_session_user2"
MEMBER_USER_ID = "test-user-2"
OWNER_USER_ID = "test-user-kalun"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_INTEGRATION") != "1" or not BASE_URL,
        reason="integration: set RUN_INTEGRATION=1 and REACT_APP_BACKEND_URL",
    ),
]


def _sess(token):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    return s


@pytest.fixture
def owner():
    s = _sess(OWNER_TOKEN)
    set_workspace_plan(s, BASE_URL, "pro")
    return s


@pytest.fixture
def member():
    return _sess(MEMBER_TOKEN)


@pytest.fixture
def mongo():
    return pymongo.MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture
def member_dept_engineering(owner, member, mongo):
    """Ensure member is pack=member in Engineering; clear section grants after."""
    me = member.get(f"{BASE_URL}/api/auth/me").json()
    ws_id = me["workspace_id"]
    assert me["pack"] == "member"
    mongo.memberships.update_one(
        {"workspace_id": ws_id, "user_id": MEMBER_USER_ID, "status": "active"},
        {"$set": {"department": "Engineering", "pack": "member"}},
    )
    # Clear grants so each test starts denied
    mongo.workspaces.update_one({"workspace_id": ws_id}, {"$set": {"section_access": {}}})
    yield {"workspace_id": ws_id, "session": member, "owner": owner}
    mongo.workspaces.update_one({"workspace_id": ws_id}, {"$set": {"section_access": {}}})


class TestDecisionsSectionAccess:
    def test_member_without_grant_cannot_act(self, member_dept_engineering):
        member = member_dept_engineering["session"]
        owner = member_dept_engineering["owner"]
        assert member.get(f"{BASE_URL}/api/decisions").json()["can_act"] is False
        # Ensure there is a decision to act on
        created = owner.post(
            f"{BASE_URL}/api/decisions",
            json={"title": f"TEST_SEC_DEC_{uuid.uuid4().hex[:6]}", "category": "Ops", "description": "x"},
        )
        assert created.status_code == 200, created.text
        did = created.json()["decision"]["id"]
        try:
            r = member.post(f"{BASE_URL}/api/decisions/{did}/action", json={"action": "approved"})
            assert r.status_code == 403
            r = member.post(
                f"{BASE_URL}/api/decisions",
                json={"title": "TEST_SEC_DENIED", "category": "Ops", "description": "x"},
            )
            assert r.status_code == 403
        finally:
            owner.delete(f"{BASE_URL}/api/decisions/{did}")

    def test_member_with_department_grant_can_act(self, member_dept_engineering, mongo):
        member = member_dept_engineering["session"]
        owner = member_dept_engineering["owner"]
        ws_id = member_dept_engineering["workspace_id"]
        mongo.workspaces.update_one(
            {"workspace_id": ws_id},
            {"$set": {"section_access": {"decisions": ["Engineering"]}}},
        )
        assert member.get(f"{BASE_URL}/api/decisions").json()["can_act"] is True
        created = member.post(
            f"{BASE_URL}/api/decisions",
            json={"title": f"TEST_SEC_OK_{uuid.uuid4().hex[:6]}", "category": "Ops", "description": "granted"},
        )
        assert created.status_code == 200, created.text
        did = created.json()["decision"]["id"]
        try:
            r = member.post(f"{BASE_URL}/api/decisions/{did}/action", json={"action": "approved"})
            assert r.status_code == 200, r.text
            statuses = {d["id"]: d["status"] for d in member.get(f"{BASE_URL}/api/decisions").json()["decisions"]}
            assert statuses[did] == "approved"
        finally:
            owner.delete(f"{BASE_URL}/api/decisions/{did}")


class TestTasksSectionAccess:
    def test_member_without_grant_cannot_assign(self, member_dept_engineering):
        member = member_dept_engineering["session"]
        assert member.get(f"{BASE_URL}/api/tasks").json()["can_assign"] is False
        r = member.post(
            f"{BASE_URL}/api/tasks",
            json={"title": "TEST_SEC_ASSIGN_DENY", "assignee_user_id": OWNER_USER_ID},
        )
        assert r.status_code == 403

    def test_member_with_department_grant_can_assign(self, member_dept_engineering, mongo):
        member = member_dept_engineering["session"]
        ws_id = member_dept_engineering["workspace_id"]
        mongo.workspaces.update_one(
            {"workspace_id": ws_id},
            {"$set": {"section_access": {"tasks": ["Engineering"]}}},
        )
        assert member.get(f"{BASE_URL}/api/tasks").json()["can_assign"] is True
        r = member.post(
            f"{BASE_URL}/api/tasks",
            json={"title": f"TEST_SEC_ASSIGN_OK_{uuid.uuid4().hex[:6]}", "assignee_user_id": OWNER_USER_ID},
        )
        assert r.status_code == 200, r.text
        assert r.json()["task"]["assignee_user_id"] == OWNER_USER_ID
