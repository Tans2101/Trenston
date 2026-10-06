"""Iteration 5 tests:
- Daily Update loop (POST /api/updates one-per-day-edit, /updates/me, /updates/today, blank -> 400)
- Briefing rollup with team_updates
- Tasks personal + departmental (create self, assign forbidden for member, owner/exec can assign)
- My-day (/api/tasks/me)
- Invite/join UX (needs_workspace, self-serve create, join-info/join, join-code perm)
- Who-can-invite (owner vs exec, non-owner cannot grant owner)
"""
import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import pymongo
import requests

from conftest import set_workspace_plan

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://exec-cockpit.preview.emergentagent.com").rstrip("/")
OWNER_TOKEN = "test_session_kalun_123"
MEMBER_TOKEN = "test_session_user2"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

WS_ID = "ws_d6b4d8c892fb"


def _sess(token):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def mongo():
    return pymongo.MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture(scope="module")
def owner():
    s = _sess(OWNER_TOKEN)
    set_workspace_plan(s, BASE_URL, "pro")
    return s


@pytest.fixture(scope="module")
def member():
    return _sess(MEMBER_TOKEN)


@pytest.fixture(scope="module")
def exec_ctx(mongo):
    """Create a temp exec user + membership + session, cleanup at end."""
    user_id = f"test-exec-{uuid.uuid4().hex[:6]}"
    email = f"test_exec_{uuid.uuid4().hex[:6]}@example.com"
    token = f"test_session_exec_{uuid.uuid4().hex[:8]}"
    mem_id = f"mem_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    exp = (now + timedelta(days=7)).isoformat()
    mongo.users.insert_one({"user_id": user_id, "email": email, "name": "Test Exec",
                            "created_at": now.isoformat(), "active_workspace_id": WS_ID})
    mongo.memberships.insert_one({"membership_id": mem_id, "workspace_id": WS_ID,
                                  "user_id": user_id, "email": email, "role": "member",
                                  "pack": "exec", "status": "active", "created_at": now.isoformat()})
    mongo.user_sessions.insert_one({"user_id": user_id, "session_token": token,
                                    "expires_at": exp, "created_at": now.isoformat()})
    s = _sess(token)
    yield {"session": s, "user_id": user_id, "email": email, "membership_id": mem_id, "token": token}
    mongo.user_sessions.delete_many({"user_id": user_id})
    mongo.memberships.delete_many({"user_id": user_id})
    mongo.users.delete_many({"user_id": user_id})


# ------------- Auth/pack defaults -------------
def test_member_default_route_me(member):
    d = member.get(f"{BASE_URL}/api/auth/me").json()
    assert d["pack"] == "member"
    assert d["default_route"] == "/app/me"
    perms = set(d["perms"])
    assert {"updates:write", "tasks:create", "tasks:move", "ask:use", "read"} <= perms
    assert "tasks:assign" not in perms
    assert "members:invite" not in perms


def test_exec_default_route_and_perms(exec_ctx):
    d = exec_ctx["session"].get(f"{BASE_URL}/api/auth/me").json()
    assert d["pack"] == "exec"
    assert d["default_route"] == "/app"
    perms = set(d["perms"])
    for p in ("members:invite", "tasks:assign", "decisions:act", "updates:write"):
        assert p in perms
    assert "members:manage" not in perms


# ------------- Daily updates -------------
def test_daily_update_empty_400(member):
    r = member.post(f"{BASE_URL}/api/updates", json={"text": "  "})
    assert r.status_code == 400


