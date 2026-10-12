"""Trenston MCP server tests. Trenston's API is stubbed with httpx.MockTransport."""
from __future__ import annotations

import json

import httpx
import pytest
from mcp import Client

from trenston_mcp.server import build_server, key_from_headers, resolve_api_key

KEY = "trn_" + "a" * 43
OTHER_KEY = "trn_" + "b" * 43


def stub(routes: dict[str, tuple[int, dict]], seen: list):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        status, body = routes.get(path, (404, {"detail": "Not Found"}))
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


ROUTES = {
    "/api/v1/me": (200, {"workspace": {"id": "ws1", "name": "Acme"}, "read_only": True}),
    "/api/v1/briefing": (200, {"headline": "Revenue up"}),
    "/api/v1/decisions": (200, {"decisions": [{"id": "d1", "title": "Hire"}], "suggestions": []}),
    "/api/v1/tasks": (200, {"tasks": []}),
    "/api/v1/my-work": (200, {"items": []}),
    "/api/v1/financials": (403, {"detail": "You don't have access to financial data in this workspace."}),
}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("TRENSTON_API_BASE", "https://example.test/api")
    monkeypatch.setenv("TRENSTON_API_KEY", KEY)


def payload(result) -> dict:
    if getattr(result, "structured_content", None):
        return result.structured_content
    return json.loads(result.content[0].text)


async def test_exposes_only_read_only_tools():
    async with Client(build_server(transport=stub(ROUTES, []))) as client:
        tools = (await client.list_tools()).tools
    names = {t.name for t in tools}
    assert names == {"get_me", "get_briefing", "list_decisions", "list_tasks", "get_my_work", "get_financials"}
    for t in tools:
        assert t.annotations.read_only_hint is True
        assert t.annotations.destructive_hint is False


async def test_tool_calls_forward_the_key_to_the_v1_api():
    seen: list[httpx.Request] = []
    async with Client(build_server(transport=stub(ROUTES, seen))) as client:
        result = await client.call_tool("list_decisions", {})
    assert not result.is_error
    assert payload(result)["decisions"][0]["title"] == "Hire"
    assert seen[0].url.path == "/api/v1/decisions"
    assert seen[0].method == "GET"
    assert seen[0].headers["authorization"] == f"Bearer {KEY}"


async def test_permission_errors_reach_the_model_as_plain_messages():
    async with Client(build_server(transport=stub(ROUTES, []))) as client:
        result = await client.call_tool("get_financials", {})
    assert result.is_error
    assert "financial data" in result.content[0].text


async def test_missing_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("TRENSTON_API_KEY")
    seen: list = []
    async with Client(build_server(transport=stub(ROUTES, seen))) as client:
        result = await client.call_tool("get_me", {})
    assert result.is_error
    assert "API key" in result.content[0].text
    assert seen == []  # never calls Trenston without a key


def test_key_from_headers_variants():
    assert key_from_headers({"Authorization": f"Bearer {KEY}"}) == KEY
    assert key_from_headers({"authorization": f"bearer {KEY}"}) == KEY
    assert key_from_headers({"X-API-Key": KEY}) == KEY
    assert key_from_headers(None) == ""


def test_http_mode_never_falls_back_to_the_server_env_key():
    # A hosted server must only ever use the caller's own key.
    assert resolve_api_key({}, http_mode=True) == ""
    assert resolve_api_key({"Authorization": f"Bearer {OTHER_KEY}"}, http_mode=True) == OTHER_KEY
    assert resolve_api_key({}, http_mode=False) == KEY


async def test_http_mode_without_header_refuses():
    seen: list = []
    async with Client(build_server(http_mode=True, transport=stub(ROUTES, seen))) as client:
        result = await client.call_tool("get_me", {})
    assert result.is_error
    assert seen == []
