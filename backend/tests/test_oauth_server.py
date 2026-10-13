"""OAuth sign-in for AI-assistant connectors: DCR, PKCE, codes, refresh rotation."""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_oauth_server")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import api_keys  # noqa: E402
import oauth_server as oauth  # noqa: E402
import server  # noqa: E402
from tests.mongo_mocks import FakeCollection  # noqa: E402

CLAUDE_CB = "https://claude.ai/api/mcp/auth_callback"
RESOURCE = "https://trenston-mcp.onrender.com/mcp"
VERIFIER = "v" * 64


def run(coro):
    return asyncio.run(coro)


class _DB(SimpleNamespace):
    def __getitem__(self, name):
        return getattr(self, name)


def make_db():
    return _DB(**{name: FakeCollection() for name in (
        "api_keys", "oauth_clients", "oauth_codes", "oauth_grants", "users", "memberships",
        "workspaces", "user_sessions", "api_rate_buckets", "oauth_register_buckets",
    )})


def auth_params(client_id, redirect=CLAUDE_CB, **over):
    p = {
        "client_id": client_id, "redirect_uri": redirect, "response_type": "code",
        "code_challenge": oauth.pkce_challenge(VERIFIER), "code_challenge_method": "S256",
        "state": "st123", "scope": "trenston.read", "resource": RESOURCE,
    }
    p.update(over)
    return p


def full_flow(db, redirect=CLAUDE_CB):
    if not db.memberships.docs:
        db.memberships.docs.append({"user_id": "u1", "workspace_id": "ws1", "role": "owner", "status": "active"})
    client = run(oauth.register_client(db, {"client_name": "Claude", "redirect_uris": [CLAUDE_CB, "http://localhost/callback"]}))
    req = run(oauth.validate_authorize_request(db, auth_params(client["client_id"], redirect), allowed_resources=[RESOURCE]))
    code = run(oauth.create_code(db, req, user_id="u1", workspace_id="ws1"))
    return client, code


# ---------------------------------------------------------------- metadata & registration

def test_metadata_advertises_what_claude_needs():
    m = oauth.authorization_server_metadata("https://www.trenston.com/")
    assert m["issuer"] == "https://www.trenston.com"
    assert m["registration_endpoint"] == "https://www.trenston.com/api/oauth/register"
    assert m["token_endpoint"] == "https://www.trenston.com/api/oauth/token"
    assert m["code_challenge_methods_supported"] == ["S256"]
    assert m["token_endpoint_auth_methods_supported"] == ["none"]
    assert "offline_access" in m["scopes_supported"]


def test_register_accepts_claude_and_loopback_and_rejects_bad_uris():
    db = make_db()
    c = run(oauth.register_client(db, {"client_name": "Claude", "redirect_uris": [CLAUDE_CB, "http://127.0.0.1/callback"]}))
    assert c["client_id"].startswith("tcl_") and c["token_endpoint_auth_method"] == "none"
    for bad in (["http://evil.example/cb"], ["https://x.example/cb#frag"], [], ["javascript:alert(1)"]):
        with pytest.raises(oauth.OAuthError):
            run(oauth.register_client(db, {"redirect_uris": bad}))
    with pytest.raises(oauth.OAuthError):
        run(oauth.register_client(db, {"redirect_uris": [CLAUDE_CB], "token_endpoint_auth_method": "client_secret_basic"}))


def test_loopback_redirect_ignores_port_but_https_is_exact():
    reg = ["http://localhost/callback", CLAUDE_CB]
    assert oauth.redirect_uri_matches(reg, "http://localhost:3118/callback")
    assert not oauth.redirect_uri_matches(reg, "http://localhost:3118/other")
    assert not oauth.redirect_uri_matches(reg, "http://127.0.0.1:3118/callback")
    assert oauth.redirect_uri_matches(reg, CLAUDE_CB)
    assert not oauth.redirect_uri_matches(reg, CLAUDE_CB + "x")
    assert not oauth.redirect_uri_matches(reg, "https://evil.example/api/mcp/auth_callback")


def test_pkce_s256():
    assert oauth.pkce_verify(VERIFIER, oauth.pkce_challenge(VERIFIER))
    assert not oauth.pkce_verify("w" * 64, oauth.pkce_challenge(VERIFIER))
    assert not oauth.pkce_verify("short", oauth.pkce_challenge("short"))


