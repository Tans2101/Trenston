"""HTTP wrapper for the hosted MCP server: OAuth discovery and the 401 handshake.

Claude's connector client needs two things from a protected MCP server:

1. Unauthenticated (or expired) requests to the MCP endpoint get ``401`` with
   ``WWW-Authenticate: Bearer resource_metadata="<url>"``. That starts sign-in
   for a new connection and a token refresh for an existing one.
2. The RFC 9728 protected-resource metadata at that URL names Trenston's
   authorization server, whose ``resource`` equals the MCP URL exactly.

A presented token is checked against Trenston's ``/api/v1/me`` (cached briefly)
so an expired or revoked token gets a real ``401`` instead of a tool error.
Personal API keys (Claude Code ``--header``) pass the same check.
"""
from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from typing import Optional

import httpx

from trenston_mcp.server import api_base, key_from_headers

SCOPE = "trenston.read"
VALID_CACHE_SECONDS = 60
MAX_CACHE_ENTRIES = 2048

# Returns an HTTP status from Trenston for this token (200 valid, 401 invalid, ...).
TokenChecker = Callable[[str], Awaitable[int]]


def _origin(url: str) -> str:
    parts = httpx.URL(url)
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{parts.host}{port}"


def protected_resource_metadata(public_url: str, issuer: str) -> dict:
    return {
        "resource": public_url,
        "authorization_servers": [issuer.rstrip("/")],
        "scopes_supported": [SCOPE],
        "bearer_methods_supported": ["header"],
        "resource_name": "Trenston",
        "resource_documentation": "https://github.com/Tans2101/Trenston/tree/main/mcp-server",
    }


def default_checker(transport: Optional[httpx.AsyncBaseTransport] = None) -> TokenChecker:
    async def check(token: str) -> int:
        try:
            async with httpx.AsyncClient(base_url=api_base(), timeout=8.0, transport=transport) as client:
                r = await client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
            return r.status_code
        except httpx.HTTPError:
            return 503
    return check


class OAuthGate:
    """ASGI middleware in front of the MCP app."""

    def __init__(self, app, *, public_url: str, issuer: str, mcp_path: str = "/mcp", checker: Optional[TokenChecker] = None):
        self.app = app
        self.public_url = public_url
        self.issuer = issuer
        self.mcp_path = mcp_path.rstrip("/") or "/mcp"
        self.metadata_url = f"{_origin(public_url)}/.well-known/oauth-protected-resource"
        self.metadata = protected_resource_metadata(public_url, issuer)
        self.checker = checker or default_checker()
        self._valid: dict[str, float] = {}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path") or "/"
        if path in ("/.well-known/oauth-protected-resource", f"/.well-known/oauth-protected-resource{self.mcp_path}"):
            await self._json(send, 200, self.metadata, extra=[(b"cache-control", b"public, max-age=300")])
            return
        if path.rstrip("/") == self.mcp_path and scope.get("method") != "OPTIONS":
            headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope.get("headers") or []}
            token = key_from_headers(headers)
            if not token:
                await self._unauthorized(send, None)
                return
            if not await self._token_ok(token):
                await self._unauthorized(send, "invalid_token")
                return
        await self.app(scope, receive, send)

    async def _token_ok(self, token: str) -> bool:
        key = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = time.monotonic()
        if self._valid.get(key, 0) > now:
            return True
        status = await self.checker(token)
        if status == 401:
            self._valid.pop(key, None)
            return False
        # 200 is valid. 403 (plan), 429 and outages are let through so the tool
        # call can explain the problem instead of looping the sign-in flow.
        if status == 200:
            if len(self._valid) >= MAX_CACHE_ENTRIES:
                self._valid.clear()
            self._valid[key] = now + VALID_CACHE_SECONDS
        return True

    async def _unauthorized(self, send, error: Optional[str]):
        value = f'Bearer resource_metadata="{self.metadata_url}", scope="{SCOPE}"'
        if error:
            value += f', error="{error}"'
        await self._json(
            send, 401,
            {"error": error or "unauthorized", "error_description": "Sign in to Trenston to use this connector."},
            extra=[(b"www-authenticate", value.encode("latin-1"))],
        )

    @staticmethod
    async def _json(send, status: int, body: dict, extra: Optional[list] = None):
        payload = json.dumps(body).encode("utf-8")
        headers = [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())]
        headers += extra or []
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": payload})
