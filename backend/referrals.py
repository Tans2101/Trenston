"""CEO-to-CEO referral tracking.

Shareable links only — no discounts, credits, or reward mechanics.
"""
from __future__ import annotations

import re
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

import plans as helm_plans
import product_analytics as helm_analytics

# token_hex(8) → 16 lowercase hex chars (same family as teammate invite_token).
_CODE_RE = re.compile(r"^[a-f0-9]{16}$")
REFERRAL_STATUSES = ("sent", "signed_up", "converted")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_referral_code() -> str:
    """URL-safe token, same hex style as teammate invite_token."""
    return secrets.token_hex(8)


def share_url(app_base: str, code: str) -> str:
    base = (app_base or "").rstrip("/")
    return f"{base}/sign-up?ref={code}"


def _normalize_email(email: str | None) -> str:
    return str(email or "").strip().lower()


def normalize_referral_code(code: str | None) -> str:
    token = str(code or "").strip().lower()
    if not token or not _CODE_RE.match(token):
        return ""
    return token


async def lookup_referrer_by_code(db, code: str):
    token = normalize_referral_code(code)
    if not token:
        return None
    return await db.users.find_one({"referral_code": token}, {"_id": 0})


async def ensure_referral_code(db, user_id: str) -> str:
    """Return a stable per-user referral code, creating one if missing."""
    uid = str(user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=400, detail="Invalid user")
    user = await db.users.find_one({"user_id": uid}, {"_id": 0, "referral_code": 1})
    # A user without a code yet comes back as {} under this projection; only None means missing.
    if user is None:
        # Do not use "User not found" — that reads like invite-email validation in the UI.
        raise HTTPException(status_code=404, detail="Referral profile unavailable")
    existing = str(user.get("referral_code") or "").strip().lower()
    if existing:
        return existing
    for _ in range(8):
        code = generate_referral_code()
        taken = await db.users.find_one({"referral_code": code}, {"_id": 0, "user_id": 1})
        if taken:
            continue
        try:
            result = await db.users.update_one(
                {
                    "user_id": uid,
                    "$or": [
                        {"referral_code": {"$exists": False}},
                        {"referral_code": None},
                        {"referral_code": ""},
                    ],
                },
                {"$set": {"referral_code": code}},
            )
        except DuplicateKeyError:
            continue
        if getattr(result, "modified_count", 0) or getattr(result, "matched_count", 0):
            fresh = await db.users.find_one({"user_id": uid}, {"_id": 0, "referral_code": 1})
            if fresh and fresh.get("referral_code"):
                return str(fresh["referral_code"])
        raced = await db.users.find_one({"user_id": uid}, {"_id": 0, "referral_code": 1})
        if raced and raced.get("referral_code"):
            return str(raced["referral_code"])
    raise HTTPException(status_code=500, detail="Could not allocate referral code")


async def record_sent_invite(db, *, referrer_user_id: str, referrer_workspace_id: str, referred_email: str):
    email = _normalize_email(referred_email)
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="A valid email is required")
    existing = await db.referrals.find_one(
        {
            "referrer_user_id": referrer_user_id,
            "referred_email": email,
            "status": {"$in": ["sent", "signed_up", "converted"]},
        }
    )
    if existing:
        return existing
    doc = {
        "referral_id": f"rfr_{uuid.uuid4().hex[:12]}",
        "referrer_user_id": referrer_user_id,
        "referrer_workspace_id": referrer_workspace_id,
        "referred_email": email,
        "status": "sent",
        "created_at": _now_iso(),
        "converted_at": None,
        "referred_workspace_id": None,
        "referred_user_id": None,
    }
    await db.referrals.insert_one(doc)
    return doc