# ---------------------------------------------------------------- authorize validation

def test_authorize_requires_pkce_and_registered_redirect_and_our_resource():
    db = make_db()
    c = run(oauth.register_client(db, {"redirect_uris": [CLAUDE_CB]}))
    ok = run(oauth.validate_authorize_request(db, auth_params(c["client_id"]), allowed_resources=[RESOURCE]))
    assert ok["redirect_host"] == "claude.ai" and ok["loopback"] is False
    for over in (
        {"code_challenge": ""},
        {"code_challenge_method": "plain"},
        {"redirect_uri": "https://evil.example/cb"},
        {"response_type": "token"},
        {"resource": "https://other.example/mcp"},
        {"scope": "trenston.write"},
        {"client_id": "tcl_unknown"},
    ):
        params = {**auth_params(c["client_id"]), **over}
        with pytest.raises(oauth.OAuthError):
            run(oauth.validate_authorize_request(db, params, allowed_resources=[RESOURCE]))


# ---------------------------------------------------------------- code exchange

def test_code_exchange_issues_tokens_that_resolve_as_read_only_api_tokens():
    db = make_db()
    client, code = full_flow(db)
    tok = run(oauth.exchange_code(db, {"code": code, "client_id": client["client_id"], "redirect_uri": CLAUDE_CB, "code_verifier": VERIFIER}))
    assert tok["token_type"] == "Bearer" and 0 < tok["expires_in"] <= 30 * 24 * 3600
    assert tok["refresh_token"] and tok["access_token"].startswith("trn_")
    doc = run(api_keys.resolve(db, tok["access_token"]))
    assert doc["user_id"] == "u1" and doc["workspace_id"] == "ws1" and doc["kind"] == "oauth"
    # OAuth tokens never show up as personal keys.
    assert run(api_keys.list_keys(db, user_id="u1", workspace_id="ws1")) == []


def test_code_is_single_use():
    db = make_db()
    client, code = full_flow(db)
    form = {"code": code, "client_id": client["client_id"], "redirect_uri": CLAUDE_CB, "code_verifier": VERIFIER}
    run(oauth.exchange_code(db, form))
    with pytest.raises(oauth.OAuthError) as e:
        run(oauth.exchange_code(db, form))
    assert e.value.error == "invalid_grant"


@pytest.mark.parametrize("over", [
    {"code_verifier": "w" * 64},
    {"redirect_uri": "http://localhost:9/callback"},
    {"client_id": "tcl_other"},
    {"code": "not-a-code"},
])
def test_code_exchange_rejects_mismatches(over):
    db = make_db()
    client, code = full_flow(db)
    form = {"code": code, "client_id": client["client_id"], "redirect_uri": CLAUDE_CB, "code_verifier": VERIFIER, **over}
    with pytest.raises(oauth.OAuthError) as e:
        run(oauth.exchange_code(db, form))
    assert e.value.error == "invalid_grant"


def test_expired_code_rejected():
    db = make_db()
    client, code = full_flow(db)
    later = datetime.now(timezone.utc) + timedelta(minutes=11)
    with pytest.raises(oauth.OAuthError):
        run(oauth.exchange_code(db, {"code": code, "client_id": client["client_id"], "redirect_uri": CLAUDE_CB, "code_verifier": VERIFIER}, now=later))


def test_loopback_flow_for_claude_code():
    db = make_db()
    client, code = full_flow(db, redirect="http://localhost:53682/callback")
    tok = run(oauth.exchange_code(db, {"code": code, "client_id": client["client_id"], "redirect_uri": "http://localhost:53682/callback", "code_verifier": VERIFIER}))
    assert tok["access_token"]


# ---------------------------------------------------------------- refresh & revoke

def _tokens(db):
    client, code = full_flow(db)
    tok = run(oauth.exchange_code(db, {"code": code, "client_id": client["client_id"], "redirect_uri": CLAUDE_CB, "code_verifier": VERIFIER}))
    return client, tok


