"""Iteration 4 tests: Access Packs (Phase 0), Activity/Briefing loop (Phase 1),
People CRUD + headcount sync (Phase 3), and regression on existing endpoints under the new pack model.

Integration: requires a seeded preview backend + live Mongo (pre-seeded sessions).
Set RUN_INTEGRATION=1 to run.
"""
import os
import uuid
import pytest
import requests
import pymongo
from datetime import datetime, timezone

from conftest import set_workspace_plan

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_INTEGRATION") != "1",
        reason="integration: seeded preview + live Mongo; set RUN_INTEGRATION=1",
    ),
]

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://exec-cockpit.preview.emergentagent.com").rstrip("/")
OWNER_TOKEN = "test_session_kalun_123"
MEMBER_TOKEN = "test_session_user2"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


def _sess(token):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def owner():
    s = _sess(OWNER_TOKEN)
    # ensure sample data is loaded
    s.post(f"{BASE_URL}/api/workspace/apply-template", json={"template": "sample"})
    set_workspace_plan(s, BASE_URL, "pro")
    return s


@pytest.fixture(scope="module")
def member():
    return _sess(MEMBER_TOKEN)


@pytest.fixture(scope="module")
def mongo():
    return pymongo.MongoClient(MONGO_URL)[DB_NAME]


# ---------------- Phase 0: /auth/me returns pack, perms, default_route, pack_label ----------------
def test_auth_me_owner_pack_and_perms(owner):
    r = owner.get(f"{BASE_URL}/api/auth/me")
    assert r.status_code == 200
    d = r.json()
    assert d["pack"] == "owner"
    assert d["default_route"] == "/app"
    assert d["pack_label"] == "Owner"
    perms = set(d["perms"])
    for p in ("finance:write", "people:write", "members:manage", "decisions:act",
              "briefing:generate", "reports:pack", "integrations:manage", "billing:manage",
              "workspace:edit", "read", "tasks:move", "ask:use"):
        assert p in perms, f"owner missing perm {p}"


def test_auth_me_member_pack_and_perms(member):
    r = member.get(f"{BASE_URL}/api/auth/me")
    assert r.status_code == 200
    d = r.json()
    assert d["pack"] == "member"
    assert d["default_route"] == "/app"
    assert d["pack_label"] == "Member"
    perms = set(d["perms"])
    for p in ("finance:write", "people:write", "members:manage", "decisions:act"):
        assert p not in perms, f"member should NOT have {p}"
    assert "calendar:write" not in perms
    for p in ("read", "tasks:move", "ask:use"):
        assert p in perms


# ---------------- Phase 0: Member 403 on writes; Owner 200 ----------------
def test_member_forbidden_on_finance_and_people_and_invite(member):
    # settings
    r = member.put(f"{BASE_URL}/api/financials/settings", json={"cash": 500000, "gross_margin": 70})
    assert r.status_code == 403, r.text[:200]
    # entry add
    r = member.post(f"{BASE_URL}/api/financials/entries",
                    json={"type": "revenue", "category": "TEST_x", "amount": 1, "month": "2025-01"})
    assert r.status_code == 403
    # people add
    r = member.post(f"{BASE_URL}/api/people", json={"name": "TEST_deny"})
    assert r.status_code == 403
    # people patch/delete on any id
    r = member.patch(f"{BASE_URL}/api/people/nonexistent", json={"name": "x"})
    assert r.status_code == 403
    r = member.delete(f"{BASE_URL}/api/people/nonexistent")
    assert r.status_code == 403
    # invite
    r = member.post(f"{BASE_URL}/api/members/invite", json={"email": "test_deny_pack@example.com"})
    assert r.status_code == 403


def test_owner_can_write_finance_and_people(owner):
    r = owner.put(f"{BASE_URL}/api/financials/settings", json={"cash": 3100000, "gross_margin": 74})
    assert r.status_code == 200
    r = owner.post(f"{BASE_URL}/api/people", json={"name": "TEST_probe_owner", "role": "QA"})
    assert r.status_code == 200
    pid = r.json()["person"]["id"]
    # cleanup
    owner.delete(f"{BASE_URL}/api/people/{pid}")


