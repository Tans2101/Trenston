"""CEO-to-CEO referral tracking — shareable links only, no rewards."""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_referrals")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import referrals as helm_referrals  # noqa: E402
import plans as helm_plans  # noqa: E402
import server  # noqa: E402


class _UpdateResult:
    def __init__(self, matched=1, modified=1):
        self.matched_count = matched
        self.modified_count = modified


def _users_store(docs):
    col = MagicMock()

    async def find_one(query, projection=None):
        if "user_id" in query:
            uid = query["user_id"]
            for d in docs:
                if d.get("user_id") == uid:
                    return dict(d)
            return None
        if "referral_code" in query:
            code = query["referral_code"]
            for d in docs:
                if d.get("referral_code") == code:
                    return dict(d)
            return None
        return None

    async def update_one(query, update):
        uid = query.get("user_id")
        for d in docs:
            if d.get("user_id") == uid:
                d.update(update.get("$set") or {})
                return _UpdateResult()
        return _UpdateResult(0, 0)

    col.find_one = find_one
    col.update_one = update_one
    return col


def _referrals_store(rows):
    col = MagicMock()

    async def find_one(query):
        for d in rows:
            ok = True
            for k, v in query.items():
                if k == "status" and isinstance(v, dict) and "$in" in v:
                    if d.get("status") not in v["$in"]:
                        ok = False
                        break
                elif d.get(k) != v:
                    ok = False
                    break
            if ok:
                return dict(d)
        return None

    async def insert_one(doc):
        rows.append(dict(doc))
        return MagicMock(inserted_id=doc.get("referral_id"))

    async def update_one(query, update):
        rec = await find_one(query)
        if not rec:
            return _UpdateResult(0, 0)
        for d in rows:
            if d.get("referral_id") == rec.get("referral_id"):
                d.update(update.get("$set") or {})
        return _UpdateResult()

    def find(query):
        matched = [dict(d) for d in rows if d.get("referrer_user_id") == query.get("referrer_user_id")]
        cursor = MagicMock()

        def sort(*_a, **_k):
            return cursor

        def limit(*_a, **_k):
            return cursor

        async def to_list(_n=None):
            return matched

        cursor.sort = sort
        cursor.limit = limit
        cursor.to_list = to_list
        return cursor

    col.find_one = find_one
    col.insert_one = insert_one
    col.update_one = update_one
    col.find = find
    return col


def _workspaces_store(docs):
    col = MagicMock()

    async def update_one(query, update):
        wid = query.get("workspace_id")
        for d in docs:
            if d.get("workspace_id") == wid:
                d.update(update.get("$set") or {})
                return _UpdateResult()
        docs.append({**query, **(update.get("$set") or {})})
        return _UpdateResult()

    col.update_one = update_one
    return col


def _db(*, users, referrals, workspaces):
    db = MagicMock()
    db.users = users
    db.referrals = referrals
    db.workspaces = workspaces
    db.product_events = MagicMock()
    db.product_events.insert_one = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_ensure_referral_code_reuses_existing():
    users = _users_store([{"user_id": "u1", "referral_code": "abcd1234abcd1234"}])
    db = _db(users=users, referrals=_referrals_store([]), workspaces=_workspaces_store([]))
    code = await helm_referrals.ensure_referral_code(db, "u1")
    assert code == "abcd1234abcd1234"


@pytest.mark.asyncio
async def test_ensure_referral_code_allocates():
    users = _users_store([{"user_id": "u1"}])
    db = _db(users=users, referrals=_referrals_store([]), workspaces=_workspaces_store([]))
    code = await helm_referrals.ensure_referral_code(db, "u1")
    assert helm_referrals._CODE_RE.match(code)
    assert users.find_one  # allocated onto user
    stored = await users.find_one({"user_id": "u1"})
    assert stored["referral_code"] == code