def test_refresh_rotates_and_reuse_kills_the_connection():
    db = make_db()
    client, tok = _tokens(db)
    new = run(oauth.refresh_tokens(db, {"refresh_token": tok["refresh_token"], "client_id": client["client_id"]}))
    assert new["refresh_token"] != tok["refresh_token"]
    assert run(api_keys.resolve(db, new["access_token"]))
    # Replayed within the grace window (two refreshes racing): refused, connection kept.
    with pytest.raises(oauth.OAuthError) as e:
        run(oauth.refresh_tokens(db, {"refresh_token": tok["refresh_token"], "client_id": client["client_id"]}))
    assert e.value.error == "invalid_grant"
    assert run(api_keys.resolve(db, new["access_token"]))
    # Replayed later: treated as theft, the whole grant ends.
    later = datetime.now(timezone.utc) + timedelta(minutes=5)
    with pytest.raises(oauth.OAuthError):
        run(oauth.refresh_tokens(db, {"refresh_token": tok["refresh_token"], "client_id": client["client_id"]}, now=later))
    assert run(api_keys.resolve(db, new["access_token"])) is None
    with pytest.raises(oauth.OAuthError):
        run(oauth.refresh_tokens(db, {"refresh_token": new["refresh_token"], "client_id": client["client_id"]}))


def test_refresh_wrong_client_rejected():
    db = make_db()
    _, tok = _tokens(db)
    with pytest.raises(oauth.OAuthError) as e:
        run(oauth.refresh_tokens(db, {"refresh_token": tok["refresh_token"], "client_id": "tcl_x"}))
    assert e.value.error == "invalid_grant"


def test_access_tokens_expire():
    db = make_db()
    _, tok = _tokens(db)
    soon = datetime.now(timezone.utc) + timedelta(days=29)
    assert run(api_keys.resolve(db, tok["access_token"], now=soon)) is not None
    later = datetime.now(timezone.utc) + timedelta(days=31)
    assert run(api_keys.resolve(db, tok["access_token"], now=later)) is None


def test_disconnecting_revokes_tokens_and_refresh():
    db = make_db()
    client, tok = _tokens(db)
    grants = run(oauth.list_grants(db, user_id="u1", workspace_id="ws1"))
    assert [g["client_name"] for g in grants] == ["Claude"]
    assert run(oauth.revoke_grant(db, grant_id=grants[0]["id"], user_id="u2", workspace_id="ws1")) is False
    assert run(oauth.revoke_grant(db, grant_id=grants[0]["id"], user_id="u1", workspace_id="ws1")) is True
    assert run(api_keys.resolve(db, tok["access_token"])) is None
    with pytest.raises(oauth.OAuthError):
        run(oauth.refresh_tokens(db, {"refresh_token": tok["refresh_token"], "client_id": client["client_id"]}))
    assert run(oauth.list_grants(db, user_id="u1", workspace_id="ws1")) == []


# ---------------------------------------------------------------- HTTP endpoints

@pytest.fixture
def http(request):
    plan = getattr(request, "param", "growth")
    db = make_db()
    db.workspaces.docs.append({"workspace_id": "ws1", "name": "Acme", "plan": plan})
    db.memberships.docs.append({"user_id": "u1", "workspace_id": "ws1", "role": "owner", "status": "active"})

    async def principal():
        return {"user_id": "u1", "name": "Owner", "email": "o@x.com", "workspace_id": "ws1", "pack": "owner", "role": "owner"}

    server.app.dependency_overrides[server.get_principal] = principal
    with patch.object(server, "db", db), patch.object(server, "BILLING_ENFORCED", True), \
            patch.object(server.doc_rate_limit, "_acquire_window_bucket", AsyncMock(return_value=True)), \
            patch.object(server, "log_activity", AsyncMock()), \
            patch.object(server, "MCP_RESOURCE_URLS", [RESOURCE]):
        yield SimpleNamespace(client=TestClient(server.app), db=db)
    server.app.dependency_overrides.clear()


def test_http_metadata_and_registration(http):
    m = http.client.get("/api/oauth/metadata").json()
    assert m["issuer"] == server.TRENSTON_CANONICAL_ORIGIN.rstrip("/")
    r = http.client.post("/api/oauth/register", json={"client_name": "Claude", "redirect_uris": [CLAUDE_CB]})
    assert r.status_code == 201, r.text
    assert r.headers["cache-control"] == "no-store"
    bad = http.client.post("/api/oauth/register", json={"redirect_uris": ["http://evil.example/cb"]})
    assert bad.status_code == 400 and bad.json()["error"] == "invalid_redirect_uri"


