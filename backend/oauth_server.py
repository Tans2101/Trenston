"""OAuth 2.1 authorization server for AI-assistant connectors (MCP).

Lets a person connect Trenston to an assistant such as Claude by signing in and
approving access, instead of pasting an API key. Implements what Claude's
connector client requires:

- RFC 8414 authorization server metadata (served at
  https://www.trenston.com/.well-known/oauth-authorization-server)
- RFC 7591 Dynamic Client Registration (public clients, no secret)
- Authorization code grant with mandatory S256 PKCE
- 30-day access tokens with rotating refresh tokens (reuse revokes the grant)
- Redirect URIs: exact match, except loopback (localhost / 127.0.0.1) where the
  port is ignored, per RFC 8252, for native clients such as Claude Code

Access tokens are minted as read-only API tokens (see api_keys.py), so the
public API and every permission check treat them exactly like a personal key.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlencode, urlsplit, urlunsplit

import api_keys

SCOPE = "trenston.read"
SUPPORTED_SCOPES = (SCOPE, "offline_access")
# 30 days: assistants that mishandle refresh (or refresh in parallel from several
# devices) used to drop the connection every hour. Still read-only, hashed, rate
# limited, and revoked instantly by Disconnect or by leaving the workspace.
ACCESS_TOKEN_TTL = timedelta(days=30)
REFRESH_TOKEN_TTL = timedelta(days=90)
CODE_TTL = timedelta(minutes=10)
MAX_REDIRECT_URIS = 5
CLIENT_NAME_MAX = 80
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}
# A rotated-out refresh token presented again within this window is treated as a
# harmless race (two refreshes at once), not theft: refused, but the grant survives.
REFRESH_REUSE_GRACE = timedelta(seconds=60)
# Redirects we can vouch for. Any other app is shown as unverified on the consent screen.
VERIFIED_REDIRECTS = {"https://claude.ai/api/mcp/auth_callback": "Claude"}

CLIENTS = "oauth_clients"
CODES = "oauth_codes"
GRANTS = "oauth_grants"


class OAuthError(Exception):
    """An RFC 6749 / 7591 error response."""

    def __init__(self, error: str, description: str = "", status: int = 400):
        super().__init__(description or error)
        self.error = error
        self.description = description
        self.status = status

    def body(self) -> dict:
        out = {"error": self.error}
        if self.description:
            out["error_description"] = self.description
        return out


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _parse_ts(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ------------------------------------------------------------------ metadata

def authorization_server_metadata(issuer: str) -> dict:
    issuer = issuer.rstrip("/")
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/app/oauth/authorize",
        "token_endpoint": f"{issuer}/api/oauth/token",
        "registration_endpoint": f"{issuer}/api/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": list(SUPPORTED_SCOPES),
        "service_documentation": f"{issuer}/integrations",
    }


# ------------------------------------------------------------------ redirect URIs

def _is_loopback(parts) -> bool:
    return parts.scheme == "http" and (parts.hostname or "").lower() in LOOPBACK_HOSTS


def redirect_uri_registrable(uri: str) -> bool:
    """HTTPS anywhere, or plain-HTTP loopback for native apps. No fragments, no userinfo."""
    try:
        parts = urlsplit(uri or "")
    except ValueError:
        return False
    if parts.fragment or parts.username or parts.password or not parts.hostname:
        return False
    if parts.scheme == "https":
        return True
    return _is_loopback(parts)


def _without_port(parts) -> tuple:
    host = (parts.hostname or "").lower()
    return (parts.scheme, host, parts.path or "/", parts.query)


def redirect_uri_matches(registered: list[str], given: str) -> bool:
    if not given:
        return False
    if given in (registered or []):
        return True
    try:
        g = urlsplit(given)
    except ValueError:
        return False
    if not _is_loopback(g):
        return False
    for r in registered or []:
        try:
            rp = urlsplit(r)
        except ValueError:
            continue
        if _is_loopback(rp) and _without_port(rp) == _without_port(g):
            return True
    return False


def redirect_with_params(redirect_uri: str, params: dict) -> str:
    parts = urlsplit(redirect_uri)
    extra = urlencode({k: v for k, v in params.items() if v is not None})
    query = f"{parts.query}&{extra}" if parts.query else extra
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


# ------------------------------------------------------------------ PKCE

def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256((verifier or "").encode("ascii", "ignore")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def pkce_verify(verifier: str, challenge: str) -> bool:
    if not verifier or not challenge or not (43 <= len(verifier) <= 128):
        return False
    return secrets.compare_digest(pkce_challenge(verifier), challenge)


# ------------------------------------------------------------------ clients (DCR)

async def register_client(db, body: dict, *, now: Optional[datetime] = None) -> dict:
    if not isinstance(body, dict):
        raise OAuthError("invalid_client_metadata", "Body must be a JSON object.")
    uris = body.get("redirect_uris")
    if not isinstance(uris, list) or not uris or len(uris) > MAX_REDIRECT_URIS:
        raise OAuthError("invalid_redirect_uri", f"Provide 1 to {MAX_REDIRECT_URIS} redirect_uris.")
    for uri in uris:
        if not isinstance(uri, str) or not redirect_uri_registrable(uri):
            raise OAuthError("invalid_redirect_uri", "Redirect URIs must be HTTPS or a loopback address.")
    auth_method = body.get("token_endpoint_auth_method") or "none"
    if auth_method != "none":
        raise OAuthError("invalid_client_metadata", "Only public clients (token_endpoint_auth_method 'none') are supported.")
    grant_types = body.get("grant_types") or ["authorization_code", "refresh_token"]
    if not set(grant_types) <= {"authorization_code", "refresh_token"}:
        raise OAuthError("invalid_client_metadata", "Unsupported grant_types.")
    response_types = body.get("response_types") or ["code"]
    if response_types != ["code"]:
        raise OAuthError("invalid_client_metadata", "Only response_types ['code'] is supported.")
    name = " ".join(str(body.get("client_name") or "AI assistant").split())[:CLIENT_NAME_MAX] or "AI assistant"
    now = now or _now()
    client = {
        "client_id": f"tcl_{secrets.token_urlsafe(18)}",
        "client_name": name,
        "redirect_uris": list(uris),
        "grant_types": list(grant_types),
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "created_at": now.isoformat(),
    }
    await db[CLIENTS].insert_one(dict(client))
    return {
        **{k: client[k] for k in ("client_id", "client_name", "redirect_uris", "grant_types", "response_types", "token_endpoint_auth_method")},
        "client_id_issued_at": int(now.timestamp()),
    }


async def get_client(db, client_id: str) -> Optional[dict]:
    if not client_id:
        return None
    return await db[CLIENTS].find_one({"client_id": client_id}, {"_id": 0})


# ------------------------------------------------------------------ authorize

async def validate_authorize_request(db, params: dict, *, allowed_resources: list[str]) -> dict:
    """Check an authorization request. Raises OAuthError; never redirects to an unverified URI."""
    client = await get_client(db, params.get("client_id") or "")
    if not client:
        raise OAuthError("invalid_client", "Unknown client. Remove the connector and add it again.")
    redirect_uri = params.get("redirect_uri") or ""
    if not redirect_uri_matches(client.get("redirect_uris") or [], redirect_uri):
        raise OAuthError("invalid_request", "This redirect address is not registered for the app.")
    if (params.get("response_type") or "") != "code":
        raise OAuthError("unsupported_response_type", "Only response_type=code is supported.")
    challenge = params.get("code_challenge") or ""
    if not challenge or (params.get("code_challenge_method") or "") != "S256":
        raise OAuthError("invalid_request", "PKCE with code_challenge_method=S256 is required.")
    resource = (params.get("resource") or "").strip() or None
    if resource and allowed_resources and resource.rstrip("/") not in {r.rstrip("/") for r in allowed_resources}:
        raise OAuthError("invalid_target", "This sign-in is for a different server.")
    scopes = [s for s in (params.get("scope") or SCOPE).split() if s]
    unknown = [s for s in scopes if s not in SUPPORTED_SCOPES]
    if unknown:
        raise OAuthError("invalid_scope", f"Unsupported scope: {' '.join(unknown)}")
    return {
        "client": client,
        "redirect_uri": redirect_uri,
        "code_challenge": challenge,
        "state": params.get("state"),
        "scope": " ".join(sorted(set(scopes) | {SCOPE})),
        "resource": resource,
        "redirect_host": urlsplit(redirect_uri).hostname or "",
        "loopback": _is_loopback(urlsplit(redirect_uri)),
        "verified_as": VERIFIED_REDIRECTS.get(redirect_uri),
    }


async def create_code(db, req: dict, *, user_id: str, workspace_id: str, now: Optional[datetime] = None) -> str:
    now = now or _now()
    raw = secrets.token_urlsafe(32)
    await db[CODES].insert_one({
        "code_hash": _hash(raw),
        "client_id": req["client"]["client_id"],
        "redirect_uri": req["redirect_uri"],
        "code_challenge": req["code_challenge"],
        "scope": req["scope"],
        "resource": req.get("resource"),
        "user_id": user_id,
        "workspace_id": workspace_id,
        "expires_at": (now + CODE_TTL).isoformat(),
        "expire_at": now + CODE_TTL + timedelta(days=1),  # TTL cleanup
        "used": False,
        "created_at": now.isoformat(),
    })
    return raw


# ------------------------------------------------------------------ tokens

def _token_response(access: str, expires_at: datetime, refresh: str, scope: str, now: datetime) -> dict:
    return {
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": max(1, int((expires_at - now).total_seconds())),
        "refresh_token": refresh,
        "scope": scope,
    }


async def _issue(db, grant: dict, now: datetime) -> tuple[str, datetime]:
    return await api_keys.mint_oauth_access_token(
        db,
        user_id=grant["user_id"],
        workspace_id=grant["workspace_id"],
        grant_id=grant["id"],
        client_name=grant.get("client_name") or "AI assistant",
        ttl=ACCESS_TOKEN_TTL,
        now=now,
    )


async def exchange_code(db, form: dict, *, now: Optional[datetime] = None) -> dict:
    now = now or _now()
    raw = form.get("code") or ""
    code = await db[CODES].find_one({"code_hash": _hash(raw)}, {"_id": 0}) if raw else None
    if not code:
        raise OAuthError("invalid_grant", "Authorization code is invalid.")
    # Single use: claim it before anything else so a replay cannot race us.
    claimed = await db[CODES].update_one(
        {"code_hash": code["code_hash"], "used": False}, {"$set": {"used": True, "used_at": now.isoformat()}},
    )
    if not getattr(claimed, "matched_count", 0):
        raise OAuthError("invalid_grant", "Authorization code was already used.")
    expires = _parse_ts(code.get("expires_at"))
    if expires is None or expires <= now:
        raise OAuthError("invalid_grant", "Authorization code has expired.")
    if (form.get("client_id") or "") != code["client_id"]:
        raise OAuthError("invalid_grant", "Authorization code was issued to another client.")
    if (form.get("redirect_uri") or "") != code["redirect_uri"]:
        raise OAuthError("invalid_grant", "redirect_uri does not match the authorization request.")
    if not pkce_verify(form.get("code_verifier") or "", code["code_challenge"]):
        raise OAuthError("invalid_grant", "PKCE verification failed.")
    client = await get_client(db, code["client_id"])
    if not client:
        raise OAuthError("invalid_client", "Unknown client.", status=401)
    refresh = secrets.token_urlsafe(48)
    grant = {
        "id": f"grant_{uuid.uuid4().hex[:16]}",
        "client_id": client["client_id"],
        "client_name": client.get("client_name") or "AI assistant",
        "user_id": code["user_id"],
        "workspace_id": code["workspace_id"],
        "scope": code["scope"],
        "resource": code.get("resource"),
        "refresh_hash": _hash(refresh),
        "previous_refresh_hash": None,
        "refresh_expires_at": (now + REFRESH_TOKEN_TTL).isoformat(),
        "created_at": now.isoformat(),
        "last_used_at": now.isoformat(),
        "revoked_at": None,
    }
    await db[GRANTS].insert_one(dict(grant))
    access, access_exp = await _issue(db, grant, now)
    return _token_response(access, access_exp, refresh, grant["scope"], now)


async def refresh_tokens(db, form: dict, *, now: Optional[datetime] = None) -> dict:
    now = now or _now()
    raw = form.get("refresh_token") or ""
    if not raw:
        raise OAuthError("invalid_request", "refresh_token is required.")
    h = _hash(raw)
    grant = await db[GRANTS].find_one({"refresh_hash": h}, {"_id": 0})
    if not grant:
        reused = await db[GRANTS].find_one({"previous_refresh_hash": h, "revoked_at": None}, {"_id": 0})
        if reused:
            rotated = _parse_ts(reused.get("rotated_at"))
            if rotated is None or now - rotated > REFRESH_REUSE_GRACE:
                # A rotated-out refresh token came back later: assume it leaked and end the grant.
                await revoke_grant(db, grant_id=reused["id"], user_id=reused["user_id"], workspace_id=reused["workspace_id"], now=now)
        raise OAuthError("invalid_grant", "Refresh token is invalid.")
    if grant.get("revoked_at"):
        raise OAuthError("invalid_grant", "This connection was disconnected in Trenston.")
    if (form.get("client_id") or "") != grant["client_id"]:
        raise OAuthError("invalid_grant", "Refresh token was issued to another client.")
    exp = _parse_ts(grant.get("refresh_expires_at"))
    if exp is None or exp <= now:
        raise OAuthError("invalid_grant", "Refresh token has expired. Connect again.")
    member = await db.memberships.find_one(
        {"user_id": grant["user_id"], "workspace_id": grant["workspace_id"], "status": "active"}, {"_id": 0},
    )
    if not member:
        await revoke_grant(db, grant_id=grant["id"], user_id=grant["user_id"], workspace_id=grant["workspace_id"], now=now)
        raise OAuthError("invalid_grant", "This person is no longer a member of the workspace.")
    new_refresh = secrets.token_urlsafe(48)
    res = await db[GRANTS].update_one(
        {"id": grant["id"], "refresh_hash": h, "revoked_at": None},
        {"$set": {
            "refresh_hash": _hash(new_refresh),
            "previous_refresh_hash": h,
            "rotated_at": now.isoformat(),
            "refresh_expires_at": (now + REFRESH_TOKEN_TTL).isoformat(),
            "last_used_at": now.isoformat(),
        }},
    )
    if not getattr(res, "matched_count", 0):
        raise OAuthError("invalid_grant", "Refresh token is invalid.")
    access, access_exp = await _issue(db, grant, now)
    return _token_response(access, access_exp, new_refresh, grant["scope"], now)


# ------------------------------------------------------------------ connected apps

def grant_view(grant: dict) -> dict:
    return {
        "id": grant.get("id"),
        "client_name": grant.get("client_name") or "AI assistant",
        "created_at": grant.get("created_at"),
        "last_used_at": grant.get("last_used_at"),
    }


async def list_grants(db, *, user_id: str, workspace_id: str) -> list[dict]:
    rows = await db[GRANTS].find(
        {"user_id": user_id, "workspace_id": workspace_id, "revoked_at": None}, {"_id": 0},
    ).sort("created_at", -1).to_list(50)
    return [grant_view(g) for g in rows]


async def revoke_grant(db, *, grant_id: str, user_id: str, workspace_id: str, now: Optional[datetime] = None) -> bool:
    now = now or _now()
    res = await db[GRANTS].update_one(
        {"id": grant_id, "user_id": user_id, "workspace_id": workspace_id, "revoked_at": None},
        {"$set": {"revoked_at": now.isoformat()}},
    )
    if not getattr(res, "matched_count", 0):
        return False
    await api_keys.revoke_grant_tokens(db, grant_id, now)
    return True