def test_daily_update_create_then_edit_single_per_day(member, mongo):
    # Workspace-local day (not UTC) — match production /updates/* keys.
    me0 = member.get(f"{BASE_URL}/api/updates/me").json()
    day = me0["day"]
    mongo.updates.delete_many({"workspace_id": WS_ID, "user_id": "test-user-2", "day": day})

    r = member.post(f"{BASE_URL}/api/updates",
                    json={"text": "TEST_shipped onboarding", "blocker": False})
    assert r.status_code == 200
    body = r.json()
    assert body["edited"] is False
    assert body["update"]["text"] == "TEST_shipped onboarding"

    # second POST same day EDITS
    r2 = member.post(f"{BASE_URL}/api/updates",
                     json={"text": "TEST_edited update", "blocker": True})
    assert r2.status_code == 200
    assert r2.json()["edited"] is True

    # only 1 doc in db
    count = mongo.updates.count_documents({"workspace_id": WS_ID, "user_id": "test-user-2", "day": day})
    assert count == 1

    # GET /updates/me returns today's
    me = member.get(f"{BASE_URL}/api/updates/me").json()
    assert me["update"]["text"] == "TEST_edited update"
    assert me["update"]["blocker"] is True


def test_updates_today_visible_to_owner(owner, member, mongo):
    # ensure member has posted (previous test) — post again if needed
    day = member.get(f"{BASE_URL}/api/updates/me").json()["day"]
    if not mongo.updates.find_one({"workspace_id": WS_ID, "user_id": "test-user-2", "day": day}):
        member.post(f"{BASE_URL}/api/updates", json={"text": "TEST_owner-visible", "blocker": False})
    d = owner.get(f"{BASE_URL}/api/updates/today").json()
    assert any(u.get("user_id") == "test-user-2" for u in d["updates"])


def test_briefing_team_updates_and_what_changed(owner, member, mongo):
    # force a fresh post to move to top of activities
    member.post(f"{BASE_URL}/api/updates", json={"text": "TEST_briefing_probe", "blocker": True})
    b = owner.get(f"{BASE_URL}/api/briefing").json()
    assert "team_updates" in b
    assert isinstance(b["team_updates"], list) and len(b["team_updates"]) >= 1
    tu = next(u for u in b["team_updates"] if "TEST_briefing_probe" in (u.get("text") or ""))
    assert tu["user_name"]
    assert tu["blocker"] is True
    # what_changed[0] should contain the same update summary
    wc0 = b["what_changed"][0]
    assert "TEST_briefing_probe" in wc0["title"]


# ------------- Tasks: personal + departmental -------------
def test_tasks_meta_fields(member, owner):
    m = member.get(f"{BASE_URL}/api/tasks").json()
    assert m["can_create"] is True
    assert m["can_assign"] is False
    assert m["my_user_id"] == "test-user-2"
    o = owner.get(f"{BASE_URL}/api/tasks").json()
    assert o["can_assign"] is True


def test_member_creates_self_task_and_appears_in_me(member):
    r = member.post(f"{BASE_URL}/api/tasks",
                    json={"title": "TEST_my personal task", "priority": "High", "tag": "personal"})
    assert r.status_code == 200
    tid = r.json()["task"]["id"]
    assert r.json()["task"]["assignee_user_id"] == "test-user-2"
    me = member.get(f"{BASE_URL}/api/tasks/me").json()
    assert any(t["id"] == tid for t in me["items"])
    return tid


def test_member_cannot_assign_to_other(member):
    r = member.post(f"{BASE_URL}/api/tasks",
                    json={"title": "TEST_illegal_assign", "assignee_user_id": "test-user-kalun"})
    assert r.status_code == 403


def test_clear_done_tasks_removes_finished(member, owner):
    created = []
    for title in ("TEST_clear_done_a", "TEST_clear_done_b"):
        r = member.post(f"{BASE_URL}/api/tasks", json={"title": title})
        assert r.status_code == 200
        tid = r.json()["task"]["id"]
        created.append(tid)
        assert member.patch(f"{BASE_URL}/api/tasks/{tid}", json={"column": "done"}).status_code == 200
    open_r = member.post(f"{BASE_URL}/api/tasks", json={"title": "TEST_clear_done_open"})
    assert open_r.status_code == 200
    open_id = open_r.json()["task"]["id"]
    r = member.delete(f"{BASE_URL}/api/tasks/done")
    assert r.status_code == 200
    assert r.json()["cleared"] >= 2
    items = owner.get(f"{BASE_URL}/api/tasks").json()["items"]
    ids = {t["id"] for t in items}
    assert open_id in ids
    for tid in created:
        assert tid not in ids


