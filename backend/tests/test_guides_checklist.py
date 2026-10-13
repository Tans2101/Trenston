"""In-app guides: per-user 'seen' state and the role-aware Get started checklist."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_guides")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402
from tests.mongo_mocks import FakeCollection, match_filter  # noqa: E402


class _Coll(FakeCollection):
    async def update_one(self, flt, update, upsert=False):
        for d in self.docs:
            if match_filter(d, flt or {}):
                for k, v in (update.get("$set") or {}).items():
                    node = d
                    *parents, leaf = k.split(".")
                    for part in parents:
                        node = node.setdefault(part, {})
                    node[leaf] = v
                for k in (update.get("$unset") or {}):
                    node = d
                    *parents, leaf = k.split(".")
                    for part in parents:
                        node = node.get(part, {})
                    node.pop(leaf, None)
                for k, v in (update.get("$addToSet") or {}).items():
                    lst = d.setdefault(k, [])
                    if v not in lst:
                        lst.append(v)
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)


def new_db():
    names = ["users", "workspaces", "memberships", "financial_entries", "updates"]
    return SimpleNamespace(**{n: _Coll() for n in names})


@pytest.fixture
def env():
    db = new_db()
    db.users.docs.append({"user_id": "u1", "email": "a@x.com", "guides_seen": {}})
    db.workspaces.docs.append({
        "workspace_id": "ws1", "name": "Co", "plan": "free", "tasks": {"items": []},
        "people": {"people": []}, "decisions": [],
    })
    db.memberships.docs.append({"workspace_id": "ws1", "user_id": "u1", "status": "active", "role": "owner"})
    state = {"principal": {"user_id": "u1", "email": "a@x.com", "workspace_id": "ws1", "pack": "owner", "role": "owner"}}

    async def principal():
        return state["principal"]

    async def user():
        return next(u for u in db.users.docs if u["user_id"] == state["principal"]["user_id"])

    server.app.dependency_overrides[server.get_principal] = principal
    server.app.dependency_overrides[server.get_user] = user
    with patch.object(server, "db", db), \
            patch.object(server, "can_access_financials", AsyncMock(return_value=True)), \
            patch.object(server.decision_engine, "workspace_has_team", return_value=False), \
            patch.object(server.helm_analytics, "log_event_once", AsyncMock()):
        yield TestClient(server.app), db, state
    server.app.dependency_overrides.clear()


def test_marking_a_guide_seen_and_resetting(env):
    client, db, _ = env
    r = client.patch("/api/account/guides", json={"guide_id": "briefing"})
    assert r.status_code == 200 and r.json()["guides_seen"] == ["briefing"]
    assert "briefing" in db.users.docs[0]["guides_seen"]
    client.patch("/api/account/guides", json={"guide_id": "briefing", "seen": False})
    assert db.users.docs[0]["guides_seen"] == {}
    client.patch("/api/account/guides", json={"guide_id": "tasks"})
    assert client.patch("/api/account/guides", json={"reset_all": True}).json() == {"guides_seen": {}}
    assert db.users.docs[0]["guides_seen"] == {}


@pytest.mark.parametrize("bad", ["", "Bad Id", "../x", "a" * 41, "$set"])
def test_guide_ids_are_validated(env, bad):
    client, _, _ = env
    assert client.patch("/api/account/guides", json={"guide_id": bad}).status_code == 400


def test_clean_guides_seen_drops_junk():
    assert server._clean_guides_seen({"ok": "t", "Bad Key": "t", "$x": "t"}) == {"ok": "t"}
    assert server._clean_guides_seen(None) == {}


def test_solo_owner_checklist_teaches_with_tours(env):
    client, db, _ = env
    j = client.get("/api/onboarding/checklist").json()
    assert [s["id"] for s in j["steps"]] == ["tour", "financials", "decision", "quickadd", "update"]
    assert all(s["tour"] and s["hint"] and s["route"] for s in j["steps"])
    assert not any(s["done"] for s in j["steps"]) and j["complete"] is False

    db.users.docs[0]["guides_seen"] = {"briefing": "t"}
    db.workspaces.docs[0]["decisions"] = [{"id": "d1"}]
    db.workspaces.docs[0]["tasks"]["items"] = [{"id": "t1", "assignee_user_id": "u1"}]
    done = {s["id"]: s["done"] for s in client.get("/api/onboarding/checklist").json()["steps"]}
    assert done == {"tour": True, "financials": False, "decision": True, "quickadd": True, "update": False}


def test_members_get_their_own_steps(env):
    client, _, state = env
    state["principal"] = {**state["principal"], "pack": "member", "role": "member"}
    ids = [s["id"] for s in client.get("/api/onboarding/checklist").json()["steps"]]
    assert ids == ["tour", "update", "tasks", "quickadd"]


def test_dismiss_is_personal(env):
    client, db, state = env
    assert client.post("/api/onboarding/checklist/dismiss").status_code == 200
    assert client.get("/api/onboarding/checklist").json()["dismissed"] is True
    assert db.workspaces.docs[0]["setup_checklist_dismissed_by"] == ["u1"]
    db.users.docs.append({"user_id": "u2", "email": "b@x.com"})
    state["principal"] = {"user_id": "u2", "email": "b@x.com", "workspace_id": "ws1", "pack": "member", "role": "member"}
    assert client.get("/api/onboarding/checklist").json()["dismissed"] is False


def test_old_workspace_wide_dismissal_still_counts_for_the_owner_only(env):
    client, db, state = env
    db.workspaces.docs[0]["setup_checklist_dismissed"] = True
    assert client.get("/api/onboarding/checklist").json()["dismissed"] is True
    state["principal"] = {"user_id": "u2", "email": "b@x.com", "workspace_id": "ws1", "pack": "member", "role": "member"}
    db.users.docs.append({"user_id": "u2", "email": "b@x.com"})
    assert client.get("/api/onboarding/checklist").json()["dismissed"] is False