@pytest.mark.asyncio
async def test_ensure_referral_code_allocates_when_projection_is_empty():
    """Real Mongo returns {} when the projected field is missing; the user still exists."""
    docs = [{"user_id": "u1", "email": "owner@example.com"}]
    users = _users_store(docs)
    plain_find_one = users.find_one

    async def projected_find_one(query, projection=None):
        doc = await plain_find_one(query, projection)
        if doc is None or not projection:
            return doc
        keep = [k for k, v in projection.items() if v and k != "_id"]
        return {k: doc[k] for k in keep if k in doc}

    users.find_one = projected_find_one
    db = _db(users=users, referrals=_referrals_store([]), workspaces=_workspaces_store([]))
    code = await helm_referrals.ensure_referral_code(db, "u1")
    assert helm_referrals._CODE_RE.match(code)
    assert docs[0]["referral_code"] == code


@pytest.mark.asyncio
async def test_ensure_referral_code_missing_user_not_invite_wording():
    """Must not raise 'User not found' — that string looked like invite-field validation."""
    from fastapi import HTTPException

    users = _users_store([])
    db = _db(users=users, referrals=_referrals_store([]), workspaces=_workspaces_store([]))
    with pytest.raises(HTTPException) as ei:
        await helm_referrals.ensure_referral_code(db, "missing")
    assert ei.value.status_code == 404
    assert "user not found" not in ei.value.detail.lower()
    assert "referral" in ei.value.detail.lower()


@pytest.mark.asyncio
async def test_attribute_signup_tags_workspace_and_signed_up():
    users = _users_store([
        {"user_id": "ceo1", "referral_code": "aabbccddeeff0011", "active_workspace_id": "ws_ceo"},
        {"user_id": "new1", "email": "new@example.com"},
    ])
    rows = []
    workspaces = [{"workspace_id": "ws_new"}]
    db = _db(users=users, referrals=_referrals_store(rows), workspaces=_workspaces_store(workspaces))
    referrer = await helm_referrals.attribute_signup(
        db,
        referral_code="aabbccddeeff0011",
        new_user={"user_id": "new1", "email": "New@Example.com"},
        new_workspace={"workspace_id": "ws_new"},
    )
    assert referrer["user_id"] == "ceo1"
    assert workspaces[0]["referred_by"] == "ceo1"
    assert rows[0]["status"] == "signed_up"
    assert rows[0]["referred_email"] == "new@example.com"


@pytest.mark.asyncio
async def test_attribute_signup_ignores_self_referral():
    users = _users_store([
        {"user_id": "ceo1", "referral_code": "aabbccddeeff0011", "email": "ceo@example.com"},
    ])
    rows = []
    workspaces = [{"workspace_id": "ws_new"}]
    db = _db(users=users, referrals=_referrals_store(rows), workspaces=_workspaces_store(workspaces))
    out = await helm_referrals.attribute_signup(
        db,
        referral_code="aabbccddeeff0011",
        new_user={"user_id": "ceo1", "email": "ceo@example.com"},
        new_workspace={"workspace_id": "ws_new"},
    )
    assert out is None
    assert "referred_by" not in workspaces[0]
    assert rows == []


@pytest.mark.asyncio
async def test_attribute_signup_promotes_sent_row():
    users = _users_store([
        {"user_id": "ceo1", "referral_code": "aabbccddeeff0011", "active_workspace_id": "ws_ceo"},
        {"user_id": "new1", "email": "friend@co.com"},
    ])
    rows = [{
        "referral_id": "rfr_existing",
        "referrer_user_id": "ceo1",
        "referred_email": "friend@co.com",
        "status": "sent",
        "referrer_workspace_id": "ws_ceo",
    }]
    workspaces = [{"workspace_id": "ws_new"}]
    db = _db(users=users, referrals=_referrals_store(rows), workspaces=_workspaces_store(workspaces))
    await helm_referrals.attribute_signup(
        db,
        referral_code="aabbccddeeff0011",
        new_user={"user_id": "new1", "email": "friend@co.com"},
        new_workspace={"workspace_id": "ws_new"},
    )
    assert len(rows) == 1
    assert rows[0]["status"] == "signed_up"
    assert rows[0]["referred_workspace_id"] == "ws_new"