def test_move_own_task_to_done_sets_progress(member):
    # create a task
    r = member.post(f"{BASE_URL}/api/tasks", json={"title": "TEST_to_done"})
    tid = r.json()["task"]["id"]
    r = member.patch(f"{BASE_URL}/api/tasks/{tid}", json={"column": "done"})
    assert r.status_code == 200
    items = member.get(f"{BASE_URL}/api/tasks/me").json()["items"]
    t = next(t for t in items if t["id"] == tid)
    assert t["column"] == "done"
    assert t["progress"] == 100


def test_member_cannot_move_other_owned_task(member, owner):
    # owner creates a task assigned to themselves
    r = owner.post(f"{BASE_URL}/api/tasks",
                   json={"title": "TEST_owner_task", "assignee_user_id": "test-user-kalun"})
    assert r.status_code == 200
    tid = r.json()["task"]["id"]
    r = member.patch(f"{BASE_URL}/api/tasks/{tid}", json={"column": "doing"})
    assert r.status_code == 403


def test_member_can_move_legacy_task_no_assignee(owner, member):
    tasks = owner.get(f"{BASE_URL}/api/tasks").json().get("items", [])
    legacy = next((t for t in tasks if not t.get("assignee_user_id")), None)
    if not legacy:
        pytest.skip("no legacy demo task without assignee_user_id")
    orig = legacy["column"]
    new_col = "doing" if orig != "doing" else "todo"
    r = member.patch(f"{BASE_URL}/api/tasks/{legacy['id']}", json={"column": new_col})
    assert r.status_code == 200
    member.patch(f"{BASE_URL}/api/tasks/{legacy['id']}", json={"column": orig})


def test_owner_can_assign_to_workspace_member(owner):
    members_resp = owner.get(f"{BASE_URL}/api/members").json()
    assert "user_id" in members_resp["members"][0]
    target = next(m for m in members_resp["members"]
                  if m.get("user_id") and not m.get("is_self"))
    r = owner.post(f"{BASE_URL}/api/tasks",
                   json={"title": "TEST_assigned_by_owner", "assignee_user_id": target["user_id"]})
    assert r.status_code == 200
    assert r.json()["task"]["assignee_user_id"] == target["user_id"]


# ------------- Invite/join UX -------------
def test_workspaces_join_info_valid(owner):
    code = owner.get(f"{BASE_URL}/api/workspaces/join-code").json()["join_code"]
    r = owner.get(f"{BASE_URL}/api/workspaces/join-info", params={"code": code})
    assert r.status_code == 200
    assert r.json()["workspace_id"] == WS_ID


def test_workspaces_join_info_invalid(owner):
    r = owner.get(f"{BASE_URL}/api/workspaces/join-info", params={"code": "NOTREAL"})
    assert r.status_code == 404


def test_member_forbidden_join_code(member):
    r = member.get(f"{BASE_URL}/api/workspaces/join-code")
    assert r.status_code == 403


def test_owner_gets_join_code(owner):
    r = owner.get(f"{BASE_URL}/api/workspaces/join-code")
    assert r.status_code == 200
    code = r.json()["join_code"]
    assert isinstance(code, str) and len(code) == 6


def test_exec_can_get_join_code(exec_ctx, owner):
    owner_code = owner.get(f"{BASE_URL}/api/workspaces/join-code").json()["join_code"]
    r = exec_ctx["session"].get(f"{BASE_URL}/api/workspaces/join-code")
    assert r.status_code == 200
    assert r.json()["join_code"] == owner_code


