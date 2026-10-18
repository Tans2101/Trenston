"""Personal API keys + read-only public API (/api/v1).

The security contract under test: a key can only ever read what its owner can
read in the app right now, in the key's own workspace, while the plan allows it.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_public_api_keys")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import api_keys  # noqa: E402
import public_api  # noqa: E402
import server  # noqa: E402
from tests.mongo_mocks import FakeCollection  # noqa: E402


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- key helpers

def test_generated_keys_are_prefixed_long_and_unique():
    a, b = api_keys.generate_key(), api_keys.generate_key()
    assert a.startswith("trn_") and b.startswith("trn_")
    assert len(a) >= api_keys.MIN_KEY_LENGTH
    assert a != b
    assert api_keys.looks_like_api_key(a)


def test_looks_like_api_key_rejects_other_tokens():
    assert not api_keys.looks_like_api_key("")
    assert not api_keys.looks_like_api_key("trn_short")
    assert not api_keys.looks_like_api_key("eyJhbGciOi.payload.sig")
    assert not api_keys.looks_like_api_key("session_token_value_that_is_long_enough_to_pass")


def test_hash_is_stable_and_not_the_key():
    raw = api_keys.generate_key()
    assert api_keys.hash_key(raw) == api_keys.hash_key(raw)
    assert raw not in api_keys.hash_key(raw)


def test_hint_shows_only_edges():
    raw = api_keys.generate_key()
    hint = api_keys.key_hint(raw)
    assert hint.startswith(raw[:8]) and hint.endswith(raw[-4:])
    assert raw[8:-4] not in hint


def test_token_from_headers_accepts_bearer_and_x_api_key():
    assert api_keys.token_from_headers({"Authorization": "Bearer trn_abc"}) == "trn_abc"
    assert api_keys.token_from_headers({"authorization": "bearer trn_abc"}) == "trn_abc"
    assert api_keys.token_from_headers({"X-API-Key": "trn_xyz"}) == "trn_xyz"
    assert api_keys.token_from_headers({}) == ""


def test_name_normalized_and_capped():
    assert api_keys.normalize_name("  My   Claude  ") == "My Claude"
    assert api_keys.normalize_name("") == api_keys.DEFAULT_KEY_NAME
    assert len(api_keys.normalize_name("x" * 200)) == api_keys.NAME_MAX_LENGTH


# ---------------------------------------------------------------- key storage

def _db(**collections):
    base = {
        "api_keys": FakeCollection(),
        "users": FakeCollection(),
        "memberships": FakeCollection(),
        "workspaces": FakeCollection(),
        "user_sessions": FakeCollection(),
        "api_rate_buckets": FakeCollection(),
    }
    base.update(collections)
    return _DB(base)


class _DB(SimpleNamespace):
    def __init__(self, collections):
        super().__init__(**collections)

    def __getitem__(self, name):
        return getattr(self, name)


def test_create_stores_hash_only_and_lists_without_secrets():
    db = _db()
    raw, view = run(api_keys.create_key(db, user_id="u1", workspace_id="ws1", name="Claude"))
    stored = db.api_keys.docs[0]
    assert stored["key_hash"] == api_keys.hash_key(raw)
    assert raw not in str(stored)
    assert set(view) == {"id", "name", "hint", "created_at", "last_used_at"}
    listed = run(api_keys.list_keys(db, user_id="u1", workspace_id="ws1"))
    assert listed == [view]
    assert "key_hash" not in listed[0]


def test_key_limit_enforced():
    db = _db()
    for _ in range(api_keys.MAX_ACTIVE_KEYS_PER_USER):
        run(api_keys.create_key(db, user_id="u1", workspace_id="ws1"))
    with pytest.raises(api_keys.ApiKeyLimitError):
        run(api_keys.create_key(db, user_id="u1", workspace_id="ws1"))


def test_revoked_key_no_longer_resolves_and_only_owner_can_revoke():
    db = _db()
    raw, view = run(api_keys.create_key(db, user_id="u1", workspace_id="ws1"))
    assert run(api_keys.resolve(db, raw))["id"] == view["id"]
    # Another user cannot revoke it.
    assert run(api_keys.revoke_key(db, key_id=view["id"], user_id="u2", workspace_id="ws1")) is False
    assert run(api_keys.revoke_key(db, key_id=view["id"], user_id="u1", workspace_id="ws1")) is True
    assert run(api_keys.resolve(db, raw)) is None
    assert run(api_keys.list_keys(db, user_id="u1", workspace_id="ws1")) == []


def test_resolve_rejects_unknown_key():
    db = _db()
    run(api_keys.create_key(db, user_id="u1", workspace_id="ws1"))
    assert run(api_keys.resolve(db, api_keys.generate_key())) is None


def test_touch_is_throttled():
    now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
    assert api_keys.needs_touch({"last_used_at": None}, now)
    recent = (now - timedelta(minutes=1)).isoformat()
    stale = (now - timedelta(minutes=10)).isoformat()
    assert not api_keys.needs_touch({"last_used_at": recent}, now)
    assert api_keys.needs_touch({"last_used_at": stale}, now)


# ---------------------------------------------------------------- projections

def test_briefing_projection_drops_mailbox_data():
    out = public_api.briefing({
        "headline": "h",
        "email_threads": [{"subject": "private"}],
        "gmail_connected": True,
        "metrics": [{"label": "MRR", "value": "$1K", "section": "finance", "secret": 1}],
    })
    assert "email_threads" not in out and "gmail_connected" not in out
    assert out["metrics"] == [{"label": "MRR", "value": "$1K", "delta": None, "tone": None, "section": "finance"}]


def test_financials_projection_never_turns_missing_into_zero():
    out = public_api.financials({
        "mrr": "—", "mrr_state": "not_entered", "mrr_value": 0,
        "burn": "$5K", "burn_state": "computed", "burn_value": 5000,
        "cash": "—", "cash_state": "not_entered", "cash_value": 0,
        "gross_margin": "—",
    })
    assert out["mrr"] == {"display": None, "value": None, "state": "not_entered"}
    assert out["cash"]["value"] is None
    assert out["burn"] == {"display": "$5K", "value": 5000, "state": "computed"}
    assert out["gross_margin"] is None


def test_tasks_projection_maps_column_names():
    out = public_api.tasks({
        "columns": [{"id": "backlog", "name": "To-Do"}, {"id": "done", "name": "Done"}],
        "items": [{"id": "t1", "title": "A", "column": "backlog"}, {"id": "t2", "title": "B", "column": "done"}],
    })
    assert [(t["status"], t["done"]) for t in out["tasks"]] == [("To-Do", False), ("Done", True)]


# ---------------------------------------------------------------- endpoints

def _seed(plan="growth", *, member_active=True):
    db = _db()
    owner_raw, owner_view = run(api_keys.create_key(db, user_id="u_owner", workspace_id="ws1"))
    member_raw, member_view = run(api_keys.create_key(db, user_id="u_member", workspace_id="ws1"))
    db.users.docs += [
        # active_workspace_id points elsewhere: the key's workspace must win.
        {"user_id": "u_owner", "email": "o@x.com", "name": "Owner", "active_workspace_id": "ws_other"},
        {"user_id": "u_member", "email": "m@x.com", "name": "Member"},
    ]
    db.memberships.docs += [
        {"user_id": "u_owner", "workspace_id": "ws1", "role": "owner", "status": "active"},
        {"user_id": "u_owner", "workspace_id": "ws_other", "role": "owner", "status": "active"},
        {"user_id": "u_member", "workspace_id": "ws1", "role": "member", "pack": "member",
         "status": "active" if member_active else "removed"},
    ]
    db.workspaces.docs += [
        {"workspace_id": "ws1", "name": "Acme", "plan": plan, "currency": "usd"},
        {"workspace_id": "ws_other", "name": "Other Co", "plan": "business", "currency": "usd"},
    ]
    return db, owner_raw, member_raw, owner_view


@pytest.fixture
def api(request):
    params = getattr(request, "param", {}) or {}
    db, owner_raw, member_raw, owner_view = _seed(**params)
    with patch.object(server, "db", db), \
            patch.object(server, "BILLING_ENFORCED", True), \
            patch.object(server.doc_rate_limit, "_acquire_window_bucket", AsyncMock(return_value=True)), \
            patch.object(server, "log_activity", AsyncMock()):
        yield SimpleNamespace(
            client=TestClient(server.app), db=db,
            owner=owner_raw, member=member_raw, owner_key=owner_view,
        )
    server.app.dependency_overrides.clear()


def _auth(raw):
    return {"Authorization": f"Bearer {raw}"}


def test_missing_and_bogus_keys_are_rejected(api):
    assert api.client.get("/api/v1/me").status_code == 401
    r = api.client.get("/api/v1/me", headers=_auth(api_keys.generate_key()))
    assert r.status_code == 401
    assert "WWW-Authenticate" in r.headers


def test_me_uses_the_keys_workspace_not_the_users_active_one(api):
    r = api.client.get("/api/v1/me", headers=_auth(api.owner))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["workspace"]["id"] == "ws1"
    assert body["workspace"]["name"] == "Acme"
    assert body["read_only"] is True


def test_x_api_key_header_also_works(api):
    r = api.client.get("/api/v1/me", headers={"X-API-Key": api.owner})
    assert r.status_code == 200, r.text


def test_revoked_key_stops_working_immediately(api):
    run(api_keys.revoke_key(api.db, key_id=api.owner_key["id"], user_id="u_owner", workspace_id="ws1"))
    assert api.client.get("/api/v1/me", headers=_auth(api.owner)).status_code == 401


@pytest.mark.parametrize("api", [{"plan": "free"}], indirect=True)
def test_free_plan_is_refused(api):
    r = api.client.get("/api/v1/me", headers=_auth(api.owner))
    assert r.status_code == 403
    assert r.json()["detail"]["feature"] == "api_access"


@pytest.mark.parametrize("api", [{"member_active": False}], indirect=True)
def test_key_dies_when_user_leaves_the_workspace(api):
    assert api.client.get("/api/v1/me", headers=_auth(api.member)).status_code == 401


def test_deleted_account_key_rejected(api):
    api.db.users.docs[0]["deleted_at"] = "2026-10-01T00:00:00+00:00"
    with patch.object(server, "_user_is_deleted", lambda u: bool((u or {}).get("deleted_at"))):
        assert api.client.get("/api/v1/me", headers=_auth(api.owner)).status_code == 401


def test_member_without_financials_access_gets_nothing_financial(api):
    r = api.client.get("/api/v1/financials", headers=_auth(api.member))
    assert r.status_code == 403
    assert r.json()["detail"] == server.FINANCIALS_ACCESS_DENIED_MESSAGE
    me = api.client.get("/api/v1/me", headers=_auth(api.member)).json()
    assert me["access"]["financials"] is False


def test_owner_gets_financial_summary(api):
    fin = {"mrr": "$10K", "mrr_state": "computed", "mrr_value": 10000, "currency": "usd",
           "burn": "—", "burn_state": "not_entered", "burn_value": 0}
    with patch.object(server, "compute_financials", AsyncMock(return_value=fin)), \
            patch.object(server.dept_access, "accessible_department_ids", AsyncMock(return_value=None)):
        r = api.client.get("/api/v1/financials", headers=_auth(api.owner))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mrr"]["value"] == 10000
    assert body["burn"] == {"display": None, "value": None, "state": "not_entered"}


def test_briefing_runs_as_the_key_owner_and_strips_mail(api):
    seen = {}

    async def fake_briefing(principal):
        seen.update(principal)
        return {"headline": "Hi", "email_threads": [{"subject": "secret"}], "metrics": []}

    with patch.object(server, "briefing", fake_briefing):
        r = api.client.get("/api/v1/briefing", headers=_auth(api.member))
    assert r.status_code == 200, r.text
    assert "email_threads" not in r.json()
    assert seen["user_id"] == "u_member"
    assert seen["workspace_id"] == "ws1"
    assert seen["pack"] == "member"
    assert seen["via_api_key"]


def test_rate_limit_returns_429(api):
    with patch.object(server.doc_rate_limit, "_acquire_window_bucket", AsyncMock(return_value=False)):
        r = api.client.get("/api/v1/me", headers=_auth(api.owner))
    assert r.status_code == 429
    assert r.headers.get("Retry-After")


def test_api_keys_do_not_work_on_app_endpoints(api):
    # App routes use session/Clerk auth only; an API key must never unlock them.
    assert api.client.get("/api/tasks", headers=_auth(api.owner)).status_code == 401


def test_v1_is_read_only(api):
    for path in ("/api/v1/me", "/api/v1/tasks", "/api/v1/decisions", "/api/v1/financials"):
        assert api.client.post(path, headers=_auth(api.owner)).status_code == 405
        assert api.client.delete(path, headers=_auth(api.owner)).status_code == 405


# ---------------------------------------------------------------- key management (session auth)

def _as(user_id, pack="owner", role="owner"):
    async def principal():
        return {"user_id": user_id, "name": "N", "email": "e@x.com",
                "workspace_id": "ws1", "pack": pack, "role": role}
    return principal


def test_create_list_revoke_round_trip(api):
    server.app.dependency_overrides[server.get_principal] = _as("u_owner")
    created = api.client.post("/api/api-keys", json={"name": "Claude"})
    assert created.status_code == 200, created.text
    raw = created.json()["key"]
    assert raw.startswith("trn_")
    listed = api.client.get("/api/api-keys").json()
    assert listed["allowed"] is True
    assert all("key" not in k and "key_hash" not in k for k in listed["keys"])
    assert any(k["name"] == "Claude" for k in listed["keys"])
    assert api.client.get("/api/v1/me", headers=_auth(raw)).status_code == 200
    key_id = created.json()["id"]
    assert api.client.delete(f"/api/api-keys/{key_id}").status_code == 200
    assert api.client.get("/api/v1/me", headers=_auth(raw)).status_code == 401


def test_cannot_revoke_someone_elses_key(api):
    server.app.dependency_overrides[server.get_principal] = _as("u_member", pack="member", role="member")
    assert api.client.delete(f"/api/api-keys/{api.owner_key['id']}").status_code == 404


@pytest.mark.parametrize("api", [{"plan": "free"}], indirect=True)
def test_creating_keys_requires_a_paid_plan(api):
    server.app.dependency_overrides[server.get_principal] = _as("u_owner")
    r = api.client.post("/api/api-keys", json={"name": "x"})
    assert r.status_code == 403
    listed = api.client.get("/api/api-keys").json()
    assert listed["allowed"] is False
    assert listed["plan_message"]
