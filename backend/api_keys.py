"""Personal API keys for the read-only public API (/api/v1) and the MCP server.

A key belongs to one user in one workspace. It never carries permissions of its
own: every request re-resolves the user's current membership, so a key can only
ever read what that person could read in the app right now. Removing someone
from the workspace, deleting their account, or revoking the key ends access on
the next request.

Only a SHA-256 hash of each key is stored. The raw key is shown once, at
creation, and cannot be recovered afterwards. Keys are 256-bit random tokens,
so a fast hash is appropriate (no password-style stretching needed).
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

KEY_PREFIX = "trn_"
# token_urlsafe(32) -> 43 chars; prefix + body. Anything shorter is not a key.
MIN_KEY_LENGTH = len(KEY_PREFIX) + 40
MAX_ACTIVE_KEYS_PER_USER = 10
NAME_MAX_LENGTH = 60
DEFAULT_KEY_NAME = "API key"
# Avoid a Mongo write on every request: refresh last_used_at at most this often.
LAST_USED_WRITE_INTERVAL = timedelta(minutes=5)
# Per-key request budget (requests per window).
RATE_LIMIT_REQUESTS = 60
RATE_LIMIT_WINDOW_SECONDS = 60

COLLECTION = "api_keys"


class ApiKeyLimitError(ValueError):
    """Raised when a user already has the maximum number of active keys."""


def generate_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def hash_key(raw_key: str) -> str:
    return hashlib.sha256((raw_key or "").encode("utf-8")).hexdigest()


def looks_like_api_key(token: Optional[str]) -> bool:
    token = (token or "").strip()
    return token.startswith(KEY_PREFIX) and len(token) >= MIN_KEY_LENGTH


def key_hint(raw_key: str) -> str:
    """Safe-to-display fragment, e.g. ``trn_AbCd…wXyZ``."""
    return f"{raw_key[:8]}…{raw_key[-4:]}"


def normalize_name(name: Optional[str]) -> str:
    cleaned = " ".join(str(name or "").split())
    return cleaned[:NAME_MAX_LENGTH] or DEFAULT_KEY_NAME


def token_from_headers(headers) -> str:
    """Accept ``Authorization: Bearer trn_…`` or ``X-API-Key: trn_…``."""
    auth = (headers.get("Authorization") or headers.get("authorization") or "").strip()
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip()
    return (headers.get("X-API-Key") or headers.get("x-api-key") or "").strip()


def public_view(doc: dict) -> dict:
    """What the Settings UI may see. Never includes the hash or the raw key."""
    return {
        "id": doc.get("id"),
        "name": doc.get("name") or DEFAULT_KEY_NAME,
        "hint": doc.get("hint"),
        "created_at": doc.get("created_at"),
        "last_used_at": doc.get("last_used_at"),
    }


def _active_filter(user_id: str, workspace_id: str) -> dict:
    return {"user_id": user_id, "workspace_id": workspace_id, "revoked_at": None}


async def list_keys(db, *, user_id: str, workspace_id: str) -> list[dict]:
    rows = await db[COLLECTION].find(
        _active_filter(user_id, workspace_id), {"_id": 0},
    ).sort("created_at", -1).to_list(MAX_ACTIVE_KEYS_PER_USER + 5)
    return [public_view(r) for r in rows]


async def create_key(
    db,
    *,
    user_id: str,
    workspace_id: str,
    name: Optional[str] = None,
    now: Optional[datetime] = None,
) -> tuple[str, dict]:
    """Create a key. Returns ``(raw_key, public_view)``; the raw key is never stored."""
    active = await db[COLLECTION].count_documents(_active_filter(user_id, workspace_id))
    if active >= MAX_ACTIVE_KEYS_PER_USER:
        raise ApiKeyLimitError(
            f"You can have up to {MAX_ACTIVE_KEYS_PER_USER} active API keys. Revoke one to create another."
        )
    now = now or datetime.now(timezone.utc)
    raw = generate_key()
    doc = {
        "id": f"key_{uuid.uuid4().hex[:16]}",
        "user_id": user_id,
        "workspace_id": workspace_id,
        "name": normalize_name(name),
        "key_hash": hash_key(raw),
        "hint": key_hint(raw),
        "created_at": now.isoformat(),
        "last_used_at": None,
        "revoked_at": None,
    }
    await db[COLLECTION].insert_one(dict(doc))
    return raw, public_view(doc)


async def revoke_key(
    db,
    *,
    key_id: str,
    user_id: str,
    workspace_id: str,
    now: Optional[datetime] = None,
) -> bool:
    """Revoke one of the caller's own keys. False when no such active key exists."""
    now = now or datetime.now(timezone.utc)
    res = await db[COLLECTION].update_one(
        {"id": key_id, **_active_filter(user_id, workspace_id)},
        {"$set": {"revoked_at": now.isoformat()}},
    )
    return bool(getattr(res, "matched_count", 0))


async def revoke_all_for_user(db, *, user_id: str, workspace_id: Optional[str] = None) -> None:
    flt = {"user_id": user_id, "revoked_at": None}
    if workspace_id:
        flt["workspace_id"] = workspace_id
    await db[COLLECTION].update_many(
        flt, {"$set": {"revoked_at": datetime.now(timezone.utc).isoformat()}},
    )


async def resolve(db, raw_key: str) -> Optional[dict]:
    """Return the active key document for a raw key, or None."""
    if not looks_like_api_key(raw_key):
        return None
    doc = await db[COLLECTION].find_one(
        {"key_hash": hash_key(raw_key.strip()), "revoked_at": None}, {"_id": 0},
    )
    return doc or None


def _parse_ts(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def needs_touch(doc: dict, now: datetime) -> bool:
    last = _parse_ts(doc.get("last_used_at"))
    return last is None or now - last >= LAST_USED_WRITE_INTERVAL


async def touch(db, doc: dict, now: Optional[datetime] = None) -> None:
    now = now or datetime.now(timezone.utc)
    if not needs_touch(doc, now):
        return
    await db[COLLECTION].update_one(
        {"id": doc.get("id")}, {"$set": {"last_used_at": now.isoformat()}},
    )