def test_needs_workspace_new_user(mongo):
    """Brand new user with no membership -> needs_workspace true, /app/welcome."""
    user_id = f"test-new-{uuid.uuid4().hex[:6]}"
    email = f"test_new_{uuid.uuid4().hex[:6]}@example.com"
    token = f"test_session_new_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    exp = (now + timedelta(days=1)).isoformat()
    mongo.users.insert_one({"user_id": user_id, "email": email, "name": "New User",
                            "created_at": now.isoformat()})
    mongo.user_sessions.insert_one({"user_id": user_id, "session_token": token,
                                    "expires_at": exp, "created_at": now.isoformat()})
    try:
        s = _sess(token)
        d = s.get(f"{BASE_URL}/api/auth/me").json()
        assert d["needs_workspace"] is True
        assert d["workspace_id"] is None
        assert d["default_route"] == "/app/welcome"
        assert d["pack"] is None

        # self-serve create
        r = s.post(f"{BASE_URL}/api/workspaces", json={"name": "TEST_SelfServe Co"})
        assert r.status_code == 200
        new_ws_id = r.json()["workspace_id"]
        try:
            d2 = s.get(f"{BASE_URL}/api/auth/me").json()
            assert d2["needs_workspace"] is False
            assert d2["pack"] == "owner"
            assert d2["workspace_id"] == new_ws_id
        finally:
            mongo.workspaces.delete_many({"workspace_id": new_ws_id})
            mongo.memberships.delete_many({"workspace_id": new_ws_id})
    finally:
        mongo.user_sessions.delete_many({"user_id": user_id})
        mongo.users.delete_many({"user_id": user_id})


def test_join_by_code_flow(mongo):
    user_id = f"test-joiner-{uuid.uuid4().hex[:6]}"
    email = f"test_joiner_{uuid.uuid4().hex[:6]}@example.com"
    token = f"test_session_join_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    exp = (now + timedelta(days=1)).isoformat()
    mongo.users.insert_one({"user_id": user_id, "email": email, "name": "Joiner",
                            "created_at": now.isoformat()})
    mongo.user_sessions.insert_one({"user_id": user_id, "session_token": token,
                                    "expires_at": exp, "created_at": now.isoformat()})
    try:
        s = _sess(token)
        # invalid code
        r = s.post(f"{BASE_URL}/api/workspaces/join", json={"code": "NOTREAL"})
        assert r.status_code == 404
        # valid code (fetched dynamically)
        code = _sess(OWNER_TOKEN).get(f"{BASE_URL}/api/workspaces/join-code").json()["join_code"]
        r = s.post(f"{BASE_URL}/api/workspaces/join", json={"code": code})
        assert r.status_code == 200
        assert r.json()["workspace_id"] == WS_ID
        d = s.get(f"{BASE_URL}/api/auth/me").json()
        assert d["workspace_id"] == WS_ID
        assert d["pack"] == "member"
    finally:
        mongo.memberships.delete_many({"user_id": user_id})
        mongo.user_sessions.delete_many({"user_id": user_id})
        mongo.users.delete_many({"user_id": user_id})


# ------------- Who-can-invite: owner vs exec -------------
def test_owner_cannot_invite_owner_pack(owner, mongo):
    email = f"test_owner_invite_{uuid.uuid4().hex[:6]}@example.com"
    r = owner.post(f"{BASE_URL}/api/members/invite", json={"email": email, "pack": "owner"})
    assert r.status_code == 400
    assert "owner" in r.text.lower() or "ceo" in r.text.lower()
    mongo.memberships.delete_many({"email": email, "workspace_id": WS_ID})


def test_exec_cannot_invite_owner_pack(exec_ctx):
    email = f"test_exec_deny_owner_{uuid.uuid4().hex[:6]}@example.com"
    r = exec_ctx["session"].post(f"{BASE_URL}/api/members/invite",
                                 json={"email": email, "pack": "owner"})
    assert r.status_code == 400
    assert "owner" in r.text.lower() or "ceo" in r.text.lower()