# ---------------- Phase 0: Invite with pack + list members + patch pack + cannot change self ----------------
def test_invite_with_pack_and_patch_pack(owner, mongo):
    email = f"test_pack_{uuid.uuid4().hex[:6]}@example.com"
    r = owner.post(f"{BASE_URL}/api/members/invite", json={"email": email, "pack": "finance"})
    assert r.status_code == 200, r.text
    try:
        ml = owner.get(f"{BASE_URL}/api/members").json()
        assert ml["my_pack"] == "owner"
        target = next(m for m in ml["members"] if m["email"] == email)
        assert target["pack"] == "finance"
        # patch to hr
        r = owner.patch(f"{BASE_URL}/api/members/{target['membership_id']}", json={"pack": "hr"})
        assert r.status_code == 200
        ml2 = owner.get(f"{BASE_URL}/api/members").json()
        assert next(m for m in ml2["members"] if m["email"] == email)["pack"] == "hr"
        # cannot change own pack
        my = next(m for m in ml2["members"] if m["is_self"])
        r = owner.patch(f"{BASE_URL}/api/members/{my['membership_id']}", json={"pack": "member"})
        assert r.status_code == 400
    finally:
        mongo.memberships.delete_many({"email": email})


# ---------------- Phase 1: Activity loop + briefing sync ----------------
def test_financial_settings_activity_and_briefing(owner):
    before = owner.get(f"{BASE_URL}/api/activities").json()["activities"]
    before_ids = {a["activity_id"] for a in before}
    tag_cash = 3100000 + int(datetime.now(timezone.utc).timestamp()) % 1000
    r = owner.put(f"{BASE_URL}/api/financials/settings", json={"cash": tag_cash, "gross_margin": 74})
    assert r.status_code == 200
    acts = owner.get(f"{BASE_URL}/api/activities").json()["activities"]
    assert acts[0]["module"] == "financials"
    assert acts[0]["action"] == "settings.update"
    assert "ago" in acts[0]
    assert "cash" in acts[0]["summary"].lower()
    assert "runway" in acts[0]["summary"].lower()
    assert acts[0]["activity_id"] not in before_ids
    # briefing.what_changed[0]
    b = owner.get(f"{BASE_URL}/api/briefing").json()
    wc = b["what_changed"]
    assert wc[0]["title"] == acts[0]["summary"]
    assert " · " in wc[0]["detail"]


def test_financial_entry_add_and_delete_activity(owner):
    r = owner.post(f"{BASE_URL}/api/financials/entries",
                   json={"type": "revenue", "category": "TEST_activity",
                         "name": "TEST activity item",
                         "amount": 12345, "month": "2025-01", "recurring": True})
    assert r.status_code == 200
    entry_id = r.json()["entry"]["id"]
    acts = owner.get(f"{BASE_URL}/api/activities").json()["activities"]
    assert acts[0]["module"] == "financials" and acts[0]["action"] == "entry.add"
    assert "revenue" in acts[0]["summary"].lower()
    # delete
    r = owner.delete(f"{BASE_URL}/api/financials/entries/{entry_id}")
    assert r.status_code == 200
    acts2 = owner.get(f"{BASE_URL}/api/activities").json()["activities"]
    assert acts2[0]["action"] == "entry.delete"


