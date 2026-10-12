"""OAuth discovery and the 401 handshake Claude needs before it will sign in."""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from trenston_mcp.__main__ import build_http_app

GOOD = "trn_" + "g" * 43
BAD = "trn_" + "b" * 43
LIMITED = "trn_" + "p" * 43


@pytest.fixture
def calls():
    return []


@pytest.fixture
def client(monkeypatch, calls):
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://trenston-mcp.onrender.com/mcp")
    monkeypatch.setenv("TRENSTON_ISSUER", "https://www.trenston.com")
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "testserver")

    async def checker(token):
        calls.append(token)
        return {GOOD: 200, LIMITED: 403}.get(token, 401)

    app = build_http_app(port=8000, checker=checker)
    with TestClient(app) as c:
        yield c


INIT = {
    "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {},
}
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def test_protected_resource_metadata(client):
    for path in ("/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp"):
        r = client.get(path)
        assert r.status_code == 200
        body = r.json()
        assert body["resource"] == "https://trenston-mcp.onrender.com/mcp"
        assert body["authorization_servers"] == ["https://www.trenston.com"]


def test_no_token_gets_401_with_resource_metadata_pointer(client):
    r = client.post("/mcp", json=INIT, headers=HEADERS)
    assert r.status_code == 401
    www = r.headers["www-authenticate"]
    assert www.startswith("Bearer ")
    assert 'resource_metadata="https://trenston-mcp.onrender.com/.well-known/oauth-protected-resource"' in www
    assert 'scope="trenston.read"' in www


def test_invalid_or_expired_token_gets_401_invalid_token(client):
    r = client.post("/mcp", json=INIT, headers={**HEADERS, "Authorization": f"Bearer {BAD}"})
    assert r.status_code == 401
    assert 'error="invalid_token"' in r.headers["www-authenticate"]


def test_valid_token_reaches_mcp_and_is_cached(client, calls):
    for _ in range(3):
        r = client.post("/mcp", json=INIT, headers={**HEADERS, "Authorization": f"Bearer {GOOD}"})
        assert r.status_code == 200, r.text
        assert "get_briefing" in r.text
    assert calls.count(GOOD) == 1


def test_plan_limited_token_is_let_through_so_tools_can_explain(client):
    r = client.post("/mcp", json=INIT, headers={**HEADERS, "Authorization": f"Bearer {LIMITED}"})
    assert r.status_code != 401


def test_personal_key_header_still_works(client):
    r = client.post("/mcp", json=INIT, headers={**HEADERS, "X-API-Key": GOOD})
    assert r.status_code == 200