def test_exec_can_invite_finance_and_member(exec_ctx, mongo):
    e1 = f"test_exec_fin_{uuid.uuid4().hex[:6]}@example.com"
    r = exec_ctx["session"].post(f"{BASE_URL}/api/members/invite",
                                 json={"email": e1, "pack": "finance"})
    assert r.status_code == 200
    e2 = f"test_exec_mem_{uuid.uuid4().hex[:6]}@example.com"
    r = exec_ctx["session"].post(f"{BASE_URL}/api/members/invite",
                                 json={"email": e2, "pack": "member"})
    assert r.status_code == 200
    mongo.memberships.delete_many({"email": {"$in": [e1, e2]}, "workspace_id": WS_ID})


def test_invalid_pack_400(owner):
    email = f"test_badpack_{uuid.uuid4().hex[:6]}@example.com"
    r = owner.post(f"{BASE_URL}/api/members/invite",
                   json={"email": email, "pack": "hacker"})
    assert r.status_code == 400


def test_exec_patch_nonowner_to_nonowner(exec_ctx, owner, mongo):
    # owner invites a finance member; exec patches to hr; then exec attempts to promote to owner -> 400
    email = f"test_patch_target_{uuid.uuid4().hex[:6]}@example.com"
    r = owner.post(f"{BASE_URL}/api/members/invite", json={"email": email, "pack": "finance"})
    assert r.status_code == 200
    try:
        ml = owner.get(f"{BASE_URL}/api/members").json()
        target = next(m for m in ml["members"] if m["email"] == email)
        mid = target["membership_id"]

        r = exec_ctx["session"].patch(f"{BASE_URL}/api/members/{mid}", json={"pack": "hr"})
        assert r.status_code == 200
        ml2 = owner.get(f"{BASE_URL}/api/members").json()
        assert next(m for m in ml2["members"] if m["email"] == email)["pack"] == "hr"

        # nobody can promote to owner via role edit
        r = exec_ctx["session"].patch(f"{BASE_URL}/api/members/{mid}", json={"pack": "owner"})
        assert r.status_code == 400

        r = owner.patch(f"{BASE_URL}/api/members/{mid}", json={"pack": "owner"})
        assert r.status_code == 400

        # exec cannot change an existing owner
        owner_mem = next(m for m in ml2["members"] if m["pack"] == "owner")
        r = exec_ctx["session"].patch(f"{BASE_URL}/api/members/{owner_mem['membership_id']}",
                                      json={"pack": "member"})
        assert r.status_code == 403

        # invalid pack
        r = exec_ctx["session"].patch(f"{BASE_URL}/api/members/{mid}", json={"pack": "hacker"})
        assert r.status_code == 400
    finally:
        mongo.memberships.delete_many({"email": email, "workspace_id": WS_ID})


# ------------- Regression: members list has user_id + my_pack -------------
def test_members_list_shape(owner):
    d = owner.get(f"{BASE_URL}/api/members").json()
    assert d["my_pack"] == "owner"
    m0 = d["members"][0]
    assert "user_id" in m0
    assert "pack" in m0


# ------------- Cleanup: purge any TEST_ leftovers -------------
@pytest.fixture(scope="module", autouse=True)
def _cleanup_updates_and_tasks(mongo):
    yield
    day = datetime.now(timezone.utc).date().isoformat()
    mongo.updates.delete_many({"workspace_id": WS_ID, "day": day, "text": {"$regex": "^TEST_"}})
    # Remove TEST_ tasks from the workspace
    ws = mongo.workspaces.find_one({"workspace_id": WS_ID})
    if ws:
        items = [t for t in ws.get("tasks", {}).get("items", []) if not t.get("title", "").startswith("TEST_")]
        mongo.workspaces.update_one({"workspace_id": WS_ID}, {"$set": {"tasks.items": items}})