@pytest.mark.asyncio
async def test_attribute_signup_does_not_steal_prior_signed_up():
    users = _users_store([
        {"user_id": "ceo1", "referral_code": "aabbccddeeff0011", "active_workspace_id": "ws_ceo"},
        {"user_id": "new1", "email": "friend@co.com"},
    ])
    rows = [{
        "referral_id": "rfr_first",
        "referrer_user_id": "ceo1",
        "referred_email": "friend@co.com",
        "status": "signed_up",
        "referred_workspace_id": "ws_first",
        "referrer_workspace_id": "ws_ceo",
    }]
    workspaces = [{"workspace_id": "ws_second"}]
    db = _db(users=users, referrals=_referrals_store(rows), workspaces=_workspaces_store(workspaces))
    await helm_referrals.attribute_signup(
        db,
        referral_code="aabbccddeeff0011",
        new_user={"user_id": "new1", "email": "friend@co.com"},
        new_workspace={"workspace_id": "ws_second"},
    )
    assert len(rows) == 2
    first = next(r for r in rows if r["referral_id"] == "rfr_first")
    assert first["referred_workspace_id"] == "ws_first"
    assert first["status"] == "signed_up"
    second = next(r for r in rows if r["referral_id"] != "rfr_first")
    assert second["referred_workspace_id"] == "ws_second"
    assert second["status"] == "signed_up"


@pytest.mark.asyncio
async def test_lookup_referral_code_is_case_insensitive():
    users = _users_store([
        {"user_id": "ceo1", "referral_code": "aabbccddeeff0011", "active_workspace_id": "ws_ceo"},
        {"user_id": "new1", "email": "new@example.com"},
    ])
    workspaces = [{"workspace_id": "ws_new"}]
    db = _db(users=users, referrals=_referrals_store([]), workspaces=_workspaces_store(workspaces))
    referrer = await helm_referrals.attribute_signup(
        db,
        referral_code="AABBCCDDEEFF0011",
        new_user={"user_id": "new1", "email": "new@example.com"},
        new_workspace={"workspace_id": "ws_new"},
    )
    assert referrer["user_id"] == "ceo1"
    assert workspaces[0]["referred_by"] == "ceo1"


@pytest.mark.asyncio
async def test_mark_referral_converted():
    rows = [{
        "referral_id": "rfr_1",
        "referrer_user_id": "ceo1",
        "status": "signed_up",
        "referred_workspace_id": "ws_new",
    }]
    db = _db(users=_users_store([]), referrals=_referrals_store(rows), workspaces=_workspaces_store([]))
    ok = await helm_referrals.mark_referral_converted(
        db,
        {"workspace_id": "ws_new", "referral_id": "rfr_1", "referred_by": "ceo1", "plan": "starter"},
    )
    assert ok is True
    assert rows[0]["status"] == "converted"
    assert rows[0]["converted_at"]


@pytest.mark.asyncio
async def test_mark_referral_converted_idempotent():
    rows = [{
        "referral_id": "rfr_1",
        "referrer_user_id": "ceo1",
        "status": "converted",
        "referred_workspace_id": "ws_new",
    }]
    db = _db(users=_users_store([]), referrals=_referrals_store(rows), workspaces=_workspaces_store([]))
    ok = await helm_referrals.mark_referral_converted(db, {"referral_id": "rfr_1", "workspace_id": "ws_new"})
    assert ok is False


def test_should_mark_converted_paid_active_only():
    assert helm_referrals.should_mark_converted("active", helm_plans.PLAN_STARTER) is True
    assert helm_referrals.should_mark_converted("trialing", helm_plans.PLAN_STARTER) is False
    assert helm_referrals.should_mark_converted("active", helm_plans.PLAN_FREE) is False


@pytest.mark.asyncio
async def test_record_sent_invite_validates_email():
    db = _db(users=_users_store([]), referrals=_referrals_store([]), workspaces=_workspaces_store([]))
    with pytest.raises(HTTPException):
        await helm_referrals.record_sent_invite(
            db, referrer_user_id="u1", referrer_workspace_id="ws1", referred_email="not-an-email",
        )