async def attribute_signup(db, *, referral_code: str | None, new_user: dict, new_workspace: dict):
    """Tag a newly created company workspace if the founder used a referral link."""
    code = normalize_referral_code(referral_code)
    if not code:
        return None
    referrer = await lookup_referrer_by_code(db, code)
    if not referrer:
        return None
    new_uid = new_user.get("user_id")
    new_wid = new_workspace.get("workspace_id")
    if not new_uid or not new_wid:
        return None
    if referrer.get("user_id") == new_uid:
        return None

    referred_email = _normalize_email(new_user.get("email"))
    referrer_ws = referrer.get("active_workspace_id")
    now = _now_iso()

    existing = None
    if referred_email:
        existing = await db.referrals.find_one(
            {
                "referrer_user_id": referrer["user_id"],
                "referred_email": referred_email,
                "status": "sent",
            }
        )

    if existing:
        referral_id = existing.get("referral_id")
        await db.referrals.update_one(
            {"referral_id": referral_id} if referral_id else {"_id": existing["_id"]},
            {
                "$set": {
                    "status": "signed_up",
                    "referred_user_id": new_uid,
                    "referred_workspace_id": new_wid,
                    "referrer_workspace_id": existing.get("referrer_workspace_id") or referrer_ws,
                }
            },
        )
    else:
        referral_id = f"rfr_{uuid.uuid4().hex[:12]}"
        await db.referrals.insert_one(
            {
                "referral_id": referral_id,
                "referrer_user_id": referrer["user_id"],
                "referrer_workspace_id": referrer_ws,
                "referred_email": referred_email,
                "status": "signed_up",
                "created_at": now,
                "converted_at": None,
                "referred_workspace_id": new_wid,
                "referred_user_id": new_uid,
            }
        )

    await db.workspaces.update_one(
        {"workspace_id": new_wid},
        {
            "$set": {
                "referred_by": referrer["user_id"],
                "referred_by_code": code,
                "referral_id": referral_id,
            }
        },
    )
    await helm_analytics.log_event(
        db,
        new_wid,
        new_uid,
        "referral_attributed",
        {
            "referrer_user_id": str(referrer.get("user_id") or ""),
            "referral_id": str(referral_id or ""),
        },
    )
    return referrer


async def mark_referral_converted(db, workspace: dict | None) -> bool:
    """When a referred workspace becomes paid, mark the matching referral converted."""
    if not workspace:
        return False
    query = None
    rid = workspace.get("referral_id")
    if rid:
        query = {"referral_id": rid}
    elif workspace.get("referred_by") and workspace.get("workspace_id"):
        query = {
            "referrer_user_id": workspace["referred_by"],
            "referred_workspace_id": workspace["workspace_id"],
        }
    if not query:
        return False
    rec = await db.referrals.find_one(query)
    if not rec:
        return False
    if rec.get("status") == "converted":
        return False
    await db.referrals.update_one(
        {"referral_id": rec["referral_id"]} if rec.get("referral_id") else {"_id": rec["_id"]},
        {"$set": {"status": "converted", "converted_at": _now_iso()}},
    )
    await helm_analytics.log_event(
        db,
        workspace.get("workspace_id"),
        rec.get("referrer_user_id"),
        "referral_converted",
        {"referral_id": str(rec.get("referral_id") or "")},
    )
    return True


def serialize_referral(doc: dict) -> dict:
    created = doc.get("created_at")
    converted = doc.get("converted_at")
    if hasattr(created, "isoformat"):
        created = created.isoformat()
    if hasattr(converted, "isoformat"):
        converted = converted.isoformat()
    return {
        "id": doc.get("referral_id") or str(doc.get("_id") or ""),
        "referred_email": doc.get("referred_email") or "",
        "status": doc.get("status") if doc.get("status") in REFERRAL_STATUSES else "sent",
        "created_at": created,
        "converted_at": converted,
    }


async def list_referrals_for_user(db, user_id: str) -> list[dict]:
    uid = str(user_id or "").strip()
    if not uid:
        return []
    cursor = db.referrals.find({"referrer_user_id": uid}).sort("created_at", -1).limit(100)
    if hasattr(cursor, "to_list"):
        rows = await cursor.to_list(100)
    else:
        rows = list(cursor)
    return [serialize_referral(r) for r in rows]


def should_mark_converted(subscription_status: str | None, plan: str | None) -> bool:
    """Paid conversion only — trials stay at signed_up. No rewards involved."""
    if (subscription_status or "").lower() != "active":
        return False
    return helm_plans.is_paid_plan(plan)