# ---------------- Phase 3: People CRUD + headcount sync + activity ----------------
def test_people_crud_headcount_sync_and_activity(owner):
    fin_before = owner.get(f"{BASE_URL}/api/company").json()
    hc_before = fin_before.get("employees", 0)

    r = owner.post(f"{BASE_URL}/api/people",
                   json={"name": "TEST_Alice CRUD", "role": "Engineer", "department": "Eng"})
    assert r.status_code == 200
    pid = r.json()["person"]["id"]

    # headcount +1
    c1 = owner.get(f"{BASE_URL}/api/company").json()
    assert c1["employees"] == hc_before + 1

    # /people returns can_write + person present
    pl = owner.get(f"{BASE_URL}/api/people").json()
    assert pl["can_write"] is True
    assert "avg_trust" not in pl
    assert "unassigned_count" in pl
    assert any(p["id"] == pid for p in pl["people"])

    # activity for add
    acts = owner.get(f"{BASE_URL}/api/activities").json()["activities"]
    assert acts[0]["module"] == "people" and acts[0]["action"] == "person.add"
    assert "TEST_Alice CRUD" in acts[0]["summary"]

    # briefing what_changed[0] = same summary
    b = owner.get(f"{BASE_URL}/api/briefing").json()
    assert b["what_changed"][0]["title"] == acts[0]["summary"]

    # PATCH edits
    r = owner.patch(f"{BASE_URL}/api/people/{pid}",
                    json={"name": "TEST_Alice CRUD", "role": "Senior Engineer",
                          "department": "Eng"})
    assert r.status_code == 200
    pl2 = owner.get(f"{BASE_URL}/api/people").json()
    edited = next(p for p in pl2["people"] if p["id"] == pid)
    assert edited["role"] == "Senior Engineer"
    acts_e = owner.get(f"{BASE_URL}/api/activities").json()["activities"]
    assert acts_e[0]["action"] == "person.edit"

    # DELETE
    r = owner.delete(f"{BASE_URL}/api/people/{pid}")
    assert r.status_code == 200
    c2 = owner.get(f"{BASE_URL}/api/company").json()
    assert c2["employees"] == hc_before
    acts_d = owner.get(f"{BASE_URL}/api/activities").json()["activities"]
    assert acts_d[0]["action"] == "person.delete"


def test_people_read_can_write_member_false(member):
    r = member.get(f"{BASE_URL}/api/people")
    assert r.status_code == 200
    d = r.json()
    assert d["can_write"] is False


# ---------------- Regression: existing endpoints still work under new pack model ----------------
REGRESSION_GETS = ["/api/briefing", "/api/telemetry", "/api/financials", "/api/decisions",
                   "/api/integrations", "/api/billing/plans"]


@pytest.mark.parametrize("path", REGRESSION_GETS)
def test_regression_owner_reads(owner, path):
    r = owner.get(f"{BASE_URL}{path}")
    assert r.status_code == 200, f"{path}: {r.status_code}"


def test_regression_owner_decision_action(owner):
    decs = owner.get(f"{BASE_URL}/api/decisions").json()["decisions"]
    if not decs:
        pytest.skip("no decisions")
    did = decs[0]["id"]
    orig = decs[0]["status"]
    r = owner.post(f"{BASE_URL}/api/decisions/{did}/action", json={"action": "approved"})
    assert r.status_code == 200
    # restore
    owner.post(f"{BASE_URL}/api/decisions/{did}/action", json={"action": orig})


def test_regression_member_can_move_task(owner, member):
    items = owner.get(f"{BASE_URL}/api/tasks").json().get("items", [])
    if not items:
        pytest.skip("no tasks")
    tid = items[0]["id"]
    orig = items[0]["column"]
    new_col = "doing" if orig != "doing" else "todo"
    r = member.patch(f"{BASE_URL}/api/tasks/{tid}", json={"column": new_col})
    assert r.status_code == 200
    member.patch(f"{BASE_URL}/api/tasks/{tid}", json={"column": orig})


def test_regression_apply_template_owner_only(owner, member):
    r = member.post(f"{BASE_URL}/api/workspace/apply-template", json={"template": "sample"})
    assert r.status_code == 403
    r = owner.post(f"{BASE_URL}/api/workspace/apply-template", json={"template": "sample"})
    assert r.status_code == 200


def test_regression_decisions_can_act_flag(owner, member):
    a = owner.get(f"{BASE_URL}/api/decisions").json()
    b = member.get(f"{BASE_URL}/api/decisions").json()
    assert a.get("can_act") is True
    assert b.get("can_act") is False


def test_financials_can_write_flags(owner, member):
    a = owner.get(f"{BASE_URL}/api/financials").json()
    b = member.get(f"{BASE_URL}/api/financials").json()
    assert a["can_write"] is True
    assert b["can_write"] is False