@pytest.mark.asyncio
async def test_list_referrals_for_user():
    rows = [
        {"referral_id": "a", "referrer_user_id": "u1", "referred_email": "a@x.com", "status": "sent", "created_at": "2026-01-01"},
        {"referral_id": "b", "referrer_user_id": "u2", "referred_email": "b@x.com", "status": "signed_up"},
    ]
    db = _db(users=_users_store([]), referrals=_referrals_store(rows), workspaces=_workspaces_store([]))
    listed = await helm_referrals.list_referrals_for_user(db, "u1")
    assert len(listed) == 1
    assert listed[0]["referred_email"] == "a@x.com"
    assert listed[0]["status"] == "sent"


def test_share_url():
    assert helm_referrals.share_url("https://gethelm.app", "aabbccddeeff0011") == "https://gethelm.app/sign-up?ref=aabbccddeeff0011"


OWNER = {
    "user_id": "u_owner",
    "email": "ceo@example.com",
    "name": "CEO",
    "workspace_id": "ws_1",
    "role": "owner",
    "pack": "owner",
}


def _override_owner(principal=None):
    p = principal or OWNER

    async def mock_principal():
        return p

    server.app.dependency_overrides[server.get_principal] = mock_principal


def test_referrals_api_generates_link_and_lists():
    users = _users_store([{"user_id": "u_owner"}])
    rows = []
    mock_db = _db(users=users, referrals=_referrals_store(rows), workspaces=_workspaces_store([]))
    _override_owner()
    try:
        with patch.object(server, "db", mock_db), patch.object(server, "APP_URL", "https://gethelm.app"):
            client = TestClient(server.app)
            created = client.post("/api/referrals", json={"email": "friend@co.com"})
            listed = client.get("/api/referrals")
    finally:
        server.app.dependency_overrides.clear()
    assert created.status_code == 200
    assert listed.status_code == 200
    body = created.json()
    assert body["share_url"].startswith("https://gethelm.app/sign-up?ref=")
    assert body["referral_code"]
    assert any(r["referred_email"] == "friend@co.com" and r["status"] == "sent" for r in body["referrals"])
    assert listed.json()["referral_code"] == body["referral_code"]


def test_referrals_api_forbidden_for_member():
    _override_owner({**OWNER, "role": "member", "pack": "member"})
    try:
        client = TestClient(server.app)
        r = client.get("/api/referrals")
    finally:
        server.app.dependency_overrides.clear()
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_maybe_mark_referral_converted_on_paid():
    rows = [{
        "referral_id": "rfr_pay",
        "referrer_user_id": "ceo1",
        "status": "signed_up",
        "referred_workspace_id": "ws_paid",
    }]
    mock_db = _db(users=_users_store([]), referrals=_referrals_store(rows), workspaces=_workspaces_store([]))

    async def find_one(query, projection=None):
        return {
            "workspace_id": "ws_paid",
            "plan": "starter",
            "referred_by": "ceo1",
            "referral_id": "rfr_pay",
            "subscription_status": "active",
        }

    mock_db.workspaces.find_one = find_one
    with patch.object(server, "db", mock_db):
        await server._maybe_mark_referral_converted("ws_paid", "active")
    assert rows[0]["status"] == "converted"


@pytest.mark.asyncio
async def test_maybe_mark_referral_converted_skips_trial():
    rows = [{
        "referral_id": "rfr_pay",
        "referrer_user_id": "ceo1",
        "status": "signed_up",
        "referred_workspace_id": "ws_paid",
    }]
    mock_db = _db(users=_users_store([]), referrals=_referrals_store(rows), workspaces=_workspaces_store([]))

    async def find_one(query, projection=None):
        return {
            "workspace_id": "ws_paid",
            "plan": "starter",
            "referred_by": "ceo1",
            "referral_id": "rfr_pay",
            "subscription_status": "trialing",
        }

    mock_db.workspaces.find_one = find_one
    with patch.object(server, "db", mock_db):
        await server._maybe_mark_referral_converted("ws_paid", "trialing")
    assert rows[0]["status"] == "signed_up"