def test_http_full_flow_approve_then_token_then_api(http):
    cid = http.client.post("/api/oauth/register", json={"client_name": "Claude", "redirect_uris": [CLAUDE_CB]}).json()["client_id"]
    params = auth_params(cid)
    info = http.client.get("/api/oauth/authorize/info", params=params).json()
    assert info["client_name"] == "Claude" and info["redirect_host"] == "claude.ai"
    assert info["workspace"]["name"] == "Acme" and info["allowed"] is True
    redirect = http.client.post("/api/oauth/authorize", json={**params, "decision": "approve"}).json()["redirect"]
    q = parse_qs(urlsplit(redirect).query)
    assert redirect.startswith(CLAUDE_CB) and q["state"] == ["st123"] and q["code"]
    tok = http.client.post("/api/oauth/token", data={
        "grant_type": "authorization_code", "code": q["code"][0], "client_id": cid,
        "redirect_uri": CLAUDE_CB, "code_verifier": VERIFIER,
    })
    assert tok.status_code == 200, tok.text
    assert tok.headers["cache-control"] == "no-store"
    access = tok.json()["access_token"]
    http.db.users.docs.append({"user_id": "u1", "email": "o@x.com", "name": "Owner"})
    me = http.client.get("/api/v1/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200, me.text
    assert me.json()["workspace"]["id"] == "ws1"


def test_http_deny_redirects_with_access_denied(http):
    cid = http.client.post("/api/oauth/register", json={"redirect_uris": [CLAUDE_CB]}).json()["client_id"]
    redirect = http.client.post("/api/oauth/authorize", json={**auth_params(cid), "decision": "deny"}).json()["redirect"]
    q = parse_qs(urlsplit(redirect).query)
    assert q["error"] == ["access_denied"] and "code" not in q


def test_http_bad_redirect_never_redirects(http):
    cid = http.client.post("/api/oauth/register", json={"redirect_uris": [CLAUDE_CB]}).json()["client_id"]
    r = http.client.post("/api/oauth/authorize", json={**auth_params(cid, redirect="https://evil.example/cb"), "decision": "deny"})
    assert r.status_code == 400 and "redirect" not in r.json()


@pytest.mark.parametrize("http", ["starter"], indirect=True)
def test_http_plan_gate_on_approve(http):
    cid = http.client.post("/api/oauth/register", json={"redirect_uris": [CLAUDE_CB]}).json()["client_id"]
    info = http.client.get("/api/oauth/authorize/info", params=auth_params(cid)).json()
    assert info["allowed"] is False and info["plan_message"]
    r = http.client.post("/api/oauth/authorize", json={**auth_params(cid), "decision": "approve"})
    assert r.status_code == 403


def test_http_token_errors_are_rfc6749(http):
    r = http.client.post("/api/oauth/token", data={"grant_type": "authorization_code", "code": "nope"})
    assert r.status_code == 400 and r.json()["error"] == "invalid_grant"
    r = http.client.post("/api/oauth/token", data={"grant_type": "password"})
    assert r.json()["error"] == "unsupported_grant_type"
    r = http.client.post("/api/oauth/token", data={"grant_type": "refresh_token", "refresh_token": "nope", "client_id": "x"})
    assert r.json()["error"] == "invalid_grant"


def test_http_grants_list_and_disconnect(http):
    cid = http.client.post("/api/oauth/register", json={"client_name": "Claude", "redirect_uris": [CLAUDE_CB]}).json()["client_id"]
    params = auth_params(cid)
    redirect = http.client.post("/api/oauth/authorize", json={**params, "decision": "approve"}).json()["redirect"]
    code = parse_qs(urlsplit(redirect).query)["code"][0]
    http.client.post("/api/oauth/token", data={"grant_type": "authorization_code", "code": code, "client_id": cid, "redirect_uri": CLAUDE_CB, "code_verifier": VERIFIER})
    grants = http.client.get("/api/oauth/grants").json()["grants"]
    assert [g["client_name"] for g in grants] == ["Claude"]
    assert http.client.delete(f"/api/oauth/grants/{grants[0]['id']}").status_code == 200
    assert http.client.get("/api/oauth/grants").json()["grants"] == []
    assert http.client.delete(f"/api/oauth/grants/{grants[0]['id']}").status_code == 404
