import os
import re
import math
import uuid
import json
import html
import hmac
import hashlib
import secrets
import asyncio
import logging
import time
from pathlib import Path
from datetime import date, datetime, timezone, timedelta
from typing import Optional, Any, Literal
from urllib.parse import urlencode, urlparse, quote
from collections import defaultdict

import httpx
import jwt
import resend
from fastapi import FastAPI, APIRouter, Request, Response, HTTPException, Depends, UploadFile, File, Form, Query, BackgroundTasks
from fastapi.responses import StreamingResponse, RedirectResponse, Response, JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr

import llm as helm_llm
import document_cleanup
import rate_limit as doc_rate_limit
import storage as doc_storage
import quickbooks as qb_sync
import xero as xero_sync
import sap_b1 as sap_b1_sync
import hubspot as hubspot_sync
import google_oauth as gcal
import google_document_ai as gcp_docai
import integrations_catalog as integ_catalog
import clerk_auth
import decision_engine
import money_fmt
from money_fmt import fmt_money, normalize_currency, currency_symbol, CURRENCY_SYMBOLS, entered_cash_amount
from pagination import clamp_limit, apply_before_filter, next_cursor
from helm_config import TRENSTON_CANONICAL_ORIGIN, is_stale_deploy_url, public_api_origin, registrable_cookie_domain
from static_frontend import mount_static_frontend, should_serve_static
from seed_data import build_workspace, sample_financial_entries, gen_join_code
from finance_entry import normalize_entry_name, require_entry_name
import access_sections as sec_access
import plans as helm_plans
import plan_usage
import simple_cache
import retention as helm_retention
import product_analytics as helm_analytics
import referrals as helm_referrals
import department_report_drafts as helm_dept_drafts
import departments_catalog as dept_catalog
import department_access as dept_access
import credential_crypto as cred_crypto
import department_migrate as dept_migrate
import work_items as helm_work_items
import data_freshness as helm_freshness
import procurement_metrics as proc_metrics
import production_daily_logs as prod_daily
import sales_order_book as sales_ob
import maintenance_ops as maint_ops
import procurement_spend as proc_spend
import dept_ops_wiring

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("helm")


def _mongo_candidate_urls() -> list[str]:
    """Ordered Mongo URLs to try — Render pserv first unless USE_ATLAS_MONGO=true."""
    seen: set[str] = set()
    urls: list[str] = []

    def add(url: str) -> None:
        if url and url not in seen:
            seen.add(url)
            urls.append(url)

    use_atlas = os.environ.get("USE_ATLAS_MONGO", "").lower() in ("1", "true", "yes")
    hostport = os.environ.get("MONGO_HOSTPORT", "").strip()
    host = os.environ.get("MONGO_HOST", "").strip()
    atlas = os.environ.get("MONGO_URL", "").strip()

    def add_pserv() -> None:
        if hostport:
            add(f"mongodb://{hostport}")
            return
        if not host and os.environ.get("RENDER"):
            host_local = "helm-mongo"
        else:
            host_local = host
        if host_local:
            add(f"mongodb://{host_local}:27017")

    if use_atlas:
        if atlas:
            add(atlas)
        # Atlas-only mode: skip Render pserv probe (avoids false "2 candidates failed" on startup).
        return urls

    # Default (Render blueprint): private Mongo first; stale Atlas URL is fallback only.
    add_pserv()
    if atlas:
        add(atlas)
    return urls


def _redact_mongo_url(url: str) -> str:
    if "@" not in url:
        return url
    prefix, rest = url.split("@", 1)
    return f"{prefix.split('://')[0]}://***@{rest}"


def _mongo_source_label(url: str) -> str:
    if url.startswith("mongodb+srv://"):
        return "atlas"
    if "helm-mongo" in url or os.environ.get("MONGO_HOST", "").strip() in url:
        return "render_pserv"
    if os.environ.get("MONGO_HOST", "").strip():
        return "mongo_host"
    return "mongo_url"


def _resolve_mongo_url() -> tuple[str, str]:
    """Pick Mongo URL without blocking import — health check probes connectivity."""
    candidates = _mongo_candidate_urls()
    if not candidates:
        raise RuntimeError("Set MONGO_URL (Atlas) or sync render.yaml for MONGO_HOST / helm-mongo")
    url = candidates[0]
    return url, _mongo_source_label(url)


DB_NAME = os.environ["DB_NAME"]


# -----------------------------------------------------------------------------
# Environment configuration
#
# ENVIRONMENT=production enforces the go-live checklist below. Keep in sync with
# README.md § "Go-live checklist".
#
# Required before ENVIRONMENT=production:
#   MONGO_URL          Atlas URI (or MONGO_HOST / helm-mongo on Render blueprint)
#   DB_NAME            Database name (e.g. helm)
#   SESSION_SECRET     Long random string — never use placeholders in production
#   OAUTH_STATE_SECRET Long random string — required in production (no fallback)
#   FRONTEND_URL       Public app URL (e.g. https://www.trenston.com)
#   APP_URL            Same as FRONTEND_URL for post-OAuth redirects
#   CORS_ORIGINS       Comma-separated allowed browser origins (same as frontend)
#   COOKIE_SECURE      true behind HTTPS
#   COOKIE_SAMESITE    lax when Vercel rewrites /api → Render (same-origin cookies);
#                      none + COOKIE_SECURE=true when the browser calls Render directly
#   ALLOW_DEMO_LOGIN   false
#   DEMO_RESET_ENABLED false (recommended)
#   CLERK_SECRET_KEY + CLERK_JWKS_URL   OR   GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET
#   ANTHROPIC_API_KEY  AI briefing / Ask Trenston
#   PADDLE_*           Billing (when BILLING_ENFORCED=true)
#   INTEGRATION_ENCRYPTION_KEY  Fernet key for Google/QuickBooks/SAP credentials at rest
#                               (python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
#
# Development: leave ENVIRONMENT unset or set to "development" — placeholders are OK.
# -----------------------------------------------------------------------------

ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").strip().lower()

def _make_mongo_client(url: str) -> AsyncIOMotorClient:
    is_atlas = url.startswith("mongodb+srv://")
    return AsyncIOMotorClient(
        url,
        serverSelectionTimeoutMS=8000 if is_atlas else 3000,
        connectTimeoutMS=8000 if is_atlas else 3000,
        socketTimeoutMS=10000,
    )


mongo_url, MONGO_SOURCE = _resolve_mongo_url()
client = _make_mongo_client(mongo_url)
db = client[DB_NAME]

SESSION_SECRET = os.environ.get('SESSION_SECRET', 'change-me-in-production')
FRONTEND_URL = os.environ.get('FRONTEND_URL', '').strip().rstrip('/')
if is_stale_deploy_url(FRONTEND_URL):
    FRONTEND_URL = TRENSTON_CANONICAL_ORIGIN
ALLOW_DEMO_LOGIN = os.environ.get("ALLOW_DEMO_LOGIN", "false").lower() in ("1", "true", "yes")
DEMO_RESET_ENABLED = os.environ.get("DEMO_RESET_ENABLED", "false").lower() in ("1", "true", "yes")
# HTTPS cookies: default false for local dev; set true on Render (see README.md).
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() in ("1", "true", "yes")
# Default lax — correct when Vercel rewrites /api to Render (browser sees same-origin).
# If REACT_APP_BACKEND_URL points at Render directly, set COOKIE_SAMESITE=none and COOKIE_SECURE=true.
COOKIE_SAMESITE = os.environ.get("COOKIE_SAMESITE", "lax")
OAUTH_STATE_SECRET = os.environ.get("OAUTH_STATE_SECRET", "")
if not OAUTH_STATE_SECRET:
    OAUTH_STATE_SECRET = SESSION_SECRET
APP_URL = (os.environ.get("APP_URL") or FRONTEND_URL or "").rstrip("/")
if is_stale_deploy_url(APP_URL):
    APP_URL = TRENSTON_CANONICAL_ORIGIN
# Display fallback — tier prices live in plans.PLANS; PRO_PRICE kept for legacy envs.
PRO_PRICE = float(os.environ.get("PRO_PRICE", "99"))
# When false (default), feature gates are open; paywall + quotas apply when true.
BILLING_ENFORCED = os.environ.get("BILLING_ENFORCED", "false").lower() in ("1", "true", "yes")
TRIAL_DAYS = helm_plans.TRIAL_DAYS
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
CORS_ORIGIN_REGEX = os.environ.get("CORS_ORIGIN_REGEX", "").strip() or None

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')  # unused; kept so old envs don't crash on import
GOOGLE_CLIENT_ID = (os.environ.get('GOOGLE_CLIENT_ID') or '').strip()
GOOGLE_CLIENT_SECRET = (os.environ.get('GOOGLE_CLIENT_SECRET') or '').strip()
QB_CLIENT_ID = (os.environ.get('QUICKBOOKS_CLIENT_ID') or '').strip()
QB_CLIENT_SECRET = (os.environ.get('QUICKBOOKS_CLIENT_SECRET') or '').strip()
QB_ENV = (os.environ.get('QUICKBOOKS_ENV') or 'sandbox').strip().lower()
XERO_CLIENT_ID = (os.environ.get('XERO_CLIENT_ID') or '').strip()
XERO_CLIENT_SECRET = (os.environ.get('XERO_CLIENT_SECRET') or '').strip()
HUBSPOT_CLIENT_ID = (os.environ.get('HUBSPOT_CLIENT_ID') or '').strip()
HUBSPOT_CLIENT_SECRET = (os.environ.get('HUBSPOT_CLIENT_SECRET') or '').strip()
RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'onboarding@resend.dev')
PADDLE_API_KEY = os.environ.get('PADDLE_API_KEY', '')
PADDLE_CLIENT_TOKEN = os.environ.get('PADDLE_CLIENT_TOKEN', '')
PADDLE_WEBHOOK_SECRET = os.environ.get('PADDLE_WEBHOOK_SECRET', '')
PADDLE_ENV = os.environ.get('PADDLE_ENV', 'sandbox')
PADDLE_API_BASE = "https://sandbox-api.paddle.com" if PADDLE_ENV == "sandbox" else "https://api.paddle.com"
CLERK_PUBLISHABLE_KEY = clerk_auth.resolve_clerk_publishable_key()
SETUP_SECRET = os.environ.get("SETUP_SECRET", "").strip()
INTERNAL_CRON_SECRET = (os.environ.get("INTERNAL_CRON_SECRET") or "").strip()
# First-party analytics summary — only this email (comma-separated), not workspace admins.
ANALYTICS_ADMIN_EMAIL = (os.environ.get("ANALYTICS_ADMIN_EMAIL") or "").strip()

_INSECURE_SESSION_SECRETS = frozenset({
    "change-me-in-production",
    "change-me-to-a-long-random-string",
})


def _enforce_production_config() -> None:
    """Refuse to boot with known-insecure settings when ENVIRONMENT=production."""
    if ENVIRONMENT != "production":
        return
    problems: list[str] = []
    raw_session = (os.environ.get("SESSION_SECRET") or "").strip()
    if not raw_session or SESSION_SECRET in _INSECURE_SESSION_SECRETS:
        problems.append("SESSION_SECRET must be set to a strong random value (not a placeholder)")
    if not (os.environ.get("OAUTH_STATE_SECRET") or "").strip():
        problems.append("OAUTH_STATE_SECRET must be set explicitly in production")
    if not INTERNAL_CRON_SECRET:
        problems.append("INTERNAL_CRON_SECRET must be set explicitly in production")
    integration_key = (os.environ.get("INTEGRATION_ENCRYPTION_KEY") or "").strip()
    if not integration_key:
        problems.append(
            "INTEGRATION_ENCRYPTION_KEY must be set (Fernet key for OAuth/ERP credentials at rest)"
        )
    else:
        try:
            cred_crypto.assert_encryption_ready()
        except cred_crypto.CredentialCryptoError:
            problems.append("INTEGRATION_ENCRYPTION_KEY must be a valid Fernet key")
    if not CORS_ORIGINS:
        problems.append("CORS_ORIGINS must list your frontend origin(s)")
    if ALLOW_DEMO_LOGIN:
        problems.append("ALLOW_DEMO_LOGIN must be false in production")
    if problems:
        raise RuntimeError(
            "Production configuration invalid (ENVIRONMENT=production):\n"
            + "\n".join(f"  - {p}" for p in problems)
            + "\nSee README.md and the config header in server.py."
        )


_enforce_production_config()

app = FastAPI()
api_router = APIRouter(prefix="/api")

# Join-code attempt limit (10 / 15 min) lives in Mongo — see rate_limit.acquire_join_slot.


def _session_cookie_domain() -> str | None:
    # When Clerk redirects to apexcoach but the app also runs on helmcontrol, use host-only cookies.
    if clerk_auth.clerk_multi_domain_auth():
        return None
    explicit = os.environ.get("COOKIE_DOMAIN", "").strip()
    if explicit:
        return explicit
    for raw in (
        clerk_auth.primary_frontend_origin(),
        FRONTEND_URL,
        APP_URL,
    ):
        if not raw:
            continue
        host = urlparse(raw).hostname
        domain = registrable_cookie_domain(host)
        if domain:
            return domain
    return None


def set_session_cookie(response: Response, token: str):
    kwargs = dict(
        key="session_token", value=token, httponly=True,
        secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE,
        path="/", max_age=7 * 24 * 60 * 60,
    )
    domain = _session_cookie_domain()
    if domain:
        kwargs["domain"] = domain
    response.set_cookie(**kwargs)


def clear_session_cookie(response: Response):
    kwargs = dict(
        key="session_token", path="/",
        httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE,
    )
    domain = _session_cookie_domain()
    if domain:
        kwargs["domain"] = domain
    response.delete_cookie(**kwargs)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


async def _check_join_rate_limit(ip: str):
    """Shared across workers via Mongo (rate_limit.join_* collections)."""
    ok = await doc_rate_limit.acquire_join_slot(
        db, ip, limit=doc_rate_limit.JOIN_RATE_LIMIT,
    )
    if not ok:
        raise HTTPException(status_code=429, detail="Too many join attempts. Try again later.")


# ------------------------- Access packs / permissions -------------------------
# Every employee can do daily work: read, move/create their tasks, ask Trenston, post a daily update.
BASE_PERMS = {"read", "tasks:move", "tasks:create", "ask:use", "updates:write"}
PACK_PERMS = {
    "member": BASE_PERMS,
    "finance": BASE_PERMS | {"finance:write"},
    "hr": BASE_PERMS | {"people:write"},
    "sales": BASE_PERMS | {"sales:write"},
    "ops": BASE_PERMS | {"ops:write", "telemetry:write"},
    "exec": BASE_PERMS | {
        "decisions:act", "briefing:generate", "reports:pack", "reports:write",
        "telemetry:write", "calendar:write",
        "members:invite", "tasks:assign",
    },
    "owner": BASE_PERMS | {
        "finance:write", "people:write", "sales:write", "ops:write",
        "decisions:act", "briefing:generate", "reports:pack", "reports:write",
        "telemetry:write", "calendar:write",
        "integrations:manage", "billing:manage",
        "members:invite", "members:manage", "tasks:assign", "workspace:edit",
    },
}
# Where each pack lands after login. Operators start on their lane or "My Day".
PACK_HOME = {"owner": "/app", "exec": "/app", "member": "/app/me",
             "finance": "/app/financials", "hr": "/app/people",
             "sales": "/app/sales", "ops": "/app/me"}
PACK_LABEL = {"owner": "Owner", "exec": "Executive", "finance": "Finance",
              "hr": "People/HR", "sales": "Sales", "ops": "Operations", "member": "Member"}
VALID_PACKS = set(PACK_PERMS.keys())
# Owner/CEO is only for the workspace creator — never assignable via invite or role edit.
ASSIGNABLE_PACKS = frozenset(p for p in VALID_PACKS if p != "owner")


def _require_assignable_pack(pack: str) -> str:
    """Validate a pack that may be granted via invite or role change (never owner/CEO)."""
    if pack not in VALID_PACKS:
        raise HTTPException(status_code=400, detail="Unknown access pack")
    if pack == "owner":
        raise HTTPException(
            status_code=400,
            detail="Owner (CEO) access cannot be assigned via invite. The workspace creator remains the owner.",
        )
    return pack


def pack_of(membership: dict) -> str:
    """Resolve a membership's access pack, defaulting for legacy owner/member rows."""
    p = membership.get("pack")
    if p in VALID_PACKS:
        return p
    return "owner" if membership.get("role") == "owner" else "member"


def perms_for(pack: str):
    return PACK_PERMS.get(pack, PACK_PERMS["member"])


def _unique_ids(values) -> list:
    """Stable unique non-empty ids for $in queries."""
    out = []
    seen = set()
    for v in values or []:
        if not v or v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


async def _docs_by_key(coll, key: str, ids, projection: dict | None = None) -> dict:
    """One find + $in → {key: doc}. Missing ids are absent (same as find_one → None)."""
    uniq = _unique_ids(ids)
    if not uniq:
        return {}
    proj = dict(projection) if projection is not None else {"_id": 0}
    # Inclusion projections need the lookup key so we can build the map.
    if proj and any(v in (1, True) for v in proj.values()):
        proj.setdefault(key, 1)
    rows = await coll.find({key: {"$in": uniq}}, proj).to_list(len(uniq))
    return {r[key]: r for r in rows if r.get(key)}


async def _users_by_ids(user_ids, projection: dict | None = None) -> dict:
    """Batch-load users. Missing user_id → omitted (callers use .get → None)."""
    proj = projection or {"_id": 0, "user_id": 1, "name": 1, "email": 1, "picture": 1}
    return await _docs_by_key(db.users, "user_id", user_ids, proj)


def _user_card(uid, u: dict | None) -> dict:
    return {
        "user_id": uid,
        "name": (u or {}).get("name"),
        "email": (u or {}).get("email"),
        "picture": (u or {}).get("picture"),
    }


async def _membership_for(principal: dict) -> dict:
    return await db.memberships.find_one(
        {"user_id": principal["user_id"], "workspace_id": principal["workspace_id"], "status": "active"},
        {"_id": 0},
    ) or {}


async def workspace_departments(workspace_id: str, ws: dict | None = None) -> list[str]:
    """Departments actually in use — members, roster, and existing access rules."""
    if ws is None:
        ws = await get_ws(workspace_id)
    depts: set[str] = set()
    mems = await db.memberships.find(
        {"workspace_id": workspace_id, "status": {"$in": ["active", "invited"]}},
        {"_id": 0, "department": 1},
    ).to_list(200)
    for m in mems:
        d = (m.get("department") or "General").strip()
        if d:
            depts.add(d)
    for p in (ws.get("people") or {}).get("people") or []:
        d = (p.get("department") or "").strip()
        if d:
            depts.add(d)
    for section_depts in (ws.get("section_access") or {}).values():
        if isinstance(section_depts, list):
            for d in section_depts:
                if str(d).strip():
                    depts.add(str(d).strip())
    if not depts:
        depts.add("General")
    return sorted(depts, key=lambda x: (x != "General", x.lower()))


def _display_name_from_email(email: str) -> str:
    local = (email or "").split("@")[0]
    cleaned = re.sub(r"[._+\-]+", " ", local).strip()
    return cleaned.title() if cleaned else "Team member"


def _find_linked_person(roster: list, membership: dict):
    mid = membership.get("membership_id")
    email = _normalize_email(membership.get("email") or "")
    user_id = membership.get("user_id")
    for p in roster:
        if mid and p.get("membership_id") == mid:
            return p
    for p in roster:
        if email and _normalize_email(p.get("email") or "") == email:
            return p
    if user_id:
        for p in roster:
            if p.get("user_id") == user_id:
                return p
    return None


async def ensure_person_for_membership(
    workspace_id: str,
    membership: dict,
    name: str | None = None,
    users_by_id: dict | None = None,
) -> dict:
    """Upsert a People roster row for a Team & Access membership. Members always appear in People."""
    ws = await get_ws(workspace_id)
    people = dict(ws.get("people") or {"people": []})
    roster = list(people.get("people") or [])
    people["people"] = roster

    email = _normalize_email(membership.get("email") or "")
    user_id = membership.get("user_id")
    display_name = (name or "").strip() or None
    if not display_name and user_id:
        if users_by_id is not None:
            u = users_by_id.get(user_id)
        else:
            u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "name": 1})
        display_name = ((u or {}).get("name") or "").strip() or None
    if not display_name:
        display_name = _display_name_from_email(email)

    found = _find_linked_person(roster, membership)
    if found:
        found["membership_id"] = membership["membership_id"]
        if email:
            found["email"] = email
        if user_id:
            found["user_id"] = user_id
        # Prefer a real account name over an email-derived placeholder
        if name and name.strip():
            found["name"] = name.strip()
        elif user_id and display_name and (
            not found.get("name")
            or (email and found.get("name") == _display_name_from_email(email))
        ):
            found["name"] = display_name
        person = found
    else:
        person = {
            "id": f"p_{uuid.uuid4().hex[:8]}",
            "name": display_name,
            "role": "",
            "tenure": "New",
            "membership_id": membership["membership_id"],
            "email": email or None,
            "user_id": user_id,
        }
        roster.append(person)

    headcount = len(roster)
    await db.workspaces.update_one(
        {"workspace_id": workspace_id},
        {"$set": {"people": people, "employees": headcount}},
    )
    return person


async def sync_members_into_people(workspace_id: str) -> dict:
    """Backfill: every active/invited membership has a People row."""
    mems = await db.memberships.find(
        {"workspace_id": workspace_id, "status": {"$in": ["active", "invited"]}},
        {"_id": 0},
    ).to_list(200)
    users_by_id = await _users_by_ids(
        [m.get("user_id") for m in mems],
        {"_id": 0, "user_id": 1, "name": 1},
    )
    for m in mems:
        await ensure_person_for_membership(workspace_id, m, users_by_id=users_by_id)
    return await get_ws(workspace_id)


async def unlink_person_membership(workspace_id: str, membership_id: str):
    """Keep the roster person when access is revoked — just clear the login link."""
    ws = await get_ws(workspace_id)
    people = dict(ws.get("people") or {"people": []})
    changed = False
    for p in people.get("people") or []:
        if p.get("membership_id") == membership_id:
            p.pop("membership_id", None)
            changed = True
    if changed:
        await db.workspaces.update_one(
            {"workspace_id": workspace_id},
            {"$set": {"people": people}},
        )


async def can_section_write(
    principal: dict,
    section_id: str,
    pack_perm: str,
    *,
    membership: Optional[dict] = None,
    workspace: Optional[dict] = None,
) -> bool:
    """Pack permission OR CEO-granted member/department access for a section.

    Pass already-loaded membership/workspace when calling in a loop (e.g. /auth/me)
    so each section check does not re-hit Mongo.
    """
    if pack_perm in perms_for(principal["pack"]):
        return True
    membership = membership if membership is not None else await _membership_for(principal)
    # Per-member grants (preferred)
    if section_id in sec_access.normalize_section_grants(membership.get("section_grants")):
        return True
    # Legacy department grants
    ws = workspace if workspace is not None else await get_ws(principal["workspace_id"])
    dept = (membership.get("department") or "General").strip()
    allowed = (ws.get("section_access") or {}).get(section_id) or []
    return dept in allowed


async def can_access_financials(
    principal: dict,
    *,
    membership: Optional[dict] = None,
    workspace: Optional[dict] = None,
) -> bool:
    """Single gate for MRR/runway/burn and related figures across Trenston surfaces.

    Same rule as Financials page write access: pack `finance:write` or a CEO
    section grant / legacy department grant for `financials`.
    """
    return await can_section_write(
        principal,
        "financials",
        "finance:write",
        membership=membership,
        workspace=workspace,
    )


# Phrases that request financial figures Ask Trenston must not answer without access.
_FINANCE_ASK_RE = re.compile(
    r"\b("
    r"mrr|arr|runway|burn(?:\s*rate)?|cash(?:\s*balance)?|revenue|revenues|"
    r"expense(?:s)?|profit(?:ability)?|p\s*&\s*l|pnl|income\s*statement|"
    r"net\s*burn|gross\s*margin|financial(?:s)?|budget|payroll\s*cost|"
    r"how\s+much\s+(?:money|cash|revenue)|out\s+of\s+(?:money|runway)"
    r")\b",
    re.IGNORECASE,
)

FINANCIALS_ACCESS_DENIED_MESSAGE = (
    "You don't have access to financial data in this workspace. "
    "Ask a workspace owner to grant you Financials access if you need MRR, "
    "runway, burn, or related figures."
)


def message_requests_financials(message: str) -> bool:
    """True when an Ask Trenston message is asking for gated financial figures."""
    text = (message or "").strip()
    if not text:
        return False
    return bool(_FINANCE_ASK_RE.search(text))


def require_section(section_id: str, pack_perm: str):
    """Section write access — Free may edit manually; AI upload uses a separate feature gate."""
    async def dep(principal=Depends(get_principal)):
        if not await can_section_write(principal, section_id, pack_perm):
            raise HTTPException(status_code=403, detail="You do not have permission for this action")
        return principal
    return dep


def _normalize_task_columns(tasks: dict) -> dict:
    """Display label Backlog → To-Do while keeping column id backlog."""
    out = dict(tasks)
    cols = []
    for col in out.get("columns") or []:
        c = dict(col)
        if c.get("id") == "backlog":
            c["name"] = "To-Do"
        cols.append(c)
    out["columns"] = cols
    return out


# ------------------------- OAuth state signing (CSRF) -------------------------
_STATE_SECRET = OAUTH_STATE_SECRET.encode()


def _allowed_auth_redirect(url: str) -> bool:
    """Only allow post-login redirects to our frontend origins (open-redirect guard)."""
    if not url:
        return False
    if url.startswith("/") and not url.startswith("//"):
        return True
    bases = {APP_URL.rstrip("/")} if APP_URL else set()
    bases.update(o.rstrip("/") for o in CORS_ORIGINS if o)
    bases.update(clerk_auth.helm_frontend_origins())
    for base in bases:
        if url == base or url.startswith(base + "/"):
            return True
    return False


def _secret_header_matches(provided: str, expected: str) -> bool:
    if not provided or not expected:
        return False
    try:
        return hmac.compare_digest(provided, expected)
    except (TypeError, ValueError):
        return False


def _require_setup_secret(request: Request) -> None:
    if not SETUP_SECRET:
        raise HTTPException(status_code=503, detail="Setup endpoint disabled (set SETUP_SECRET on Render)")
    provided = request.headers.get("X-Setup-Secret", "").strip()
    if not _secret_header_matches(provided, SETUP_SECRET):
        raise HTTPException(status_code=401, detail="Invalid setup secret")


def _require_internal_cron(request: Request) -> None:
    """Shared-secret gate for Render cron (trial / inactivity emails)."""
    if not INTERNAL_CRON_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Retention cron disabled (set INTERNAL_CRON_SECRET)",
        )
    provided = (
        request.headers.get("X-Trenston-Cron-Secret")
        or request.headers.get("X-Setup-Secret")
        or ""
    ).strip()
    if provided.lower().startswith("bearer "):
        provided = provided[7:].strip()
    if _secret_header_matches(provided, INTERNAL_CRON_SECRET):
        return
    raise HTTPException(status_code=401, detail="Invalid cron secret")


def _sign_state(provider: str, workspace_id: str, user_id: str, nonce: str) -> str:
    ts = str(int(datetime.now(timezone.utc).timestamp()))
    body = f"{provider}:{workspace_id}:{user_id}:{nonce}:{ts}"
    sig = hmac.new(_STATE_SECRET, body.encode(), hashlib.sha256).hexdigest()
    return f"{body}:{sig}"


def _verify_state(state: str, max_age: int = 600):
    try:
        provider, workspace_id, user_id, nonce, ts, sig = state.split(":")
        age = int(datetime.now(timezone.utc).timestamp()) - int(ts)
    except (ValueError, TypeError, AttributeError):
        return None
    body = f"{provider}:{workspace_id}:{user_id}:{nonce}:{ts}"
    expected = hmac.new(_STATE_SECRET, body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    if age < 0 or age > max_age:
        return None
    return provider, workspace_id, user_id, nonce


# ------------------------- Email (Resend) -------------------------
def _invite_email_html(inviter_name: str, workspace_name: str, role: str, app_url: str) -> str:
    inviter_name = html.escape(inviter_name)
    workspace_name = html.escape(workspace_name)
    role = html.escape(role)
    app_url = html.escape(app_url, quote=True)
    return f"""\
<!DOCTYPE html><html><body style="margin:0;padding:0;background:#09090b;font-family:'Helvetica Neue',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#09090b;padding:40px 0;">
<tr><td align="center">
<table width="480" cellpadding="0" cellspacing="0" style="background:#121214;border:1px solid rgba(255,255,255,0.08);border-radius:14px;overflow:hidden;">
<tr><td style="padding:32px 36px 8px 36px;">
<table cellpadding="0" cellspacing="0"><tr>
<td style="width:34px;height:34px;background:rgba(201,169,98,0.15);border:1px solid rgba(201,169,98,0.35);border-radius:8px;text-align:center;vertical-align:middle;color:#c9a962;font-weight:600;font-size:15px;">H</td>
<td style="padding-left:10px;color:#ffffff;font-size:16px;font-weight:600;">Trenston</td>
</tr></table>
<p style="color:#c9a962;font-size:11px;letter-spacing:2px;text-transform:uppercase;margin:22px 0 0 0;">You've been added</p>
<h1 style="color:#ffffff;font-size:24px;font-weight:400;margin:10px 0 0 0;line-height:1.3;">{inviter_name} invited you to<br><span style="color:#c9a962;">{workspace_name}</span></h1>
<p style="color:#a1a1aa;font-size:15px;line-height:1.6;margin:18px 0 0 0;">You now have <b style="color:#ffffff;">{role}</b> access to this company's command center on Trenston, the CEO Operating System. Sign in with Google to see the briefing, decisions, financials and more.</p>
<table cellpadding="0" cellspacing="0" style="margin:28px 0 8px 0;"><tr>
<td style="background:#c9a962;border-radius:8px;">
<a href="{app_url}" style="display:inline-block;padding:12px 26px;color:#09090b;font-size:14px;font-weight:600;text-decoration:none;">Open Trenston &rarr;</a>
</td></tr></table>
</td></tr>
<tr><td style="padding:20px 36px 30px 36px;border-top:1px solid rgba(255,255,255,0.06);">
<p style="color:#52525b;font-size:12px;margin:0;line-height:1.6;">Know what matters before your first meeting.<br>If you didn't expect this invite, you can ignore this email.</p>
</td></tr>
</table>
</td></tr></table></body></html>"""


async def send_invite_email(to_email: str, inviter_name: str, workspace_name: str, role: str, app_url: str):
    if not RESEND_API_KEY:
        logger.info("RESEND_API_KEY not set — skipping invite email to %s", to_email)
        return {"sent": False, "reason": "no_key"}
    resend.api_key = RESEND_API_KEY
    params = {
        "from": SENDER_EMAIL, "to": [to_email],
        "subject": f"{inviter_name} invited you to {workspace_name} on Trenston",
        "html": _invite_email_html(inviter_name, workspace_name, role, app_url),
    }
    try:
        email = await asyncio.to_thread(resend.Emails.send, params)
        return {"sent": True, "id": (email or {}).get("id")}
    except Exception:
        logger.exception("resend send failed")
        return {"sent": False, "reason": "error"}


async def send_resend_email(
    *,
    to: list,
    subject: str,
    html: str,
    attachments: Optional[list] = None,
    headers: Optional[dict] = None,
) -> dict:
    """Shared Resend send helper (best-effort). `to` may include multiple recipients in one send.

    attachments: optional list of {"filename": str, "content": bytes, "content_type": optional str}.
    headers: optional extra SMTP/API headers (e.g. List-Unsubscribe for commercial mail).
    """
    recipients = [e for e in (to or []) if e and "@" in str(e)]
    if not recipients:
        return {"sent": False, "reason": "no_recipients"}
    if not RESEND_API_KEY:
        logger.info("RESEND_API_KEY not set — skipping email: %s", subject)
        return {"sent": False, "reason": "no_key"}
    resend.api_key = RESEND_API_KEY
    params = {"from": SENDER_EMAIL, "to": recipients, "subject": subject, "html": html}
    if headers:
        clean = {str(k): str(v) for k, v in headers.items() if k and v is not None}
        if clean:
            params["headers"] = clean
    if attachments:
        packed = []
        for att in attachments:
            raw = att.get("content")
            if raw is None or not att.get("filename"):
                continue
            if isinstance(raw, (bytes, bytearray)):
                content = list(raw)
            else:
                content = raw
            row = {"filename": att["filename"], "content": content}
            if att.get("content_type"):
                row["content_type"] = att["content_type"]
            packed.append(row)
        if packed:
            params["attachments"] = packed
    try:
        email = await asyncio.to_thread(resend.Emails.send, params)
        logger.info("resend sent subject=%r to=%s id=%s", subject, recipients, (email or {}).get("id"))
        return {"sent": True, "id": (email or {}).get("id"), "to": recipients}
    except Exception:
        logger.exception("resend send failed subject=%r to=%s", subject, recipients)
        return {"sent": False, "reason": "error"}


async def send_notification_email(
    to: str | list,
    subject: str,
    body: str,
    headers: Optional[dict] = None,
) -> dict:
    """Reusable single/multi-recipient notification email via Resend. Never raises."""
    recipients = to if isinstance(to, list) else [to]
    return await send_resend_email(to=recipients, subject=subject, html=body, headers=headers)


def _app_base_url() -> str:
    return (APP_URL or FRONTEND_URL or TRENSTON_CANONICAL_ORIGIN or "").rstrip("/")


def _task_delegation_email_html(
    *,
    task_title: str,
    task_note: str,
    delegator_name: str,
    workspace_name: str,
    task_url: str,
) -> str:
    title = html.escape(task_title or "Task")
    note = html.escape((task_note or "").strip()[:400])
    delegator = html.escape(delegator_name or "A teammate")
    workspace = html.escape(workspace_name or "your company")
    url = html.escape(task_url, quote=True)
    note_block = (
        f'<p style="color:#a1a1aa;font-size:14px;line-height:1.6;margin:14px 0 0 0;">{note}</p>'
        if note else ""
    )
    return f"""\
<!DOCTYPE html><html><body style="margin:0;padding:0;background:#09090b;font-family:'Helvetica Neue',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#09090b;padding:40px 0;">
<tr><td align="center">
<table width="480" cellpadding="0" cellspacing="0" style="background:#121214;border:1px solid rgba(255,255,255,0.08);border-radius:14px;overflow:hidden;">
<tr><td style="padding:32px 36px 8px 36px;">
<p style="color:#c9a962;font-size:11px;letter-spacing:2px;text-transform:uppercase;margin:0;">Task delegated</p>
<h1 style="color:#ffffff;font-size:22px;font-weight:400;margin:10px 0 0 0;line-height:1.3;">{title}</h1>
<p style="color:#a1a1aa;font-size:15px;line-height:1.6;margin:16px 0 0 0;">{delegator} assigned you a task in <b style="color:#ffffff;">{workspace}</b> on Trenston.</p>
{note_block}
<table cellpadding="0" cellspacing="0" style="margin:28px 0 8px 0;"><tr>
<td style="background:#c9a962;border-radius:8px;">
<a href="{url}" style="display:inline-block;padding:12px 26px;color:#09090b;font-size:14px;font-weight:600;text-decoration:none;">Open task in Trenston &rarr;</a>
</td></tr></table>
</td></tr>
</table>
</td></tr></table></body></html>"""


async def notify_task_delegated(
    *,
    assignee_user_id: str | None,
    previous_assignee_user_id: str | None,
    task: dict,
    principal: dict,
    workspace_name: str,
) -> dict:
    """Send delegation email only when assignee changes to a different user. Never raises / never blocks."""
    new_uid = (assignee_user_id or "").strip() or None
    old_uid = (previous_assignee_user_id or "").strip() or None
    if not new_uid or new_uid == old_uid:
        return {"sent": False, "reason": "unchanged"}
    if new_uid == principal.get("user_id"):
        return {"sent": False, "reason": "self_assign"}
    try:
        user = await db.users.find_one({"user_id": new_uid}, {"_id": 0, "email": 1, "name": 1})
        email = _normalize_email((user or {}).get("email") or "")
        if not email:
            mem = await db.memberships.find_one(
                {"workspace_id": principal["workspace_id"], "user_id": new_uid},
                {"_id": 0, "email": 1},
            )
            email = _normalize_email((mem or {}).get("email") or "")
        if not email:
            logger.info("task delegation email skipped — no email for user_id=%s", new_uid)
            return {"sent": False, "reason": "no_email"}
        title = (task.get("title") or "Task").strip()
        note = (task.get("note") or task.get("tag") or "").strip()
        task_url = f"{_app_base_url()}/app/tasks?task={task.get('id') or ''}"
        html_body = _task_delegation_email_html(
            task_title=title,
            task_note=note,
            delegator_name=principal.get("name") or principal.get("email") or "A teammate",
            workspace_name=workspace_name,
            task_url=task_url,
        )
        result = await send_notification_email(
            email,
            f"Delegated to you: {title}",
            html_body,
        )
        return result
    except Exception:
        logger.exception("notify_task_delegated failed for task=%s", task.get("id"))
        return {"sent": False, "reason": "error"}


async def post_slack_webhook(webhook_url: str, text: str) -> dict:
    """Best-effort Slack Incoming Webhook post. Never raises."""
    url = (webhook_url or "").strip()
    if not url.startswith("https://hooks.slack.com/"):
        return {"ok": False, "reason": "invalid_or_missing"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, json={"text": text})
        if r.status_code >= 400:
            logger.warning("slack webhook failed status=%s body=%s", r.status_code, r.text[:200])
            return {"ok": False, "reason": "http_error", "status": r.status_code}
        return {"ok": True}
    except Exception:
        logger.exception("slack webhook post failed")
        return {"ok": False, "reason": "error"}


# Packs that should receive high-severity CEO alerts (owner + executive/"manager")
ALERT_RECIPIENT_PACKS = frozenset({"owner", "exec"})


async def _alert_recipient_emails(workspace_id: str) -> list[str]:
    mems = await db.memberships.find(
        {"workspace_id": workspace_id, "status": "active"},
        {"_id": 0, "user_id": 1, "pack": 1, "role": 1, "email": 1},
    ).to_list(200)
    emails = []
    seen = set()
    missing_email_uids = [
        m.get("user_id")
        for m in mems
        if (pack_of(m) in ALERT_RECIPIENT_PACKS or m.get("role") == "owner")
        and not (m.get("email") or "").strip()
        and m.get("user_id")
    ]
    users_by_id = await _users_by_ids(missing_email_uids, {"_id": 0, "user_id": 1, "email": 1})
    for m in mems:
        if pack_of(m) not in ALERT_RECIPIENT_PACKS and m.get("role") != "owner":
            continue
        email = (m.get("email") or "").strip().lower()
        if not email and m.get("user_id"):
            u = users_by_id.get(m["user_id"])
            email = ((u or {}).get("email") or "").strip().lower()
        if email and email not in seen:
            seen.add(email)
            emails.append(email)
    return emails


async def _notify_high_severity_alerts(workspace_id: str, decision_suggestions: list, c: dict) -> dict:
    """Email + optional Slack for newly seen high-severity signals. Best-effort; never blocks."""
    import alert_notify as an

    notified = set(c.get("notified_signal_ids") or [])
    fresh = an.new_high_alerts(decision_suggestions, notified)
    if not fresh:
        return {"emailed": False, "slack": False, "new_alerts": 0}

    app_url = APP_URL or FRONTEND_URL or TRENSTON_CANONICAL_ORIGIN
    ws_name = c.get("name") or "Your workspace"
    html = an.build_alert_email_html(ws_name, fresh, app_url)
    slack_text = an.build_slack_text(ws_name, fresh, app_url)
    recipients = await _alert_recipient_emails(workspace_id)
    email_result = await send_resend_email(
        to=recipients,
        subject=f"Trenston alert: {len(fresh)} high-severity signal{'s' if len(fresh) != 1 else ''}: {ws_name}",
        html=html,
    )
    slack_result = {"ok": False, "reason": "not_configured"}
    webhook = (c.get("slack_webhook_url") or "").strip()
    if webhook:
        slack_result = await post_slack_webhook(webhook, slack_text)

    new_keys = [an.signal_notify_key(s.get("signal") or s) for s in fresh]
    delivered = bool(email_result.get("sent")) or bool(slack_result.get("ok"))
    # Only debounce after at least one channel succeeds — failed delivery must retry
    if delivered:
        updated_ids = list(notified | set(new_keys))
        await db.workspaces.update_one(
            {"workspace_id": workspace_id},
            {"$set": {
                "notified_signal_ids": updated_ids,
                "notified_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
    return {
        "emailed": bool(email_result.get("sent")),
        "slack": bool(slack_result.get("ok")),
        "new_alerts": len(fresh),
        "debounced": delivered,
        "email": email_result,
        "slack_result": slack_result,
    }


# ------------------------- Auth / principal -------------------------
def _looks_like_jwt(token: str) -> bool:
    return token.count(".") == 2


async def _user_from_clerk_jwt(token: str):
    """Authenticate via Clerk session JWT (no Trenston cookie required)."""
    if not clerk_auth.clerk_configured():
        raise HTTPException(status_code=401, detail="Clerk is not configured")
    try:
        payload = await clerk_auth.decode_clerk_jwt(token)
        clerk_id = payload.get("sub")
        if not clerk_id:
            raise ValueError("Clerk token missing sub")
        existing = await db.users.find_one({"clerk_id": clerk_id}, {"_id": 0})
        if existing:
            await _bootstrap(existing)
            return existing
        identity = await clerk_auth.fetch_clerk_user_profile(clerk_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except HTTPException:
        raise
    except Exception:
        logger.exception("clerk jwt auth failed")
        raise HTTPException(
            status_code=401,
            detail="Clerk sign-in failed. Check Render CLERK_SECRET_KEY matches your Clerk publishable key",
        )
    try:
        return await _upsert_clerk_user(
            email=identity["email"],
            name=identity.get("name"),
            picture=identity.get("picture"),
            clerk_id=identity["clerk_id"],
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("clerk user upsert failed for %s", identity.get("email"))
        raise HTTPException(
            status_code=503,
            detail="Could not save your account: database unavailable. Try again in a moment.",
        )


async def _user_from_request(request: Request):
    auth = request.headers.get("Authorization", "")
    bearer = auth[7:].strip() if auth.startswith("Bearer ") else ""
    if bearer and _looks_like_jwt(bearer):
        try:
            return await _user_from_clerk_jwt(bearer)
        except HTTPException as exc:
            if exc.status_code != 401:
                raise
            # Fall back to Trenston session cookie when Clerk JWT is stale/invalid.

    token = request.cookies.get("session_token")
    if not token and bearer:
        token = bearer
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")
    expires_at = session["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")
    user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def _activate_invites(user):
    """Attach any pending email invites to this user (join inviting workspace)."""
    email = _normalize_email(user.get("email") or "")
    if not email:
        return
    await db.memberships.update_many(
        {"email": email, "status": "invited"},
        {"$set": {"user_id": user["user_id"], "status": "active",
                  "joined_at": datetime.now(timezone.utc).isoformat()}},
    )
    # Legacy mixed-case invite emails
    await db.memberships.update_many(
        {"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}, "status": "invited"},
        {"$set": {"user_id": user["user_id"], "email": email, "status": "active",
                  "joined_at": datetime.now(timezone.utc).isoformat()}},
    )
    # Enroll into Sales / Accounting & Finance when those departments exist.
    mems = await db.memberships.find(
        {"user_id": user["user_id"], "status": "active"},
        {"_id": 0, "workspace_id": 1},
    ).to_list(50)
    for m in mems:
        ws_id = m.get("workspace_id")
        if ws_id:
            await dept_migrate.enroll_user_in_sales_finance(db, ws_id, user["user_id"])


async def _bootstrap(user):
    """Activate any pending email invites for this user. No silent company creation —
    genuinely new users choose to create a company or join via code (see /auth/me)."""
    await _activate_invites(user)


async def get_user(request: Request):
    """Authenticated user, invites activated — but does NOT require a workspace."""
    user = await _user_from_request(request)
    await _activate_invites(user)
    return user


async def get_principal(request: Request):
    user = await _user_from_request(request)
    await _bootstrap(user)
    active = user.get("active_workspace_id")
    membership = None
    if active:
        membership = await db.memberships.find_one(
            {"user_id": user["user_id"], "workspace_id": active, "status": "active"}, {"_id": 0})
    if not membership:
        membership = await db.memberships.find_one(
            {"user_id": user["user_id"], "status": "active"}, {"_id": 0})
        if membership:
            active = membership["workspace_id"]
            await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"active_workspace_id": active}})
    if not membership:
        raise HTTPException(status_code=403, detail="No workspace")
    return {
        "user_id": user["user_id"], "email": user["email"], "name": user.get("name"),
        "picture": user.get("picture"), "workspace_id": membership["workspace_id"],
        "role": membership["role"], "pack": pack_of(membership),
    }


def _is_analytics_admin(principal: dict | None) -> bool:
    allowed = {
        _normalize_email(part)
        for part in ANALYTICS_ADMIN_EMAIL.split(",")
        if part.strip()
    }
    return bool(allowed) and _normalize_email((principal or {}).get("email") or "") in allowed


async def require_analytics_admin(principal=Depends(get_principal)):
    """Trenston operator only — not a workspace owner/admin permission."""
    if not _is_analytics_admin(principal):
        raise HTTPException(status_code=403, detail="Not available")
    return principal


async def _product_event(workspace_id, user_id, event_type: str, metadata: dict | None = None) -> None:
    await helm_analytics.log_event(db, workspace_id, user_id, event_type, metadata)


def require(action: str):
    async def dep(principal=Depends(get_principal)):
        if action not in perms_for(principal["pack"]):
            raise HTTPException(status_code=403, detail="You do not have permission for this action")
        return principal
    return dep


def workspace_plan_id(ws_or_plan) -> str:
    plan = ws_or_plan.get("plan") if isinstance(ws_or_plan, dict) else ws_or_plan
    return helm_plans.normalize_plan(plan)


def workspace_is_pro(ws_or_plan) -> bool:
    """True when billing is off, or workspace is on a paid tier (Starter+). Legacy name kept for API fields."""
    if not BILLING_ENFORCED:
        return True
    return helm_plans.is_paid_plan(workspace_plan_id(ws_or_plan))


def workspace_allows(ws_or_plan, feature: str) -> bool:
    """Plan feature gate. past_due / paused subscriptions lose paid features."""
    if not helm_plans.plan_allows(workspace_plan_id(ws_or_plan), feature, billing_enforced=BILLING_ENFORCED):
        return False
    if not BILLING_ENFORCED:
        return True
    if isinstance(ws_or_plan, dict):
        status = (ws_or_plan.get("subscription_status") or ws_or_plan.get("billing_status") or "").lower()
        if status in ("past_due", "paused", "canceled", "cancelled"):
            return False
    return True


def workspace_allows_provider(ws_or_plan, provider: str) -> bool:
    """Per-provider integration gate (QuickBooks/Xero/SAP/HubSpot/Slack). Google always allowed."""
    if not helm_plans.plan_allows_provider(
        workspace_plan_id(ws_or_plan), provider, billing_enforced=BILLING_ENFORCED,
    ):
        return False
    if not BILLING_ENFORCED:
        return True
    if isinstance(ws_or_plan, dict):
        status = (ws_or_plan.get("subscription_status") or ws_or_plan.get("billing_status") or "").lower()
        if status in ("past_due", "paused", "canceled", "cancelled"):
            return False
    return True


_PROVIDER_UPGRADE_LABELS = {
    "quickbooks": "QuickBooks",
    "xero": "Xero",
    "sap_b1": "SAP Business One",
    "hubspot": "HubSpot",
    "slack": "Slack",
}


def _plan_provider_denied_detail(provider: str) -> dict:
    label = _PROVIDER_UPGRADE_LABELS.get((provider or "").strip().lower(), "this integration")
    return {
        "reason": "plan",
        "message": f"Upgrade your plan to use {label}",
        "feature": helm_plans.FEATURE_INTEGRATIONS,
        "provider": (provider or "").strip().lower(),
    }


def require_integration_provider(provider: str):
    """Pack integrations:manage + plan allows this specific provider."""
    async def dep(principal=Depends(get_principal)):
        if "integrations:manage" not in perms_for(principal["pack"]):
            raise HTTPException(
                status_code=403,
                detail={
                    "reason": "permission",
                    "message": "You do not have permission for this action",
                },
            )
        if BILLING_ENFORCED:
            c = await get_ws(principal["workspace_id"])
            if not workspace_allows_provider(c, provider):
                raise HTTPException(status_code=403, detail=_plan_provider_denied_detail(provider))
        return principal
    return dep


def _valid_fin_month(month: str, *, allow_future: bool = False) -> bool:
    """Syntactically valid YYYY-MM. Future months rejected unless allow_future."""
    import finance_recurrence as fin_recur
    s = (month or "").strip()
    if not fin_recur.is_valid_month(s):
        return False
    if not allow_future and fin_recur.is_future_month(s):
        return False
    return True


def _reject_future_fin_month(month: str) -> None:
    """Raise 400 when month is in the future (manual / AI commit / CSV)."""
    import finance_recurrence as fin_recur
    s = (month or "").strip()
    if fin_recur.is_valid_month(s) and fin_recur.is_future_month(s):
        raise HTTPException(
            status_code=400,
            detail="month cannot be in the future — use the current or a past month",
        )
    if not fin_recur.is_valid_month(s):
        raise HTTPException(status_code=400, detail="month must be a valid YYYY-MM")


async def require_pro(principal=Depends(get_principal)):
    if not BILLING_ENFORCED:
        return principal
    c = await get_ws(principal["workspace_id"])
    if not helm_plans.is_paid_plan(c.get("plan")):
        raise HTTPException(status_code=403, detail="A paid Trenston plan is required for this action")
    return principal


def require_feature(feature: str):
    async def dep(principal=Depends(get_principal)):
        c = await get_ws(principal["workspace_id"])
        if not workspace_allows(c, feature):
            raise HTTPException(
                status_code=403,
                detail={
                    "reason": "plan",
                    "message": f"Upgrade your plan to use this feature ({feature.replace('_', ' ')})",
                },
            )
        return principal
    return dep


def require_pro_perm(action: str):
    """Pack permission + optional plan feature gate (Free keeps core cockpit writes)."""
    async def dep(principal=Depends(get_principal)):
        if action not in perms_for(principal["pack"]):
            raise HTTPException(
                status_code=403,
                detail={
                    "reason": "permission",
                    "message": "You do not have permission for this action",
                },
            )
        feature = helm_plans.feature_for_action(action)
        if feature and BILLING_ENFORCED:
            c = await get_ws(principal["workspace_id"])
            if not workspace_allows(c, feature):
                if action == "ask:use":
                    plan_message = "Ask Trenston isn't included in your plan"
                else:
                    plan_message = "Upgrade your plan to use this feature"
                raise HTTPException(
                    status_code=403,
                    detail={"reason": "plan", "message": plan_message, "feature": feature},
                )
        return principal
    return dep


async def _seat_count(workspace_id: str) -> int:
    return await db.memberships.count_documents({
        "workspace_id": workspace_id,
        "status": {"$in": ["active", "invited"]},
    })


async def _enforce_seat_available(workspace_id: str, plan: str | None = None) -> None:
    """Atomically reserve one seat under the plan cap (check-then-act safe).

    Callers that fail to insert a membership after this succeeds must call
    `_release_seat_reservation` so a phantom seat is not held.
    """
    if not BILLING_ENFORCED:
        return
    if plan is None:
        ws = await get_ws(workspace_id)
        plan = ws.get("plan")
    limit = helm_plans.seats_limit(plan)
    if limit is None:
        return
    used = await _seat_count(workspace_id)
    ok = await plan_usage.acquire_seat_slot(
        db, workspace_id, limit, membership_count=used,
    )
    if not ok:
        raise HTTPException(
            status_code=403,
            detail=f"Upgrade to add more members. Your plan allows {limit} seat{'s' if limit != 1 else ''} ({used}/{limit} used).",
        )


async def _release_seat_reservation(workspace_id: str) -> None:
    if not BILLING_ENFORCED:
        return
    try:
        await plan_usage.release_seat_slot(db, workspace_id)
    except Exception:
        logger.exception("seat reservation release failed for %s", workspace_id)


async def _enforce_ai_extract_quota(principal) -> None:
    """Read-only quota gate (e.g. upload). Extract/summarize must use acquire."""
    c = await get_ws(principal["workspace_id"])
    if not workspace_allows(c, helm_plans.FEATURE_AI_EXTRACT):
        raise HTTPException(
            status_code=403,
            detail="AI document upload is not available on this plan. Upgrade to Starter or higher.",
        )
    if not BILLING_ENFORCED:
        return
    lifetime_limit = helm_plans.ai_extracts_lifetime_limit(c.get("plan"))
    if lifetime_limit > 0:
        used = plan_usage.get_lifetime_extract_count(c)
        if used >= lifetime_limit:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"You've used your {lifetime_limit} free AI extracts. "
                    "upgrade to continue."
                ),
            )
        return
    limit = helm_plans.ai_extracts_limit(c.get("plan"))
    if limit <= 0:
        raise HTTPException(
            status_code=403,
            detail="AI document upload is not available on your plan. Upgrade to continue.",
        )
    period = plan_usage.current_usage_period(c)
    used = await plan_usage.get_period_extract_count(db, principal["workspace_id"], period["key"])
    if used >= limit:
        raise HTTPException(
            status_code=429,
            detail="You've hit this month's document limit. Upgrade for more.",
        )


async def _acquire_ai_extract_quota(principal) -> dict:
    """Atomically consume one AI-extract slot before processing starts.

    Returns a ticket; pass to `_release_ai_extract_quota` if processing fails
    or does not produce a billable extract so the slot is not left phantom.
    """
    c = await get_ws(principal["workspace_id"])
    if not workspace_allows(c, helm_plans.FEATURE_AI_EXTRACT):
        raise HTTPException(
            status_code=403,
            detail="AI document upload is not available on this plan. Upgrade to Starter or higher.",
        )
    if not BILLING_ENFORCED:
        return {"mode": "unenforced"}
    ws_id = principal["workspace_id"]
    lifetime_limit = helm_plans.ai_extracts_lifetime_limit(c.get("plan"))
    if lifetime_limit > 0:
        ok = await plan_usage.acquire_lifetime_extract_slot(db, ws_id, lifetime_limit)
        if not ok:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"You've used your {lifetime_limit} free AI extracts. "
                    "upgrade to continue."
                ),
            )
        return {"mode": "lifetime"}
    limit = helm_plans.ai_extracts_limit(c.get("plan"))
    if limit <= 0:
        raise HTTPException(
            status_code=403,
            detail="AI document upload is not available on your plan. Upgrade to continue.",
        )
    period = plan_usage.current_usage_period(c)
    ok = await plan_usage.acquire_period_extract_slot(db, ws_id, period["key"], limit)
    if not ok:
        raise HTTPException(
            status_code=429,
            detail="You've hit this month's document limit. Upgrade for more.",
        )
    return {"mode": "period", "period_key": period["key"]}


async def _release_ai_extract_quota(principal, ticket: dict | None) -> None:
    if not ticket or ticket.get("mode") in (None, "unenforced"):
        return
    ws_id = principal["workspace_id"]
    try:
        if ticket.get("mode") == "lifetime":
            await plan_usage.release_lifetime_extract_slot(db, ws_id)
        elif ticket.get("mode") == "period" and ticket.get("period_key"):
            await plan_usage.release_period_extract_slot(db, ws_id, ticket["period_key"])
    except Exception:
        logger.exception("AI extract quota release failed for %s", ws_id)


async def get_ws(workspace_id: str):
    ws = await db.workspaces.find_one({"workspace_id": workspace_id}, {"_id": 0})
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    # Conscious migration: legacy plan=pro → starter (see README.md)
    if ws.get("plan") == "pro":
        await db.workspaces.update_one(
            {"workspace_id": workspace_id, "plan": "pro"},
            {"$set": {"plan": "starter", "plan_migrated_from": "pro"}},
        )
        ws["plan"] = "starter"
        ws["plan_migrated_from"] = "pro"
        invalidate_plan_cache(workspace_id)
    # Apply scheduled downgrade when the billing period ends
    pending = ws.get("pending_plan")
    effective_at = plan_usage.parse_dt(ws.get("pending_plan_effective_at"))
    if pending and effective_at and datetime.now(timezone.utc) >= effective_at:
        target = helm_plans.normalize_plan(pending)
        await db.workspaces.update_one(
            {"workspace_id": workspace_id},
            {
                "$set": {"plan": target},
                "$unset": {"pending_plan": "", "pending_plan_effective_at": ""},
            },
        )
        ws["plan"] = target
        ws.pop("pending_plan", None)
        ws.pop("pending_plan_effective_at", None)
        invalidate_plan_cache(workspace_id)
    return ws


# ------------------------- Activity log -------------------------
def _rel_time(iso: str) -> str:
    try:
        t = datetime.fromisoformat(iso)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
    except Exception:
        return ""
    secs = (datetime.now(timezone.utc) - t).total_seconds()
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


async def log_activity(principal, module, action, summary, patch=None):
    doc = {
        "activity_id": f"act_{uuid.uuid4().hex[:12]}",
        "workspace_id": principal["workspace_id"],
        "actor_user_id": principal["user_id"],
        "actor_name": principal.get("name") or principal.get("email") or "Someone",
        "module": module, "action": action, "summary": summary,
        "patch": patch or {}, "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.activities.insert_one(doc)
    return doc


async def _enforce_document_rate_limit(principal, action: str, limit: int, message: str) -> None:
    if await doc_rate_limit.acquire_event_slot(db, principal["workspace_id"], action, limit):
        return
    label = "Upload" if action == "upload" else "Extraction"
    await log_activity(
        principal, "financials", "document.rate_limit",
        f"{label} limit reached for this workspace ({limit}/hour)",
        {"action": action, "limit": limit},
    )
    raise HTTPException(status_code=429, detail=message)


# ------------------------- Financials (computed from entries) -------------------------
_FINANCIALS_CACHE_TTL_SECONDS = 30.0


def _financials_cache_key(workspace_id: str, department_ids: Optional[list] = None) -> str:
    # None = CEO bypass (all workspace rows). [] = no department access.
    # Must not collapse those cases — empty list is falsy but not "all data".
    if department_ids is None:
        return f"financials:{workspace_id}"
    scoped = ",".join(sorted(str(d) for d in department_ids))
    return f"financials:{workspace_id}:{scoped or 'none'}"


def invalidate_financials_cache(workspace_id: str) -> None:
    """Drop all cached compute_financials results for a workspace (any dept scope)."""
    if not workspace_id:
        return
    simple_cache.invalidate(f"financials:{workspace_id}")
    simple_cache.invalidate_prefix(f"financials:{workspace_id}:")
    invalidate_workspace_list_cache(workspace_id, "financials_page")


def invalidate_departments_cache(workspace_id: str) -> None:
    if not workspace_id:
        return
    simple_cache.invalidate_prefix(f"departments:{workspace_id}:")


def invalidate_plan_cache(workspace_id: str) -> None:
    if not workspace_id:
        return
    simple_cache.invalidate(f"planmeta:{workspace_id}")


# Short TTL for department list endpoints — write handlers must call
# invalidate_workspace_list_cache so CEOs see updates on the next fetch.
_DEPT_LIST_CACHE_TTL_SECONDS = 20.0


def _list_cache_key(kind: str, workspace_id: str, *parts: str) -> str:
    tail = ":".join(str(p) for p in parts if p is not None)
    return f"list:{kind}:{workspace_id}:{tail}" if tail else f"list:{kind}:{workspace_id}"


def invalidate_workspace_list_cache(workspace_id: str, *kinds: str) -> None:
    """Drop cached department list payloads after a successful write.

    This is the primary freshness guarantee; the 20s TTL is only a fallback for
    writes that bypass Trenston (e.g. external accounting sync).
    """
    if not workspace_id:
        return
    targets = kinds or (
        "production", "procurement", "legal", "maintenance", "hr",
        "deals", "people", "calendar", "reports", "tasks", "notes",
        "financials_page", "me_work",
    )
    for kind in targets:
        simple_cache.invalidate_prefix(f"list:{kind}:{workspace_id}:")
        simple_cache.invalidate(f"list:{kind}:{workspace_id}")


async def get_workspace_plan_limits(workspace_id: str, *, bypass_cache: bool = False) -> dict:
    """Workspace plan id + static limits from plans.py (60s TTL).

    Live usage counts (extracts used, seats used) are NOT cached here — only
    the plan metadata / limit ceilings that change when billing updates plan.
    """
    key = f"planmeta:{workspace_id}"

    async def loader():
        c = await db.workspaces.find_one(
            {"workspace_id": workspace_id},
            {"_id": 0, "plan": 1, "pending_plan": 1},
        ) or {}
        plan = workspace_plan_id(c)
        pdef = helm_plans.plan_def(plan)
        return {
            "plan": plan,
            "plan_label": pdef["label"],
            "features": dict(pdef["features"]),
            "seats_limit": int(pdef.get("seats") or 0),
            "ai_extracts_mo": int(pdef.get("ai_extracts_mo") or 0),
            "ai_extracts_lifetime": int(pdef.get("ai_extracts_lifetime") or 0),
            "ask_helm_mo": int(pdef.get("ask_helm_mo") or 0),
            "price": pdef.get("price"),
            "is_paid": helm_plans.is_paid_plan(plan),
            "pending_plan": c.get("pending_plan"),
        }

    if bypass_cache:
        simple_cache.invalidate(key)
    return await simple_cache.get_or_set(key, 60.0, loader)


async def _workspace_currency(workspace_id: str) -> str:
    ws = await db.workspaces.find_one({"workspace_id": workspace_id}, {"_id": 0, "financial_settings": 1})
    settings = (ws or {}).get("financial_settings") or {}
    return normalize_currency(settings.get("currency"))


async def compute_financials(
    workspace_id: str,
    department_ids: Optional[list] = None,
    *,
    return_entries: bool = False,
    bypass_cache: bool = False,
):
    from collections import defaultdict
    import finance_recurrence as fin_recur

    cache_key = _financials_cache_key(workspace_id, department_ids)

    async def loader():
        ws = await db.workspaces.find_one({"workspace_id": workspace_id}, {"_id": 0, "financial_settings": 1})
        settings = dict((ws or {}).get("financial_settings") or {})
        if not settings.get("currency"):
            settings["currency"] = "usd"
        else:
            settings["currency"] = normalize_currency(settings.get("currency"))
        currency = settings["currency"]
        entry_filt = dept_access.apply_department_filter(
            {"workspace_id": workspace_id}, department_ids,
        )
        entries = await db.financial_entries.find(entry_filt, {"_id": 0}).to_list(5000)
        # Drop invalid months; future-dated sync rows stay in DB but are excluded
        # from current burn/MRR/runway (they cannot redefine the horizon).
        valid = [e for e in entries if fin_recur.is_valid_month(str(e.get("month") or ""))]
        entries, scheduled = fin_recur.partition_ledger_entries(valid)
        horizon = fin_recur.resolve_expense_horizon(entries)
        rev_by = defaultdict(float, fin_recur.expand_entries_by_month(entries, entry_type="revenue", horizon_end=horizon))
        exp_by = defaultdict(float, fin_recur.expand_entries_by_month(entries, entry_type="expense", horizon_end=horizon))
        # Recurring-only revenue by month (for MRR) — never mix one-time sales into MRR
        rec_entries = [e for e in entries if e.get("type") == "revenue" and e.get("recurring")]
        rec_by = defaultdict(float, fin_recur.expand_entries_by_month(rec_entries, entry_type="revenue", horizon_end=horizon))
        exp_cat = defaultdict(float)
        cat_totals = fin_recur.expand_expense_category_totals(entries, horizon)
        for _month, cats in cat_totals.items():
            for cat, amt in cats.items():
                exp_cat[cat] += amt
        months = sorted(set(list(rev_by) + list(exp_by)))
        last = months[-6:]

        def lbl(m):
            return datetime.strptime(m, "%Y-%m").strftime("%b")

        revenue_series = [{"month": lbl(m), "revenue": round(rev_by[m]), "expenses": round(exp_by[m])} for m in last]
        burn_series = [{"month": lbl(m), "burn": round(exp_by[m] - rev_by[m])} for m in last]
        latest = months[-1] if months else None
        # MRR is recurring revenue only — one-time sales must not look like confirmed $0 MRR
        has_ledger = bool(entries)
        has_recurring_revenue = any(
            e.get("type") == "revenue" and e.get("recurring") for e in entries
        )
        mrr_known = has_recurring_revenue
        mrr_val = float(rec_by[latest]) if latest and mrr_known else 0.0
        cash_val = entered_cash_amount(settings)
        cash_entered = cash_val is not None
        net = [max(exp_by[m] - rev_by[m], 0) for m in months[-3:]]
        avg_burn = sum(net) / len(net) if net else 0
        burn_known = has_ledger
        # Distinct from missing data: entered ledger + cash with non-positive burn = profitable/breakeven
        runway_no_burn = bool(cash_entered and burn_known and avg_burn <= 0)
        runway = round(cash_val / avg_burn, 1) if cash_entered and avg_burn > 0 else None
        burn_val = (exp_by[latest] - rev_by[latest]) if latest else 0
        total_exp = sum(exp_cat.values())
        expense_breakdown = ([{"name": k, "value": round(v / total_exp * 100)} for k, v in sorted(exp_cat.items(), key=lambda x: -x[1])] if total_exp else [])
        gm = settings.get("gross_margin")
        scenarios = []
        if cash_entered and avg_burn > 0:
            scenarios = [
                {"name": "Base", "runway": runway, "desc": "Current net burn held."},
                {"name": "Efficient", "runway": round(cash_val / (avg_burn * 0.8), 1), "desc": "Trim burn 20%."},
                {"name": "Aggressive Hire", "runway": round(cash_val / (avg_burn * 1.4), 1), "desc": "Scale spend 40%."},
            ]
        mrr_delta = 0
        rec_months = sorted(rec_by.keys())
        if mrr_known and len(rec_months) >= 2:
            prev_m, curr_m = rec_months[-2], rec_months[-1]
            prev_r, curr_r = rec_by[prev_m], rec_by[curr_m]
            if prev_r > 0:
                mrr_delta = round((curr_r - prev_r) / prev_r * 100, 1)
        mrr_value = round(float(mrr_val or 0)) if mrr_known else None
        burn_value = round(float(burn_val or 0)) if burn_known else None
        result = {
            "mrr": fmt_money(mrr_val, currency) if mrr_known else "—",
            "arr": fmt_money(mrr_val * 12, currency) if mrr_known else "—",
            "runway_months": runway,
            "runway_no_burn": runway_no_burn,
            "burn": fmt_money(burn_val, currency) if burn_known else "—",
            "cash": fmt_money(cash_val, currency) if cash_entered else "—",
            "gross_margin": ((f"{int(gm)}%" if float(gm).is_integer() else f"{gm}%") if gm is not None else "—"),
            "revenue_series": revenue_series, "burn_series": burn_series, "scenarios": scenarios,
            "expense_breakdown": expense_breakdown, "settings": settings,
            "currency": currency, "currency_symbol": currency_symbol(currency),
            "mrr_delta": mrr_delta if mrr_known else 0,
            "spark": [r["revenue"] for r in revenue_series],
            "burn_tone": "negative" if burn_known and burn_val > 0 else "positive",
            "has_data": has_ledger,
            "mrr_known": mrr_known,
            "burn_known": burn_known,
            "cash_entered": cash_entered,
            "cash_value": cash_val,
            "mrr_value": mrr_value,
            "burn_value": burn_value,
            # Explicit three-state for display/synthesis (not_entered | zero_confirmed | computed)
            "mrr_state": _figure_state(mrr_known, mrr_value),
            "burn_state": _figure_state(burn_known, burn_value),
            "cash_state": _figure_state(cash_entered, cash_val),
            "runway_state": _runway_state(runway_months=runway, runway_no_burn=runway_no_burn),
            "months": months,
            "latest_month": latest,
            "horizon_month": horizon,
            "scheduled_count": len(scheduled),
            "scheduled_entries": [
                {
                    "id": e.get("id"),
                    "month": e.get("month"),
                    "type": e.get("type"),
                    "name": normalize_entry_name(e.get("name"), e.get("category")),
                    "category": e.get("category"),
                    "amount": e.get("amount"),
                    "source": e.get("source"),
                }
                for e in scheduled[:50]
            ],
        }
        # Metrics use current/past only; return_entries keeps that set for signal reuse.
        return {"fin": result, "entries": list(entries)}

    if bypass_cache:
        simple_cache.invalidate(cache_key)
        payload = await loader()
    else:
        payload = await simple_cache.get_or_set(cache_key, _FINANCIALS_CACHE_TTL_SECONDS, loader)

    fin = dict(payload["fin"])
    if return_entries:
        fin["entries"] = list(payload["entries"])
    return fin


RUNWAY_NO_BURN_LABEL = "No burn — cash growing"

FIGURE_NOT_ENTERED = "not_entered"
FIGURE_ZERO_CONFIRMED = "zero_confirmed"
FIGURE_COMPUTED = "computed"


def _figure_state(known: bool, value) -> str:
    """Three-state for figures that can be unset vs confirmed zero vs computed."""
    if not known or value is None:
        return FIGURE_NOT_ENTERED
    try:
        if float(value) == 0:
            return FIGURE_ZERO_CONFIRMED
    except (TypeError, ValueError):
        return FIGURE_COMPUTED
    return FIGURE_COMPUTED


def _runway_state(*, runway_months, runway_no_burn: bool) -> str:
    if runway_months is not None:
        try:
            if float(runway_months) == 0:
                return FIGURE_ZERO_CONFIRMED
        except (TypeError, ValueError):
            pass
        return FIGURE_COMPUTED
    if runway_no_burn:
        # Profitable / breakeven with cash entered — confirmed non-positive burn.
        return FIGURE_ZERO_CONFIRMED
    return FIGURE_NOT_ENTERED


def format_runway_display(fin: dict, *, missing: str = "Add data") -> str:
    """Human runway label: months, profitable/breakeven, or missing-data copy."""
    if fin.get("runway_months") is not None:
        return f"{fin['runway_months']} months"
    if fin.get("runway_no_burn"):
        return RUNWAY_NO_BURN_LABEL
    return missing


def format_mrr_display(fin: dict, *, missing: str = "Add data") -> str:
    """MRR label: formatted amount, confirmed $0, or missing-data copy — never fake $0."""
    if not fin.get("mrr_known"):
        return missing
    return fin.get("mrr") if fin.get("mrr") not in (None, "") else missing


def format_burn_display(fin: dict, *, missing: str = "Add data") -> str:
    if not fin.get("burn_known"):
        return missing
    return fin.get("burn") if fin.get("burn") not in (None, "") else missing


def financials_for_synthesis(fin: dict) -> dict:
    """Numbers for AI prompts: missing fields stay null instead of looking like $0."""
    cash_entered = bool(fin.get("cash_entered"))
    mrr_known = bool(fin.get("mrr_known"))
    burn_known = bool(fin.get("burn_known"))
    runway = fin.get("runway_months")
    runway_no_burn = bool(fin.get("runway_no_burn"))
    unknown = []
    if not cash_entered:
        unknown.append("cash_balance_not_entered")
    if not mrr_known:
        unknown.append("revenue_not_entered")
    if not burn_known:
        unknown.append("burn_not_entered")
    if runway is None and not runway_no_burn:
        unknown.append("runway_not_computable")
    return {
        "cash": fin.get("cash_value") if cash_entered else None,
        "cash_entered": cash_entered,
        "mrr": fin.get("mrr_value") if mrr_known else None,
        "mrr_known": mrr_known,
        "burn": fin.get("burn_value") if burn_known else None,
        "burn_known": burn_known,
        "runway_months": runway,
        "runway_no_burn": runway_no_burn,
        "currency": fin.get("currency") or "usd",
        "unknown_fields": unknown,
        "instructions_for_missing_data": (
            "Fields that are null were never entered — they are not zero. "
            "If cash_entered is false, tell the CEO to add a cash balance on Financials "
            "to get an accurate runway picture. Never say they are out of runway, have "
            "zero cash, or are technically out of money when cash was not entered. "
            "Urgent out-of-runway language is allowed only when cash_entered is true and "
            "runway_months is a real number (including 0). If runway_no_burn is true, "
            "net burn is zero or negative with cash entered — say cash is growing / no "
            "burn, not that runway is missing. If mrr_known is false, recurring revenue was never "
            "logged (expense-only or one-time sales are not confirmed $0 MRR). If burn_known is false, "
            "say burn is not in Trenston yet."
        ),
    }


def company_profile_for_synthesis(c: dict) -> dict:
    """Stage/headcount for AI: blank or default-zero is not a measured 0-person company."""
    stage = (c.get("stage") or "").strip() or None
    employees_entered = bool(c.get("employees_entered"))
    raw_employees = c.get("employees")
    unknown = []
    if stage is None:
        unknown.append("stage")
    if employees_entered:
        employees = 0 if raw_employees is None else raw_employees
    elif raw_employees in (None, 0, "0"):
        employees = None
        unknown.append("employees")
    else:
        employees = raw_employees
    return {
        "name": c.get("name"),
        "stage": stage,
        "employees": employees,
        "employees_entered": employees_entered,
        "unknown_fields": unknown,
        "instructions_for_missing_data": (
            "Null stage or employees were never entered — they are not zero. "
            "Do not call this a 0-person company or invent a funding stage."
            if unknown
            else ""
        ),
    }


def calendar_for_synthesis(cal_snap: Optional[dict], *, google_connected: bool = False) -> dict:
    """Calendar for AI: not connected / fetch failure is not the same as a free day."""
    unavailable = (
        "Google Calendar could not be loaded. Do not invent meetings and do not "
        "say the founder has a free day. Say calendar data is not available."
    )
    not_connected = (
        "Google Calendar is not connected. Do not invent meetings and do not "
        "say the founder has a free day. Say calendar data is not available."
    )
    snap = cal_snap or {}
    live = bool(cal_snap) and snap.get("live") is not False and snap.get("meetings") is not None
    if live:
        all_meetings = snap.get("meetings") or []
        meetings = [
            {"time": m.get("time"), "title": m.get("title"), "duration": m.get("duration")}
            for m in all_meetings[:8]
        ]
        return {
            "connected": True,
            "meetings": meetings,
            "meeting_count": len(all_meetings),
            "unknown_fields": [],
            "instructions_for_missing_data": "",
        }
    failed = google_connected or snap.get("live") is False or snap.get("auth_error") or snap.get("fetch_error")
    return {
        "connected": bool(google_connected or snap.get("live") is False or snap.get("auth_error")),
        "meetings": None,
        "meeting_count": None,
        "unknown_fields": ["calendar"],
        "instructions_for_missing_data": unavailable if failed else not_connected,
    }


def pipeline_for_synthesis(deals, *, sales_tracked: bool) -> dict:
    """Pipeline for AI: Sales off + no deals is not the same as a $0 pipeline."""
    deals = list(deals or [])
    annotated = helm_freshness.annotate_possibly_stale(
        deals, dept_type=dept_catalog.TYPE_SALES,
    ) if deals or sales_tracked else []
    if not annotated and not sales_tracked:
        return {
            "tracked": False,
            "deal_count": None,
            "open_value": None,
            "possibly_stale_count": None,
            "unknown_fields": ["sales_pipeline"],
            "instructions_for_missing_data": (
                "Sales pipeline is not tracked in this workspace. Do not say pipeline "
                "is $0 or that there are no deals as if that was measured. Say pipeline "
                "data is not available."
            ),
        }
    normalized = []
    for d in annotated:
        try:
            value = float(d.get("value") or 0)
        except (TypeError, ValueError):
            value = 0.0
        normalized.append({"stage": d.get("stage") or "lead", "value": value})
    metrics = _deal_metrics(normalized)
    stale_count = helm_freshness.count_possibly_stale(annotated)
    return {
        "tracked": True,
        "deal_count": metrics["open_count"],
        "open_value": metrics["open_value"],
        "possibly_stale_count": stale_count,
        "unknown_fields": [],
        "instructions_for_missing_data": (
            "If possibly_stale_count is greater than zero, say some open deals may be "
            "outdated rather than treating every count as freshly updated."
            if stale_count else ""
        ),
    }


def onboarding_for_synthesis(instances, *, hr_tracked: bool) -> dict:
    """HR onboarding for AI: HR unused is not the same as zero hires onboarding."""
    instances = list(instances or [])
    annotated = helm_freshness.annotate_possibly_stale(
        instances, dept_type=dept_catalog.TYPE_HR,
    ) if instances or hr_tracked else []
    if not annotated and not hr_tracked:
        return {
            "tracked": False,
            "instance_count": None,
            "possibly_stale_count": None,
            "unknown_fields": ["hr_onboarding"],
            "instructions_for_missing_data": (
                "HR onboarding is not used in this workspace. Do not say there are no "
                "hires onboarding as if that was measured. Say onboarding tracking is "
                "not available."
            ),
        }
    # "active" means the hire finished onboarding — not currently in the pipeline.
    in_progress = [i for i in annotated if (i.get("overall_status") or "in_progress") != "active"]
    stale_count = helm_freshness.count_possibly_stale(in_progress)
    return {
        "tracked": True,
        "instance_count": len(in_progress),
        "possibly_stale_count": stale_count,
        "unknown_fields": [],
        "instructions_for_missing_data": (
            "If possibly_stale_count is greater than zero, say some open onboardings may be "
            "outdated rather than treating every count as freshly updated."
            if stale_count else ""
        ),
    }


def _ask_dept_restricted(note: str) -> dict:
    return {"access": "restricted", "note": note}


def _status_histogram(rows, key: str = "status") -> dict:
    out: dict[str, int] = {}
    for r in rows or []:
        st = str(r.get(key) or "unknown").strip().lower() or "unknown"
        out[st] = out.get(st, 0) + 1
    return out


def dept_queue_for_synthesis(
    rows,
    *,
    tracked: bool,
    field_name: str,
    open_statuses: Optional[frozenset] = None,
    status_key: str = "status",
    empty_label: str = "This department queue",
    dept_type: Optional[str] = None,
) -> dict:
    """Compact status counts for Ask Trenston — no row-level PII beyond aggregates."""
    rows = list(rows or [])
    annotated = helm_freshness.annotate_possibly_stale(
        rows, dept_type=dept_type,
    ) if rows or tracked else []
    if not annotated and not tracked:
        return {
            "tracked": False,
            "open_count": None,
            "total_count": None,
            "by_status": None,
            "possibly_stale_count": None,
            "unknown_fields": [field_name],
            "instructions_for_missing_data": (
                f"{empty_label} is not tracked in this workspace. Do not invent items "
                "or treat an empty list as measured. Say this data is not available."
            ),
        }
    by_status = _status_histogram(annotated, status_key)
    if open_statuses is not None:
        open_rows = [
            r for r in annotated
            if str(r.get(status_key) or "").strip().lower() in open_statuses
        ]
        open_count = len(open_rows)
        stale_count = helm_freshness.count_possibly_stale(open_rows)
    else:
        open_count = len(annotated)
        stale_count = helm_freshness.count_possibly_stale(annotated)
    return {
        "tracked": True,
        "open_count": open_count,
        "total_count": len(annotated),
        "by_status": by_status,
        "possibly_stale_count": stale_count,
        "unknown_fields": [],
        "instructions_for_missing_data": (
            "If possibly_stale_count is greater than zero, say some open items may be "
            "outdated rather than treating every count as freshly updated."
            if stale_count else ""
        ),
    }


def _ask_slice_context(
    rows,
    *,
    enabled: bool,
    visible: bool,
    field_name: str,
    restricted_note: str,
    open_statuses: Optional[frozenset] = None,
    status_key: str = "status",
    empty_label: str = "This department queue",
    dept_type: Optional[str] = None,
    legacy_builder=None,
):
    """Enabled → membership → data. Disabled → not tracked. No access → restricted."""
    if not enabled:
        if legacy_builder is not None:
            return legacy_builder([], tracked=False)
        return dept_queue_for_synthesis(
            [],
            tracked=False,
            field_name=field_name,
            open_statuses=open_statuses,
            status_key=status_key,
            empty_label=empty_label,
            dept_type=dept_type,
        )
    if not visible:
        return _ask_dept_restricted(restricted_note)
    if legacy_builder is not None:
        return legacy_builder(rows, tracked=True)
    return dept_queue_for_synthesis(
        rows,
        tracked=True,
        field_name=field_name,
        open_statuses=open_statuses,
        status_key=status_key,
        empty_label=empty_label,
        dept_type=dept_type,
    )


_ASK_HELM_ACCESS_LOOKUP = object()


async def _ask_helm_department_slice(
    principal: dict,
    dept_type: str,
    collection_attr: str,
    *,
    enabled_dept: Optional[dict] = None,
    access_ids: Any = _ASK_HELM_ACCESS_LOOKUP,
):
    """Load Ask Trenston rows with the same membership rule as department pages.

    Returns ``(rows, enabled, visible)``. CEO → visible with unfiltered ids (None bypass).

    Pass ``enabled_dept`` / ``access_ids`` from a batched lookup to skip per-type queries.
    Omit ``access_ids`` (default) to look up; pass ``None`` for CEO bypass.
    """
    ws_id = principal["workspace_id"]
    if enabled_dept is None and access_ids is _ASK_HELM_ACCESS_LOOKUP:
        dept = await dept_migrate.get_enabled_department(db, ws_id, dept_type)
    else:
        dept = enabled_dept
    if not dept:
        return [], False, False
    if access_ids is _ASK_HELM_ACCESS_LOOKUP:
        ids = await dept_access.accessible_department_ids(db, principal, dept_type)
    else:
        ids = access_ids
    visible = ids is None or len(ids) > 0
    if not visible:
        return [], True, False
    coll = getattr(db, collection_attr)
    filt = dept_access.apply_department_filter({"workspace_id": ws_id}, ids)
    rows = await coll.find(filt, {"_id": 0}).to_list(500)
    return rows, True, True


def risks_for_synthesis(c: dict) -> dict:
    """Risk radar for AI: seeded sample risks are not workspace-entered facts."""
    manual = c.get("telemetry_manual") or {}
    if manual.get("risks") is not None:
        return {
            "tracked": True,
            "items": list(manual.get("risks") or []),
            "unknown_fields": [],
            "instructions_for_missing_data": "",
        }
    return {
        "tracked": False,
        "items": None,
        "unknown_fields": ["risk_radar"],
        "instructions_for_missing_data": (
            "Risk radar has not been filled in by this workspace. Do not invent risks "
            "or treat a sample list as real. Say risk tracking is not in Trenston yet."
        ),
    }


def company_context_for_synthesis(c: dict, fin: dict) -> dict:
    """Decision-draft company payload: finance + profile, with missing-data instructions."""
    profile = company_profile_for_synthesis(c)
    nums = financials_for_synthesis(fin)
    unknown = list(dict.fromkeys([*profile["unknown_fields"], *nums["unknown_fields"]]))
    instructions = " ".join(
        part for part in (
            profile.get("instructions_for_missing_data"),
            nums.get("instructions_for_missing_data"),
        ) if part
    )
    return {
        "name": profile.get("name"),
        "stage": profile.get("stage"),
        "employees": profile.get("employees"),
        "cash": nums.get("cash"),
        "cash_entered": nums.get("cash_entered"),
        "mrr": nums.get("mrr"),
        "mrr_known": nums.get("mrr_known"),
        "burn": nums.get("burn"),
        "burn_known": nums.get("burn_known"),
        "runway_months": nums.get("runway_months"),
        "currency": nums.get("currency"),
        "unknown_fields": unknown,
        "instructions_for_missing_data": instructions,
    }


def ask_context_for_synthesis(
    c: dict,
    fin: dict,
    *,
    deals=None,
    sales_tracked: bool = False,
    onboarding_instances=None,
    hr_tracked: bool = False,
    financials_visible: bool = True,
    sales_visible: bool = True,
    hr_visible: bool = True,
    sales_enabled: Optional[bool] = None,
    hr_enabled: Optional[bool] = None,
    production_rows=None,
    production_enabled: bool = False,
    production_visible: bool = True,
    procurement_rows=None,
    procurement_enabled: bool = False,
    procurement_visible: bool = True,
    legal_rows=None,
    legal_enabled: bool = False,
    legal_visible: bool = True,
    maintenance_rows=None,
    maintenance_enabled: bool = False,
    maintenance_visible: bool = True,
) -> dict:
    """Ask Trenston snapshot: live facts only, with unknown vs confirmed-zero distinguished.

    Department-backed slices are omitted or marked restricted unless the requester
    can access that department — same membership rule as the department pages
    (CEO sees all enabled departments). Finance uses the Financials section grant
    (``financials_visible``), not department membership alone.
    """
    profile = company_profile_for_synthesis(c)
    roster = ((c.get("people") or {}).get("people") or [])
    if financials_visible:
        financials_ctx = financials_for_synthesis(fin)
    else:
        financials_ctx = _ask_dept_restricted(
            "Financial figures are not shared with this user's role.",
        )

    # Back-compat: older callers passed sales_tracked/hr_tracked without enabled flags.
    # Visibility alone must not invent a tracked queue when the department is off.
    if sales_enabled is None:
        sales_enabled = bool(sales_tracked)
    if hr_enabled is None:
        hr_enabled = bool(hr_tracked)

    pipeline_ctx = _ask_slice_context(
        deals,
        enabled=sales_enabled,
        visible=sales_visible,
        field_name="sales_pipeline",
        restricted_note="Sales pipeline is not shared with this user's role.",
        empty_label="Sales pipeline",
        legacy_builder=lambda rows, tracked: pipeline_for_synthesis(rows, sales_tracked=tracked),
    )
    onboarding_ctx = _ask_slice_context(
        onboarding_instances,
        enabled=hr_enabled,
        visible=hr_visible,
        field_name="hr_onboarding",
        restricted_note="HR onboarding data is not shared with this user's role.",
        empty_label="HR onboarding",
        legacy_builder=lambda rows, tracked: onboarding_for_synthesis(rows, hr_tracked=tracked),
    )
    production_ctx = _ask_slice_context(
        production_rows,
        enabled=production_enabled,
        visible=production_visible,
        field_name="production_queue",
        restricted_note="Production data is not shared with this user's role.",
        open_statuses=frozenset({"awaiting_materials", "in_production", "quality_check"}),
        empty_label="Production",
        dept_type=dept_catalog.TYPE_PRODUCTION,
    )
    procurement_ctx = _ask_slice_context(
        procurement_rows,
        enabled=procurement_enabled,
        visible=procurement_visible,
        field_name="procurement_queue",
        restricted_note="Procurement data is not shared with this user's role.",
        open_statuses=frozenset({"requested", "approved", "ordered"}),
        empty_label="Procurement",
        dept_type=dept_catalog.TYPE_PROCUREMENT,
    )
    legal_ctx = _ask_slice_context(
        legal_rows,
        enabled=legal_enabled,
        visible=legal_visible,
        field_name="legal_queue",
        restricted_note="Legal data is not shared with this user's role.",
        open_statuses=frozenset({"draft", "internal_review", "counterparty_review"}),
        empty_label="Legal",
        dept_type=dept_catalog.TYPE_LEGAL,
    )
    maintenance_ctx = _ask_slice_context(
        maintenance_rows,
        enabled=maintenance_enabled,
        visible=maintenance_visible,
        field_name="maintenance_queue",
        restricted_note="Engineering & Maintenance data is not shared with this user's role.",
        open_statuses=frozenset({"reported", "diagnosed", "in_repair"}),
        empty_label="Engineering & Maintenance",
        dept_type=dept_catalog.TYPE_ENGINEERING_MAINTENANCE,
    )

    in_context = ["financials", "sales_pipeline", "hr_onboarding",
                  "production", "procurement", "legal", "maintenance"]
    return {
        "company": profile.get("name"),
        "company_profile": profile,
        # People-roster length is computed — 0 means nobody on the list, not "headcount not entered".
        "people_count": len(roster),
        "financials": financials_ctx,
        "pipeline": pipeline_ctx,
        "onboarding": onboarding_ctx,
        "production": production_ctx,
        "procurement": procurement_ctx,
        "legal": legal_ctx,
        "maintenance": maintenance_ctx,
        "risks": risks_for_synthesis(c),
        # Pending decision titles are a computed list of existing cards — empty means
        # none are pending, not that the Decision Center was never used.
        "open_decisions": [
            d.get("title") for d in (c.get("decisions") or []) if d.get("status") == "pending"
        ],
        "department_data_in_context": in_context,
    }


# ------------------------- Auth routes -------------------------
class SessionInput(BaseModel):
    session_id: str


async def _find_user_by_identity(
    email: str,
    google_sub: Optional[str] = None,
    clerk_id: Optional[str] = None,
):
    """Stable identity: Clerk id / Google sub first, then normalized email."""
    if clerk_id:
        by_clerk = await db.users.find_one({"clerk_id": clerk_id}, {"_id": 0})
        if by_clerk:
            return by_clerk
    if google_sub:
        by_sub = await db.users.find_one({"google_sub": google_sub}, {"_id": 0})
        if by_sub:
            return by_sub
    if not email:
        return None
    by_email = await db.users.find_one({"email": email}, {"_id": 0})
    if by_email:
        return by_email
    return await db.users.find_one(
        {"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}}, {"_id": 0}
    )


async def _upsert_clerk_user(*, email: str, name: Optional[str], picture: Optional[str], clerk_id: str):
    email = _normalize_email(email)
    if not email or not clerk_id:
        raise HTTPException(status_code=400, detail="Clerk account email is required")
    existing = await _find_user_by_identity(email, clerk_id=clerk_id)
    now = datetime.now(timezone.utc).isoformat()
    if existing:
        user_id = existing["user_id"]
        updates = {
            "email": email,
            "name": name or existing.get("name"),
            "picture": picture or existing.get("picture"),
            "clerk_id": clerk_id,
        }
        await db.users.update_one({"user_id": user_id}, {"$set": updates})
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": user_id, "email": email, "name": name, "picture": picture,
            "clerk_id": clerk_id, "appearance": "light", "created_at": now,
        })
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    await _bootstrap(user)
    return user


async def _upsert_google_user(*, email: str, name: Optional[str], picture: Optional[str], google_sub: Optional[str]):
    email = _normalize_email(email)
    if not email:
        raise HTTPException(status_code=400, detail="Google account email is required")
    existing = await _find_user_by_identity(email, google_sub)
    now = datetime.now(timezone.utc).isoformat()
    if existing:
        user_id = existing["user_id"]
        updates = {"email": email, "name": name or existing.get("name"), "picture": picture or existing.get("picture")}
        if google_sub:
            updates["google_sub"] = google_sub
        await db.users.update_one({"user_id": user_id}, {"$set": updates})
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": user_id, "email": email, "name": name, "picture": picture,
            "google_sub": google_sub, "appearance": "light", "created_at": now,
        })
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    await _bootstrap(user)
    return user


async def _issue_session(response: Response, user_id: str) -> str:
    session_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await db.user_sessions.insert_one({
        "user_id": user_id, "session_token": session_token,
        "expires_at": expires_at, "created_at": datetime.now(timezone.utc),
    })
    set_session_cookie(response, session_token)
    return session_token


def _auth_redirect_uri(_request: Request) -> str:
    return f"{public_api_origin()}/api/auth/google/callback"


def _oauth_callback_uri(provider: str) -> str:
    return f"{public_api_origin()}/api/oauth/{provider}/callback"


@api_router.get("/auth/config")
async def auth_config():
    clerk_on = clerk_auth.clerk_configured()
    google_on = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET) and not clerk_on
    provider = "clerk" if clerk_on else ("google" if google_on else "none")
    clerk_mode = clerk_auth.clerk_secret_mode() if clerk_on else None
    keys_aligned = (
        clerk_auth.clerk_keys_aligned(CLERK_PUBLISHABLE_KEY, clerk_auth.CLERK_JWKS_URL)
        if clerk_on and CLERK_PUBLISHABLE_KEY
        else None
    )
    mode_match = (
        clerk_auth.clerk_secret_publishable_mode_match(CLERK_PUBLISHABLE_KEY)
        if clerk_on and CLERK_PUBLISHABLE_KEY
        else None
    )
    ssl_ok = api_ok = jwks_ok = None
    signup_policy: dict = {}
    if clerk_on:
        # Probe Clerk in parallel + TTL cache (see clerk_auth) — was ~1.5s sequential.
        ssl_ok, api_ok, jwks_ok, signup_policy = await asyncio.gather(
            clerk_auth.clerk_custom_domain_ssl_ok(),
            clerk_auth.clerk_api_ok(),
            clerk_auth.clerk_jwks_ok(),
            clerk_auth.clerk_signup_policy(),
        )
    return {
        "demo_login": ALLOW_DEMO_LOGIN,
        "clerk_enabled": clerk_on,
        "clerk_secret_mode": clerk_mode if clerk_on else None,
        "clerk_publishable_key": CLERK_PUBLISHABLE_KEY or None,
        "clerk_jwks_host": clerk_auth.clerk_jwks_host(),
        "clerk_keys_aligned": keys_aligned,
        "clerk_secret_mode_match": mode_match,
        "clerk_primary_origin": clerk_auth.clerk_primary_origin() if clerk_on else None,
        "clerk_post_auth_url": clerk_auth.clerk_post_auth_url() if clerk_on else None,
        "helm_canonical_origin": TRENSTON_CANONICAL_ORIGIN,
        "clerk_multi_domain": clerk_auth.clerk_multi_domain_auth() if clerk_on else False,
        "clerk_api_ok": api_ok,
        "clerk_jwks_ok": jwks_ok,
        "clerk_custom_domain_ssl_ok": ssl_ok,
        "clerk_proxy_url": clerk_auth.clerk_proxy_url() if clerk_on else None,
        "clerk_use_proxy": (not ssl_ok) if clerk_on else None,
        "clerk_password_min_length": signup_policy.get("password_min_length") if clerk_on else None,
        "clerk_captcha_enabled": signup_policy.get("captcha_enabled") if clerk_on else None,
        "google_oauth": google_on,
        "provider": provider,
        "ai_ready": helm_llm.anthropic_configured(),
        "billing_enforced": BILLING_ENFORCED,
    }


@api_router.post("/auth/clerk")
async def clerk_login(request: Request, response: Response):
    if not clerk_auth.clerk_configured():
        raise HTTPException(status_code=400, detail="Clerk is not configured")
    await _require_mongo()
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.startswith("Bearer ") else ""
    if not token:
        raise HTTPException(status_code=401, detail="Missing Clerk session token")
    try:
        identity = await clerk_auth.verify_clerk_session_token(token)
    except ValueError as exc:
        logger.warning("clerk token verification failed: %s", exc)
        raise HTTPException(status_code=401, detail=str(exc))
    except Exception:
        logger.exception("clerk token verification failed")
        raise HTTPException(
            status_code=401,
            detail="Invalid Clerk session. Check Render CLERK_SECRET_KEY matches your pk_live key",
        )
    user = await _upsert_clerk_user(
        email=identity["email"],
        name=identity.get("name"),
        picture=identity.get("picture"),
        clerk_id=identity["clerk_id"],
    )
    await _issue_session(response, user["user_id"])
    return {"ok": True, "user_id": user["user_id"], "email": user["email"]}


@api_router.post("/auth/session")
async def process_session_removed():
    raise HTTPException(
        status_code=410,
        detail="Emergent session auth is retired. Use Google sign-in via /api/auth/google/login.",
    )


@api_router.post("/auth/demo-login")
async def demo_login_removed():
    raise HTTPException(status_code=410, detail="Demo login is disabled for production.")


@api_router.get("/auth/google/login")
async def google_login(request: Request, redirect: Optional[str] = None):
    if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET):
        raise HTTPException(status_code=400, detail="Google OAuth not configured")
    dest = redirect or (f"{APP_URL}/app" if APP_URL else "/app")
    if not _allowed_auth_redirect(dest):
        raise HTTPException(status_code=400, detail="Invalid redirect URL")
    state = jwt.encode(
        {
            "redirect": dest,
            "ts": int(datetime.now(timezone.utc).timestamp()),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        },
        OAUTH_STATE_SECRET, algorithm="HS256",
    )
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": _auth_redirect_uri(request),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}")


@api_router.get("/auth/google/callback")
async def google_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    fail = f"{APP_URL or ''}/login?error=oauth"
    if error or not code or not state:
        return RedirectResponse(fail)
    try:
        payload = jwt.decode(state, OAUTH_STATE_SECRET, algorithms=["HS256"])
    except Exception:
        return RedirectResponse(fail)
    dest = payload.get("redirect") or (f"{APP_URL}/app" if APP_URL else "/app")
    if not _allowed_auth_redirect(dest):
        return RedirectResponse(fail)
    try:
        async with httpx.AsyncClient(timeout=30) as hc:
            token_res = await hc.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": _auth_redirect_uri(request),
                    "grant_type": "authorization_code",
                },
            )
            if token_res.status_code >= 400:
                logger.error("google token exchange failed with status %s", token_res.status_code)
                return RedirectResponse(fail)
            tokens = token_res.json()
            access = tokens.get("access_token")
            if not access:
                return RedirectResponse(fail)
            info_res = await hc.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access}"},
            )
            if info_res.status_code >= 400:
                logger.error("google userinfo failed with status %s", info_res.status_code)
                return RedirectResponse(fail)
            info = info_res.json()
        user = await _upsert_google_user(
            email=info.get("email"),
            name=info.get("name"),
            picture=info.get("picture"),
            google_sub=info.get("sub"),
        )
        response = RedirectResponse(dest)
        await _issue_session(response, user["user_id"])
        return response
    except HTTPException:
        return RedirectResponse(fail)
    except Exception:
        logger.exception("google oauth callback failed")
        return RedirectResponse(fail)


async def _user_session_payload(user: dict) -> dict:
    base = {
        "user_id": user["user_id"],
        "email": user["email"],
        "name": user.get("name"),
        "picture": user.get("picture"),
        "appearance": _normalize_appearance(user.get("appearance")),
        "age_confirmed": bool(user.get("age_confirmed")),
    }
    active = user.get("active_workspace_id")
    membership = None
    if active:
        membership = await db.memberships.find_one(
            {"user_id": user["user_id"], "workspace_id": active, "status": "active"}, {"_id": 0})
    if not membership:
        membership = await db.memberships.find_one(
            {"user_id": user["user_id"], "status": "active"}, {"_id": 0})
        if membership:
            await db.users.update_one(
                {"user_id": user["user_id"]},
                {"$set": {"active_workspace_id": membership["workspace_id"]}},
            )
    if not membership:
        return {
            **base,
            "workspace_id": None,
            "needs_workspace": True,
            "role": None,
            "pack": None,
            "perms": [],
            "granted_sections": [],
            "default_route": "/app/welcome",
            "pack_label": None,
        }
    pack = pack_of(membership)
    principal_like = {
        "user_id": user["user_id"],
        "email": user["email"],
        "name": user.get("name"),
        "workspace_id": membership["workspace_id"],
        "role": membership["role"],
        "pack": pack,
    }
    granted_sections = []
    # Hoist membership + workspace once — can_section_write used to re-fetch both
    # per MANAGEABLE_SECTIONS item (16 sequential round-trips on every /auth/me).
    ws_for_grants = await get_ws(membership["workspace_id"])
    for item in sec_access.MANAGEABLE_SECTIONS:
        if await can_section_write(
            principal_like,
            item["id"],
            item["perm"],
            membership=membership,
            workspace=ws_for_grants,
        ):
            granted_sections.append(item["id"])
    payload = {
        **base,
        "workspace_id": membership["workspace_id"],
        "needs_workspace": False,
        "role": membership["role"],
        "pack": pack,
        "perms": sorted(perms_for(pack)),
        "granted_sections": granted_sections,
        "default_route": PACK_HOME.get(pack, "/app"),
        "pack_label": PACK_LABEL.get(pack, "Member"),
    }
    by_user = await dept_access.department_names_by_user_id(db, membership["workspace_id"])
    dept_access.attach_real_departments(payload, by_user.get(user["user_id"]) or [])
    return payload


def _bearer_token(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    return auth[7:].strip() if auth.startswith("Bearer ") else ""


@api_router.post("/auth/clerk/exchange")
async def clerk_exchange(request: Request, response: Response):
    """Clerk JWT → Trenston session payload (+ optional httpOnly cookie)."""
    if not clerk_auth.clerk_configured():
        raise HTTPException(status_code=400, detail="Clerk is not configured")
    await _require_mongo()
    if CLERK_PUBLISHABLE_KEY and not clerk_auth.clerk_secret_publishable_mode_match(CLERK_PUBLISHABLE_KEY):
        raise HTTPException(
            status_code=503,
            detail=(
                f"CLERK_SECRET_KEY is {clerk_auth.clerk_secret_mode() or 'unknown'} but the publishable key "
                "is a different mode. Use matching sk_live_/pk_live_ keys from the same Clerk instance on Render"
            ),
        )
    if not await clerk_auth.clerk_jwks_ok():
        raise HTTPException(
            status_code=503,
            detail="Clerk signing keys unavailable. Check CLERK_SECRET_KEY on Render matches clerk.trenston.com",
        )
    token = _bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing Clerk session token")
    if not _looks_like_jwt(token):
        raise HTTPException(
            status_code=401,
            detail="Clerk returned a non-JWT token. Try signing out and back in",
        )
    user = await _user_from_clerk_jwt(token)
    await _issue_session(response, user["user_id"])
    return await _user_session_payload(user)


@api_router.get("/auth/me")
async def auth_me(user=Depends(get_user)):
    return await _user_session_payload(user)


@api_router.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    clear_session_cookie(response)
    return {"ok": True}


# ------------------------- Workspaces & members -------------------------
@api_router.get("/workspaces")
async def list_workspaces(principal=Depends(get_principal)):
    mems = await db.memberships.find({"user_id": principal["user_id"], "status": "active"}, {"_id": 0}).to_list(50)
    out = []
    by_ws = await _docs_by_key(
        db.workspaces,
        "workspace_id",
        [m["workspace_id"] for m in mems],
        {"_id": 0, "name": 1, "workspace_id": 1, "plan": 1},
    )
    for m in mems:
        ws = by_ws.get(m["workspace_id"])
        if ws:
            out.append({"workspace_id": ws["workspace_id"], "name": ws["name"], "plan": ws["plan"],
                        "role": m["role"], "active": ws["workspace_id"] == principal["workspace_id"]})
    return {"workspaces": out}


class SwitchInput(BaseModel):
    workspace_id: str


@api_router.post("/workspaces/switch")
async def switch_workspace(payload: SwitchInput, principal=Depends(get_principal)):
    m = await db.memberships.find_one({"user_id": principal["user_id"], "workspace_id": payload.workspace_id, "status": "active"}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Workspace not found")
    await db.users.update_one({"user_id": principal["user_id"]}, {"$set": {"active_workspace_id": payload.workspace_id}})
    return {"ok": True, "workspace_id": payload.workspace_id}


class CreateWsInput(BaseModel):
    name: str
    referral_code: Optional[str] = None


@api_router.post("/workspaces")
async def create_workspace(payload: CreateWsInput, user=Depends(get_user)):
    user_doc = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "age_confirmed": 1})
    if not (user_doc or {}).get("age_confirmed"):
        raise HTTPException(
            status_code=403,
            detail="Confirm you are 18 or older (or using Trenston under a parent/guardian) before creating a company",
        )
    ws_id = f"ws_{uuid.uuid4().hex[:12]}"
    doc = build_workspace(ws_id, payload.name.strip() or "New Company", user["user_id"], empty=True)
    await db.workspaces.insert_one(doc)
    membership = {
        "membership_id": f"mem_{uuid.uuid4().hex[:12]}", "workspace_id": ws_id,
        "user_id": user["user_id"], "email": user["email"], "role": "owner",
        "pack": "owner", "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.memberships.insert_one(membership)
    await ensure_person_for_membership(ws_id, membership, name=user.get("name"))
    await dept_migrate.migrate_workspace_sales_finance(db, ws_id)
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"active_workspace_id": ws_id}})
    try:
        await helm_referrals.attribute_signup(
            db,
            referral_code=payload.referral_code,
            new_user=user,
            new_workspace={"workspace_id": ws_id},
        )
    except Exception:
        logger.exception("referral attribution failed for workspace %s", ws_id)
        try:
            await helm_referrals.attribute_signup(
                db,
                referral_code=payload.referral_code,
                new_user=user,
                new_workspace={"workspace_id": ws_id},
            )
        except Exception:
            logger.exception("referral attribution retry failed for workspace %s", ws_id)
    return {"ok": True, "workspace_id": ws_id}


class ReferralInviteInput(BaseModel):
    email: Optional[EmailStr] = None


def _require_workspace_owner(principal: dict):
    if principal.get("role") != "owner" and principal.get("pack") != "owner":
        raise HTTPException(status_code=403, detail="Only the workspace owner can manage referrals")
    return principal


async def _referral_payload(principal: dict) -> dict:
    code = await helm_referrals.ensure_referral_code(db, principal["user_id"])
    return {
        "referral_code": code,
        "share_url": helm_referrals.share_url(_app_base_url(), code),
        "referrals": await helm_referrals.list_referrals_for_user(db, principal["user_id"]),
    }


@api_router.get("/referrals")
async def get_referrals(principal=Depends(get_principal)):
    _require_workspace_owner(principal)
    return await _referral_payload(principal)


@api_router.post("/referrals")
async def create_or_fetch_referral(payload: ReferralInviteInput | None = None, principal=Depends(get_principal)):
    _require_workspace_owner(principal)
    if payload and payload.email:
        await helm_referrals.record_sent_invite(
            db,
            referrer_user_id=principal["user_id"],
            referrer_workspace_id=principal["workspace_id"],
            referred_email=str(payload.email),
        )
    return await _referral_payload(principal)


class JoinInput(BaseModel):
    code: str


async def _find_workspace_by_join_code(code: str):
    """Match invite codes case-insensitively so pasted codes always work."""
    c = (code or "").strip()
    if not c:
        return None
    ws = await db.workspaces.find_one({"join_code": c}, {"_id": 0})
    if ws:
        return ws
    rows = await db.workspaces.find(
        {"join_code": {"$regex": f"^{re.escape(c)}$", "$options": "i"}},
        {"_id": 0},
    ).to_list(1)
    return rows[0] if rows else None


@api_router.get("/workspaces/join-info")
async def join_info(code: str, user=Depends(get_user)):
    ws = await _find_workspace_by_join_code(code)
    if not ws:
        raise HTTPException(status_code=404, detail="Invalid invite code")
    return {"name": ws["name"], "workspace_id": ws["workspace_id"]}


@api_router.post("/workspaces/join")
async def join_workspace(payload: JoinInput, request: Request, user=Depends(get_user)):
    await _check_join_rate_limit(_client_ip(request))
    ws = await _find_workspace_by_join_code(payload.code)
    if not ws:
        raise HTTPException(status_code=404, detail="Invalid invite code")
    ws_id = ws["workspace_id"]
    existing = await db.memberships.find_one({"workspace_id": ws_id, "user_id": user["user_id"]}, {"_id": 0})
    if not existing:
        await _enforce_seat_available(ws_id, ws.get("plan"))
        membership = {
            "membership_id": f"mem_{uuid.uuid4().hex[:12]}", "workspace_id": ws_id,
            "user_id": user["user_id"], "email": user["email"], "role": "member",
            "pack": "member", "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await db.memberships.insert_one(membership)
        except Exception:
            await _release_seat_reservation(ws_id)
            raise
        existing = membership
    await ensure_person_for_membership(ws_id, existing, name=user.get("name"))
    await dept_migrate.enroll_user_in_sales_finance(db, ws_id, user["user_id"])
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"active_workspace_id": ws_id}})
    return {"ok": True, "workspace_id": ws_id}


@api_router.get("/workspaces/join-code")
async def get_join_code(principal=Depends(require_pro_perm("members:invite"))):
    ws = await get_ws(principal["workspace_id"])
    code = ws.get("join_code")
    if not code:
        code = gen_join_code()
        await db.workspaces.update_one({"workspace_id": principal["workspace_id"]}, {"$set": {"join_code": code}})
    return {"join_code": code}


@api_router.get("/members")
async def list_members(principal=Depends(get_principal)):
    mems = await db.memberships.find({"workspace_id": principal["workspace_id"]}, {"_id": 0}).to_list(100)
    users_by_id = await _users_by_ids(
        [m.get("user_id") for m in mems],
        {"_id": 0, "user_id": 1, "name": 1, "picture": 1},
    )
    out = []
    for m in mems:
        u = users_by_id.get(m.get("user_id")) if m.get("user_id") else None
        pack = pack_of(m)
        out.append({
            "membership_id": m["membership_id"], "email": m["email"], "role": m["role"],
            "pack": pack, "status": m["status"], "name": (u or {}).get("name"),
            "picture": (u or {}).get("picture"), "user_id": m.get("user_id"),
            "section_grants": sec_access.normalize_section_grants(m.get("section_grants")),
            "is_self": m.get("user_id") == principal["user_id"],
        })
    by_user = await dept_access.department_names_by_user_id(db, principal["workspace_id"])
    for row in out:
        dept_access.attach_real_departments(row, by_user.get(row.get("user_id") or "") or [])
    ws = await get_ws(principal["workspace_id"])
    plan = workspace_plan_id(ws)
    seats = helm_plans.seats_limit(plan)
    return {
        "members": out,
        "my_role": principal["role"],
        "my_pack": principal["pack"],
        "plan": plan,
        "seats_used": len(out),
        "seats_limit": seats,
    }


class InviteInput(BaseModel):
    email: EmailStr
    pack: str = "member"
    # Legacy free-text label — ignored. Department access is department_members.
    department: Optional[str] = None
    name: Optional[str] = None


@api_router.post("/members/invite")
async def invite_member(payload: InviteInput, request: Request, principal=Depends(require_pro_perm("members:invite"))):
    pack = _require_assignable_pack(payload.pack)
    role = "member"
    email = payload.email.strip().lower()
    existing = await db.memberships.find_one({"workspace_id": principal["workspace_id"], "email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Already a member or invited")
    await _enforce_seat_available(principal["workspace_id"])
    existing_user = await db.users.find_one({"email": email}, {"_id": 0})
    membership = {
        "membership_id": f"mem_{uuid.uuid4().hex[:12]}", "workspace_id": principal["workspace_id"],
        "user_id": existing_user["user_id"] if existing_user else None, "email": email,
        "role": role, "pack": pack,
        "status": "active" if existing_user else "invited",
        "invite_token": uuid.uuid4().hex, "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db.memberships.insert_one(membership)
    except Exception:
        await _release_seat_reservation(principal["workspace_id"])
        raise
    display_name = (existing_user or {}).get("name") or payload.name
    await ensure_person_for_membership(principal["workspace_id"], membership, name=display_name)
    if membership.get("user_id"):
        await dept_migrate.enroll_user_in_sales_finance(
            db, principal["workspace_id"], membership["user_id"],
        )
    ws = await get_ws(principal["workspace_id"])
    app_url = APP_URL or FRONTEND_URL or str(request.base_url).rstrip("/")
    email_result = await send_invite_email(email, principal.get("name") or "Your team lead", ws["name"], PACK_LABEL.get(pack, "Member"), app_url)
    return {"ok": True, "auto_joined": bool(existing_user), "email_sent": email_result.get("sent", False)}


class RoleInput(BaseModel):
    pack: str
    # Legacy free-text label — ignored; do not write membership.department.
    department: Optional[str] = None


@api_router.patch("/members/{membership_id}")
async def update_member_role(membership_id: str, payload: RoleInput, principal=Depends(require_pro_perm("members:invite"))):
    m = await db.memberships.find_one({"membership_id": membership_id, "workspace_id": principal["workspace_id"]}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Member not found")
    if m.get("user_id") == principal["user_id"]:
        raise HTTPException(status_code=400, detail="You cannot change your own access")
    pack = _require_assignable_pack(payload.pack)
    is_owner_admin = "members:manage" in perms_for(principal["pack"])
    if pack_of(m) == "owner" and not is_owner_admin:
        raise HTTPException(status_code=403, detail="Only an owner can change owner access")
    role = "member"
    upd = {"role": role, "pack": pack}
    await db.memberships.update_one({"membership_id": membership_id, "workspace_id": principal["workspace_id"]}, {"$set": upd})
    m2 = {**m, **upd}
    await ensure_person_for_membership(principal["workspace_id"], m2)
    return {"ok": True}


class SectionAccessInput(BaseModel):
    section_access: dict


class MemberGrantsInput(BaseModel):
    """Map membership_id → list of manageable section ids the CEO grants that person."""
    grants: dict


class MemberDepartmentsInput(BaseModel):
    """Map membership_id → list of enabled department_ids that person belongs to."""
    assignments: dict


@api_router.get("/access/sections")
async def get_section_access(principal=Depends(get_principal)):
    ws = await get_ws(principal["workspace_id"])
    can_manage = "members:manage" in perms_for(principal["pack"])
    section_access = sec_access.normalize_section_access(ws.get("section_access"))
    depts = await workspace_departments(principal["workspace_id"], ws)
    enabled_departments = await dept_access.list_enabled_departments(db, principal["workspace_id"])
    enabled_ids = {d["department_id"] for d in enabled_departments}
    mems = await db.memberships.find({"workspace_id": principal["workspace_id"]}, {"_id": 0}).to_list(200)
    users_by_id = await _users_by_ids(
        [m.get("user_id") for m in mems if pack_of(m) != "owner"],
        {"_id": 0, "user_id": 1, "name": 1, "picture": 1},
    )
    members_out = []
    for m in mems:
        pack = pack_of(m)
        if pack == "owner":
            continue  # Owners/CEOs always have full access — not managed here
        u = users_by_id.get(m.get("user_id")) if m.get("user_id") else None
        grants = sec_access.normalize_section_grants(m.get("section_grants"))
        from_pack = sec_access.sections_for_perms(perms_for(pack))
        # Legacy free-text label still drives old section_access department grants.
        legacy_dept = (m.get("department") or "").strip()
        from_dept = [sid for sid, depts_map in section_access.items() if legacy_dept and legacy_dept in (depts_map or [])]
        effective = sorted(set(from_pack) | set(grants) | set(from_dept))
        row = {
            "membership_id": m["membership_id"],
            "email": m["email"],
            "name": (u or {}).get("name") or m["email"],
            "picture": (u or {}).get("picture"),
            "pack": pack,
            "status": m.get("status"),
            "section_grants": grants,
            "from_pack": from_pack,
            "from_department": from_dept,
            "effective": effective,
            "user_id": m.get("user_id"),
            "legacy_department": legacy_dept or None,
            "department_ids": [],
        }
        members_out.append(row)
    by_user_names = await dept_access.department_names_by_user_id(db, principal["workspace_id"])
    by_user_ids = await dept_access.department_ids_by_user_id(db, principal["workspace_id"])
    for row in members_out:
        uid = row.get("user_id") or ""
        dept_access.attach_real_departments(row, by_user_names.get(uid) or [])
        row["department_ids"] = [did for did in (by_user_ids.get(uid) or []) if did in enabled_ids]
    members_out.sort(key=lambda x: (x.get("name") or x["email"]).lower())
    return {
        "sections": sec_access.MANAGEABLE_SECTIONS,
        "departments": depts,
        "enabled_departments": enabled_departments,
        "section_access": section_access,
        "members": members_out,
        "can_manage": can_manage,
    }


@api_router.patch("/access/sections")
async def update_section_access(payload: SectionAccessInput, principal=Depends(require_pro_perm("members:manage"))):
    """Legacy department → section map (kept for API compatibility). Prefer /access/member-grants."""
    normalized = sec_access.normalize_section_access(payload.section_access)
    await db.workspaces.update_one(
        {"workspace_id": principal["workspace_id"]},
        {"$set": {"section_access": normalized}},
    )
    return {"ok": True, "section_access": normalized}


@api_router.patch("/access/member-grants")
async def update_member_grants(payload: MemberGrantsInput, principal=Depends(require_pro_perm("members:manage"))):
    """CEO sets per-member section grants. Owners are ignored — they always have full access."""
    if not isinstance(payload.grants, dict):
        raise HTTPException(status_code=400, detail="grants must be an object")
    ws_id = principal["workspace_id"]
    updated = 0
    mids = [str(mid).strip() for mid, _ in payload.grants.items() if str(mid).strip()]
    by_mid = await _docs_by_key(
        db.memberships,
        "membership_id",
        mids,
        {"_id": 0},
    )
    # Only keep rows in this workspace (same filter as the old find_one).
    by_mid = {mid: m for mid, m in by_mid.items() if m.get("workspace_id") == ws_id}
    for membership_id, raw_grants in payload.grants.items():
        mid = str(membership_id).strip()
        if not mid:
            continue
        m = by_mid.get(mid)
        if not m:
            continue
        if pack_of(m) == "owner":
            continue
        grants = sec_access.normalize_section_grants(raw_grants if isinstance(raw_grants, list) else [])
        await db.memberships.update_one(
            {"membership_id": mid, "workspace_id": ws_id},
            {"$set": {"section_grants": grants}},
        )
        updated += 1
    return {"ok": True, "updated": updated}


@api_router.patch("/access/member-departments")
async def update_member_departments(
    payload: MemberDepartmentsInput,
    principal=Depends(require_pro_perm("members:manage")),
):
    """CEO sets which enabled department lanes each teammate belongs to."""
    if not isinstance(payload.assignments, dict):
        raise HTTPException(status_code=400, detail="assignments must be an object")
    ws_id = principal["workspace_id"]
    enabled = await dept_access.list_enabled_departments(db, ws_id)
    enabled_ids = {d["department_id"] for d in enabled}
    mids = [str(mid).strip() for mid, _ in payload.assignments.items() if str(mid).strip()]
    by_mid = await _docs_by_key(db.memberships, "membership_id", mids, {"_id": 0})
    by_mid = {mid: m for mid, m in by_mid.items() if m.get("workspace_id") == ws_id}
    updated = 0
    now = datetime.now(timezone.utc).isoformat()
    for membership_id, raw_ids in payload.assignments.items():
        mid = str(membership_id).strip()
        if not mid:
            continue
        m = by_mid.get(mid)
        if not m or pack_of(m) == "owner":
            continue
        user_id = (m.get("user_id") or "").strip()
        if not user_id:
            raise HTTPException(
                status_code=400,
                detail=f"{m.get('email') or mid} has not joined yet — department lanes need an active login",
            )
        wanted = []
        seen = set()
        for raw in (raw_ids if isinstance(raw_ids, list) else []):
            did = str(raw or "").strip()
            if not did or did not in enabled_ids or did in seen:
                continue
            seen.add(did)
            wanted.append(did)
        existing_rows = await db.department_members.find(
            {"user_id": user_id, "department_id": {"$in": list(enabled_ids)}},
            {"_id": 0, "department_id": 1, "role": 1},
        ).to_list(50)
        existing = {r["department_id"]: r for r in existing_rows if r.get("department_id")}
        to_add = [did for did in wanted if did not in existing]
        to_remove = [did for did in existing if did not in seen]
        for did in to_add:
            await db.department_members.update_one(
                {"department_id": did, "user_id": user_id},
                {"$setOnInsert": {
                    "department_id": did,
                    "user_id": user_id,
                    "role": "member",
                    "created_at": now,
                }},
                upsert=True,
            )
        if to_remove:
            await db.department_members.delete_many(
                {"user_id": user_id, "department_id": {"$in": to_remove}},
            )
        if to_add or to_remove:
            updated += 1
    if updated:
        invalidate_departments_cache(ws_id)
    return {"ok": True, "updated": updated}


@api_router.delete("/members/{membership_id}")
async def remove_member(membership_id: str, principal=Depends(require_pro_perm("members:manage"))):
    m = await db.memberships.find_one({"membership_id": membership_id, "workspace_id": principal["workspace_id"]}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Member not found")
    if m.get("user_id") == principal["user_id"]:
        raise HTTPException(status_code=400, detail="You cannot remove yourself")
    await db.memberships.delete_one({"membership_id": membership_id, "workspace_id": principal["workspace_id"]})
    await _release_seat_reservation(principal["workspace_id"])
    await unlink_person_membership(principal["workspace_id"], membership_id)
    # People list caches has_access from memberships — drop it so roster badges update.
    invalidate_workspace_list_cache(principal["workspace_id"], "people")
    return {"ok": True}


# ------------------------- Company / module data -------------------------
@api_router.get("/company")
async def company(principal=Depends(get_principal)):
    c = await get_ws(principal["workspace_id"])
    return {
        "name": c["name"], "plan": c["plan"], "stage": c["stage"], "employees": c["employees"],
        "founded": c["founded"], "mission": c["mission"], "industry": c.get("industry", ""),
        "founder_title": c.get("founder_title", ""),
        "ceo_name": principal.get("name") or "CEO",
        "role": principal["role"], "workspace_id": c["workspace_id"],
        "onboarding_done": c.get("onboarding_done", True),
        "company_setup_done": c.get("company_setup_done", True),
        "template": c.get("template", "sample"),
    }


COMPANY_STAGES = frozenset({
    "Just starting out",
    "Established, growing",
    "Established, stable",
    "Family-owned / multi-generation",
    "Other",
})
FOUNDER_TITLES = frozenset({"CEO", "Founder", "Co-founder", "Managing Director", "President", "Other"})


class CompanySetupInput(BaseModel):
    name: Optional[str] = None
    industry: Optional[str] = None
    stage: Optional[str] = None
    employees: Optional[int] = None
    founded: Optional[str] = None
    mission: Optional[str] = None
    founder_title: Optional[str] = None
    company_setup_done: bool = True


@api_router.patch("/company")
async def update_company(payload: CompanySetupInput, principal=Depends(require("workspace:edit"))):
    updates = {}
    if payload.name is not None:
        # Renaming the company is owner/CEO-only (workspace:edit is already owner-scoped;
        # keep an explicit check so the rule stays obvious if packs change).
        if not dept_access.is_workspace_ceo(principal):
            raise HTTPException(status_code=403, detail="Only the CEO can rename the company")
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Company name is required")
        if len(name) > 120:
            raise HTTPException(status_code=400, detail="Company name is too long")
        updates["name"] = name
    if payload.industry is not None:
        updates["industry"] = payload.industry.strip()[:120]
    if payload.stage is not None:
        stage = payload.stage.strip()
        if stage and stage not in COMPANY_STAGES:
            raise HTTPException(status_code=400, detail="Invalid company stage")
        updates["stage"] = stage
    if payload.employees is not None:
        if payload.employees < 0 or payload.employees > 100000:
            raise HTTPException(status_code=400, detail="Invalid team size")
        updates["employees"] = payload.employees
        updates["employees_entered"] = True
    if payload.founded is not None:
        founded = payload.founded.strip()
        if founded and (len(founded) != 4 or not founded.isdigit()):
            raise HTTPException(status_code=400, detail="Founded year must be YYYY")
        updates["founded"] = founded
    if payload.mission is not None:
        updates["mission"] = payload.mission.strip()[:500]
    if payload.founder_title is not None:
        title = payload.founder_title.strip()
        if title and title not in FOUNDER_TITLES:
            raise HTTPException(status_code=400, detail="Invalid role")
        updates["founder_title"] = title or "CEO"
    if payload.company_setup_done:
        updates["company_setup_done"] = True
    if not updates:
        raise HTTPException(status_code=400, detail="No changes provided")
    await db.workspaces.update_one({"workspace_id": principal["workspace_id"]}, {"$set": updates})
    return {"ok": True}


class TemplateInput(BaseModel):
    template: str  # sample | clean


_PRESERVE_WS_FIELDS = frozenset({
    "join_code", "oauth_session_token_enc", "quickbooks_tokens", "xero_tokens", "hubspot_tokens", "sap_b1_credentials",
    "plan", "billing_provider", "paddle_subscription_id", "paddle_customer_id",
    "paddle_last_event_at", "billing_status", "subscription_status", "canceled_at",
    "workspace_id", "owner_user_id", "created_at",
})


@api_router.post("/workspace/apply-template")
async def apply_template(payload: TemplateInput, principal=Depends(require("workspace:edit"))):
    ws_id = principal["workspace_id"]
    if payload.template == "sample":
        current = await get_ws(ws_id)
        fresh = build_workspace(ws_id, current["name"], principal["user_id"], empty=False)
        update = {k: v for k, v in fresh.items() if k not in _PRESERVE_WS_FIELDS}
        await db.workspaces.update_one({"workspace_id": ws_id}, {"$set": update})
        await db.financial_entries.delete_many({"workspace_id": ws_id})
        await dept_migrate.migrate_workspace_sales_finance(db, ws_id)
        finance_dept_id = await dept_migrate.finance_department_id(db, ws_id)
        samples = sample_financial_entries(ws_id)
        if finance_dept_id:
            for e in samples:
                e["department_id"] = finance_dept_id
        await db.financial_entries.insert_many(samples)
        invalidate_financials_cache(ws_id)
    else:
        await db.workspaces.update_one({"workspace_id": ws_id}, {"$set": {"onboarding_done": True}})
    return {"ok": True}


_insights_refresh_inflight: set[str] = set()
_insights_refresh_tasks: set[asyncio.Task] = set()


def _schedule_insights_refresh(workspace_id: str) -> None:
    """Refresh AI suggestions in the background — never block the briefing response."""
    if workspace_id in _insights_refresh_inflight:
        return
    if not helm_llm.anthropic_configured():
        return
    # Claim the slot before create_task to avoid duplicate concurrent runs.
    _insights_refresh_inflight.add(workspace_id)

    async def _run() -> None:
        try:
            await _generate_insights(workspace_id, raise_on_rate_limit=False)
        except Exception:
            logger.exception("background insights refresh failed for %s", workspace_id)
        finally:
            _insights_refresh_inflight.discard(workspace_id)

    try:
        task = asyncio.get_running_loop().create_task(_run())
        _insights_refresh_tasks.add(task)
        task.add_done_callback(_insights_refresh_tasks.discard)
    except RuntimeError:
        _insights_refresh_inflight.discard(workspace_id)
        logger.debug("no running loop — skip background insights for %s", workspace_id)


def _briefing_finance_metrics(fin: dict) -> list[dict]:
    """Briefing KPI cards; missing values include hrefs to add the underlying data."""
    mrr_known = bool(fin.get("mrr_known"))
    burn_known = bool(fin.get("burn_known"))
    runway_ready = fin.get("runway_months") is not None or bool(fin.get("runway_no_burn"))
    return [
        {
            "label": "MRR",
            "value": format_mrr_display(fin),
            "delta": fin["mrr_delta"] if mrr_known else 0,
            "tone": "positive" if mrr_known else "neutral",
            "missing": not mrr_known,
            "state": fin.get("mrr_state") or _figure_state(mrr_known, fin.get("mrr_value")),
            "href": None if mrr_known else "/app/financials#log-mrr",
            "section": "finance",
        },
        {
            "label": "Runway",
            "value": format_runway_display(fin),
            "delta": 0,
            "tone": "positive" if fin.get("runway_no_burn") else "neutral",
            "missing": not runway_ready,
            "state": fin.get("runway_state") or _runway_state(
                runway_months=fin.get("runway_months"),
                runway_no_burn=bool(fin.get("runway_no_burn")),
            ),
            "href": (
                None
                if runway_ready
                else (
                    "/app/financials#cash"
                    if not fin.get("cash_entered")
                    else "/app/financials#log-entry"
                )
            ),
            "section": "finance",
        },
        {
            "label": "Burn",
            "value": format_burn_display(fin),
            "delta": 0,
            "tone": fin["burn_tone"] if burn_known else "neutral",
            "missing": not burn_known,
            "state": fin.get("burn_state") or _figure_state(burn_known, fin.get("burn_value")),
            "href": None if burn_known else "/app/financials#log-entry",
            "section": "finance",
        },
    ]


def _fmt_days_metric(value: Optional[float]) -> str:
    if value is None:
        return "Not tracked"
    n = float(value)
    if n == int(n):
        return f"{int(n)}d"
    return f"{n:.1f}d"


async def assemble_ops_briefing_data(workspace_id: str) -> dict:
    """Shared ops snapshot for Briefing UI and the daily morning email cron."""
    import ops_briefing as ob
    return await ob.assemble_ops_briefing_data(db, workspace_id)


async def _briefing_ops_metrics(workspace_id: str) -> list[dict]:
    """Procurement / Production / Sales / Maintenance rollups for Briefing.

    Delegates to assemble_ops_briefing_data so the daily email uses the same
    numbers. Missing timestamps / logs / budgets / targets surface as not
    tracked / no data — never fabricated zeros.
    """
    import ops_briefing as ob
    data = await assemble_ops_briefing_data(workspace_id)
    return ob.ops_briefing_metric_cards(data)


@api_router.get("/briefing")
async def briefing(principal=Depends(get_principal)):
    c = await get_ws(principal["workspace_id"])
    try:
        await db.workspaces.update_one(
            {"workspace_id": c["workspace_id"]},
            {"$set": {"last_active_at": datetime.now(timezone.utc).isoformat()}},
        )
    except Exception:
        logger.debug("last_active_at update skipped", exc_info=True)
    # Stale AI suggestions: refresh in background so Briefing stays fast.
    if _insights_stale(c):
        _schedule_insights_refresh(c["workspace_id"])
    b = dict(c["briefing"])
    # Soften legacy vibecode default copy stored on older workspaces
    if (b.get("headline") or "").startswith("Your cockpit is ready"):
        b["headline"] = "Start by logging your financials and adding your team."
    is_pro = workspace_is_pro(c)
    has_fin_access = await can_access_financials(principal)
    day = datetime.now(timezone.utc).date().isoformat()

    async def _load_fin():
        if not has_fin_access:
            return None
        return await compute_financials(c["workspace_id"])

    async def _load_acts():
        return await db.activities.find(
            {"workspace_id": c["workspace_id"]}, {"_id": 0},
        ).sort("created_at", -1).to_list(5)

    async def _load_updates():
        return await db.updates.find(
            {"workspace_id": c["workspace_id"], "day": day}, {"_id": 0},
        ).sort("updated_at", -1).to_list(50)

    async def _load_ops():
        try:
            return await _briefing_ops_metrics(c["workspace_id"])
        except Exception:
            logger.exception("briefing ops metrics failed for %s", c.get("workspace_id"))
            return []

    fin, acts, ups, (email_threads, gmail_meta), freshness, ops_metrics = await asyncio.gather(
        _load_fin(),
        _load_acts(),
        _load_updates(),
        _briefing_gmail_swr(c, principal),
        helm_freshness.resolve_workspace_data_as_of(db, c),
        _load_ops(),
    )

    metrics = []
    if has_fin_access and fin is not None:
        metrics = _briefing_finance_metrics(fin)
        nrr = b.get("nrr")
        if nrr:
            metrics.append({
                "label": "NRR",
                "value": nrr["value"],
                "delta": nrr["delta"],
                "tone": nrr["tone"],
                "section": "finance",
            })
    metrics.extend(ops_metrics or [])
    b["metrics"] = metrics
    act_items = [{"title": a["summary"], "detail": f"{a['actor_name']} · {_rel_time(a['created_at'])}", "tone": "neutral"} for a in acts]
    b["what_changed"] = act_items + list(b.get("what_changed", []))
    b["team_updates"] = [{"user_name": u.get("user_name"), "text": u.get("text"),
                          "blocker": u.get("blocker", False),
                          "ago": _rel_time(u.get("updated_at", ""))} for u in ups]
    b["what_to_decide"] = _briefing_what_to_decide(c)
    b["what_to_delegate"] = _briefing_what_to_delegate(c)
    b["insights_generated_at"] = c.get("insights_generated_at")
    b["email_threads"] = email_threads
    b["gmail_connected"] = gmail_meta["connected"]
    b["gmail_needs_reconnect"] = gmail_meta["needs_reconnect"]
    b["gmail_compose"] = gmail_meta.get("compose", False)
    b["data_as_of"] = freshness.get("data_as_of")
    b["data_freshness_sources"] = freshness.get("sources") or {}
    # Free includes AI briefing — do not strip the stored summary just because
    # the workspace is not on a paid tier (legacy is_pro gate was wrong).
    can_ai_briefing = workspace_allows(c, helm_plans.FEATURE_AI_BRIEFING)
    can_generate = (
        can_ai_briefing and "briefing:generate" in perms_for(principal.get("pack") or "member")
    )
    return {
        **b,
        "is_pro": is_pro,
        "ai_summary": b.get("ai_summary") if can_ai_briefing else None,
        "can_generate_ai_summary": can_generate,
    }


# Gmail briefing: stale-while-revalidate. Key includes user_id so a future
# per-user Google token change keeps the same cache shape.
GMAIL_BRIEFING_SOFT_TTL_SECONDS = 45.0
GMAIL_BRIEFING_HARD_TTL_SECONDS = 1800.0
_gmail_briefing_cache: dict[str, tuple[list, dict, float]] = {}
_gmail_briefing_refresh_inflight: set[str] = set()
_gmail_briefing_refresh_tasks: set[asyncio.Task] = set()


def _gmail_briefing_cache_key(workspace: dict, principal: dict | None) -> str:
    ws_id = workspace.get("workspace_id") or ""
    uid = (principal or {}).get("user_id") or "anon"
    return f"{ws_id}:{uid}"


def _gmail_timeout_fallback(*, connected: bool = False) -> tuple[list, dict]:
    return [], {
        "connected": connected,
        "needs_reconnect": False,
        "compose": False,
    }


def clear_gmail_briefing_cache() -> None:
    """Tests / process recycle."""
    _gmail_briefing_cache.clear()
    _gmail_briefing_refresh_inflight.clear()


async def _briefing_gmail_fetch_and_store(
    workspace: dict, principal: dict | None, cache_key: str,
) -> tuple[list, dict]:
    """Live Gmail fetch with the existing 3s timeout; updates SWR cache on success."""
    connected_hint = False
    if principal and principal.get("user_id"):
        connected_hint = await _user_google_tokens_present(
            workspace.get("workspace_id") or "", principal["user_id"],
        )
    try:
        threads, meta = await asyncio.wait_for(
            _briefing_email_threads(workspace, principal),
            timeout=3.0,
        )
    except asyncio.TimeoutError:
        logger.warning("Gmail briefing fetch timed out for %s", workspace.get("workspace_id"))
        return _gmail_timeout_fallback(connected=connected_hint)
    _gmail_briefing_cache[cache_key] = (threads, meta, time.monotonic())
    return threads, meta


def _schedule_gmail_briefing_refresh(
    workspace: dict, principal: dict | None, cache_key: str,
) -> None:
    if cache_key in _gmail_briefing_refresh_inflight:
        return
    _gmail_briefing_refresh_inflight.add(cache_key)

    async def _run() -> None:
        try:
            await _briefing_gmail_fetch_and_store(workspace, principal, cache_key)
        except Exception:
            logger.exception("background Gmail briefing refresh failed for %s", cache_key)
        finally:
            _gmail_briefing_refresh_inflight.discard(cache_key)

    try:
        task = asyncio.get_running_loop().create_task(_run())
        _gmail_briefing_refresh_tasks.add(task)
        task.add_done_callback(_gmail_briefing_refresh_tasks.discard)
    except RuntimeError:
        _gmail_briefing_refresh_inflight.discard(cache_key)


async def _briefing_gmail_swr(
    workspace: dict, principal: dict | None = None,
) -> tuple[list, dict]:
    """Serve cached Gmail threads immediately; refresh in the background when soft-stale.

    Cold miss (first load / no cache): wait on the live fetch (same 3s timeout).
    """
    cache_key = _gmail_briefing_cache_key(workspace, principal)
    cached = _gmail_briefing_cache.get(cache_key)
    now = time.monotonic()
    if cached is not None:
        threads, meta, fetched_at = cached
        age = now - fetched_at
        if age <= GMAIL_BRIEFING_HARD_TTL_SECONDS:
            if age >= GMAIL_BRIEFING_SOFT_TTL_SECONDS:
                _schedule_gmail_briefing_refresh(workspace, principal, cache_key)
            return threads, meta
        _gmail_briefing_cache.pop(cache_key, None)
    return await _briefing_gmail_fetch_and_store(workspace, principal, cache_key)


async def _briefing_email_threads(workspace: dict, principal: dict | None = None) -> tuple[list, dict]:
    """Fetch a few relevant Gmail threads for the briefing; never writes email content to Mongo.

    Uses the calling user's own Google tokens (per-user connection). Users who
    have not connected Google simply get empty threads — never another teammate's
    mailbox.
    """
    meta = {"connected": False, "needs_reconnect": False, "compose": False, "access_denied": False}
    if not principal or not principal.get("user_id"):
        return [], meta
    ws_id = workspace.get("workspace_id") or principal.get("workspace_id") or ""
    tokens = await _user_google_tokens(ws_id, principal["user_id"])
    if not tokens:
        return [], meta
    if not gcal.has_gmail_scope(tokens):
        meta["needs_reconnect"] = True
        return [], meta
    meta["connected"] = True
    meta["compose"] = gcal.has_scope(tokens, "gmail.compose")
    try:
        threads, refreshed = await gcal.fetch_important_threads(
            tokens, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, limit=5,
        )
        if refreshed is not tokens:
            await _store_user_google_tokens(ws_id, principal["user_id"], refreshed)
        return threads, meta
    except gcal.GoogleAuthError as exc:
        logger.warning("Gmail auth failed for %s: %s", ws_id, exc)
        if "not granted" in str(exc).lower():
            meta["connected"] = False
            meta["needs_reconnect"] = True
        else:
            await _store_user_google_tokens(ws_id, principal["user_id"], None)
            meta["connected"] = False
        return [], meta
    except Exception:
        logger.exception("Gmail fetch failed for %s", ws_id)
        return [], meta


INSIGHTS_STALE_HOURS = 24
_IMPACT_RANK = {"High": 0, "Medium": 1, "Low": 2}


def _insights_stale(c: dict) -> bool:
    raw = c.get("insights_generated_at")
    if not raw:
        return True
    try:
        taken = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if taken.tzinfo is None:
            taken = taken.replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    return datetime.now(timezone.utc) - taken >= timedelta(hours=INSIGHTS_STALE_HOURS)


def _briefing_what_to_decide(c: dict) -> list:
    """Pending decisions + AI suggestions for the Briefing column."""
    items = []
    for d in c.get("decisions") or []:
        if d.get("status") != "pending":
            continue
        items.append({
            "id": d["id"],
            "title": d.get("title") or "Untitled",
            "detail": (d.get("recommendation") or d.get("description") or "").strip(),
            "urgency": "high" if d.get("impact") == "High" else "medium",
            "impact": d.get("impact") or "Medium",
            "due": d.get("due") or "",
            "source": d.get("source") or "manual",
            "confidence": d.get("confidence"),
            "confidence_unavailable": bool(d.get("confidence_unavailable")),
        })
    for s in c.get("decision_suggestions") or []:
        if s.get("status") != "suggested":
            continue
        items.append({
            "id": s["id"],
            "title": s.get("title") or "Untitled",
            "detail": (s.get("recommendation") or s.get("description") or "").strip(),
            "urgency": "high" if s.get("impact") == "High" else "medium",
            "impact": s.get("impact") or "Medium",
            "due": s.get("due") or "",
            "source": "ai_suggested",
            "confidence": s.get("confidence"),
            "confidence_unavailable": bool(s.get("confidence_unavailable")),
        })

    def sort_key(x):
        return (_IMPACT_RANK.get(x.get("impact"), 9), x.get("due") or "9999")

    items.sort(key=sort_key)
    return items[:5]


def _briefing_what_to_delegate(c: dict) -> list:
    out = []
    for s in c.get("delegate_suggestions") or []:
        if s.get("status") and s.get("status") != "suggested":
            continue
        out.append({
            "id": s["id"],
            "title": s.get("title") or "Untitled",
            "detail": s.get("detail") or "",
            "owner": s.get("suggested_owner_name") or "Unassigned",
            "suggested_owner_user_id": s.get("suggested_owner_user_id"),
            "suggested_owner_name": s.get("suggested_owner_name"),
            "source": "ai_suggested",
        })
        if len(out) >= 5:
            break
    return out


async def _recent_updates(workspace_id: str, days: int = 7) -> list:
    today = datetime.now(timezone.utc).date()
    day_list = [(today - timedelta(days=i)).isoformat() for i in range(days)]
    return await db.updates.find(
        {"workspace_id": workspace_id, "day": {"$in": day_list}},
        {"_id": 0},
    ).to_list(500)


async def _department_signal_inputs(workspace_id: str) -> list:
    """Load open department records only for types this workspace has enabled."""
    out = []
    for spec in helm_dept_drafts.DEPT_SPECS:
        enabled = await dept_migrate.get_enabled_department(db, workspace_id, spec["type"])
        if not enabled:
            continue
        coll = getattr(db, spec["collection"], None)
        if coll is None:
            continue
        items = await coll.find({"workspace_id": workspace_id}, {"_id": 0}).to_list(500)
        if spec.get("type") == dept_catalog.TYPE_PROCUREMENT and items:
            blocking = await _blocking_production_orders_by_request(
                workspace_id, [i.get("id") for i in items if i.get("id")],
            )
            for item in items:
                item["blocking_production_orders"] = list(blocking.get(item.get("id")) or [])
        bundle = {"spec": spec, "items": items}
        if spec.get("type") == dept_catalog.TYPE_HR:
            # Leave requests are separate from onboarding instances (DEPT_SPECS).
            leaves = await db.hr_leave_requests.find(
                {"workspace_id": workspace_id}, {"_id": 0},
            ).to_list(500)
            bundle["leave_requests"] = leaves
        out.append(bundle)
    return out


def _signal_suggestion_key(signal: dict) -> str:
    """Stable id for matching a live signal to a prior suggestion card."""
    import alert_notify as an
    return an.signal_notify_key(signal or {})


def _index_suggestions_by_signal(suggestions: list) -> dict:
    """Map signal fingerprint → most recent suggested card (status=suggested)."""
    out = {}
    for s in suggestions or []:
        if s.get("status") and s.get("status") != "suggested":
            continue
        sig = s.get("signal")
        if not isinstance(sig, dict) or not sig:
            sig = {
                "type": s.get("signal_type"),
                "related_id": s.get("related_id"),
                "summary": s.get("title") or s.get("summary") or "",
            }
        out[_signal_suggestion_key(sig)] = s
    return out


def _severity_to_impact_label(severity) -> str:
    return {"high": "High", "medium": "Medium", "low": "Low"}.get(
        str(severity or "medium").lower(), "Medium",
    )


def _raw_decision_card_from_signal(sig: dict, *, now: str) -> dict:
    """Minimal undrafted decision card so a failed LLM draft cannot drop the signal."""
    return {
        "id": f"sug_{uuid.uuid4().hex[:10]}",
        "status": "suggested",
        "source": "signal_fallback",
        "draft_failed": True,
        "signal_type": sig.get("type"),
        "signal": sig,
        "severity": sig.get("severity"),
        "created_at": now,
        "title": (sig.get("summary") or "Review detected signal")[:200],
        "description": str(sig.get("detail") or "").strip()[:800],
        "recommendation": "Review the signal and choose a course of action.",
        "confidence": None,
        "confidence_unavailable": True,
        "category": str(sig.get("category") or "General")[:80] or "General",
        "impact": _severity_to_impact_label(sig.get("severity")),
        "due": "",
        "owner": None,
    }


def _raw_delegate_card_from_signal(sig: dict, *, now: str) -> dict:
    """Minimal undrafted delegate card for a failed LLM draft."""
    owner_id = sig.get("assignee_user_id")
    if owner_id is not None:
        owner_id = str(owner_id).strip() or None
    owner_name = str(sig.get("assignee_name") or "Unassigned").strip()[:100] or "Unassigned"
    title = (sig.get("summary") or "Follow up on blocker")[:200]
    return {
        "id": f"del_{uuid.uuid4().hex[:10]}",
        "status": "suggested",
        "source": "signal_fallback",
        "draft_failed": True,
        "signal_type": sig.get("type"),
        "signal": sig,
        "severity": sig.get("severity"),
        "created_at": now,
        "title": title,
        "detail": str(sig.get("detail") or title).strip()[:800],
        "suggested_owner_user_id": owner_id,
        "suggested_owner_name": owner_name,
    }


def _merge_partial_draft_fallbacks(
    *,
    failed_signals: list,
    decision_suggestions: list,
    delegate_suggestions: list,
    prior_decisions: list,
    prior_delegates: list,
    now: str,
) -> tuple[list, list]:
    """Keep active signals that failed to draft via prior card or raw-signal fallback."""
    prior_d = _index_suggestions_by_signal(prior_decisions)
    prior_g = _index_suggestions_by_signal(prior_delegates)
    decisions = list(decision_suggestions)
    delegates = list(delegate_suggestions)
    seen_d = {_signal_suggestion_key(s.get("signal") or {}) for s in decisions}
    seen_g = {_signal_suggestion_key(s.get("signal") or {}) for s in delegates}

    for sig in failed_signals or []:
        key = _signal_suggestion_key(sig)
        stype = sig.get("type")
        if stype in decision_engine.DECISION_SIGNAL_TYPES:
            if key in seen_d:
                continue
            prior = prior_d.get(key)
            if prior:
                merged = dict(prior)
                merged.update({
                    "status": "suggested",
                    "signal": sig,
                    "signal_type": stype,
                    "severity": sig.get("severity"),
                    "draft_reused": True,
                })
                decisions.append(merged)
            else:
                decisions.append(_raw_decision_card_from_signal(sig, now=now))
            seen_d.add(key)
        elif stype in decision_engine.DELEGATE_SIGNAL_TYPES:
            if key in seen_g:
                continue
            prior = prior_g.get(key)
            if prior:
                merged = dict(prior)
                merged.update({
                    "status": "suggested",
                    "signal": sig,
                    "signal_type": stype,
                    "severity": sig.get("severity"),
                    "draft_reused": True,
                })
                delegates.append(merged)
            else:
                delegates.append(_raw_delegate_card_from_signal(sig, now=now))
            seen_g.add(key)
    return decisions, delegates


async def _generate_insights(workspace_id: str, *, raise_on_rate_limit: bool = True) -> dict:
    """Detect signals, draft AI suggestions, replace workspace suggestion lists."""
    if await doc_rate_limit.insights_over_limit(db, workspace_id):
        if raise_on_rate_limit:
            raise HTTPException(
                status_code=429,
                detail="Suggestion regeneration limit reached. Try again tomorrow",
            )
        return {"skipped": "rate_limited"}

    if not helm_llm.anthropic_configured():
        if raise_on_rate_limit:
            raise HTTPException(status_code=503, detail="AI is not configured (ANTHROPIC_API_KEY)")
        return {"skipped": "ai_unconfigured"}

    c = await get_ws(workspace_id)
    fin = await compute_financials(workspace_id, return_entries=True)
    currency = fin.get("currency") or "usd"
    entries = fin.pop("entries", None) or []
    expense_by_month = decision_engine.expense_totals_by_month_category(entries)
    deals = await db.deals.find({"workspace_id": workspace_id}, {"_id": 0}).to_list(500)
    tasks = list((c.get("tasks") or {}).get("items") or [])
    updates = await _recent_updates(workspace_id, days=7)
    department_items = await _department_signal_inputs(workspace_id)
    signals = decision_engine.collect_signals(
        fin=fin,
        expense_by_month=expense_by_month,
        deals=deals,
        tasks=tasks,
        updates=updates,
        currency=currency,
        department_items=department_items,
    )
    # Detector counts (overdue tasks, stall days, deal age) are computed — zero means
    # none matched, not "not entered". Missing-vs-zero applies to company financials
    # and profile fields on the draft payload, not to the signal list itself.
    company_context = company_context_for_synthesis(c, fin)
    decision_suggestions = []
    delegate_suggestions = []
    failed_signals = []
    now = datetime.now(timezone.utc).isoformat()
    for sig in signals:
        try:
            if sig.get("type") in decision_engine.DECISION_SIGNAL_TYPES:
                draft = await helm_llm.draft_decision(sig, company_context)
                decision_suggestions.append({
                    "id": f"sug_{uuid.uuid4().hex[:10]}",
                    "status": "suggested",
                    "source": "ai_suggested",
                    "signal_type": sig.get("type"),
                    "signal": sig,
                    "severity": sig.get("severity"),
                    "created_at": now,
                    **draft,
                    "due": "",
                    "owner": None,
                })
            elif sig.get("type") in decision_engine.DELEGATE_SIGNAL_TYPES:
                draft = await helm_llm.draft_delegate(sig, company_context)
                delegate_suggestions.append({
                    "id": f"del_{uuid.uuid4().hex[:10]}",
                    "status": "suggested",
                    "source": "ai_suggested",
                    "signal_type": sig.get("type"),
                    "signal": sig,
                    "severity": sig.get("severity"),
                    "created_at": now,
                    **draft,
                })
        except Exception:
            failed_signals.append(sig)
            logger.exception(
                "draft failed for signal %s related_id=%s workspace=%s",
                sig.get("type"),
                sig.get("related_id"),
                workspace_id,
            )

    # If every draft failed, keep prior suggestions and do not burn the daily stamp.
    if signals and not decision_suggestions and not delegate_suggestions:
        logger.warning(
            "insights draft failure for %s — keeping prior suggestions (%d signals)",
            workspace_id,
            len(signals),
        )
        return {"skipped": "draft_failed", "signals": len(signals)}

    if failed_signals:
        fail_types = sorted({(s.get("type") or "?") for s in failed_signals})
        logger.warning(
            "insights partial draft failures for %s: failed=%s ok_decision=%s ok_delegate=%s types=%s",
            workspace_id,
            len(failed_signals),
            len(decision_suggestions),
            len(delegate_suggestions),
            ",".join(fail_types),
        )
        decision_suggestions, delegate_suggestions = _merge_partial_draft_fallbacks(
            failed_signals=failed_signals,
            decision_suggestions=decision_suggestions,
            delegate_suggestions=delegate_suggestions,
            prior_decisions=c.get("decision_suggestions") or [],
            prior_delegates=c.get("delegate_suggestions") or [],
            now=now,
        )

    if not await doc_rate_limit.acquire_insights_slot(db, workspace_id):
        if raise_on_rate_limit:
            raise HTTPException(
                status_code=429,
                detail="Suggestion regeneration limit reached. Try again tomorrow",
            )
        return {"skipped": "rate_limited"}
    await db.workspaces.update_one(
        {"workspace_id": workspace_id},
        {"$set": {
            "decision_suggestions": decision_suggestions,
            "delegate_suggestions": delegate_suggestions,
            "insights_generated_at": now,
        }},
    )
    notify = {"emailed": False, "slack": False, "new_alerts": 0}
    try:
        # Re-read workspace so notified_signal_ids / slack webhook are current
        c_fresh = await get_ws(workspace_id)
        notify = await _notify_high_severity_alerts(workspace_id, decision_suggestions, c_fresh)
    except Exception:
        logger.exception("high-severity notify failed (non-blocking)")
    return {
        "ok": True,
        "signals": len(signals),
        "decision_suggestions": len(decision_suggestions),
        "delegate_suggestions": len(delegate_suggestions),
        "insights_generated_at": now,
        "notifications": notify,
    }


@api_router.get("/activities")
async def list_activities(
    principal=Depends(get_principal),
    limit: int = Query(50, ge=1),
    before: Optional[str] = None,
):
    page_limit = clamp_limit(limit)
    ws = principal["workspace_id"]
    filt = apply_before_filter({"workspace_id": ws}, "created_at", before, id_field="activity_id")
    acts = await db.activities.find(filt, {"_id": 0}).sort([("created_at", -1), ("activity_id", -1)]).limit(page_limit).to_list(page_limit)
    for a in acts:
        a["ago"] = _rel_time(a["created_at"])
    cursor = next_cursor(acts, "created_at", page_limit, id_field="activity_id")
    return {"items": acts, "activities": acts, "next_cursor": cursor}


@api_router.get("/activities/export")
async def export_activities(
    start: str = Query(..., description="Start date YYYY-MM-DD (inclusive)"),
    end: str = Query(..., description="End date YYYY-MM-DD (inclusive)"),
    format: str = Query("csv"),
    principal=Depends(get_principal),
):
    """Owner/admin activity audit export. Non-admins get 403."""
    if "members:manage" not in perms_for(principal["pack"]):
        raise HTTPException(status_code=403, detail="Only workspace owners/admins can export the activity log")
    if (format or "csv").lower() != "csv":
        raise HTTPException(status_code=400, detail="Only format=csv is supported")
    try:
        start_d = datetime.strptime(start.strip()[:10], "%Y-%m-%d").date()
        end_d = datetime.strptime(end.strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="start and end must be YYYY-MM-DD")
    if end_d < start_d:
        raise HTTPException(status_code=400, detail="end must be on or after start")
    start_iso = datetime(start_d.year, start_d.month, start_d.day, tzinfo=timezone.utc).isoformat()
    end_exclusive = datetime(end_d.year, end_d.month, end_d.day, tzinfo=timezone.utc) + timedelta(days=1)
    end_iso = end_exclusive.isoformat()
    acts = await db.activities.find(
        {
            "workspace_id": principal["workspace_id"],
            "created_at": {"$gte": start_iso, "$lt": end_iso},
        },
        {"_id": 0},
    ).sort("created_at", 1).to_list(50000)

    import csv as csv_mod
    import io as io_mod
    buf = io_mod.StringIO()
    writer = csv_mod.writer(buf)
    writer.writerow(["timestamp", "actor_name", "area", "action", "message"])
    for a in acts:
        writer.writerow([
            a.get("created_at") or "",
            a.get("actor_name") or "",
            a.get("module") or "",
            a.get("action") or "",
            a.get("summary") or "",
        ])
    data = buf.getvalue()
    filename = f"helm-activity-{start_d.isoformat()}-to-{end_d.isoformat()}.csv"
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api_router.post("/briefing/generate")
async def generate_briefing(principal=Depends(require_pro_perm("briefing:generate"))):
    c = await get_ws(principal["workspace_id"])
    if not helm_llm.anthropic_configured():
        raise HTTPException(status_code=503, detail="AI is not configured (ANTHROPIC_API_KEY)")
    b = c["briefing"]
    fin = await compute_financials(c["workspace_id"])
    # Use the same live builders as GET /briefing — stored lists are often empty seeds.
    what_to_decide = _briefing_what_to_decide(c)
    what_changed = b.get("what_changed") or []
    cal_snap = await _google_calendar_snapshot(c, principal=principal)
    context = {
        "company": c["name"],
        "metrics": what_to_decide,
        "what_changed": what_changed,
        "decisions": what_to_decide,
        "financials": financials_for_synthesis(fin),
        "calendar": calendar_for_synthesis(
            cal_snap,
            google_connected=bool(cal_snap and cal_snap.get("live")),
        ),
    }
    system = (
        "You are a clear, practical chief of staff writing a short daily note for a founder. "
        "Write 3–4 sentences in plain English. Sound like a thoughtful human, not an AI analysis. "
        "Lead with what matters most today, name the one decision that needs a call if there is one, "
        "and end with a concrete next step. No lists, no bold, no confidence language. "
        "Write plainly. Avoid em dashes. Prefer periods, commas, or plain connecting words instead, "
        "unless a sentence genuinely cannot be split any other way. "
        "Never say 'synthesis', 'signal', 'blind spot', 'monetization', 'execution velocity', "
        "'worth confirming', or similar consultant/AI phrasing. "
        "Never treat missing financial figures as zero. Follow financials.instructions_for_missing_data exactly: "
        "if cash was not entered, say to add a cash balance for an accurate runway picture. "
        "Do not claim they are out of runway. "
        "Follow calendar.instructions_for_missing_data: if calendar is not connected, say so. "
        "Do not treat a missing calendar as a free day. "
        "Only state figures that appear literally in the company data. Never invent, estimate, or "
        "round into a number that is not present. If a fact is missing, say so plainly."
    )
    text = await helm_llm.complete(
        system,
        f"Company data for today:\n{json.dumps(context, indent=2)}\n\nWrite today's short briefing note.",
    )
    freshness = await helm_freshness.resolve_workspace_data_as_of(db, c)
    await db.workspaces.update_one(
        {"workspace_id": c["workspace_id"]},
        {"$set": {
            "briefing.ai_summary": text,
            "briefing.ai_summary_data_as_of": freshness.get("data_as_of"),
        }},
    )
    return {"ai_summary": text, "data_as_of": freshness.get("data_as_of")}


class DecisionAction(BaseModel):
    action: str
    owner: Optional[str] = None


def _decision_owner_is_self(principal: dict, owner: Optional[str]) -> bool:
    """True when a delegate/owner label refers to the acting principal (e.g. Myself)."""
    if not owner or not str(owner).strip():
        return False
    label = str(owner).strip().lower()
    if label in ("myself", "me"):
        return True
    names = {
        (principal.get("name") or "").strip().lower(),
        (principal.get("email") or "").strip().lower(),
    }
    names.discard("")
    return label in names


def _heal_self_delegated_decisions(principal: dict, decisions: list) -> bool:
    """Delegating to yourself must stay actionable — rewrite stuck status=delegated rows."""
    changed = False
    for d in decisions:
        if d.get("status") == "delegated" and _decision_owner_is_self(principal, d.get("owner")):
            d["status"] = "pending"
            changed = True
    return changed


@api_router.get("/decisions")
async def decisions(principal=Depends(get_principal)):
    c = await get_ws(principal["workspace_id"])
    decisions_list = list(c.get("decisions") or [])
    if _heal_self_delegated_decisions(principal, decisions_list):
        await db.workspaces.update_one(
            {"workspace_id": c["workspace_id"]},
            {"$set": {"decisions": decisions_list}},
        )
    suggestions = [s for s in (c.get("decision_suggestions") or []) if s.get("status") == "suggested"]
    return {
        "decisions": decisions_list,
        "suggestions": suggestions,
        "insights_generated_at": c.get("insights_generated_at"),
        "is_pro": workspace_is_pro(c),
        "can_act": await can_section_write(principal, "decisions", "decisions:act"),
    }


@api_router.post("/decisions/{decision_id}/action")
async def decision_action(decision_id: str, payload: DecisionAction, principal=Depends(require_section("decisions", "decisions:act"))):
    c = await get_ws(principal["workspace_id"])
    decisions = c["decisions"]
    found = False
    for d in decisions:
        if d["id"] == decision_id:
            # "Delegate to Myself" is claim ownership, not a terminal resolution —
            # keep status pending so approve/reject remain available.
            if payload.action == "delegated" and _decision_owner_is_self(principal, payload.owner):
                d["status"] = "pending"
                d["owner"] = (payload.owner or "").strip() or (
                    principal.get("name") or principal.get("email") or "Myself"
                )
            else:
                d["status"] = payload.action
                if payload.owner:
                    d["owner"] = payload.owner
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="Not found")
    await db.workspaces.update_one({"workspace_id": c["workspace_id"]}, {"$set": {"decisions": decisions}})
    invalidate_workspace_list_cache(principal["workspace_id"], "me_work", "calendar")
    return {"ok": True, "decisions": decisions}


class DecisionInput(BaseModel):
    title: str
    category: str = "General"
    description: str = ""
    recommendation: Optional[str] = ""
    confidence: Optional[int] = None
    due: str = ""
    impact: str = "Medium"


def _decision_fields(p: "DecisionInput"):
    # Manual creates should not invent a confidence %; AI drafts set it explicitly.
    conf = None if p.confidence is None else max(0, min(100, int(p.confidence)))
    return {"title": p.title.strip(), "category": p.category.strip() or "General",
            "description": p.description.strip(), "recommendation": (p.recommendation or "").strip(),
            "confidence": conf, "due": p.due.strip() or "—",
            "impact": p.impact if p.impact in ("High", "Medium", "Low") else "Medium"}


@api_router.post("/decisions")
async def create_decision(payload: DecisionInput, principal=Depends(require_section("decisions", "decisions:act"))):
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="Title is required")
    c = await get_ws(principal["workspace_id"])
    d = {
        "id": f"d_{uuid.uuid4().hex[:8]}",
        "status": "pending",
        "owner": None,
        "source": "manual",
        **_decision_fields(payload),
    }
    # Manual form never sends a meaningful confidence — drop empty/zero noise
    if payload.confidence is None:
        d["confidence"] = None
    decisions = c["decisions"] + [d]
    await db.workspaces.update_one({"workspace_id": c["workspace_id"]}, {"$set": {"decisions": decisions}})
    invalidate_workspace_list_cache(principal["workspace_id"], "me_work", "calendar")
    await log_activity(principal, "decisions", "decision.create", f"New decision: {d['title']}")
    return {"ok": True, "decision": d}


@api_router.post("/decisions/generate-suggestions")
async def generate_decision_suggestions(principal=Depends(require_section("decisions", "decisions:act"))):
    result = await _generate_insights(principal["workspace_id"], raise_on_rate_limit=True)
    c = await get_ws(principal["workspace_id"])
    return {
        **result,
        "suggestions": [s for s in (c.get("decision_suggestions") or []) if s.get("status") == "suggested"],
        "delegate_suggestions": [s for s in (c.get("delegate_suggestions") or []) if s.get("status") == "suggested"],
    }


@api_router.post("/decisions/suggestions/{suggestion_id}/approve")
async def approve_decision_suggestion(suggestion_id: str, principal=Depends(require_section("decisions", "decisions:act"))):
    c = await get_ws(principal["workspace_id"])
    suggestions = list(c.get("decision_suggestions") or [])
    sug = next((s for s in suggestions if s.get("id") == suggestion_id), None)
    if not sug or sug.get("status") != "suggested":
        raise HTTPException(status_code=404, detail="Suggestion not found")
    decision = {
        "id": f"d_{uuid.uuid4().hex[:8]}",
        "title": sug.get("title") or "Untitled",
        "category": sug.get("category") or "General",
        "description": sug.get("description") or "",
        "recommendation": sug.get("recommendation") or "",
        "confidence": sug.get("confidence"),
        "confidence_unavailable": bool(sug.get("confidence_unavailable")),
        "status": "pending",
        "owner": None,
        "due": sug.get("due") or "—",
        "impact": sug.get("impact") if sug.get("impact") in ("High", "Medium", "Low") else "Medium",
        "source": "ai_suggested",
        "from_suggestion_id": suggestion_id,
        "signal_type": sug.get("signal_type"),
    }
    decisions = list(c.get("decisions") or []) + [decision]
    suggestions = [s for s in suggestions if s.get("id") != suggestion_id]
    await db.workspaces.update_one(
        {"workspace_id": c["workspace_id"]},
        {"$set": {"decisions": decisions, "decision_suggestions": suggestions}},
    )
    invalidate_workspace_list_cache(principal["workspace_id"], "me_work", "calendar")
    await log_activity(principal, "decisions", "suggestion.approve", f"Accepted Trenston suggestion: {decision['title']}")
    return {"ok": True, "decision": decision}


@api_router.post("/decisions/suggestions/{suggestion_id}/dismiss")
async def dismiss_decision_suggestion(suggestion_id: str, principal=Depends(require_section("decisions", "decisions:act"))):
    import alert_notify as an
    c = await get_ws(principal["workspace_id"])
    suggestions = list(c.get("decision_suggestions") or [])
    sug = next((s for s in suggestions if s.get("id") == suggestion_id), None)
    before = len(suggestions)
    suggestions = [s for s in suggestions if s.get("id") != suggestion_id]
    if len(suggestions) == before:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    # Allow re-notify if the same signal recurs after dismiss
    notified = list(c.get("notified_signal_ids") or [])
    if sug:
        key = an.signal_notify_key(sug.get("signal") or sug)
        notified = [k for k in notified if k != key]
    await db.workspaces.update_one(
        {"workspace_id": c["workspace_id"]},
        {"$set": {"decision_suggestions": suggestions, "notified_signal_ids": notified}},
    )
    return {"ok": True}


@api_router.post("/delegates/suggestions/{suggestion_id}/assign")
async def assign_delegate_suggestion(suggestion_id: str, principal=Depends(require_section("decisions", "decisions:act"))):
    """Promote a delegate suggestion into a real task assigned to the suggested owner."""
    c = await get_ws(principal["workspace_id"])
    suggestions = list(c.get("delegate_suggestions") or [])
    sug = next((s for s in suggestions if s.get("id") == suggestion_id), None)
    if not sug or (sug.get("status") and sug.get("status") != "suggested"):
        raise HTTPException(status_code=404, detail="Suggestion not found")
    t = c["tasks"]
    assignee_uid = sug.get("suggested_owner_user_id") or principal["user_id"]
    assignee_name = sug.get("suggested_owner_name") or principal.get("name") or "Me"
    if sug.get("suggested_owner_user_id"):
        member = await db.memberships.find_one(
            {"workspace_id": principal["workspace_id"], "user_id": sug["suggested_owner_user_id"], "status": "active"},
            {"_id": 0},
        )
        if member:
            u = await db.users.find_one({"user_id": sug["suggested_owner_user_id"]}, {"_id": 0, "name": 1})
            assignee_uid = sug["suggested_owner_user_id"]
            assignee_name = (u or {}).get("name") or member.get("email") or assignee_name
    item = {
        "id": f"t_{uuid.uuid4().hex[:8]}",
        "title": (sug.get("title") or "Follow up").strip()[:200],
        "assignee": assignee_name,
        "assignee_user_id": assignee_uid,
        "priority": "High" if (sug.get("signal") or {}).get("severity") == "high" else "Medium",
        "column": "backlog",
        "tag": "Delegated",
        "due": "",
        "progress": 0,
        "source": "ai_suggested",
        "from_suggestion_id": suggestion_id,
        "note": sug.get("detail") or "",
    }
    t["items"].append(item)
    suggestions = [s for s in suggestions if s.get("id") != suggestion_id]
    await db.workspaces.update_one(
        {"workspace_id": c["workspace_id"]},
        {"$set": {"tasks": t, "delegate_suggestions": suggestions}},
    )
    await log_activity(principal, "tasks", "delegate.assign", f"Assigned from Trenston: {item['title']} → {assignee_name}")
    await notify_task_delegated(
        assignee_user_id=assignee_uid,
        previous_assignee_user_id=None,
        task=item,
        principal=principal,
        workspace_name=c.get("name") or "your company",
    )
    return {"ok": True, "task": item}


@api_router.post("/delegates/suggestions/{suggestion_id}/dismiss")
async def dismiss_delegate_suggestion(suggestion_id: str, principal=Depends(require_section("decisions", "decisions:act"))):
    c = await get_ws(principal["workspace_id"])
    suggestions = list(c.get("delegate_suggestions") or [])
    before = len(suggestions)
    suggestions = [s for s in suggestions if s.get("id") != suggestion_id]
    if len(suggestions) == before:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    await db.workspaces.update_one(
        {"workspace_id": c["workspace_id"]},
        {"$set": {"delegate_suggestions": suggestions}},
    )
    return {"ok": True}

@api_router.patch("/decisions/{decision_id}")
async def edit_decision(decision_id: str, payload: DecisionInput, principal=Depends(require_section("decisions", "decisions:act"))):
    c = await get_ws(principal["workspace_id"])
    decisions = c["decisions"]
    found = None
    for d in decisions:
        if d["id"] == decision_id:
            d.update(_decision_fields(payload))
            found = d
            break
    if not found:
        raise HTTPException(status_code=404, detail="Decision not found")
    await db.workspaces.update_one({"workspace_id": c["workspace_id"]}, {"$set": {"decisions": decisions}})
    invalidate_workspace_list_cache(principal["workspace_id"], "me_work", "calendar")
    return {"ok": True}


@api_router.delete("/decisions/{decision_id}")
async def delete_decision(decision_id: str, principal=Depends(require_section("decisions", "decisions:act"))):
    c = await get_ws(principal["workspace_id"])
    decisions = [d for d in c["decisions"] if d["id"] != decision_id]
    await db.workspaces.update_one({"workspace_id": c["workspace_id"]}, {"$set": {"decisions": decisions}})
    invalidate_workspace_list_cache(principal["workspace_id"], "me_work", "calendar")
    return {"ok": True}


@api_router.get("/onboarding/checklist")
async def onboarding_checklist(principal=Depends(get_principal)):
    c = await get_ws(principal["workspace_id"])
    ws = c["workspace_id"]
    dismissed = bool(c.get("setup_checklist_dismissed"))
    has_fin = await db.financial_entries.count_documents({"workspace_id": ws}) > 0
    people_n = len(c["people"]["people"])
    members_n = await db.memberships.count_documents({"workspace_id": ws, "status": "active"})
    day = datetime.now(timezone.utc).date().isoformat()
    has_update = await db.updates.count_documents({"workspace_id": ws, "user_id": principal["user_id"], "day": day}) > 0
    steps = [
        {"id": "financials", "label": "Add your financials", "done": has_fin, "route": "/app/financials"},
        {"id": "people", "label": "Add your team roster", "done": people_n > 0, "route": "/app/people"},
        {"id": "invite", "label": "Invite a teammate", "done": members_n > 1, "route": "/app/members"},
        {"id": "update", "label": "Post your first status update", "done": has_update, "route": "/app/me"},
    ]
    for step in steps:
        if step["done"]:
            await helm_analytics.log_event_once(
                db, ws, principal["user_id"],
                helm_analytics.EVENT_ONBOARDING_STEP,
                {"step": step["id"]},
                once_key=step["id"],
            )
    complete = all(s["done"] for s in steps)
    return {"steps": steps, "complete": complete, "dismissed": dismissed}


@api_router.post("/onboarding/checklist/dismiss")
async def dismiss_onboarding_checklist(principal=Depends(get_principal)):
    """Hide the Briefing 'Finish setting up' card for this workspace."""
    ws_id = principal["workspace_id"]
    await db.workspaces.update_one(
        {"workspace_id": ws_id},
        {"$set": {"setup_checklist_dismissed": True}},
    )
    return {"ok": True, "dismissed": True}


def _connected_integrations_count(workspace: dict, user_google_tokens) -> int:
    """Count connectable integrations the same way the Integrations page does."""
    ints = integ_catalog.merge_integrations(
        workspace,
        google_configured=bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
        qb_configured=bool(QB_CLIENT_ID and QB_CLIENT_SECRET),
        xero_configured=bool(XERO_CLIENT_ID and XERO_CLIENT_SECRET),
        hubspot_configured=bool(HUBSPOT_CLIENT_ID and HUBSPOT_CLIENT_SECRET),
        user_google_tokens=user_google_tokens,
    )
    return sum(
        1
        for i in ints
        if (i.get("kind") in ("oauth", "credentials"))
        and not i.get("coming_soon")
        and i.get("connected")
    )


@api_router.get("/onboarding/integrations-prompt")
async def onboarding_integrations_prompt(principal=Depends(get_principal)):
    """Briefing card: connect tools when the workspace has none linked yet."""
    if "integrations:manage" not in perms_for(principal["pack"]):
        raise HTTPException(
            status_code=403,
            detail={
                "reason": "permission",
                "message": "You do not have permission for this action",
            },
        )
    c = await get_ws(principal["workspace_id"])
    my_google_row = await _user_google_row(principal["workspace_id"], principal["user_id"])
    my_google_sealed = (my_google_row or {}).get("google_tokens")
    return {
        "connected_count": _connected_integrations_count(c, my_google_sealed),
        "dismissed": bool(c.get("integrations_prompt_dismissed")),
    }


@api_router.post("/onboarding/integrations-prompt/dismiss")
async def dismiss_onboarding_integrations_prompt(principal=Depends(get_principal)):
    """Hide the Briefing 'Connect your tools' card for this workspace."""
    if "integrations:manage" not in perms_for(principal["pack"]):
        raise HTTPException(
            status_code=403,
            detail={
                "reason": "permission",
                "message": "You do not have permission for this action",
            },
        )
    ws_id = principal["workspace_id"]
    await db.workspaces.update_one(
        {"workspace_id": ws_id},
        {"$set": {"integrations_prompt_dismissed": True}},
    )
    return {"ok": True, "dismissed": True}


# ------------------------- Sales pipeline -------------------------
DEAL_STAGES = ["lead", "qualified", "proposal", "negotiation", "won", "lost"]
STAGE_LABEL = {"lead": "Lead", "qualified": "Qualified", "proposal": "Proposal",
               "negotiation": "Negotiation", "won": "Won", "lost": "Lost"}


def _deal_metrics(deals):
    open_deals = [d for d in deals if d["stage"] not in ("won", "lost")]
    by_stage = [{"stage": s, "label": STAGE_LABEL[s],
                 "count": len([d for d in deals if d["stage"] == s]),
                 "value": round(sum(d["value"] for d in deals if d["stage"] == s), 2)} for s in DEAL_STAGES]
    return {"open_value": round(sum(d["value"] for d in open_deals), 2),
            "won_value": round(sum(d["value"] for d in deals if d["stage"] == "won"), 2),
            "open_count": len(open_deals), "by_stage": by_stage}


async def _deal_metrics_for_workspace(workspace_id: str, department_ids: Optional[list] = None):
    """Aggregate pipeline metrics in MongoDB instead of loading all deals."""
    match = dept_access.apply_department_filter(
        {"workspace_id": workspace_id}, department_ids,
    )
    rows = await db.deals.aggregate([
        {"$match": match},
        {"$group": {"_id": "$stage", "count": {"$sum": 1}, "value": {"$sum": "$value"}}},
    ]).to_list(None)
    by_stage_map = {r["_id"]: r for r in rows}
    by_stage = []
    open_value = open_count = 0.0
    won_value = 0.0
    for s in DEAL_STAGES:
        row = by_stage_map.get(s, {"count": 0, "value": 0})
        count = int(row["count"])
        value = round(float(row["value"]), 2)
        by_stage.append({"stage": s, "label": STAGE_LABEL[s], "count": count, "value": value})
        if s not in ("won", "lost"):
            open_value += value
            open_count += count
        elif s == "won":
            won_value = value
    return {"open_value": round(open_value, 2),
            "won_value": round(won_value, 2), "open_count": int(open_count), "by_stage": by_stage}


class DealInput(BaseModel):
    name: str
    company: str = ""
    value: float = 0
    stage: str = "lead"
    owner_name: str = ""
    owner_user_id: Optional[str] = None
    close_date: str = ""
    next_step: str = ""
    next_step_date: str = ""


def _can_lead_sales(principal: dict, membership: dict | None) -> bool:
    if dept_access.is_workspace_ceo(principal):
        return True
    return bool(membership) and membership.get("role") == "lead"


async def _sales_department_row(workspace_id: str) -> dict | None:
    return await dept_migrate.get_enabled_department(db, workspace_id, dept_catalog.TYPE_SALES)


async def _sales_member_rows(workspace_id: str) -> list[dict]:
    dept = await _sales_department_row(workspace_id)
    if not dept:
        return []
    rows = await db.department_members.find(
        {"department_id": dept["department_id"]},
        {"_id": 0, "user_id": 1, "role": 1},
    ).to_list(500)
    users = await _users_by_ids([r.get("user_id") for r in rows])
    out = []
    for r in rows:
        uid = r.get("user_id")
        if not uid:
            continue
        card = _user_card(uid, users.get(uid))
        out.append({
            "user_id": uid,
            "role": r.get("role") or "member",
            "name": card.get("name"),
            "email": card.get("email"),
            "picture": card.get("picture"),
        })
    out.sort(key=lambda x: ((x.get("name") or x.get("email") or "").lower(), x["user_id"]))
    return out


async def _validate_sales_owner(workspace_id: str, user_id: str) -> dict:
    """Ensure user_id is a Sales department member; return member card."""
    members = await _sales_member_rows(workspace_id)
    for m in members:
        if m["user_id"] == user_id:
            return m
    raise HTTPException(
        status_code=400,
        detail="owner_user_id must be a member of the Sales department",
    )


def _owner_display_name(member: dict | None, fallback: str = "") -> str:
    if not member:
        return (fallback or "").strip()
    return (member.get("name") or member.get("email") or fallback or "").strip()


async def _migrate_deal_owner_user_ids(workspace_id: str, deals: list[dict]) -> None:
    """Best-effort: link legacy owner_name to a unique Sales member display name.

    Ambiguous names (multiple members share the same name) are left alone.
    """
    need = [d for d in deals if not d.get("owner_user_id") and (d.get("owner_name") or "").strip()]
    if not need:
        return
    members = await _sales_member_rows(workspace_id)
    by_name: dict[str, str] = {}
    ambiguous: set[str] = set()
    for m in members:
        key = (m.get("name") or "").strip().lower()
        if not key:
            continue
        if key in ambiguous:
            continue
        if key in by_name and by_name[key] != m["user_id"]:
            ambiguous.add(key)
            by_name.pop(key, None)
            continue
        by_name[key] = m["user_id"]
    for deal in need:
        key = (deal.get("owner_name") or "").strip().lower()
        uid = by_name.get(key)
        if not uid:
            continue
        # Match by id only — avoid $in/null operators so FakeMongo/tests stay simple.
        await db.deals.update_one(
            {"id": deal["id"], "workspace_id": workspace_id},
            {"$set": {"owner_user_id": uid}},
        )
        deal["owner_user_id"] = uid


async def _enrich_deals(deals: list[dict]) -> list[dict]:
    owner_ids = [d.get("owner_user_id") for d in deals if d.get("owner_user_id")]
    users = await _users_by_ids(owner_ids)
    out = []
    for deal in deals:
        row = {k: v for k, v in deal.items() if k != "_id"}
        uid = row.get("owner_user_id") or None
        if uid:
            card = _user_card(uid, users.get(uid))
            row["owner"] = card
            # Derived display name — keep legacy free-text when user lookup misses.
            derived = _owner_display_name(card, row.get("owner_name") or "")
            if derived:
                row["owner_name"] = derived
        else:
            row["owner"] = None
        out.append(row)
    return out


async def _apply_deal_owner_assignment(
    *,
    principal: dict,
    workspace_id: str,
    existing: dict,
    requested_owner_user_id: Optional[str],
    owner_name_fallback: str,
    is_create: bool = False,
) -> tuple[Optional[str], str]:
    """Resolve owner_user_id + display owner_name with lead/CEO reassignment rules.

    Returns (owner_user_id, owner_name).
    """
    sales_dept = await _sales_department_row(workspace_id)
    membership = None
    if sales_dept:
        membership = await dept_access.get_department_membership(
            db, sales_dept["department_id"], principal["user_id"],
        )
    is_lead = _can_lead_sales(principal, membership)

    current_uid = (existing.get("owner_user_id") or "").strip() or None
    current_name = (existing.get("owner_name") or "").strip()

    if requested_owner_user_id is None and not is_create:
        # Patch omitted owner_user_id — keep existing ownership; refresh display from link.
        if current_uid:
            try:
                member = await _validate_sales_owner(workspace_id, current_uid)
                return current_uid, _owner_display_name(member, current_name or owner_name_fallback)
            except HTTPException:
                # Owner left Sales — keep the link and legacy display name.
                return current_uid, current_name or owner_name_fallback
        return None, owner_name_fallback or current_name

    raw = "" if requested_owner_user_id is None else str(requested_owner_user_id).strip()
    if requested_owner_user_id is None and is_create:
        # Default new deals to the creator when they are on Sales.
        raw = principal["user_id"] if membership else ""

    new_uid = raw or None
    if new_uid != current_uid:
        assigning_other = bool(new_uid) and new_uid != principal["user_id"]
        clearing = current_uid is not None and new_uid is None
        taking_over = (
            bool(current_uid)
            and current_uid != principal["user_id"]
            and new_uid == principal["user_id"]
        )
        if not is_lead and (assigning_other or clearing or taking_over):
            raise HTTPException(
                status_code=403,
                detail="Only a Sales lead or the CEO can reassign deal ownership",
            )
        if not is_lead and new_uid and new_uid != principal["user_id"]:
            raise HTTPException(
                status_code=403,
                detail="Only a Sales lead or the CEO can assign a deal to someone else",
            )

    member = None
    if new_uid:
        member = await _validate_sales_owner(workspace_id, new_uid)
    display = _owner_display_name(member, owner_name_fallback or current_name)
    if not display and not new_uid:
        display = owner_name_fallback or current_name
    return new_uid, display


def _deal_revenue_month(close_date: str, *, now: Optional[datetime] = None) -> str:
    """YYYY-MM from close_date when parseable, else current UTC month."""
    now = now or datetime.now(timezone.utc)
    raw = (close_date or "").strip()
    if raw:
        try:
            if "T" in raw:
                raw = raw.split("T", 1)[0]
            datetime.strptime(raw[:10], "%Y-%m-%d")
            return raw[:7]
        except ValueError:
            pass
    return now.strftime("%Y-%m")


async def _ensure_deal_won_revenue_entry(deal: dict, principal: dict) -> tuple[Optional[dict], bool]:
    """Create at most one revenue financial_entries row for a won deal.

    Returns (entry, created). Uses source_deal_id uniqueness (same idea as
    ai_upload's one-commit-per-document guard).
    """
    ws = principal["workspace_id"]
    deal_id = deal.get("id")
    if not deal_id:
        return None, False
    existing = await db.financial_entries.find_one(
        {"workspace_id": ws, "source_deal_id": deal_id},
        {"_id": 0},
    )
    if existing:
        return existing, False

    try:
        entry_name = require_entry_name(deal.get("name") or "Won deal")
    except ValueError:
        entry_name = "Won deal"
    amount = round(float(deal.get("value") or 0), 2)
    if amount < 0:
        amount = 0.0
    month = _deal_revenue_month(deal.get("close_date") or "")
    finance_dept_id = await dept_migrate.finance_department_id(db, ws)
    entry = {
        "id": f"fe_{uuid.uuid4().hex[:10]}",
        "workspace_id": ws,
        "department_id": finance_dept_id,
        "type": "revenue",
        "category": "Sales",
        "name": entry_name,
        "amount": amount,
        "month": month,
        "recurring": False,
        "note": f"Auto-created from won deal {deal_id}",
        "source": "deal",
        "source_deal_id": deal_id,
        "created_by": principal["user_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db.financial_entries.insert_one(dict(entry))
    except Exception as exc:
        # Duplicate key / concurrent win — treat as already created.
        msg = str(exc).lower()
        if "duplicate" in msg or "e11000" in msg:
            existing = await db.financial_entries.find_one(
                {"workspace_id": ws, "source_deal_id": deal_id},
                {"_id": 0},
            )
            return existing, False
        raise
    invalidate_financials_cache(ws)
    entry.pop("_id", None)
    return entry, True


def _procurement_expense_month(req: dict, *, now: Optional[datetime] = None) -> str:
    """YYYY-MM from delivery / order date when parseable, else current UTC month."""
    now = now or datetime.now(timezone.utc)
    for key in ("actual_delivery_date", "ordered_at", "created_at"):
        raw = (req.get(key) or "").strip()
        if not raw:
            continue
        try:
            if "T" in raw:
                raw = raw.split("T", 1)[0]
            datetime.strptime(raw[:10], "%Y-%m-%d")
            return raw[:7]
        except ValueError:
            continue
    return now.strftime("%Y-%m")


async def _ensure_procurement_expense_entry(req: dict, principal: dict) -> tuple[Optional[dict], bool]:
    """Create (or refresh) one expense financial_entries row for a delivered request.

    Mirrors won-deal revenue: priced + delivered procurement spend lands in burn.
    Returns (entry, created). Idempotent via source_procurement_request_id.
    """
    if (req.get("status") or "") != "delivered":
        return None, False
    if req.get("cost") is None or req.get("cost") == "":
        return None, False
    try:
        amount = round(float(req["cost"]), 2)
    except (TypeError, ValueError):
        return None, False
    if amount < 0:
        return None, False

    ws = principal["workspace_id"]
    req_id = req.get("id")
    if not req_id:
        return None, False

    existing = await db.financial_entries.find_one(
        {"workspace_id": ws, "source_procurement_request_id": req_id},
        {"_id": 0},
    )
    try:
        entry_name = require_entry_name(req.get("item") or "Procurement")
    except ValueError:
        entry_name = "Procurement"
    vendor = (req.get("vendor_name") or "").strip()
    month = _procurement_expense_month(req)
    finance_dept_id = await dept_migrate.finance_department_id(db, ws)
    note = f"Auto-created from delivered procurement {req_id}"
    if vendor:
        note = f"{note} · {vendor}"

    if existing:
        # Keep burn in sync when cost/item changes after delivery.
        changed = (
            float(existing.get("amount") or 0) != amount
            or (existing.get("name") or "") != entry_name
            or (existing.get("month") or "") != month
            or (existing.get("note") or "") != note
        )
        if not changed:
            return existing, False
        await db.financial_entries.update_one(
            {"id": existing["id"], "workspace_id": ws},
            {"$set": {
                "amount": amount,
                "name": entry_name,
                "month": month,
                "note": note,
                "category": "Procurement",
                "type": "expense",
            }},
        )
        invalidate_financials_cache(ws)
        return {**existing, "amount": amount, "name": entry_name, "month": month, "note": note}, False

    entry = {
        "id": f"fe_{uuid.uuid4().hex[:10]}",
        "workspace_id": ws,
        "department_id": finance_dept_id,
        "type": "expense",
        "category": "Procurement",
        "name": entry_name,
        "amount": amount,
        "month": month,
        "recurring": False,
        "note": note,
        "source": "procurement",
        "source_procurement_request_id": req_id,
        "created_by": principal["user_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db.financial_entries.insert_one(dict(entry))
    except Exception as exc:
        msg = str(exc).lower()
        if "duplicate" in msg or "e11000" in msg:
            existing = await db.financial_entries.find_one(
                {"workspace_id": ws, "source_procurement_request_id": req_id},
                {"_id": 0},
            )
            return existing, False
        raise
    invalidate_financials_cache(ws)
    entry.pop("_id", None)
    return entry, True


@api_router.get("/deals")
async def list_deals(
    principal=Depends(get_principal),
    limit: int = Query(50, ge=1),
    before: Optional[str] = None,
    owner_user_id: Optional[str] = Query(None),
):
    page_limit = clamp_limit(limit)
    ws = principal["workspace_id"]
    owner_key = (owner_user_id or "").strip() or "all"
    cache_key = _list_cache_key(
        "deals", ws, principal["user_id"], owner_key, before or "", str(page_limit),
    )
    cached = simple_cache.peek(cache_key)
    if cached is not None:
        asyncio.create_task(_product_event(
            ws, principal["user_id"], helm_analytics.EVENT_DEPARTMENT_PAGE_VIEWED,
            {"department": dept_catalog.TYPE_SALES},
        ))
        return cached
    dept_ids = await dept_access.accessible_department_ids(db, principal, dept_catalog.TYPE_SALES)
    base = dept_access.apply_department_filter({"workspace_id": ws}, dept_ids)
    if owner_user_id is not None:
        raw = owner_user_id.strip()
        if raw == "me":
            base = {**base, "owner_user_id": principal["user_id"]}
        elif raw:
            base = {**base, "owner_user_id": raw}
    filt = apply_before_filter(base, "updated_at", before, id_field="id")
    deals = await db.deals.find(filt, {"_id": 0}).sort([("updated_at", -1), ("id", -1)]).limit(page_limit).to_list(page_limit)
    await _migrate_deal_owner_user_ids(ws, deals)
    deals = await _enrich_deals(deals)
    deals = helm_freshness.annotate_possibly_stale(deals, dept_type=dept_catalog.TYPE_SALES)
    metrics = await _deal_metrics_for_workspace(ws, department_ids=dept_ids)
    cursor = next_cursor(deals, "updated_at", page_limit, id_field="id")
    currency = await _workspace_currency(ws)
    sales_dept = await _sales_department_row(ws)
    membership = None
    if sales_dept:
        membership = await dept_access.get_department_membership(
            db, sales_dept["department_id"], principal["user_id"],
        )
    is_lead = _can_lead_sales(principal, membership)
    sales_owners = await _sales_member_rows(ws)
    asyncio.create_task(_product_event(
        ws, principal["user_id"], helm_analytics.EVENT_DEPARTMENT_PAGE_VIEWED,
        {"department": dept_catalog.TYPE_SALES},
    ))
    payload_out = {
        "items": deals,
        "deals": deals,
        "next_cursor": cursor,
        "can_write": await can_section_write(principal, "sales", "sales:write"),
        "can_reassign_owner": is_lead,
        "is_lead": is_lead,
        "my_user_id": principal["user_id"],
        "sales_owners": sales_owners,
        "metrics": metrics,
        "currency": currency,
        "currency_symbol": currency_symbol(currency),
        "stages": [{"id": s, "label": STAGE_LABEL[s]} for s in DEAL_STAGES],
    }
    simple_cache.put(cache_key, payload_out, _DEPT_LIST_CACHE_TTL_SECONDS)
    return payload_out


@api_router.post("/deals")
async def create_deal(payload: DealInput, principal=Depends(require_section("sales", "sales:write"))):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Deal name is required")
    stage = payload.stage if payload.stage in DEAL_STAGES else "lead"
    now = datetime.now(timezone.utc).isoformat()
    currency = await _workspace_currency(principal["workspace_id"])
    creator_name = (principal.get("name") or principal.get("email") or "").strip()
    sales_dept_id = await dept_migrate.sales_department_id(db, principal["workspace_id"])
    owner_uid, owner_name = await _apply_deal_owner_assignment(
        principal=principal,
        workspace_id=principal["workspace_id"],
        existing={},
        requested_owner_user_id=payload.owner_user_id,
        owner_name_fallback=payload.owner_name.strip() or creator_name,
        is_create=True,
    )
    if payload.value < 0:
        raise HTTPException(status_code=400, detail="Deal value cannot be negative")
    deal = {
        "id": f"deal_{uuid.uuid4().hex[:8]}",
        "workspace_id": principal["workspace_id"],
        "department_id": sales_dept_id,
        "name": payload.name.strip(),
        "company": payload.company.strip(),
        "value": round(payload.value, 2),
        "stage": stage,
        "owner_user_id": owner_uid,
        "owner_name": owner_name or creator_name,
        "created_by_user_id": principal["user_id"],
        "created_by_name": creator_name,
        "close_date": payload.close_date.strip(),
        "next_step": (payload.next_step or "").strip()[:280],
        "next_step_date": (payload.next_step_date or "").strip()[:10],
        "created_at": now,
        "updated_at": now,
    }
    await db.deals.insert_one(dict(deal))
    invalidate_workspace_list_cache(principal["workspace_id"], "deals", "me_work")
    enriched = (await _enrich_deals([deal]))[0]
    await log_activity(principal, "sales", "deal.create",
                       f"New deal: {deal['name']} · {fmt_money(deal['value'], currency)} ({STAGE_LABEL[stage]})",
                       {"value": deal["value"], "stage": stage})
    return {"ok": True, "deal": enriched}


@api_router.patch("/deals/{deal_id}")
async def update_deal(deal_id: str, payload: DealInput, principal=Depends(require_section("sales", "sales:write"))):
    d = await db.deals.find_one({"id": deal_id, "workspace_id": principal["workspace_id"]}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Deal not found")
    if payload.value < 0:
        raise HTTPException(status_code=400, detail="Deal value cannot be negative")
    stage = payload.stage if payload.stage in DEAL_STAGES else d["stage"]
    owner_uid, owner_name = await _apply_deal_owner_assignment(
        principal=principal,
        workspace_id=principal["workspace_id"],
        existing=d,
        requested_owner_user_id=payload.owner_user_id,
        owner_name_fallback=payload.owner_name.strip() or d.get("owner_name", ""),
        is_create=False,
    )
    # created_by_* are set once at creation and never edited here.
    # next_step / next_step_date updates bump updated_at so stalled-deal clocks reset.
    upd = {
        "name": payload.name.strip() or d["name"],
        "company": payload.company.strip(),
        "value": round(payload.value, 2),
        "stage": stage,
        "owner_user_id": owner_uid,
        "owner_name": owner_name or d.get("owner_name", ""),
        "close_date": payload.close_date.strip(),
        "next_step": (payload.next_step or "").strip()[:280],
        "next_step_date": (payload.next_step_date or "").strip()[:10],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.deals.update_one({"id": deal_id, "workspace_id": principal["workspace_id"]}, {"$set": upd})
    invalidate_workspace_list_cache(principal["workspace_id"], "deals", "me_work")
    updated = {**d, **upd}
    enriched = (await _enrich_deals([updated]))[0]
    financial_entry = None
    production_prompt = False
    production_prefill = None
    if stage != d["stage"]:
        currency = await _workspace_currency(principal["workspace_id"])
        if stage == "won":
            summary = f"Won {upd['name']} · {fmt_money(upd['value'], currency)}"
            financial_entry, _created = await _ensure_deal_won_revenue_entry(updated, principal)
            if financial_entry:
                await log_activity(
                    principal, "financials", "entry.add",
                    f"Logged revenue from won deal · {financial_entry['name']} "
                    f"{fmt_money(financial_entry['amount'], currency)} ({financial_entry['month']})",
                    {
                        "type": "revenue",
                        "amount": financial_entry["amount"],
                        "month": financial_entry["month"],
                        "source": "deal",
                        "source_deal_id": deal_id,
                    },
                )
            prod_dept = await dept_migrate.get_enabled_department(
                db, principal["workspace_id"], dept_catalog.TYPE_PRODUCTION,
            )
            if prod_dept:
                production_prompt = True
                production_prefill = {
                    "reference": (updated.get("name") or "").strip()[:200],
                    "customer": (updated.get("company") or "").strip()[:200],
                    "source_deal_id": deal_id,
                }
        elif stage == "lost":
            summary = f"Lost {upd['name']}"
        else:
            summary = f"{upd['name']} moved to {STAGE_LABEL[stage]}"
        await log_activity(principal, "sales", "deal.stage", summary, {"stage": stage})
    return {
        "ok": True,
        "deal": enriched,
        "financial_entry": financial_entry,
        "production_prompt": production_prompt,
        "production_prefill": production_prefill,
    }


@api_router.delete("/deals/{deal_id}")
async def delete_deal(deal_id: str, principal=Depends(require_section("sales", "sales:write"))):
    await db.deals.delete_one({"id": deal_id, "workspace_id": principal["workspace_id"]})
    invalidate_workspace_list_cache(principal["workspace_id"], "deals", "me_work")
    return {"ok": True}


# ------------------------- Telemetry helpers -------------------------
_TELEMETRY_RISK_SUGGEST_TYPES = (
    "runway_risk",
    "burn_increase",
    "expense_spike",
    "new_expense_category",
    "recurring_blocker",
    "overdue_work_order",
    "overdue_procurement",
    "overdue_procurement_blocking_production",
    "overdue_legal_deadline",
    "urgent_maintenance",
)
_TELEMETRY_RISK_SUGGEST_CATEGORY = {
    "runway_risk": "Financial",
    "burn_increase": "Financial",
    "expense_spike": "Financial",
    "new_expense_category": "Financial",
    "recurring_blocker": "People",
    "overdue_work_order": "Production",
    "overdue_procurement": "Procurement",
    "overdue_procurement_blocking_production": "Procurement",
    "overdue_legal_deadline": "Legal",
    "urgent_maintenance": "Maintenance",
}


def _normalize_telemetry_targets(raw) -> dict:
    """Return {enabled: bool, monthly_growth_pct: float} with safe bounds."""
    if not isinstance(raw, dict):
        return {"enabled": False, "monthly_growth_pct": 0.0}
    enabled = bool(raw.get("enabled"))
    try:
        pct = float(raw.get("monthly_growth_pct") if raw.get("monthly_growth_pct") is not None else 0)
    except (TypeError, ValueError):
        pct = 0.0
    if not math.isfinite(pct):
        pct = 0.0
    pct = max(-100.0, min(1000.0, pct))
    return {"enabled": enabled, "monthly_growth_pct": pct}


def _revenue_trend_with_targets(revenue_series: list, targets: dict) -> list:
    """Build revenue_trend points; include target only when targets.enabled."""
    series = list(revenue_series or [])
    enabled = bool((targets or {}).get("enabled"))
    pct = float((targets or {}).get("monthly_growth_pct") or 0)
    out = []
    for i, row in enumerate(series):
        point = {"month": row.get("month"), "mrr": row.get("revenue")}
        if enabled:
            try:
                actual = float(row.get("revenue") or 0)
            except (TypeError, ValueError):
                actual = 0.0
            if i == 0:
                point["target"] = round(actual)
            else:
                try:
                    prev = float(series[i - 1].get("revenue") or 0)
                except (TypeError, ValueError):
                    prev = 0.0
                point["target"] = round(prev * (1 + pct / 100.0))
        out.append(point)
    return out


def _summarize_telemetry_signal_group(signal_type: str, group: list) -> str:
    if not group:
        return signal_type
    first = (group[0].get("summary") or signal_type).strip()
    if len(group) == 1:
        return first[:120]
    n = len(group)
    if signal_type == "recurring_blocker":
        return f"{n} teammates with recurring blockers"[:120]
    if signal_type.startswith("overdue_"):
        return f"{n} overdue items: {first}"[:120]
    if signal_type == "urgent_maintenance":
        return f"{n} urgent maintenance tickets"[:120]
    return f"{first} (+{n - 1} more)"[:120]


def _telemetry_risk_suggestions_from_signals(signals: list, *, cap: int = 5) -> list:
    """One suggestion per signal type, capped — no storage, fresh each load."""
    by_type: dict[str, list] = {}
    for sig in signals or []:
        t = sig.get("type")
        if t not in _TELEMETRY_RISK_SUGGEST_TYPES:
            continue
        by_type.setdefault(t, []).append(sig)
    out = []
    for t in _TELEMETRY_RISK_SUGGEST_TYPES:
        group = by_type.get(t) or []
        if not group:
            continue
        out.append({
            "name": _summarize_telemetry_signal_group(t, group),
            "category": _TELEMETRY_RISK_SUGGEST_CATEGORY.get(t, "General"),
            "source_signal": t,
        })
        if len(out) >= cap:
            break
    return out


async def _workspace_live_signals(
    workspace_id: str,
    *,
    fin: Optional[dict] = None,
    deals: Optional[list] = None,
    c: Optional[dict] = None,
) -> list:
    """Same detector path Decisions/Briefing use — reuse, don't reimplement."""
    c = c or await get_ws(workspace_id)
    if fin is None:
        fin = await compute_financials(workspace_id, return_entries=True)
    currency = fin.get("currency") or "usd"
    # Prefer entries already loaded by compute_financials (or a prior caller).
    entries = fin.pop("entries", None) if isinstance(fin, dict) else None
    if entries is None:
        entries = await db.financial_entries.find({"workspace_id": workspace_id}, {"_id": 0}).to_list(5000)
    expense_by_month = decision_engine.expense_totals_by_month_category(entries)
    if deals is None:
        deals = await db.deals.find({"workspace_id": workspace_id}, {"_id": 0}).to_list(500)
    tasks = list((c.get("tasks") or {}).get("items") or [])
    updates = await _recent_updates(workspace_id, days=7)
    department_items = await _department_signal_inputs(workspace_id)
    return decision_engine.collect_signals(
        fin=fin,
        expense_by_month=expense_by_month,
        deals=deals,
        tasks=tasks,
        updates=updates,
        currency=currency,
        department_items=department_items,
    )


async def _activity_heatmap_for_workspace(workspace_id: str, weeks: int = 12) -> dict:
    """Aggregate db.activities into a Bklit heatmap grid (Sunday-first week columns).

    Returns {"columns": [...], "total": int} where each bin.count is the raw
    activity count for that calendar day (frontend/chart levels via Bklit's
    getHeatmapContributionLevel). Dates are ISO date strings for JSON.
    """
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    days_since_sunday = (now.weekday() + 1) % 7
    this_sunday = now - timedelta(days=days_since_sunday)
    start_sunday = this_sunday - timedelta(weeks=max(1, weeks) - 1)
    start_iso = start_sunday.isoformat()

    counts: dict[str, int] = {}
    cursor = db.activities.find(
        {"workspace_id": workspace_id, "created_at": {"$gte": start_iso}},
        {"_id": 0, "created_at": 1},
    )
    async for doc in cursor:
        raw = doc.get("created_at") or ""
        try:
            if isinstance(raw, datetime):
                day = raw.astimezone(timezone.utc).date()
            else:
                day = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(timezone.utc).date()
        except (TypeError, ValueError):
            continue
        key = day.isoformat()
        counts[key] = counts.get(key, 0) + 1

    columns = []
    total = 0
    for week_i in range(max(1, weeks)):
        week_start = start_sunday + timedelta(weeks=week_i)
        bins = []
        for day_i in range(7):
            day = (week_start + timedelta(days=day_i)).date()
            raw_count = 0 if day > now.date() else int(counts.get(day.isoformat(), 0))
            total += raw_count
            bins.append({
                "bin": day_i,
                "count": raw_count,
                "date": day.isoformat(),
            })
        columns.append({"bin": week_i, "bins": bins})
    return {"columns": columns, "total": total}


def _resolve_telemetry_funnel_and_risks(
    *,
    template: str | None,
    tel: dict,
    manual: dict,
    metrics: dict | None,
) -> tuple[list, bool, list, bool]:
    """Funnel + risks for Telemetry UI.

    Seed funnel/risks from build_workspace(empty=False) are only served when
    template == \"sample\". Non-sample workspaces get a real empty state until
    deals exist or the user edits telemetry_manual.risks.
    """
    is_sample = (template or "") == "sample"
    funnel: list = []
    funnel_is_sample = False
    if metrics:
        funnel = [
            {"stage": row["label"], "value": row["count"]}
            for row in metrics["by_stage"]
            if row["count"] > 0
        ]
    elif is_sample and tel.get("funnel"):
        funnel = list(tel.get("funnel") or [])
        funnel_is_sample = True

    risks_is_sample = False
    if manual.get("risks") is not None:
        risks = list(manual.get("risks") or [])
    elif is_sample and tel.get("risks"):
        risks = list(tel.get("risks") or [])
        risks_is_sample = bool(risks)
    else:
        risks = []
    return funnel, funnel_is_sample, risks, risks_is_sample


async def _scrub_orphaned_seed_telemetry(workspace_id: str, c: dict) -> None:
    """Backfill: clear seed funnel/risks left on non-sample workspaces.

    New signups use empty=True (no seed). Sample template workspaces keep seed
    data intentionally. Any other workspace that still carries seed arrays in
    telemetry gets scrubbed so the empty state is durable, not only at read time.
    """
    if (c.get("template") or "") == "sample":
        return
    tel = c.get("telemetry") or {}
    manual = c.get("telemetry_manual") or {}
    sets: dict = {}
    if tel.get("funnel"):
        sets["telemetry.funnel"] = []
    # Only clear seed risks when the user has never taken ownership via manual.
    if tel.get("risks") and manual.get("risks") is None:
        sets["telemetry.risks"] = []
    if not sets:
        return
    try:
        await db.workspaces.update_one({"workspace_id": workspace_id}, {"$set": sets})
    except Exception:
        logger.exception("scrub orphaned seed telemetry failed for %s", workspace_id)


@api_router.get("/telemetry")
async def telemetry(principal=Depends(require_section("telemetry", "telemetry:write"))):
    c = await get_ws(principal["workspace_id"])
    fin = await compute_financials(c["workspace_id"], return_entries=True)
    items = c["tasks"]["items"]
    open_tasks = len([t for t in items if t.get("column") != "done"])
    headcount = c.get("employees") or len(c["people"]["people"])
    now = datetime.now(timezone.utc)
    kpis = []
    sources = []
    # Always surface finance KPIs with not-entered vs confirmed-zero labels —
    # never hide them or show a confident $0 when data was never entered.
    kpis += [
        {
            "label": "MRR",
            "value": format_mrr_display(fin),
            "delta": fin["mrr_delta"] if fin.get("mrr_known") else 0,
            "tone": "positive" if fin.get("mrr_known") and fin.get("mrr_delta", 0) >= 0 else (
                "negative" if fin.get("mrr_known") else "neutral"
            ),
            "spark": fin["spark"] if fin.get("mrr_known") else [],
            "missing": not fin.get("mrr_known"),
            "state": fin.get("mrr_state"),
        },
        {
            "label": "ARR",
            "value": (fin.get("arr") if fin.get("mrr_known") else "Add data"),
            "delta": 0,
            "tone": "neutral",
            "spark": fin["spark"] if fin.get("mrr_known") else [],
            "missing": not fin.get("mrr_known"),
            "state": fin.get("mrr_state"),
        },
        {
            "label": "Runway",
            "value": format_runway_display(fin),
            "delta": 0,
            "tone": "positive" if fin.get("runway_no_burn") else "neutral",
            "spark": [],
            "missing": fin.get("runway_months") is None and not fin.get("runway_no_burn"),
            "state": fin.get("runway_state"),
        },
        {
            "label": "Net Burn",
            "value": format_burn_display(fin),
            "delta": 0,
            "tone": fin["burn_tone"] if fin.get("burn_known") else "neutral",
            "spark": [b["burn"] for b in fin["burn_series"]] if fin.get("burn_known") else [],
            "missing": not fin.get("burn_known"),
            "state": fin.get("burn_state"),
        },
    ]
    if fin["has_data"] or fin.get("cash_entered"):
        sources.append({"label": "Financials", "detail": "Live from your financial entries", "freshness": "live"})
    else:
        sources.append({"label": "Financials", "detail": "Add revenue, expenses, and cash on Financials", "freshness": "missing"})
    kpis += [
        {"label": "Headcount", "value": str(headcount), "delta": 0, "tone": "neutral", "spark": []},
        {"label": "Open Tasks", "value": str(open_tasks), "delta": 0, "tone": "neutral", "spark": []},
    ]
    sources.append({"label": "People & Tasks", "detail": "Headcount and open tasks from workspace data", "freshness": "live"})
    deals = await db.deals.find({"workspace_id": c["workspace_id"]}, {"_id": 0}).to_list(500)
    metrics = _deal_metrics(deals) if deals else None
    currency = fin.get("currency") or "usd"
    if metrics:
        kpis.append({"label": "Pipeline", "value": fmt_money(metrics["open_value"], currency),
                     "delta": 0, "tone": "neutral", "spark": []})
        sources.append({"label": "Pipeline", "detail": "Live from deals in your CRM board", "freshness": "live"})
    tel = c.get("telemetry") or {}
    manual = c.get("telemetry_manual") or {}
    targets = _normalize_telemetry_targets(manual.get("targets"))
    revenue_trend = _revenue_trend_with_targets(fin.get("revenue_series") or [], targets)
    funnel, funnel_is_sample, risks, risks_is_sample = _resolve_telemetry_funnel_and_risks(
        template=c.get("template"),
        tel=tel,
        manual=manual,
        metrics=metrics,
    )
    if funnel_is_sample:
        sources.append({"label": "Sales Funnel", "detail": "Sample funnel. Add deals for live pipeline stages", "freshness": "sample"})
    if risks_is_sample:
        sources.append({"label": "Risks", "detail": "Sample risk radar. Edit risks below or connect integrations", "freshness": "sample"})
    elif manual.get("risks") is not None:
        sources.append({"label": "Risks", "detail": "Manually maintained risk radar", "freshness": "live"})
    # Durable empty state for any non-sample workspace still carrying seed arrays.
    if (c.get("template") or "") != "sample" and (tel.get("funnel") or (tel.get("risks") and manual.get("risks") is None)):
        await _scrub_orphaned_seed_telemetry(c["workspace_id"], c)
    qb = c.get("quickbooks_tokens")
    if cred_crypto.credentials_present(qb):
        sources.append({"label": "QuickBooks", "detail": "Accounting sync when connected", "freshness": "hourly"})
    if cred_crypto.credentials_present(c.get("xero_tokens")):
        sources.append({"label": "Xero", "detail": "Accounting sync when connected", "freshness": "hourly"})
    if cred_crypto.credentials_present(c.get("hubspot_tokens")):
        sources.append({"label": "HubSpot", "detail": "CRM deals synced into Pipeline", "freshness": "live"})
    if await _user_google_tokens_present(c["workspace_id"], principal["user_id"]):
        sources.append({"label": "Google Calendar", "detail": "Meeting load from your calendar", "freshness": "live"})
    suggested_risks = []
    try:
        signals = await _workspace_live_signals(
            c["workspace_id"], fin=fin, deals=deals, c=c,
        )
        suggested_risks = _telemetry_risk_suggestions_from_signals(signals, cap=5)
    except Exception:
        logger.exception("telemetry risk suggestions failed for %s", c.get("workspace_id"))
    can_write = await can_section_write(principal, "telemetry", "telemetry:write")
    activity_heatmap = {"columns": [], "total": 0}
    try:
        activity_heatmap = await _activity_heatmap_for_workspace(c["workspace_id"], weeks=12)
    except Exception:
        logger.exception("telemetry activity heatmap failed for %s", c.get("workspace_id"))
    freshness = await helm_freshness.resolve_workspace_data_as_of(db, c)
    return {
        "kpis": kpis, "revenue_trend": revenue_trend, "funnel": funnel, "risks": risks,
        "funnel_is_sample": funnel_is_sample,
        "risks_is_sample": risks_is_sample,
        "suggested_risks": suggested_risks,
        "expense_breakdown": fin["expense_breakdown"],
        "data_as_of": freshness.get("data_as_of") or now.isoformat(),
        "data_freshness_sources": freshness.get("sources") or {},
        "sources": sources,
        "can_write": can_write,
        "notes": manual.get("notes") or "",
        "targets": targets,
        "activity_heatmap": activity_heatmap,
    }


class TelemetryTargetsInput(BaseModel):
    enabled: bool = False
    monthly_growth_pct: float = 0.0


class TelemetryRiskInput(BaseModel):
    risks: list
    notes: Optional[str] = ""
    targets: Optional[TelemetryTargetsInput] = None


@api_router.patch("/telemetry")
async def update_telemetry(payload: TelemetryRiskInput, principal=Depends(require_section("telemetry", "telemetry:write"))):
    c = await get_ws(principal["workspace_id"])
    cleaned = []
    for r in payload.risks[:20]:
        if not isinstance(r, dict):
            continue
        name = (r.get("name") or "").strip()
        if not name:
            continue
        cleaned.append({
            "id": r.get("id") or f"r_{uuid.uuid4().hex[:8]}",
            "name": name[:120],
            "likelihood": max(1, min(5, int(r.get("likelihood") or 3))),
            "impact": max(1, min(5, int(r.get("impact") or 3))),
            "category": (r.get("category") or "General").strip()[:40],
        })
    prior = dict(c.get("telemetry_manual") or {})
    manual = {
        "risks": cleaned,
        "notes": (payload.notes or "").strip()[:1000],
        "targets": prior.get("targets") or {"enabled": False, "monthly_growth_pct": 0.0},
    }
    if payload.targets is not None:
        manual["targets"] = _normalize_telemetry_targets(payload.targets.model_dump())
    else:
        manual["targets"] = _normalize_telemetry_targets(manual.get("targets"))
    await db.workspaces.update_one(
        {"workspace_id": c["workspace_id"]},
        {"$set": {"telemetry_manual": manual}},
    )
    await log_activity(principal, "telemetry", "telemetry.edit", f"Updated telemetry: {len(cleaned)} risk(s)")
    return {
        "ok": True,
        "risks": cleaned,
        "notes": manual["notes"],
        "targets": manual["targets"],
    }


@api_router.get("/financials")
async def financials(principal=Depends(require_section("financials", "finance:write"))):
    dept_ids = await dept_access.accessible_department_ids(
        db, principal, dept_catalog.TYPE_ACCOUNTING_FINANCE,
    )
    ws_id = principal["workspace_id"]
    scope = ",".join(sorted(str(d) for d in (dept_ids or []))) if dept_ids is not None else "all"
    cache_key = _list_cache_key("financials_page", ws_id, scope)

    async def loader():
        # compute_financials already caches metrics; return_entries avoids a
        # second uncached financial_entries scan on every page load.
        fin = await compute_financials(ws_id, department_ids=dept_ids, return_entries=True)
        entries = list(fin.pop("entries", None) or [])
        import finance_recurrence as fin_recur
        for e in entries:
            e["name"] = normalize_entry_name(e.get("name"), e.get("category"))
            e["scheduled"] = fin_recur.is_future_month(str(e.get("month") or ""))
        return {**fin, "entries": entries}

    payload = await simple_cache.get_or_set(cache_key, _DEPT_LIST_CACHE_TTL_SECONDS, loader)
    # Analytics + Google capabilities are per-request / per-user — keep out of cache.
    asyncio.create_task(_product_event(
        ws_id, principal["user_id"],
        helm_analytics.EVENT_DEPARTMENT_PAGE_VIEWED,
        {"department": dept_catalog.TYPE_ACCOUNTING_FINANCE},
    ))
    my_google = await _user_google_tokens(ws_id, principal["user_id"])
    c = await get_ws(ws_id)
    return {
        **payload,
        "can_write": await can_access_financials(principal),
        "can_manage": "integrations:manage" in perms_for(principal["pack"]),
        "google": gcal.google_capabilities(my_google),
        "accounting": _workspace_accounting_sync(c),
    }


class FinEntryInput(BaseModel):
    type: str
    category: str
    name: str
    amount: float
    month: str
    recurring: bool = False
    recurrence: Optional[str] = None  # "monthly" | "annual" when recurring (expenses)
    note: Optional[str] = ""
    source_document_id: Optional[str] = None


def _fin_entry_recurrence(payload: "FinEntryInput") -> Optional[str]:
    import finance_recurrence as fin_recur
    return fin_recur.normalize_recurrence(payload.recurring, payload.recurrence, payload.type)


ALLOWED_DOC_TYPES = frozenset({"application/pdf", "image/png", "image/jpeg"})
# Reports digest accepts bills-style files plus spreadsheets. Bills pipeline above
# stays on ALLOWED_DOC_TYPES only — do not widen that set.
ALLOWED_REPORT_DOC_TYPES = frozenset({
    "application/pdf",
    "image/png",
    "image/jpeg",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
    "application/csv",
})
MAX_DOC_BYTES = 15 * 1024 * 1024


async def _read_validated_document(file: UploadFile) -> bytes:
    """Read a bounded upload and verify its bytes match the claimed media type."""
    data = await file.read(MAX_DOC_BYTES + 1)
    if len(data) > MAX_DOC_BYTES:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 15MB.")
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    signatures = {
        "application/pdf": (b"%PDF-",),
        "image/png": (b"\x89PNG\r\n\x1a\n",),
        "image/jpeg": (b"\xff\xd8\xff",),
    }
    if not any(data.startswith(sig) for sig in signatures.get(file.content_type, ())):
        raise HTTPException(status_code=400, detail="File content does not match its declared type.")
    return data


async def _read_validated_report_document(file: UploadFile) -> bytes:
    """Bounded read + type check for report digest uploads (PDF/images + sheets)."""
    data = await file.read(MAX_DOC_BYTES + 1)
    if len(data) > MAX_DOC_BYTES:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 15MB.")
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    ctype = file.content_type or ""
    if ctype == "application/pdf":
        ok = data.startswith(b"%PDF-")
    elif ctype == "image/png":
        ok = data.startswith(b"\x89PNG\r\n\x1a\n")
    elif ctype == "image/jpeg":
        ok = data.startswith(b"\xff\xd8\xff")
    elif ctype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        # xlsx is a ZIP package
        ok = data.startswith(b"PK\x03\x04") or data.startswith(b"PK\x05\x06")
    elif ctype in ("text/csv", "application/csv"):
        # Reject obvious binary masquerading as CSV
        ok = b"\x00" not in data[:1024]
    else:
        ok = False
    if not ok:
        raise HTTPException(status_code=400, detail="File content does not match its declared type.")
    return data


@api_router.get("/documents/library")
async def documents_library(
    background_tasks: BackgroundTasks,
    principal=Depends(get_principal),
):
    """List every document the caller may open — filtered by each context's own permission bar.

    Returns metadata + open_path only (no presigned URLs). Opening a file still goes through
    the existing per-context GET endpoint.
    """
    ws_id = principal["workspace_id"]
    uid = principal["user_id"]
    # Hoist membership + workspace once — can_section_write would re-fetch both otherwise.
    membership = await _membership_for(principal)
    workspace = await get_ws(ws_id)
    can_fin, can_rep = await asyncio.gather(
        can_section_write(
            principal, "financials", "finance:write",
            membership=membership, workspace=workspace,
        ),
        can_section_write(
            principal, "reports", "reports:write",
            membership=membership, workspace=workspace,
        ),
    )

    async def _load_financial() -> list[dict]:
        rows = await db.documents.find(
            {"workspace_id": ws_id},
            {
                "_id": 0,
                "id": 1,
                "filename": 1,
                "content_type": 1,
                "uploaded_at": 1,
                "uploaded_by": 1,
                "status": 1,
            },
        ).sort("uploaded_at", -1).to_list(500)
        out = []
        for d in rows:
            doc_id = d.get("id")
            if not doc_id:
                continue
            out.append({
                "id": doc_id,
                "context": "financial",
                "filename": d.get("filename") or "document",
                "content_type": d.get("content_type"),
                "uploaded_at": d.get("uploaded_at"),
                "uploaded_by": d.get("uploaded_by"),
                "status": d.get("status"),
                "open_path": f"/documents/{doc_id}",
            })
        return out

    async def _load_reports() -> list[dict]:
        rows = await db.report_documents.find(
            {"workspace_id": ws_id},
            {
                "_id": 0,
                "id": 1,
                "filename": 1,
                "content_type": 1,
                "uploaded_at": 1,
                "uploaded_by": 1,
                "report_date": 1,
                "status": 1,
            },
        ).sort("uploaded_at", -1).to_list(500)
        out = []
        for d in rows:
            doc_id = d.get("id")
            if not doc_id:
                continue
            out.append({
                "id": doc_id,
                "context": "reports",
                "filename": d.get("filename") or "report",
                "content_type": d.get("content_type"),
                "uploaded_at": d.get("uploaded_at"),
                "uploaded_by": d.get("uploaded_by"),
                "report_date": d.get("report_date"),
                "status": d.get("status"),
                "open_path": f"/reports/documents/{doc_id}",
            })
        return out

    async def _load_legal() -> list[dict]:
        try:
            dept = await _legal_department(principal)
        except HTTPException:
            return []
        dept_membership = await dept_access.get_department_membership(
            db, dept["department_id"], uid,
        )
        is_lead = _can_lead_legal(principal, dept_membership)
        filt: dict = {
            "department_id": dept["department_id"],
            "document_ref.storage_key": {"$type": "string", "$ne": ""},
        }
        # Non-leads: push assignee filter into Mongo instead of scanning every matter.
        if not is_lead:
            filt["assigned_to"] = uid
        matters = await db.legal_matters.find(
            filt,
            {
                "_id": 0,
                "id": 1,
                "title": 1,
                "assigned_to": 1,
                "document_ref.document_id": 1,
                "document_ref.filename": 1,
                "document_ref.content_type": 1,
                "document_ref.uploaded_at": 1,
                "document_ref.uploaded_by": 1,
            },
        ).sort("updated_at", -1).to_list(500)
        out = []
        for matter in matters:
            if not is_lead and matter.get("assigned_to") != uid:
                continue
            ref = matter.get("document_ref") if isinstance(matter.get("document_ref"), dict) else {}
            mid = matter.get("id")
            if not mid:
                continue
            out.append({
                "id": ref.get("document_id") or mid,
                "context": "legal",
                "matter_id": mid,
                "matter_title": matter.get("title"),
                "filename": ref.get("filename") or "document",
                "content_type": ref.get("content_type"),
                "uploaded_at": ref.get("uploaded_at"),
                "uploaded_by": ref.get("uploaded_by"),
                "open_path": f"/legal/matters/{mid}/document",
            })
        return out

    loads = []
    if can_fin:
        loads.append(_load_financial())
    if can_rep:
        loads.append(_load_reports())
    loads.append(_load_legal())
    chunks = await asyncio.gather(*loads)
    items = [row for chunk in chunks for row in chunk]

    background_tasks.add_task(
        _audit_document_access,
        principal,
        "documents",
        "document.library.view",
        f"Viewed document library · {len(items)} item{'s' if len(items) != 1 else ''}",
        {"count": len(items)},
    )
    return {"documents": items, "count": len(items)}


async def _audit_document_access(principal, module: str, action: str, summary: str, patch=None) -> None:
    """Best-effort activity log for document access — never raises to the caller."""
    try:
        await log_activity(principal, module, action, summary, patch)
    except Exception:
        logger.exception("document access audit failed action=%s", action)


def _document_response_without_storage(doc: dict, *, presigned_url: str) -> dict:
    """Presigned GET payloads must not echo the private R2 object key."""
    out = {k: v for k, v in doc.items() if k not in ("_id", "storage_key")}
    out["presigned_url"] = presigned_url
    return out


@api_router.post("/documents/upload")
async def upload_financial_document(
    file: UploadFile = File(...),
    principal=Depends(require_section("financials", "finance:write")),
):
    await _enforce_ai_extract_quota(principal)
    await _enforce_document_rate_limit(
        principal, "upload", doc_rate_limit.DOC_UPLOAD_HOURLY_LIMIT,
        "Upload limit reached. Try again in a bit",
    )
    if file.content_type not in ALLOWED_DOC_TYPES:
        raise HTTPException(status_code=400, detail="File type not allowed. Upload PDF, PNG, or JPEG.")
    data = await _read_validated_document(file)
    if not doc_storage.r2_configured():
        raise HTTPException(status_code=503, detail="Document storage is not configured")
    filename = (file.filename or "document").replace("/", "_").replace("\\", "_")[:200]
    try:
        storage_key = await asyncio.to_thread(
            doc_storage.upload_document,
            principal["workspace_id"], data, filename, file.content_type,
        )
    except Exception as exc:
        logger.exception("document upload failed")
        raise HTTPException(status_code=500, detail="Could not store document") from exc
    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    doc = {
        "id": doc_id,
        "workspace_id": principal["workspace_id"],
        "storage_key": storage_key,
        "filename": filename,
        "content_type": file.content_type,
        "uploaded_by": principal["user_id"],
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "status": "uploaded",
        "extracted_data": None,
        "linked_entry_id": None,
    }
    await db.documents.insert_one(doc)
    await log_activity(principal, "financials", "document.upload", f"Uploaded bill · {filename}")
    return {"document_id": doc_id, "status": "uploaded"}


@api_router.post("/documents/{document_id}/extract")
async def extract_financial_document_route(
    document_id: str,
    force: bool = Query(False),
    principal=Depends(require_section("financials", "finance:write")),
):
    doc = await db.documents.find_one(
        {"id": document_id, "workspace_id": principal["workspace_id"]}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if (
        not force
        and doc.get("status") == "extracted"
        and doc.get("extracted_data")
    ):
        return doc["extracted_data"]
    if not helm_llm.extraction_configured():
        raise HTTPException(status_code=503, detail="AI extraction is not configured")
    quota_ticket = await _acquire_ai_extract_quota(principal)
    await _enforce_document_rate_limit(
        principal, "extract", doc_rate_limit.DOC_EXTRACT_HOURLY_LIMIT,
        "Extraction limit reached. Try again in a bit",
    )
    use_document_ai = False
    if gcp_docai.document_ai_configured():
        use_document_ai = await doc_rate_limit.document_ai_allowed(db, principal["workspace_id"])
    try:
        file_bytes = await asyncio.to_thread(doc_storage.get_document_bytes, doc["storage_key"])
        if use_document_ai:
            await doc_rate_limit.record_document_ai(db, principal["workspace_id"])
        extracted = await helm_llm.extract_financial_document(
            file_bytes, doc["content_type"], use_document_ai=use_document_ai,
        )
        status = "failed" if extracted.get("error") in ("not_financial", "unparseable_amount") else "extracted"
        await db.documents.update_one(
            {"id": document_id, "workspace_id": principal["workspace_id"]},
            {"$set": {"status": status, "extracted_data": extracted}},
        )
        if status == "extracted":
            await log_activity(
                principal, "financials", "document.extract",
                f"Extracted bill data · {doc['filename']}",
            )
            await _product_event(
                principal["workspace_id"], principal["user_id"],
                helm_analytics.EVENT_AI_EXTRACT,
                {"document_id": document_id},
            )
        else:
            await _release_ai_extract_quota(principal, quota_ticket)
            quota_ticket = None
        return extracted
    except ValueError as exc:
        await _release_ai_extract_quota(principal, quota_ticket)
        quota_ticket = None
        await db.documents.update_one(
            {"id": document_id, "workspace_id": principal["workspace_id"]},
            {"$set": {"status": "failed", "extracted_data": {"error": "parse_failed"}}},
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        await _release_ai_extract_quota(principal, quota_ticket)
        quota_ticket = None
        logger.exception("document extract failed for %s", document_id)
        await db.documents.update_one(
            {"id": document_id, "workspace_id": principal["workspace_id"]},
            {"$set": {"status": "failed", "extracted_data": {"error": "extract_failed"}}},
        )
        raise HTTPException(status_code=500, detail="Could not extract document") from exc


@api_router.get("/documents/{document_id}")
async def get_financial_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    principal=Depends(require_section("financials", "finance:write")),
):
    doc = await db.documents.find_one(
        {"id": document_id, "workspace_id": principal["workspace_id"]}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    storage_key = doc.get("storage_key")
    if not storage_key:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        presigned_url = await asyncio.to_thread(doc_storage.get_presigned_url, storage_key)
    except Exception as exc:
        logger.exception("presigned url failed for %s", document_id)
        raise HTTPException(status_code=500, detail="Could not generate document URL") from exc
    background_tasks.add_task(
        _audit_document_access,
        principal,
        "financials",
        "document.download",
        f"Opened bill · {doc.get('filename') or document_id}",
        {"document_id": document_id},
    )
    return _document_response_without_storage(doc, presigned_url=presigned_url)


class DriveImportInput(BaseModel):
    file_id: str


@api_router.post("/documents/from-drive")
async def import_financial_document_from_drive(
    payload: DriveImportInput,
    principal=Depends(require_section("financials", "finance:write")),
):
    file_id = (payload.file_id or "").strip()
    if not file_id:
        raise HTTPException(status_code=400, detail="file_id is required")
    c = await get_ws(principal["workspace_id"])
    tokens = await _require_user_google_tokens(principal)
    if not gcal.has_scope(tokens, "drive.file"):
        raise HTTPException(status_code=400, detail="Reconnect Google to import from Drive")
    await _enforce_ai_extract_quota(principal)
    await _enforce_document_rate_limit(
        principal, "upload", doc_rate_limit.DOC_UPLOAD_HOURLY_LIMIT,
        "Upload limit reached. Try again in a bit",
    )
    if not doc_storage.r2_configured():
        raise HTTPException(status_code=503, detail="Document storage is not configured")
    try:
        data, mime, name, refreshed = await gcal.download_drive_file(
            tokens, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, file_id,
        )
        await _store_user_google_tokens(c["workspace_id"], principal["user_id"], refreshed)
    except gcal.GoogleAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Drive import failed")
        raise HTTPException(status_code=400, detail="Could not download that Drive file") from exc
    if mime not in ALLOWED_DOC_TYPES:
        raise HTTPException(status_code=400, detail="Use a PDF, PNG, or JPEG from Drive")
    if len(data) > MAX_DOC_BYTES:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 15MB.")
    filename = (name or "document").replace("/", "_").replace("\\", "_")[:200]
    try:
        storage_key = await asyncio.to_thread(
            doc_storage.upload_document,
            principal["workspace_id"], data, filename, mime,
        )
    except Exception as exc:
        logger.exception("document upload failed")
        raise HTTPException(status_code=500, detail="Could not store document") from exc
    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    doc = {
        "id": doc_id,
        "workspace_id": principal["workspace_id"],
        "storage_key": storage_key,
        "filename": filename,
        "content_type": mime,
        "uploaded_by": principal["user_id"],
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "status": "uploaded",
        "extracted_data": None,
        "linked_entry_id": None,
        "source": "google_drive",
    }
    await db.documents.insert_one(doc)
    await log_activity(principal, "financials", "document.upload", f"Imported from Drive · {filename}")
    return {"document_id": doc_id, "status": "uploaded"}


@api_router.post("/financials/export-sheets")
async def export_financials_to_sheets(principal=Depends(require_section("financials", "finance:write"))):
    c = await get_ws(principal["workspace_id"])
    tokens = await _require_user_google_tokens(principal)
    if not gcal.has_scope(tokens, "spreadsheets"):
        raise HTTPException(status_code=400, detail="Reconnect Google to export to Sheets")
    dept_ids = await dept_access.accessible_department_ids(
        db, principal, dept_catalog.TYPE_ACCOUNTING_FINANCE,
    )
    fin = await compute_financials(principal["workspace_id"], department_ids=dept_ids)
    entry_filt = dept_access.apply_department_filter(
        {"workspace_id": principal["workspace_id"]}, dept_ids,
    )
    entries = await db.financial_entries.find(entry_filt, {"_id": 0}).sort("month", -1).to_list(5000)
    company = c.get("name") or "Trenston"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    summary_rows = [
        ["Metric", "Value"],
        ["Company", company],
        ["Exported", today],
        ["MRR", fin.get("mrr") or "—"],
        ["ARR", fin.get("arr") or "—"],
        ["Cash", fin.get("cash") or "—"],
        ["Burn", fin.get("burn") or "—"],
        ["Runway (months)", format_runway_display(fin, missing="—")],
        ["Gross margin", fin.get("gross_margin") or "—"],
    ]
    entry_rows = [["Month", "Type", "Name", "Category", "Amount", "Recurring", "Note"]]
    for e in entries:
        entry_rows.append([
            e.get("month") or "",
            e.get("type") or "",
            normalize_entry_name(e.get("name"), e.get("category")),
            e.get("category") or "",
            e.get("amount") if e.get("amount") is not None else "",
            "yes" if e.get("recurring") else "",
            (e.get("note") or "")[:200],
        ])
    body = gcal.build_ledger_spreadsheet_body(
        f"{company} financials {today}",
        summary_rows,
        entry_rows,
    )
    try:
        sid, url, refreshed = await gcal.create_spreadsheet(
            tokens, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, body,
        )
        await _store_user_google_tokens(c["workspace_id"], principal["user_id"], refreshed)
    except gcal.GoogleAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Sheets export failed")
        raise HTTPException(status_code=500, detail="Could not create Google Sheet") from exc
    await log_activity(principal, "financials", "sheets.export", "Exported financials to Google Sheets")
    return {"spreadsheet_id": sid, "url": url}


@api_router.post("/financials/entries")
async def add_fin_entry(payload: FinEntryInput, principal=Depends(require_section("financials", "finance:write"))):
    from pymongo.errors import DuplicateKeyError

    if payload.type not in ("revenue", "expense"):
        raise HTTPException(status_code=400, detail="type must be revenue or expense")
    _reject_future_fin_month(payload.month)
    if payload.amount < 0:
        raise HTTPException(status_code=400, detail="amount must be non-negative")
    if not math.isfinite(payload.amount):
        raise HTTPException(status_code=400, detail="amount must be a finite number")
    try:
        entry_name = require_entry_name(payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    source = "manual"
    source_document_id = payload.source_document_id
    if source_document_id:
        # Atomic claim: only transition uploaded/extracted → committing once
        from pymongo import ReturnDocument
        claim = await db.documents.find_one_and_update(
            {
                "id": payload.source_document_id,
                "workspace_id": principal["workspace_id"],
                "status": {"$in": ["uploaded", "extracted"]},
            },
            {"$set": {"status": "committing"}},
            return_document=ReturnDocument.AFTER,
        )
        if not claim:
            src_doc = await db.documents.find_one(
                {"id": payload.source_document_id, "workspace_id": principal["workspace_id"]}, {"_id": 0},
            )
            if not src_doc:
                raise HTTPException(status_code=400, detail="Source document not found")
            raise HTTPException(status_code=400, detail="Document already committed to an entry")
        source = "ai_upload"
        source_document_id = payload.source_document_id
    finance_dept_id = await dept_migrate.finance_department_id(db, principal["workspace_id"])
    if not finance_dept_id:
        raise HTTPException(status_code=500, detail="Finance department is not available. Try again")
    # Keep writers enrolled so the new row stays visible under department filters.
    try:
        await dept_migrate.ensure_department_member(
            db, finance_dept_id, principal["user_id"], role="member",
        )
    except Exception:
        logger.exception("finance department enroll failed for %s", principal.get("user_id"))
    category = (payload.category or "").strip() or "Other"
    entry = {
        "id": f"fe_{uuid.uuid4().hex[:10]}",
        "workspace_id": principal["workspace_id"],
        "department_id": finance_dept_id,
        "type": payload.type,
        "category": category,
        "name": entry_name,
        "amount": round(payload.amount, 2),
        "month": payload.month.strip(),
        "recurring": payload.recurring,
        "note": (payload.note or "").strip(),
        "source": source,
        "created_by": principal["user_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    # Omit null optional keys — sparse unique indexes on qb_txn_id / source_deal_id
    # still index explicit nulls, so never store those fields as null on manual rows.
    recurrence = _fin_entry_recurrence(payload)
    if recurrence:
        entry["recurrence"] = recurrence
    if source_document_id:
        entry["source_document_id"] = source_document_id
    try:
        await db.financial_entries.insert_one(entry)
    except DuplicateKeyError as exc:
        logger.exception("financial entry insert duplicate key for %s", principal["workspace_id"])
        raise HTTPException(
            status_code=409,
            detail="Could not save this entry: a matching ledger row already exists. Refresh and try again.",
        ) from exc
    invalidate_financials_cache(principal["workspace_id"])
    entry.pop("_id", None)
    if source_document_id:
        await db.documents.update_one(
            {"id": source_document_id, "workspace_id": principal["workspace_id"]},
            {"$set": {"status": "committed", "linked_entry_id": entry["id"]}},
        )
    try:
        await log_activity(
            principal, "financials", "entry.add",
            f"Logged {payload.type} · {entry['name']} {fmt_money(entry['amount'], await _workspace_currency(principal['workspace_id']))} ({payload.month})",
            {"type": payload.type, "amount": entry["amount"], "month": payload.month},
        )
    except Exception:
        # Entry is already persisted — don't fail the client over the activity feed.
        logger.exception("activity log failed after financial entry add")
    return {"ok": True, "entry": entry}


@api_router.patch("/financials/entries/{entry_id}")
async def edit_fin_entry(entry_id: str, payload: FinEntryInput, principal=Depends(require_section("financials", "finance:write"))):
    if payload.type not in ("revenue", "expense"):
        raise HTTPException(status_code=400, detail="type must be revenue or expense")
    _reject_future_fin_month(payload.month)
    if payload.amount < 0:
        raise HTTPException(status_code=400, detail="amount must be non-negative")
    if not math.isfinite(payload.amount):
        raise HTTPException(status_code=400, detail="amount must be a finite number")
    try:
        entry_name = require_entry_name(payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    category = (payload.category or "").strip() or "Other"
    res = await db.financial_entries.update_one(
        {"id": entry_id, "workspace_id": principal["workspace_id"]},
        {"$set": {"type": payload.type, "category": category, "name": entry_name,
                  "amount": round(payload.amount, 2), "month": payload.month.strip(),
                  "recurring": payload.recurring, "recurrence": _fin_entry_recurrence(payload),
                  "note": (payload.note or "").strip()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Entry not found")
    invalidate_financials_cache(principal["workspace_id"])
    await log_activity(principal, "financials", "entry.edit",
                       f"Updated a {payload.type} entry · {entry_name} ({payload.month})")
    return {"ok": True}


@api_router.delete("/financials/entries/{entry_id}")
async def delete_fin_entry(entry_id: str, principal=Depends(require_section("financials", "finance:write"))):
    doc = await db.financial_entries.find_one({"id": entry_id, "workspace_id": principal["workspace_id"]}, {"_id": 0})
    await db.financial_entries.delete_one({"id": entry_id, "workspace_id": principal["workspace_id"]})
    invalidate_financials_cache(principal["workspace_id"])
    if doc:
        label = normalize_entry_name(doc.get("name"), doc.get("category"))
        await log_activity(principal, "financials", "entry.delete",
                           f"Removed a {doc.get('type')} entry · {label} ({doc.get('month')})")
    return {"ok": True}


class FinSettingsInput(BaseModel):
    cash: Optional[float] = None
    gross_margin: Optional[float] = None
    currency: Optional[str] = None


@api_router.put("/financials/settings")
async def update_fin_settings(payload: FinSettingsInput, principal=Depends(require_section("financials", "finance:write"))):
    if payload.cash is not None and not math.isfinite(payload.cash):
        raise HTTPException(status_code=400, detail="cash must be a finite number")
    if payload.gross_margin is not None and not math.isfinite(payload.gross_margin):
        raise HTTPException(status_code=400, detail="gross_margin must be a finite number")
    currency = normalize_currency(payload.currency) if payload.currency is not None else None
    sets: dict = {
        "financial_settings.gross_margin": payload.gross_margin,
    }
    if payload.cash is not None:
        sets["financial_settings.cash"] = round(payload.cash, 2)
        sets["financial_settings.cash_entered"] = True
    if currency is not None:
        sets["financial_settings.currency"] = currency
    await db.workspaces.update_one({"workspace_id": principal["workspace_id"]}, {"$set": sets})
    invalidate_financials_cache(principal["workspace_id"])
    fin = await compute_financials(principal["workspace_id"])
    runway = fin["runway_months"]
    cur = fin.get("currency") or "usd"
    cash_note = (
        f"Updated cash to {fmt_money(payload.cash, cur)}"
        if payload.cash is not None
        else "Updated financial settings"
    )
    await log_activity(
        principal, "financials", "settings.update",
        cash_note + (f", runway now {runway}mo" if runway is not None and payload.cash is not None else ""),
        {"cash": payload.cash, "runway_months": runway, "currency": cur},
    )
    return {"ok": True, "settings": fin.get("settings"), "currency": cur}

class CsvImportConfirmInput(BaseModel):
    entries: list


@api_router.post("/financials/import-csv")
async def import_financials_csv_preview(
    file: UploadFile = File(...),
    principal=Depends(require_section("financials", "finance:write")),
):
    """Parse + validate CSV; return preview without writing to financial_entries."""
    import finance_csv as fin_csv
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="CSV too large (max 5MB)")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("latin-1")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="Could not decode CSV as UTF-8 or Latin-1")
    try:
        parsed = fin_csv.parse_financial_csv(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("csv parse failed")
        raise HTTPException(status_code=400, detail="Malformed CSV. Check headers and row formatting")
    return {
        "ok": True,
        "preview": True,
        "committed": False,
        "filename": file.filename,
        **parsed,
    }


@api_router.post("/financials/import-csv/confirm")
async def import_financials_csv_confirm(
    payload: CsvImportConfirmInput,
    principal=Depends(require_section("financials", "finance:write")),
):
    """Bulk-insert previously previewed valid rows with source=csv_import."""
    if not payload.entries:
        raise HTTPException(status_code=400, detail="No entries to import")
    if len(payload.entries) > 5000:
        raise HTTPException(status_code=400, detail="Too many rows (max 5000)")
    now = datetime.now(timezone.utc).isoformat()
    finance_dept_id = await dept_migrate.finance_department_id(db, principal["workspace_id"])
    docs = []
    for raw in payload.entries:
        if not isinstance(raw, dict):
            continue
        entry_type = (raw.get("type") or "").strip().lower()
        if entry_type not in ("revenue", "expense"):
            continue
        try:
            amount = round(float(raw.get("amount")), 2)
        except (TypeError, ValueError):
            continue
        if amount < 0:
            continue
        month = (raw.get("month") or "").strip()
        if not re.fullmatch(r"\d{4}-\d{2}", month) or not _valid_fin_month(month):
            continue
        category = (raw.get("category") or "Other").strip() or "Other"
        docs.append({
            "id": f"fe_{uuid.uuid4().hex[:10]}",
            "workspace_id": principal["workspace_id"],
            "department_id": finance_dept_id,
            "type": entry_type,
            "category": category,
            "name": normalize_entry_name(raw.get("name"), category),
            "amount": amount,
            "month": month,
            "recurring": bool(raw.get("recurring")),
            "note": (raw.get("note") or "").strip(),
            "source": "csv_import",
            "created_by": principal["user_id"],
            "created_at": now,
        })
    if not docs:
        raise HTTPException(status_code=400, detail="No valid entries to import")
    await db.financial_entries.insert_many(docs)
    invalidate_financials_cache(principal["workspace_id"])
    for d in docs:
        d.pop("_id", None)
    await log_activity(
        principal, "financials", "entry.import",
        f"Imported {len(docs)} entr{'y' if len(docs) == 1 else 'ies'} from CSV",
        {"count": len(docs), "source": "csv_import"},
    )
    return {"ok": True, "committed": True, "imported_count": len(docs), "entries": docs}


@api_router.get("/tasks")
async def tasks(principal=Depends(get_principal)):
    c = await get_ws(principal["workspace_id"])
    t = _normalize_task_columns(dict(c["tasks"]))
    t["can_create"] = "tasks:create" in perms_for(principal["pack"])
    t["can_assign"] = await can_section_write(principal, "tasks", "tasks:assign")
    t["my_user_id"] = principal["user_id"]
    return t


@api_router.get("/tasks/me")
async def my_tasks(principal=Depends(get_principal)):
    c = await get_ws(principal["workspace_id"])
    items = [t for t in c["tasks"]["items"] if t.get("assignee_user_id") == principal["user_id"]]
    return {"items": items, "columns": _normalize_task_columns(c["tasks"])["columns"]}


class TaskInput(BaseModel):
    title: str
    priority: str = "Medium"
    tag: str = "General"
    due: str = ""
    column: str = "backlog"
    assignee_user_id: Optional[str] = None


@api_router.post("/tasks")
async def create_task(payload: TaskInput, principal=Depends(require_pro_perm("tasks:create"))):
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="Title is required")
    c = await get_ws(principal["workspace_id"])
    t = c["tasks"]
    assignee_uid = principal["user_id"]
    assignee_name = principal.get("name") or principal.get("email") or "Me"
    if payload.assignee_user_id and payload.assignee_user_id != principal["user_id"]:
        if not await can_section_write(principal, "tasks", "tasks:assign"):
            raise HTTPException(status_code=403, detail="You can only create tasks for yourself")
        member = await db.memberships.find_one({"workspace_id": principal["workspace_id"], "user_id": payload.assignee_user_id, "status": "active"}, {"_id": 0})
        if not member:
            raise HTTPException(status_code=404, detail="Assignee is not in this workspace")
        u = await db.users.find_one({"user_id": payload.assignee_user_id}, {"_id": 0, "name": 1})
        assignee_uid = payload.assignee_user_id
        assignee_name = (u or {}).get("name") or member["email"]
    item = {"id": f"t_{uuid.uuid4().hex[:8]}", "title": payload.title.strip(),
            "assignee": assignee_name, "assignee_user_id": assignee_uid,
            "priority": payload.priority if payload.priority in ("High", "Medium", "Low") else "Medium",
            "column": payload.column or "backlog", "tag": (payload.tag or "General").strip(),
            "due": (payload.due or "").strip(), "progress": 0}
    if item["column"] == "done":
        item["progress"] = 100
        item["done_at"] = datetime.now(timezone.utc).isoformat()
    t["items"].append(item)
    await db.workspaces.update_one({"workspace_id": c["workspace_id"]}, {"$set": {"tasks": t}})
    invalidate_workspace_list_cache(principal["workspace_id"], "tasks", "me_work", "calendar", "reports")
    await notify_task_delegated(
        assignee_user_id=assignee_uid,
        previous_assignee_user_id=None,
        task=item,
        principal=principal,
        workspace_name=c.get("name") or "your company",
    )
    return {"ok": True, "task": item}


class TaskPatch(BaseModel):
    column: Optional[str] = None
    assignee_user_id: Optional[str] = None


@api_router.patch("/tasks/{task_id}")
async def patch_task(task_id: str, payload: TaskPatch, principal=Depends(require_pro_perm("tasks:move"))):
    c = await get_ws(principal["workspace_id"])
    t = c["tasks"]
    target = next((i for i in t["items"] if i["id"] == task_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Task not found")
    owns = target.get("assignee_user_id") == principal["user_id"]
    if target.get("assignee_user_id") and not owns and not await can_section_write(principal, "tasks", "tasks:assign"):
        raise HTTPException(status_code=403, detail="You can only move your own tasks")

    fields = payload.model_dump(exclude_unset=True)
    prev_assignee = target.get("assignee_user_id")

    if "column" in fields and fields["column"] is not None:
        prev_col = target.get("column")
        target["column"] = fields["column"]
        if fields["column"] == "done":
            target["progress"] = 100
            if prev_col != "done" or not target.get("done_at"):
                target["done_at"] = datetime.now(timezone.utc).isoformat()
        elif prev_col == "done":
            target.pop("done_at", None)
            # Leaving Done should not keep a 100% progress display.
            if fields.get("progress") is None:
                target["progress"] = 50

    if "assignee_user_id" in fields:
        if not await can_section_write(principal, "tasks", "tasks:assign"):
            raise HTTPException(status_code=403, detail="You cannot reassign tasks")
        new_uid = (fields["assignee_user_id"] or "").strip() or None
        if new_uid:
            member = await db.memberships.find_one(
                {"workspace_id": principal["workspace_id"], "user_id": new_uid, "status": "active"},
                {"_id": 0},
            )
            if not member:
                raise HTTPException(status_code=404, detail="Assignee is not in this workspace")
            u = await db.users.find_one({"user_id": new_uid}, {"_id": 0, "name": 1})
            target["assignee_user_id"] = new_uid
            target["assignee"] = (u or {}).get("name") or member.get("email") or "Teammate"
        else:
            target["assignee_user_id"] = principal["user_id"]
            target["assignee"] = principal.get("name") or principal.get("email") or "Me"

    await db.workspaces.update_one({"workspace_id": c["workspace_id"]}, {"$set": {"tasks": t}})
    invalidate_workspace_list_cache(principal["workspace_id"], "tasks", "me_work", "calendar", "reports")
    if "assignee_user_id" in fields:
        await notify_task_delegated(
            assignee_user_id=target.get("assignee_user_id"),
            previous_assignee_user_id=prev_assignee,
            task=target,
            principal=principal,
            workspace_name=c.get("name") or "your company",
        )
    return {"ok": True}


@api_router.delete("/tasks/done")
async def clear_done_tasks(principal=Depends(require_pro_perm("tasks:move"))):
    """Remove finished (Done) tasks from the board."""
    c = await get_ws(principal["workspace_id"])
    t = c["tasks"]
    can_assign = await can_section_write(principal, "tasks", "tasks:assign")
    uid = principal["user_id"]
    kept, cleared = [], 0
    for item in t.get("items") or []:
        if item.get("column") != "done":
            kept.append(item)
            continue
        owns = item.get("assignee_user_id") == uid
        unassigned = not item.get("assignee_user_id")
        if can_assign or owns or unassigned:
            cleared += 1
        else:
            kept.append(item)
    if cleared:
        t["items"] = kept
        await db.workspaces.update_one({"workspace_id": c["workspace_id"]}, {"$set": {"tasks": t}})
        invalidate_workspace_list_cache(principal["workspace_id"], "tasks", "me_work", "calendar", "reports")
        await log_activity(principal, "tasks", "tasks.clear_done", f"Cleared {cleared} finished task{'s' if cleared != 1 else ''}")
    return {"ok": True, "cleared": cleared}


# ------------------------- Daily updates -------------------------
class UpdateInput(BaseModel):
    text: str
    blocker: bool = False


@api_router.get("/updates/me")
async def my_update(principal=Depends(get_principal)):
    day = datetime.now(timezone.utc).date().isoformat()
    u = await db.updates.find_one({"workspace_id": principal["workspace_id"], "user_id": principal["user_id"], "day": day}, {"_id": 0})
    return {"update": u, "day": day}


@api_router.get("/updates/today")
async def todays_updates(principal=Depends(get_principal)):
    day = datetime.now(timezone.utc).date().isoformat()
    ups = await db.updates.find({"workspace_id": principal["workspace_id"], "day": day}, {"_id": 0}).sort("updated_at", -1).to_list(50)
    for u in ups:
        u["ago"] = _rel_time(u.get("updated_at", ""))
    return {"updates": ups, "day": day}


@api_router.post("/updates")
async def post_update(payload: UpdateInput, principal=Depends(require_pro_perm("updates:write"))):
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Update text is required")
    day = datetime.now(timezone.utc).date().isoformat()
    now = datetime.now(timezone.utc).isoformat()
    text = payload.text.strip()[:600]
    name = principal.get("name") or principal.get("email") or "Someone"
    summary = f'Update from {name}: "{text[:90]}"' + (" (blocked)" if payload.blocker else "")
    existing = await db.updates.find_one({"workspace_id": principal["workspace_id"], "user_id": principal["user_id"], "day": day}, {"_id": 0})
    if existing:
        await db.updates.update_one({"update_id": existing["update_id"]},
                                    {"$set": {"text": text, "blocker": payload.blocker, "updated_at": now}})
        if existing.get("activity_id"):
            await db.activities.update_one({"activity_id": existing["activity_id"]}, {"$set": {"summary": summary, "created_at": now}})
        invalidate_workspace_list_cache(principal["workspace_id"], "reports")
        return {"ok": True, "edited": True}
    act = await log_activity(principal, "updates", "daily.update", summary, {"blocker": payload.blocker})
    doc = {"update_id": f"upd_{uuid.uuid4().hex[:10]}", "workspace_id": principal["workspace_id"],
           "user_id": principal["user_id"], "user_name": name, "day": day, "text": text,
           "blocker": payload.blocker, "activity_id": act["activity_id"],
           "created_at": now, "updated_at": now}
    await db.updates.insert_one(doc)
    invalidate_workspace_list_cache(principal["workspace_id"], "reports")
    doc.pop("_id", None)
    return {"ok": True, "edited": False, "update": doc}


# ------------------------- Private notes (My Day) -------------------------
NOTE_COLORS = ("gold", "sky", "emerald", "rose", "violet", "amber")


class NoteInput(BaseModel):
    text: str
    color: str = "gold"


@api_router.get("/notes")
async def list_notes(principal=Depends(get_principal)):
    notes = await db.private_notes.find(
        {"workspace_id": principal["workspace_id"], "user_id": principal["user_id"]},
        {"_id": 0},
    ).sort("updated_at", -1).to_list(100)
    return {"notes": notes}


@api_router.post("/notes")
async def create_note(payload: NoteInput, principal=Depends(get_principal)):
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Note text is required")
    now = datetime.now(timezone.utc).isoformat()
    color = payload.color if payload.color in NOTE_COLORS else "gold"
    doc = {
        "note_id": f"note_{uuid.uuid4().hex[:10]}",
        "workspace_id": principal["workspace_id"],
        "user_id": principal["user_id"],
        "text": payload.text.strip()[:800],
        "color": color,
        "created_at": now,
        "updated_at": now,
    }
    await db.private_notes.insert_one(doc)
    invalidate_workspace_list_cache(principal["workspace_id"], "notes")
    doc.pop("_id", None)
    return {"ok": True, "note": doc}


@api_router.patch("/notes/{note_id}")
async def edit_note(note_id: str, payload: NoteInput, principal=Depends(get_principal)):
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Note text is required")
    now = datetime.now(timezone.utc).isoformat()
    color = payload.color if payload.color in NOTE_COLORS else None
    upd = {"text": payload.text.strip()[:800], "updated_at": now}
    if color:
        upd["color"] = color
    res = await db.private_notes.update_one(
        {"note_id": note_id, "workspace_id": principal["workspace_id"], "user_id": principal["user_id"]},
        {"$set": upd},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Note not found")
    invalidate_workspace_list_cache(principal["workspace_id"], "notes")
    return {"ok": True}


@api_router.delete("/notes/{note_id}")
async def delete_note(note_id: str, principal=Depends(get_principal)):
    res = await db.private_notes.delete_one(
        {"note_id": note_id, "workspace_id": principal["workspace_id"], "user_id": principal["user_id"]},
    )
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Note not found")
    invalidate_workspace_list_cache(principal["workspace_id"], "notes")
    return {"ok": True}


# ------------------------- My Work (cross-department feed) -------------------------
# Deep-link query params are not wired on department pages yet — URLs point at the
# department page itself (known limitation; Tasks is the only page with ?task= today).
_ME_WORK_URLS = helm_work_items.WORK_URLS


def _me_work_due(raw, today: date) -> tuple[Optional[str], bool]:
    return helm_work_items.due_info(raw, today)


def _me_work_row(
    *,
    item_id: str,
    department_type: str,
    title: str,
    due_raw,
    status: str,
    today: date,
    relationship: str = "assigned_to_me",
) -> dict:
    return helm_work_items.work_row(
        item_id=item_id,
        department_type=department_type,
        title=title,
        due_raw=due_raw,
        status=status,
        today=today,
        relationship=relationship,
    )


async def _me_work_dept_ids_by_type(
    principal: dict, dept_types: tuple[str, ...] | list[str],
) -> dict[str, Optional[list[str]]]:
    """Batched version of ``_me_work_dept_ids`` for all My Day department types."""
    access_by_type = await dept_access.accessible_department_ids_by_type(
        db, principal, dept_types,
    )
    out: dict[str, Optional[list[str]]] = {}
    # CEO bypass → need enabled department ids (one query for all types).
    ceo_types = [t for t, access in access_by_type.items() if access is None]
    enabled_ids_by_type: dict[str, Optional[list[str]]] = {t: None for t in ceo_types}
    if ceo_types:
        rows = await db.departments.find(
            {
                "workspace_id": principal["workspace_id"],
                "type": {"$in": ceo_types},
                "enabled": True,
            },
            {"_id": 0, "department_id": 1, "type": 1},
        ).to_list(200)
        buckets: dict[str, list[str]] = {t: [] for t in ceo_types}
        for row in rows:
            dtype = row.get("type")
            did = row.get("department_id")
            if dtype in buckets and did:
                buckets[dtype].append(did)
        enabled_ids_by_type = {t: (ids or None) for t, ids in buckets.items()}

    for dtype in dept_types:
        access = access_by_type.get(dtype)
        if access is not None:
            out[dtype] = access if access else None
        else:
            out[dtype] = enabled_ids_by_type.get(dtype)
    return out


async def _me_work_dept_ids(principal: dict, dept_type: str) -> Optional[list[str]]:
    """Department ids to query for this type, or None to skip entirely.

    Non-CEO with no membership → []. CEO → enabled dept ids (assignee filter still applies).
    """
    batched = await _me_work_dept_ids_by_type(principal, (dept_type,))
    return batched.get(dept_type)


@api_router.get("/me/work-items")
async def my_work_items(principal=Depends(get_principal)):
    """Cross-department open items assigned to (or, for Procurement, requested by) me."""
    types = (
        dept_catalog.TYPE_PRODUCTION,
        dept_catalog.TYPE_LEGAL,
        dept_catalog.TYPE_ENGINEERING_MAINTENANCE,
        dept_catalog.TYPE_HR,
        dept_catalog.TYPE_SALES,
        dept_catalog.TYPE_PROCUREMENT,
    )
    department_ids_by_type = await _me_work_dept_ids_by_type(principal, types)
    items = await helm_work_items.collect_for_user(
        db,
        principal["workspace_id"],
        principal["user_id"],
        department_ids_by_type=department_ids_by_type,
        include_procurement=True,
    )
    return {"items": items}


def _parse_iso_dt(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _shipped_in_window(items, *, now: Optional[datetime] = None, days: int = 7) -> int:
    """Count tasks that entered done within the last `days` (requires done_at)."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    n = 0
    for t in items:
        if t.get("column") != "done":
            continue
        done_at = _parse_iso_dt(t.get("done_at"))
        if done_at is not None and done_at >= cutoff:
            n += 1
    return n


def _signed_delta(curr, prev, *, money: bool = False, suffix: str = "", currency: str = "usd") -> str:
    if prev is None and curr is None:
        return "first week, no trend yet"
    if prev is None:
        return "first week, no trend yet"
    try:
        delta = float(curr if curr is not None else 0) - float(prev if prev is not None else 0)
    except (TypeError, ValueError):
        return "first week, no trend yet"
    if abs(delta) < 0.05:
        return f"flat vs last week{suffix}"
    sign = "+" if delta > 0 else ""
    if money:
        return f"{sign}{fmt_money(delta, currency)} vs last week{suffix}"
    if float(delta).is_integer():
        return f"{sign}{int(delta)} vs last week{suffix}"
    return f"{sign}{delta:.1f} vs last week{suffix}"


def _plain_weekly_change(curr, prev, *, money: bool = False, unit: str = "", currency: str = "usd") -> str:
    """Describe a weekly change in words instead of dashboard shorthand."""
    if prev is None or curr is None:
        return "No comparison yet"
    try:
        delta = float(curr) - float(prev)
    except (TypeError, ValueError):
        return "No comparison yet"
    if abs(delta) < 0.05:
        return "No change from last week"
    amount = fmt_money(abs(delta), currency) if money else (
        str(int(abs(delta))) if float(delta).is_integer() else f"{abs(delta):.1f}"
    )
    direction = "up" if delta > 0 else "down"
    return f"{direction.capitalize()} {amount}{unit} from last week"


def _report_metric_snapshot(fin, items, ups, headcount) -> dict:
    return {
        "taken_at": datetime.now(timezone.utc).isoformat(),
        "mrr": None if fin.get("mrr_value") is None else int(fin.get("mrr_value") or 0),
        "arr": None if fin.get("mrr_value") is None else int(fin.get("mrr_value") or 0) * 12,
        "runway_months": fin.get("runway_months"),
        "burn": None if fin.get("burn_value") is None else int(fin.get("burn_value") or 0),
        "headcount": int(headcount or 0),
        "updates_count": len(ups or []),
        "blocked_count": len([u for u in (ups or []) if u.get("blocker")]),
        "shipped_week": _shipped_in_window(items or []),
        "open_tasks": len([t for t in (items or []) if t.get("column") != "done"]),
        "in_progress": len([t for t in (items or []) if t.get("column") == "in_progress"]),
    }


async def _apply_report_snapshot(workspace_id: str, current: dict) -> Optional[dict]:
    """Keep current and previous weekly baselines so cards and the pack compare the same dates."""
    c = await get_ws(workspace_id)
    prior = c.get("report_snapshot")
    previous = c.get("report_previous_snapshot")
    now = datetime.now(timezone.utc)
    taken = _parse_iso_dt((prior or {}).get("taken_at")) if prior else None
    rotate = prior is None or taken is None or (now - taken) >= timedelta(days=7)
    if rotate:
        update = {"report_snapshot": current}
        if prior and taken is not None:
            update["report_previous_snapshot"] = prior
        await db.workspaces.update_one(
            {"workspace_id": workspace_id},
            {"$set": update},
        )
        return prior if (prior and taken is not None) else None
    # A freshly-created first baseline has nothing honest to compare with yet.
    return previous


def _computed_report_cards(c, fin, items, ups, headcount, prior=None, *, include_financials: bool = True):
    # Task / update / blocker / shipped counts and people-roster headcount are
    # computed from workspace collections. Zero is unambiguous (none found) —
    # there is no separate "not entered" state. Money fields still use fin
    # display values ("—" when unknown) and financials_for_synthesis in the pack.
    curr = _report_metric_snapshot(fin, items, ups, headcount)
    first_week = prior is None
    baseline_at = (prior or {}).get("taken_at")
    baseline_dt = _parse_iso_dt(baseline_at) if baseline_at else None
    baseline_label = baseline_dt.strftime("%b %d").replace(" 0", " ") if baseline_dt else None
    period = "First weekly check-in" if first_week else f"Compared with {baseline_label or 'last check-in'}"
    currency = fin.get("currency") or "usd"

    previous = prior or {}
    mrr_change = _plain_weekly_change(curr["mrr"], previous.get("mrr"), money=True, currency=currency)
    runway_change = _plain_weekly_change(curr["runway_months"], previous.get("runway_months"), unit=" months")
    burn_change = _plain_weekly_change(curr["burn"], previous.get("burn"), money=True, currency=currency)
    hc_change = _plain_weekly_change(curr["headcount"], previous.get("headcount"), unit=" people")
    updates_change = _plain_weekly_change(curr["updates_count"], previous.get("updates_count"), unit=" updates")
    blocked_change = _plain_weekly_change(curr["blocked_count"], previous.get("blocked_count"), unit=" blockers")
    shipped_change = _plain_weekly_change(curr["shipped_week"], previous.get("shipped_week"), unit=" items")

    if first_week:
        fin_summary = "This is your first weekly baseline. Next week Trenston will explain what changed."
        team_summary = "This is your first weekly baseline for team size, updates, and blockers."
        exec_summary = "This is your first weekly baseline for completed and open work."
    else:
        fin_summary = (
            f"Monthly recurring revenue: {mrr_change.lower()}. "
            f"Cash runway: {runway_change.lower()}. Net burn: {burn_change.lower()}."
        )
        team_summary = (
            f"Team size: {hc_change.lower()}. Updates today: {updates_change.lower()}. "
            f"Blocked items: {blocked_change.lower()}."
        )
        exec_summary = (
            f"Your team completed {curr['shipped_week']} items in the last seven days "
            f"({shipped_change.lower()}). {curr['in_progress']} are in progress and "
            f"{curr['open_tasks']} remain open."
        )

    cards = []
    if include_financials:
        cards.append(
            {"id": "auto_fin", "title": "Money check-in", "type": "Updated weekly", "period": period,
             "summary": fin_summary,
             "metrics": [
                 {"label": "Monthly recurring revenue", "value": format_mrr_display(fin), "change": mrr_change},
                 {"label": "Cash runway", "value": (
                     f"{fin['runway_months']} months" if fin["runway_months"] is not None
                     else (RUNWAY_NO_BURN_LABEL if fin.get("runway_no_burn") else "Add data")
                 ), "change": runway_change},
                 {"label": "Net burn this month", "value": format_burn_display(fin), "change": burn_change},
             ],
             "baseline_at": baseline_at, "source": "auto"},
        )
    cards.extend([
        {"id": "auto_team", "title": "Team check-in", "type": "Updated weekly", "period": period,
         "summary": team_summary,
         "metrics": [
             {"label": "People", "value": str(curr["headcount"]), "change": hc_change},
             {"label": "Updates today", "value": str(curr["updates_count"]), "change": updates_change},
             {"label": "Blocked items", "value": str(curr["blocked_count"]), "change": blocked_change},
         ],
         "baseline_at": baseline_at, "source": "auto"},
        {"id": "auto_exec", "title": "Work completed", "type": "Updated weekly", "period": period,
         "summary": exec_summary,
         "metrics": [
             {"label": "Completed (7 days)", "value": str(curr["shipped_week"]), "change": shipped_change},
             {"label": "In progress", "value": str(curr["in_progress"]), "change": "Current total"},
             {"label": "Still open", "value": str(curr["open_tasks"]), "change": "Current total"},
         ],
         "baseline_at": baseline_at, "source": "auto"},
    ])
    return cards


@api_router.get("/reports")
async def reports(principal=Depends(get_principal)):
    cache_key = _list_cache_key("reports", principal["workspace_id"], principal["user_id"])
    cached = simple_cache.peek(cache_key)
    if cached is not None:
        return cached
    c = await get_ws(principal["workspace_id"])
    fin = await compute_financials(c["workspace_id"])
    items = c["tasks"]["items"]
    day = datetime.now(timezone.utc).date().isoformat()
    ups = await db.updates.find({"workspace_id": c["workspace_id"], "day": day}, {"_id": 0}).to_list(200)
    headcount = c.get("employees") or len(c["people"]["people"])
    manual = [r for r in (c.get("manual_reports") or []) if r.get("source") != helm_dept_drafts.SOURCE]
    current = _report_metric_snapshot(fin, items, ups, headcount)
    prior = await _apply_report_snapshot(c["workspace_id"], current)
    can_write = await can_section_write(principal, "reports", "reports:write")
    can_export_financials = await can_access_financials(principal)
    auto = _computed_report_cards(
        c, fin, items, ups, headcount, prior=prior, include_financials=can_export_financials,
    )
    drafts = await helm_dept_drafts.list_open_drafts(db, c["workspace_id"])
    financial_months: list = []
    financial_latest_month = None
    if can_export_financials:
        financial_months = list(fin.get("months") or [])
        financial_latest_month = fin.get("latest_month")
        dept_ids = await dept_access.accessible_department_ids(
            db, principal, dept_catalog.TYPE_ACCOUNTING_FINANCE,
        )
        if dept_ids is not None:
            scoped = await compute_financials(c["workspace_id"], department_ids=dept_ids)
            financial_months = list(scoped.get("months") or [])
            financial_latest_month = scoped.get("latest_month")
    payload_out = {
        "reports": manual + auto,
        "manual_reports": manual,
        "auto_reports": auto,
        "draft_reports": drafts,
        "can_write": can_write,
        "can_export_financials": can_export_financials,
        "financial_months": financial_months,
        "financial_latest_month": financial_latest_month,
        "is_pro": workspace_is_pro(c),
        "can_generate_pack": (
            "reports:pack" in perms_for(principal["pack"])
            and workspace_allows(c, helm_plans.FEATURE_ADVANCED_REPORTS)
        ),
    }
    simple_cache.put(cache_key, payload_out, _DEPT_LIST_CACHE_TTL_SECONDS)
    return payload_out


class ReportInput(BaseModel):
    title: str
    type: str = "General"
    period: str = ""
    summary: str = ""
    metrics: list = []
    from_draft_id: Optional[str] = None


@api_router.post("/reports")
async def create_report(payload: ReportInput, principal=Depends(require_section("reports", "reports:write"))):
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="Title is required")
    c = await get_ws(principal["workspace_id"])
    draft_id = (payload.from_draft_id or "").strip()
    if draft_id:
        draft = await db.department_report_drafts.find_one(
            {
                "id": draft_id,
                "workspace_id": c["workspace_id"],
                "status": helm_dept_drafts.STATUS_DRAFT,
            },
            {"_id": 1},
        )
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found or already closed")
    manual = list(c.get("manual_reports") or [])
    report = {
        "id": f"rep_{uuid.uuid4().hex[:10]}",
        "title": payload.title.strip(),
        "type": (payload.type or "General").strip(),
        "period": (payload.period or "Manual").strip(),
        "summary": payload.summary.strip(),
        "metrics": payload.metrics[:6] if payload.metrics else [],
        "source": "manual",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    manual.append(report)
    await db.workspaces.update_one({"workspace_id": c["workspace_id"]}, {"$set": {"manual_reports": manual}})
    invalidate_workspace_list_cache(principal["workspace_id"], "reports")
    if draft_id:
        await helm_dept_drafts.mark_published(db, c["workspace_id"], draft_id)
    await log_activity(principal, "reports", "report.create", f"Added report: {report['title']}")
    return {"ok": True, "report": report}


@api_router.patch("/reports/{report_id}")
async def edit_report(report_id: str, payload: ReportInput, principal=Depends(require_section("reports", "reports:write"))):
    c = await get_ws(principal["workspace_id"])
    manual = list(c.get("manual_reports") or [])
    found = None
    for r in manual:
        if r["id"] == report_id:
            r.update({
                "title": payload.title.strip() or r["title"],
                "type": (payload.type or r.get("type", "General")).strip(),
                "period": (payload.period or r.get("period", "Manual")).strip(),
                "summary": payload.summary.strip() if payload.summary is not None else r.get("summary", ""),
                "metrics": payload.metrics if payload.metrics is not None else r.get("metrics", []),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            found = r
            break
    if not found:
        raise HTTPException(status_code=404, detail="Report not found")
    await db.workspaces.update_one({"workspace_id": c["workspace_id"]}, {"$set": {"manual_reports": manual}})
    invalidate_workspace_list_cache(principal["workspace_id"], "reports")
    return {"ok": True, "report": found}


@api_router.delete("/reports/{report_id}")
async def delete_report(report_id: str, principal=Depends(require_section("reports", "reports:write"))):
    c = await get_ws(principal["workspace_id"])
    manual = [r for r in (c.get("manual_reports") or []) if r["id"] != report_id]
    if len(manual) == len(c.get("manual_reports") or []):
        raise HTTPException(status_code=404, detail="Report not found")
    await db.workspaces.update_one({"workspace_id": c["workspace_id"]}, {"$set": {"manual_reports": manual}})
    invalidate_workspace_list_cache(principal["workspace_id"], "reports")
    return {"ok": True}


@api_router.post("/reports/drafts/{draft_id}/dismiss")
async def dismiss_report_draft(draft_id: str, principal=Depends(require_section("reports", "reports:write"))):
    ok = await helm_dept_drafts.dismiss_draft(db, principal["workspace_id"], draft_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Draft not found")
    invalidate_workspace_list_cache(principal["workspace_id"], "reports")
    return {"ok": True}


def _today_report_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _parse_report_date(value: Optional[str]) -> str:
    raw = (value or "").strip() or _today_report_date()
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD") from exc


@api_router.post("/reports/documents/upload")
async def upload_report_document(
    file: UploadFile = File(...),
    report_date: Optional[str] = Form(None),
    principal=Depends(require_section("reports", "reports:write")),
):
    """Upload a report file for the daily digest (xlsx/csv/pdf/png/jpeg).

    Shares the AI-extract quota pool with bill extraction — intentional for v1;
    revisit with a separate quota if digest usage competes with bills in practice.
    """
    await _enforce_ai_extract_quota(principal)
    await _enforce_document_rate_limit(
        principal, "upload", doc_rate_limit.DOC_UPLOAD_HOURLY_LIMIT,
        "Upload limit reached. Try again in a bit",
    )
    if file.content_type not in ALLOWED_REPORT_DOC_TYPES:
        raise HTTPException(
            status_code=400,
            detail="File type not allowed. Upload PDF, PNG, JPEG, XLSX, or CSV.",
        )
    data = await _read_validated_report_document(file)
    if not doc_storage.r2_configured():
        raise HTTPException(status_code=503, detail="Document storage is not configured")
    filename = (file.filename or "report").replace("/", "_").replace("\\", "_")[:200]
    try:
        storage_key = await asyncio.to_thread(
            doc_storage.upload_document,
            principal["workspace_id"], data, filename, file.content_type,
        )
    except Exception as exc:
        logger.exception("report document upload failed")
        raise HTTPException(status_code=500, detail="Could not store document") from exc
    doc_id = f"rdoc_{uuid.uuid4().hex[:12]}"
    day = _parse_report_date(report_date)
    doc = {
        "id": doc_id,
        "workspace_id": principal["workspace_id"],
        "storage_key": storage_key,
        "filename": filename,
        "content_type": file.content_type,
        "uploaded_by": principal["user_id"],
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "report_date": day,
        "status": "uploaded",
        "summary": None,
        "key_figures": None,
        "unclear": None,
        "summarized_at": None,
    }
    await db.report_documents.insert_one(doc)
    await log_activity(principal, "reports", "report_document.upload", f"Uploaded report · {filename}")
    return {"document_id": doc_id, "status": "uploaded", "report_date": day}


@api_router.post("/reports/documents/{document_id}/summarize")
async def summarize_report_document_route(
    document_id: str,
    principal=Depends(require_section("reports", "reports:write")),
):
    """Summarize one report file. Shares bill AI-extract quota (see upload docstring)."""
    doc = await db.report_documents.find_one(
        {"id": document_id, "workspace_id": principal["workspace_id"]}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.get("status") == "summarized" and doc.get("summary"):
        return {
            "document_id": document_id,
            "status": "summarized",
            "summary": doc.get("summary"),
            "key_figures": doc.get("key_figures") or [],
            "unclear": bool(doc.get("unclear")),
            "report_date": doc.get("report_date"),
        }
    if not helm_llm.anthropic_configured():
        raise HTTPException(status_code=503, detail="AI summarization is not configured")
    quota_ticket = await _acquire_ai_extract_quota(principal)
    await _enforce_document_rate_limit(
        principal, "extract", doc_rate_limit.DOC_EXTRACT_HOURLY_LIMIT,
        "Extraction limit reached. Try again in a bit",
    )
    import report_text as report_txt
    try:
        file_bytes = await asyncio.to_thread(doc_storage.get_document_bytes, doc["storage_key"])
        ctype = doc.get("content_type") or ""
        truncated = False
        if report_txt.is_spreadsheet_mime(ctype):
            text, truncated = await asyncio.to_thread(
                report_txt.spreadsheet_bytes_to_text, file_bytes, ctype, doc.get("filename") or "",
            )
            result = await helm_llm.summarize_report_document(
                text, ctype, doc.get("filename") or "report", truncated=truncated,
            )
        else:
            result = await helm_llm.summarize_report_document(
                file_bytes, ctype, doc.get("filename") or "report", truncated=False,
            )
        now = datetime.now(timezone.utc).isoformat()
        await db.report_documents.update_one(
            {"id": document_id, "workspace_id": principal["workspace_id"]},
            {"$set": {
                "status": "summarized",
                "summary": result["summary"],
                "key_figures": result["key_figures"],
                "unclear": result["unclear"],
                "summarized_at": now,
            }},
        )
        report_day = doc.get("report_date") or _today_report_date()
        await db.report_digests.update_one(
            {"workspace_id": principal["workspace_id"], "date": report_day},
            {"$set": {
                "workspace_id": principal["workspace_id"],
                "date": report_day,
                "stale": True,
            }, "$setOnInsert": {
                "combined_digest": "",
                "computed_at": None,
            }},
            upsert=True,
        )
        await log_activity(
            principal, "reports", "report_document.summarize",
            f"Summarized report · {doc.get('filename') or document_id}",
        )
        await _product_event(
            principal["workspace_id"], principal["user_id"],
            helm_analytics.EVENT_AI_EXTRACT,
            {"document_id": document_id, "kind": "report_digest"},
        )
        return {
            "document_id": document_id,
            "status": "summarized",
            "summary": result["summary"],
            "key_figures": result["key_figures"],
            "unclear": result["unclear"],
            "report_date": doc.get("report_date"),
        }
    except ValueError as exc:
        await _release_ai_extract_quota(principal, quota_ticket)
        quota_ticket = None
        await db.report_documents.update_one(
            {"id": document_id, "workspace_id": principal["workspace_id"]},
            {"$set": {"status": "failed", "summary": str(exc), "unclear": True}},
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        await _release_ai_extract_quota(principal, quota_ticket)
        quota_ticket = None
        logger.exception("report summarize failed for %s", document_id)
        await db.report_documents.update_one(
            {"id": document_id, "workspace_id": principal["workspace_id"]},
            {"$set": {"status": "failed"}},
        )
        raise HTTPException(status_code=500, detail="Could not summarize report") from exc


@api_router.get("/reports/documents/{document_id}")
async def get_report_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    principal=Depends(require_section("reports", "reports:write")),
):
    """Return metadata + presigned URL for a report document (same bar as upload)."""
    doc = await db.report_documents.find_one(
        {"id": document_id, "workspace_id": principal["workspace_id"]}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    storage_key = doc.get("storage_key")
    if not storage_key:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc_storage.r2_configured():
        raise HTTPException(status_code=503, detail="Document storage is not configured")
    try:
        presigned_url = await asyncio.to_thread(doc_storage.get_presigned_url, storage_key)
    except Exception as exc:
        logger.exception("presigned url failed for report %s", document_id)
        raise HTTPException(status_code=500, detail="Could not generate document URL") from exc
    background_tasks.add_task(
        _audit_document_access,
        principal,
        "reports",
        "document.download",
        f"Opened report · {doc.get('filename') or document_id}",
        {"document_id": document_id},
    )
    return _document_response_without_storage(doc, presigned_url=presigned_url)


@api_router.get("/reports/digest")
async def reports_daily_digest(
    date: Optional[str] = Query(None),
    principal=Depends(require_section("reports", "reports:write")),
):
    """Return that day's report documents plus a cached combined digest.

    Recomputes combined_digest only when the day's digest record is stale
    (marked after a successful summarize). Digests do not decrement the
    AI-extract quota — only per-file summarize does.
    """
    day = _parse_report_date(date)
    ws_id = principal["workspace_id"]
    rows = await db.report_documents.find(
        {"workspace_id": ws_id, "report_date": day},
        {"_id": 0, "storage_key": 0},
    ).sort("uploaded_at", 1).to_list(200)
    summarized = [
        {
            "filename": r.get("filename") or "report",
            "summary": r.get("summary") or "",
            "key_figures": r.get("key_figures") or [],
            "unclear": bool(r.get("unclear")),
        }
        for r in rows
        if r.get("status") == "summarized" and r.get("summary")
    ]

    digest_rec = await db.report_digests.find_one(
        {"workspace_id": ws_id, "date": day}, {"_id": 0},
    )
    combined = (digest_rec or {}).get("combined_digest") or ""
    needs_recompute = bool(summarized) and (
        digest_rec is None
        or digest_rec.get("stale", True)
        or not combined
    )

    if not summarized:
        combined = ""
        if digest_rec is not None:
            await db.report_digests.update_one(
                {"workspace_id": ws_id, "date": day},
                {"$set": {
                    "combined_digest": "",
                    "stale": False,
                    "computed_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
    elif needs_recompute:
        try:
            combined = await helm_llm.combine_daily_report_digest(summarized)
        except Exception:
            logger.exception("report digest combine failed for %s %s", ws_id, day)
            combined = "\n\n".join(s["summary"] for s in summarized if s.get("summary"))
        now = datetime.now(timezone.utc).isoformat()
        await db.report_digests.update_one(
            {"workspace_id": ws_id, "date": day},
            {"$set": {
                "workspace_id": ws_id,
                "date": day,
                "combined_digest": combined,
                "stale": False,
                "computed_at": now,
            }},
            upsert=True,
        )

    return {
        "date": day,
        "reports": [
            {
                "id": r.get("id"),
                "filename": r.get("filename"),
                "content_type": r.get("content_type"),
                "uploaded_at": r.get("uploaded_at"),
                "status": r.get("status"),
                "summary": r.get("summary"),
                "key_figures": r.get("key_figures") or [],
                "unclear": r.get("unclear"),
                "summarized_at": r.get("summarized_at"),
            }
            for r in rows
        ],
        "combined_digest": combined,
        "digest_cached": bool(summarized) and not needs_recompute,
        "data_as_of": helm_freshness.pick_data_as_of(
            *[r.get("uploaded_at") or r.get("summarized_at") for r in rows],
        ),
    }


def _build_weekly_pack_context(c, fin, items, ups, headcount, prior=None) -> dict:
    """Assemble a small, null-safe context with one unambiguous weekly baseline.

    Stored telemetry.kpis are omitted: they can be seed/sample values, and live
    money/team/work figures already come from financials_for_synthesis plus the
    auto cards. Auto-card counts (open tasks, updates, blockers, shipped items,
    headcount from the people roster) are computed — zero means none, not unknown.
    """
    manual = [r for r in (c.get("manual_reports") or []) if r.get("source") != helm_dept_drafts.SOURCE]
    auto = _computed_report_cards(c, fin, items, ups, headcount, prior=prior)
    return {
        "company": c["name"],
        "financials": financials_for_synthesis(fin),
        "financial_period": fin.get("latest_month"),
        "reports": [{"title": r["title"], "summary": r["summary"]} for r in manual],
        "weekly_comparison": {
            "baseline_at": (prior or {}).get("taken_at"),
            "note": (
                "Financial values are current monthly figures. Their change only means the monthly figure "
                "changed since the weekly baseline; it is not weekly revenue or weekly spend."
            ),
            "cards": [
                {"title": r["title"], "summary": r["summary"], "metrics": r.get("metrics")}
                for r in auto
            ],
        },
    }


_WEEKLY_PACK_SYSTEM = """You are a sharp chief of staff briefing the founder in person about this week.

Write the way you would speak in a short hallway update: clear prose, natural sentence rhythm,
no synthesized-report voice. Use only facts in the supplied data. It must sound like a thoughtful
human wrote it in plain English, not an AI analysis.

Form:
- Open with one title line: # [Company]: this week
- Follow with a short opening that states what mattered (one or two plain sentences, not bolded).
- Add ## headings only for topics that are actually notable this week. Name them for the content
  (for example "## Cash", "## Hiring", "## Monday"). Never invent empty sections to fill a template.
- Prefer short paragraphs. Use bullets only when a short list is clearer than prose, not as the default.
- If the week is quiet, say so briefly and stop. Do not pad.

Style (hard rules):
- Write plainly. Avoid em dashes. Prefer periods, commas, or plain connecting words instead,
  unless a sentence genuinely cannot be split any other way.
- Do not structure lines as "**Label:** fact". That bold-label-plus-colon pattern is banned as the
  default sentence shape. Bold at most one or two critical numbers in the whole note, and only when
  emphasis truly helps a reader catch them.
- Do not force the same section set every week. Never default to fixed headers such as Headline,
  Growth, Financial Health, Risks, This Week's Focus, or always-on blocks like What happened /
  What needs attention / Next week, when there is nothing real to put there. Structure follows
  what changed.
- Maximum about 350 words.
- Explain financial terms on first use: write "monthly recurring revenue (MRR)" and "cash runway".
- Never say "monetization signal", "execution velocity", "financial blind spot", "tracked period",
  "worth confirming", "possible bottleneck", "core open question", or similar consultant/AI language.
- Never speculate about causes, investor reactions, unpaid labor, solvency, or missing records.
- Do not turn every fact into a warning. Report zeroes and missing data neutrally.
- Do not repeat a fact.
- Do not include horizontal rules, confidence language, generic advice, or an explanation of your process.
- Use "we" and "our" where natural. Do not call the business "the company".
- Manual reports are founder-provided context; prioritize them when they contain specific facts.
- Week-over-week cards are supporting data, not text to copy verbatim.
- Financial figures are monthly. Never describe monthly burn or revenue as money earned or spent "this week".
- Follow instructions_for_missing_data exactly. Missing cash is a data-entry gap, not evidence of financial distress.
- Only state a number, date, or figure that appears literally in the company data. Never invent, estimate,
  average, or round into a figure that is not present. If data is missing or marked restricted, say so.
- When an item is marked possibly_stale, mention that the underlying record may be outdated rather than
  treating it as a fresh fact.
"""


async def _generate_weekly_pack_content(workspace_id: str) -> dict:
    """Build weekly pack markdown for a workspace. Shared by the API endpoint and weekly digest cron."""
    if not helm_llm.anthropic_configured():
        raise HTTPException(status_code=503, detail="AI is not configured (ANTHROPIC_API_KEY)")
    c = await get_ws(workspace_id)
    fin = await compute_financials(workspace_id)
    items = c["tasks"]["items"]
    day = datetime.now(timezone.utc).date().isoformat()
    ups = await db.updates.find({"workspace_id": workspace_id, "day": day}, {"_id": 0}).to_list(200)
    headcount = c.get("employees") or len(c["people"]["people"])
    current = _report_metric_snapshot(fin, items, ups, headcount)
    baseline = await _apply_report_snapshot(workspace_id, current)
    context = _build_weekly_pack_context(c, fin, items, ups, headcount, prior=baseline)
    recent = await db.financial_entries.find(
        {"workspace_id": workspace_id, "type": "expense"},
        {"_id": 0, "name": 1, "category": 1, "amount": 1, "month": 1, "updated_at": 1, "created_at": 1},
    ).sort("month", -1).to_list(12)
    context["recent_expenses"] = helm_freshness.annotate_possibly_stale(
        [
            {
                "name": normalize_entry_name(e.get("name"), e.get("category")),
                "category": (e.get("category") or "Other"),
                "amount": e.get("amount"),
                "month": e.get("month"),
                "updated_at": e.get("updated_at") or e.get("created_at"),
            }
            for e in recent
        ],
        dept_type=dept_catalog.TYPE_ACCOUNTING_FINANCE,
    )
    # Department queue samples that feed this summary — flag possibly_stale items.
    dept_slices = []
    for dept_type, coll_name, label, open_statuses in (
        (dept_catalog.TYPE_PRODUCTION, "production_work_orders", "Production",
         frozenset({"awaiting_materials", "in_production", "quality_check"})),
        (dept_catalog.TYPE_PROCUREMENT, "procurement_requests", "Procurement",
         frozenset({"requested", "approved", "ordered"})),
        (dept_catalog.TYPE_LEGAL, "legal_matters", "Legal",
         frozenset({"draft", "internal_review", "counterparty_review"})),
        (dept_catalog.TYPE_ENGINEERING_MAINTENANCE, "maintenance_tickets",
         "Engineering & Maintenance",
         frozenset({"reported", "diagnosed", "in_repair"})),
        (dept_catalog.TYPE_SALES, "deals", "Sales", None),
        (dept_catalog.TYPE_HR, "hr_onboarding_instances", "HR", None),
    ):
        coll = getattr(db, coll_name, None)
        if coll is None:
            continue
        try:
            raw = await coll.find(
                {"workspace_id": workspace_id},
                {"_id": 0, "id": 1, "status": 1, "overall_status": 1, "stage": 1,
                 "title": 1, "reference": 1, "item": 1, "updated_at": 1, "created_at": 1},
            ).sort("updated_at", -1).to_list(40)
        except Exception:
            raw = []
        annotated = helm_freshness.annotate_possibly_stale(raw, dept_type=dept_type)
        if open_statuses is not None:
            open_items = [
                r for r in annotated
                if str(r.get("status") or "").strip().lower() in open_statuses
            ]
        elif dept_type == dept_catalog.TYPE_HR:
            open_items = [
                r for r in annotated
                if (r.get("overall_status") or "in_progress") != "active"
            ]
        else:
            open_items = annotated
        stale_items = [r for r in open_items if r.get("possibly_stale")]
        dept_slices.append({
            "department": label,
            "open_count": len(open_items),
            "possibly_stale_count": len(stale_items),
            "possibly_stale_items": [
                {
                    "id": r.get("id"),
                    "label": r.get("reference") or r.get("title") or r.get("item") or r.get("id"),
                    "status": r.get("status") or r.get("overall_status") or r.get("stage"),
                    "updated_at": r.get("updated_at") or r.get("created_at"),
                    "possibly_stale": True,
                }
                for r in stale_items[:8]
            ],
        })
    context["department_queues"] = dept_slices
    freshness = await helm_freshness.resolve_workspace_data_as_of(db, c)
    context["data_as_of"] = freshness.get("data_as_of")
    context["data_freshness_sources"] = freshness.get("sources") or {}
    text = await helm_llm.complete(
        _WEEKLY_PACK_SYSTEM,
        f"Company data:\n{json.dumps(context, indent=2)}\n\n"
        "Write this week's briefing note now. Let the structure follow what is actually notable.",
    )
    return {
        "content": text,
        "workspace_name": c.get("name") or "Company",
        "workspace_id": workspace_id,
        "data_as_of": freshness.get("data_as_of"),
        "data_freshness_sources": freshness.get("sources") or {},
    }


@api_router.post("/reports/weekly-pack")
async def weekly_pack(principal=Depends(require_pro_perm("reports:pack"))):
    result = await _generate_weekly_pack_content(principal["workspace_id"])
    return {
        "content": result["content"],
        "data_as_of": result.get("data_as_of"),
        "data_freshness_sources": result.get("data_freshness_sources") or {},
    }


class WeeklyPackExportInput(BaseModel):
    content: str


@api_router.post("/reports/weekly-pack/export-pdf")
async def weekly_pack_export_pdf(payload: WeeklyPackExportInput, principal=Depends(require_pro_perm("reports:pack"))):
    import weekly_pack_export as pack_pdf

    content = (payload.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Pack content is required")
    c = await get_ws(principal["workspace_id"])
    try:
        pdf = pack_pdf.render_weekly_pack_pdf(content, workspace_name=c.get("name") or "Company")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("weekly pack PDF export failed")
        raise HTTPException(status_code=500, detail="Could not build PDF")
    filename = pack_pdf.pdf_filename(c.get("name") or "Company")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class FinancialExportInput(BaseModel):
    period: Optional[str] = None


async def _assemble_financial_export_for(principal, period: Optional[str]):
    import financial_export as fin_exp

    dept_ids = await dept_access.accessible_department_ids(
        db, principal, dept_catalog.TYPE_ACCOUNTING_FINANCE,
    )
    entry_filt = dept_access.apply_department_filter(
        {"workspace_id": principal["workspace_id"]}, dept_ids,
    )
    entries = await db.financial_entries.find(entry_filt, {"_id": 0}).to_list(5000)
    ws = await get_ws(principal["workspace_id"])
    settings = dict((ws or {}).get("financial_settings") or {})
    try:
        bundle = fin_exp.assemble_financial_export(entries, settings, period)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return bundle, ws


@api_router.get("/reports/financial-export")
async def financial_export_preview(
    period: Optional[str] = None,
    principal=Depends(require_section("financials", "finance:write")),
):
    """Accountant-view JSON for the on-screen ledger preview (same bundle as PDF/Excel)."""
    bundle, ws = await _assemble_financial_export_for(principal, period)
    return {**bundle, "workspace_name": (ws or {}).get("name") or "Company"}


@api_router.post("/reports/financial-export/pdf")
async def financial_export_pdf(
    payload: FinancialExportInput,
    principal=Depends(require_section("financials", "finance:write")),
):
    import financial_export as fin_exp

    bundle, ws = await _assemble_financial_export_for(principal, payload.period)
    try:
        pdf = fin_exp.render_financial_pdf(bundle, workspace_name=ws.get("name") or "Company")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("financial export PDF failed")
        raise HTTPException(status_code=500, detail="Could not build PDF")
    filename = fin_exp.financial_pdf_filename(ws.get("name") or "Company", bundle["period"])
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api_router.post("/reports/financial-export/xlsx")
async def financial_export_xlsx(
    payload: FinancialExportInput,
    principal=Depends(require_section("financials", "finance:write")),
):
    import financial_export as fin_exp

    bundle, ws = await _assemble_financial_export_for(principal, payload.period)
    try:
        xlsx = fin_exp.render_financial_xlsx(bundle, workspace_name=ws.get("name") or "Company")
    except Exception:
        logger.exception("financial export Excel failed")
        raise HTTPException(status_code=500, detail="Could not build spreadsheet")
    filename = fin_exp.financial_xlsx_filename(ws.get("name") or "Company", bundle["period"])
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _google_calendar_snapshot(
    workspace: dict,
    week_start: Optional[datetime] = None,
    principal: dict | None = None,
) -> Optional[dict]:
    """Fetch the calling user's Google Calendar events for a week; None if not connected.

    Never falls back to another teammate's tokens — personal Google data is per-user.
    """
    if not principal or not principal.get("user_id"):
        return None
    ws_id = workspace.get("workspace_id") or principal.get("workspace_id") or ""
    tokens = await _user_google_tokens(ws_id, principal["user_id"])
    if not tokens:
        return None
    if week_start is None:
        week_start = _calendar_week_start(datetime.now(timezone.utc).date())
    try:
        events, refreshed = await gcal.fetch_week_calendar(
            tokens, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, week_start,
        )
        if refreshed is not tokens:
            await _store_user_google_tokens(ws_id, principal["user_id"], refreshed)
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        meetings = [e for e in events if e.get("date") == today_str and not e.get("all_day")]
        focus_hours, meeting_hours = gcal._compute_hours(meetings)
        return {
            "events": events,
            "meetings": meetings,
            "focus_hours": focus_hours,
            "meeting_hours": meeting_hours,
            "live": True,
            "source": "google_calendar",
            "week_start": week_start.strftime("%Y-%m-%d"),
        }
    except gcal.GoogleAuthError as exc:
        logger.warning("Google Calendar auth failed for %s/%s: %s", ws_id, principal["user_id"], exc)
        await _store_user_google_tokens(ws_id, principal["user_id"], None)
        return {"events": [], "meetings": [], "focus_hours": 0, "meeting_hours": 0, "live": False, "auth_error": str(exc)}
    except Exception:
        logger.exception("Google Calendar fetch failed for %s", ws_id)
        return None


def _calendar_week_start(day) -> datetime:
    """Week starts Sunday (matches Trenston calendar UI)."""
    sunday_offset = (day.weekday() + 1) % 7
    start = day - timedelta(days=sunday_offset)
    return datetime(start.year, start.month, start.day, tzinfo=timezone.utc)


def _normalize_seed_events(meetings: list[dict], day) -> list[dict]:
    day_str = day.isoformat()
    out = []
    for m in meetings:
        if m.get("start_at"):
            out.append(dict(m))
            continue
        parts = (m.get("time") or "09:00").split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        start = datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)
        duration = int(m.get("duration") or 30)
        end = start + timedelta(minutes=duration)
        row = dict(m)
        row.update({
            "date": day_str,
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "all_day": False,
        })
        out.append(row)
    return out


# Extensible registry of department date fields → Trenston Calendar.
# Add a row here when a new department ships a date field; the collector below
# picks it up automatically (no changes needed in GET /calendar).
CALENDAR_DATE_SOURCES = [
    {
        "collection": "production_work_orders",
        "date_field": "due_date",
        "title_field": "reference",
        "type_label": "Production",
        "department_type": dept_catalog.TYPE_PRODUCTION,
        "open_statuses": frozenset({"awaiting_materials", "in_production", "quality_check"}),
        "source_type": "production_work_order",
    },
    {
        "collection": "procurement_requests",
        "date_field": "expected_delivery_date",
        "title_field": "item",
        "type_label": "Procurement",
        "department_type": dept_catalog.TYPE_PROCUREMENT,
        "open_statuses": frozenset({"ordered"}),
        "source_type": "procurement_request",
    },
    {
        "collection": "legal_matters",
        "date_field": "due_date",
        "title_field": "title",
        "type_label": "Legal",
        "department_type": dept_catalog.TYPE_LEGAL,
        # Filed = deadline met — exclude from calendar + deadline signals.
        "open_statuses": frozenset({"draft", "internal_review", "counterparty_review", "signed"}),
        "source_type": "legal_matter",
    },
    {
        "collection": "hr_leave_requests",
        "date_field": "start_date",
        "end_date_field": "end_date",
        "title_field": "title",
        "type_label": "Leave",
        "department_type": dept_catalog.TYPE_HR,
        "open_statuses": frozenset({"approved"}),
        "source_type": "hr_leave_request",
    },
]


def _parse_calendar_day(raw) -> Optional[str]:
    day = str(raw or "").strip()[:10]
    if not day:
        return None
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        return None
    return day


async def _department_calendar_upcoming(
    workspace_id: str,
    *,
    accessible_department_ids: Optional[set[str]] = None,
) -> list[dict]:
    """Load open department dates from CALENDAR_DATE_SOURCES for this workspace.

    ``accessible_department_ids``:
      - ``None`` — CEO / unrestricted: include every enabled department source
      - ``set`` — only sources whose department_id is in the set (may be empty)

    Sources may set optional ``end_date_field`` for inclusive date ranges
    (e.g. approved leave). Without it, behavior stays single-day.
    """
    out: list[dict] = []
    for src in CALENDAR_DATE_SOURCES:
        enabled = await dept_migrate.get_enabled_department(
            db, workspace_id, src["department_type"],
        )
        if not enabled:
            continue
        dept_id = enabled["department_id"]
        if accessible_department_ids is not None and dept_id not in accessible_department_ids:
            continue
        coll = getattr(db, src["collection"], None)
        if coll is None:
            continue
        date_field = src["date_field"]
        end_date_field = src.get("end_date_field")
        filt: dict = {
            "workspace_id": workspace_id,
            "department_id": dept_id,
            "status": {"$in": list(src["open_statuses"])},
            date_field: {"$exists": True, "$nin": [None, ""]},
        }
        if end_date_field:
            filt[end_date_field] = {"$exists": True, "$nin": [None, ""]}
        rows = await coll.find(filt, {"_id": 0}).to_list(1000)
        dept_name = (
            (enabled.get("name") or "").strip()
            or dept_catalog.default_name(src["department_type"])
        )
        for row in rows:
            day = _parse_calendar_day(row.get(date_field))
            if not day:
                continue
            end_day = day
            if end_date_field:
                parsed_end = _parse_calendar_day(row.get(end_date_field))
                if not parsed_end:
                    continue
                end_day = parsed_end if parsed_end >= day else day
            rid = row.get("id")
            if not rid:
                continue
            title = (row.get(src["title_field"]) or "").strip() or src["type_label"]
            item = {
                "id": rid,
                "title": title,
                "date": day,
                "type": src["type_label"],
                "meta": "",
                "source_type": src["source_type"],
                "source_id": rid,
                "visibility": "department",
                "department_id": dept_id,
                "department_name": dept_name,
            }
            if end_date_field and end_day != day:
                item["end_date"] = end_day
            elif end_date_field:
                item["end_date"] = end_day
            out.append(item)
    return out


def _deadlines_as_events(upcoming: list[dict]) -> list[dict]:
    """Turn upcoming deadline rows into calendar events.

    Uses source=\"deadline\" (not \"helm\") so the UI does not treat them as
    editable helm_events — PATCH/DELETE only apply to user-created helm rows.
    Range sources (leave) set end_at from end_date when present.
    """
    events = []
    for u in upcoming:
        start_day = u["date"]
        end_day = u.get("end_date") or start_day
        ev = {
            "id": f"deadline_{u['id']}",
            "title": u["title"],
            "time": "",
            "duration": 0,
            "attendees": 0,
            "type": u.get("type", "Deadline"),
            "prep": None,
            "importance": "medium",
            "source": "deadline",
            "date": start_day,
            "start_at": f"{start_day}T00:00:00+00:00",
            "end_at": f"{end_day}T23:59:59+00:00",
            "all_day": True,
            "visibility": u.get("visibility") or "department",
        }
        if u.get("end_date"):
            ev["end_date"] = u["end_date"]
        if u.get("source_type"):
            ev["source_type"] = u["source_type"]
        if u.get("source_id"):
            ev["source_id"] = u["source_id"]
        if u.get("department_id"):
            ev["department_id"] = u["department_id"]
        if u.get("department_name"):
            ev["department_name"] = u["department_name"]
        events.append(ev)
    return events


def _upcoming_overlaps_week(item: dict, week_start_s: str, week_end_s: str) -> bool:
    """True when item's date (or start–end range) overlaps the week inclusive."""
    start = item.get("date") or ""
    end = item.get("end_date") or start
    if not start:
        return False
    return start <= week_end_s and end >= week_start_s


@api_router.get("/calendar")
async def calendar(
    principal=Depends(get_principal),
    week_start: Optional[str] = Query(None, description="Sunday of the week to load (YYYY-MM-DD)"),
):
    week_key = (week_start or "").strip() or "default"
    cache_key = _list_cache_key("calendar", principal["workspace_id"], principal["user_id"], week_key)
    cached = simple_cache.peek(cache_key)
    if cached is not None:
        return cached
    c = await get_ws(principal["workspace_id"])
    if week_start:
        try:
            anchor_day = datetime.strptime(week_start, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="week_start must be YYYY-MM-DD")
    else:
        anchor_day = datetime.now(timezone.utc).date()
    week_anchor = _calendar_week_start(anchor_day)

    visible_dept_ids = await _calendar_accessible_department_ids(principal)
    dept_names = await _calendar_department_names(principal["workspace_id"])

    live_cal = await _google_calendar_snapshot(c, week_anchor, principal)
    if live_cal is not None:
        data = {**dict(c["calendar"]), **live_cal}
    else:
        data = dict(c["calendar"])
        data["live"] = False
        today = datetime.now(timezone.utc).date()
        seed_events = _normalize_seed_events(data.get("meetings") or [], today)
        data["events"] = seed_events
        data["week_start"] = week_anchor.strftime("%Y-%m-%d")
    # Upcoming deadlines from decisions that carry a real (YYYY-MM-DD) due date.
    upcoming = []
    for d in c.get("decisions", []):
        due = (d.get("due") or "").strip()
        try:
            datetime.strptime(due, "%Y-%m-%d")
        except ValueError:
            continue
        if d.get("status") == "pending":
            upcoming.append({"id": d["id"], "title": d["title"], "date": due,
                             "type": "Decision", "meta": d.get("category", "")})
    for t in c["tasks"]["items"]:
        due = (t.get("due") or "").strip()
        try:
            datetime.strptime(due, "%Y-%m-%d")
        except ValueError:
            continue
        if t.get("column") != "done" and (not t.get("assignee_user_id") or t.get("assignee_user_id") == principal["user_id"]):
            upcoming.append({"id": t["id"], "title": t["title"], "date": due,
                             "type": "Task", "meta": t.get("tag", "")})
    upcoming.extend(await _department_calendar_upcoming(
        principal["workspace_id"],
        accessible_department_ids=visible_dept_ids,
    ))
    upcoming.sort(key=lambda x: x["date"])
    data["upcoming"] = upcoming
    week_end = (week_anchor + timedelta(days=6)).strftime("%Y-%m-%d")
    week_start_s = week_anchor.strftime("%Y-%m-%d")
    in_week_deadlines = [
        u for u in upcoming if _upcoming_overlaps_week(u, week_start_s, week_end)
    ]
    events = list(data.get("events") or data.get("meetings") or [])
    if not data.get("events"):
        events = _normalize_seed_events(events, datetime.now(timezone.utc).date())
    existing_ids = {e.get("id") for e in events}
    for ev in _deadlines_as_events(in_week_deadlines):
        if ev["id"] not in existing_ids:
            events.append(ev)
    data["events"] = events
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    data["meetings"] = [e for e in events if e.get("date") == today_str and not e.get("all_day")]
    if "focus_hours" not in data:
        data["focus_hours"], data["meeting_hours"] = gcal._compute_hours(data["meetings"])
    data["week_start"] = week_start_s
    helm_events = c.get("calendar", {}).get("helm_events") or []
    if helm_events:
        week_end_dt = week_anchor + timedelta(days=6)
        for ev in helm_events:
            if not can_view_helm_calendar_event(
                principal, ev, accessible_department_ids=visible_dept_ids,
            ):
                continue
            ev_date = (ev.get("date") or (ev.get("start_at") or "")[:10]).strip()
            try:
                ev_day = datetime.strptime(ev_date, "%Y-%m-%d").date()
            except ValueError:
                continue
            if week_anchor.date() <= ev_day <= week_end_dt.date():
                if ev.get("id") not in existing_ids:
                    row = dict(ev)
                    _enrich_helm_event_scope_labels(row, dept_names)
                    events.append(row)
                    existing_ids.add(ev.get("id"))
        data["events"] = events
    # Enrich deadline/helm rows already in the list with scope labels.
    data["events"] = [
        _enrich_helm_event_scope_labels(dict(ev), dept_names)
        for ev in (data.get("events") or [])
    ]
    data["can_write"] = await can_section_write(principal, "calendar", "calendar:write")
    if data["can_write"] and not _has_pack_calendar_write(principal):
        member_depts = await _principal_calendar_department_ids(principal)
        annotate_depts = set() if member_depts is None else set(member_depts)
    else:
        # Pack writers (owner/exec) manage everything; no department overlap needed.
        annotate_depts = set()
    data["events"] = _annotate_helm_event_permissions(
        principal,
        data.get("events") or [],
        can_write=data["can_write"],
        accessible_department_ids=annotate_depts,
    )
    data["google_connected"] = await _user_google_tokens_present(
        principal["workspace_id"], principal["user_id"],
    )
    data["google_available"] = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
    tokens = await _user_google_tokens(principal["workspace_id"], principal["user_id"]) if data["google_connected"] else None
    data["google"] = gcal.google_capabilities(tokens)
    simple_cache.put(cache_key, data, _DEPT_LIST_CACHE_TTL_SECONDS)
    return data


class CalendarEventInput(BaseModel):
    title: str
    date: str
    time: str = "09:00"
    duration: int = 30
    type: str = "Internal"
    all_day: bool = False
    push_to_google: bool = False
    visibility: Literal["personal", "department"]
    department_id: Optional[str] = None


def _helm_event_creator_id(event: dict | None) -> Optional[str]:
    if not event:
        return None
    return (event.get("created_by") or event.get("created_by_user_id") or "").strip() or None


def _helm_event_department_ids(event: dict | None) -> set[str]:
    if not event:
        return set()
    out: set[str] = set()
    one = (event.get("department_id") or "").strip()
    if one:
        out.add(one)
    for raw in event.get("department_ids") or []:
        value = str(raw or "").strip()
        if value:
            out.add(value)
    return out


def _helm_event_visibility(event: dict | None) -> str:
    """Effective read visibility. Missing/unknown → personal (legacy safe default)."""
    if not event:
        return "personal"
    raw = (event.get("visibility") or "").strip().lower()
    if raw in ("personal", "department"):
        return raw
    return "personal"


def _has_pack_calendar_write(principal: dict) -> bool:
    """Owner/exec (and any pack with calendar:write) — full calendar manage, all events."""
    return "calendar:write" in perms_for(principal.get("pack") or "")


async def _calendar_accessible_department_ids(principal: dict) -> Optional[set[str]]:
    """Department ids visible on the calendar for this principal.

    ``None`` = CEO (all departments). Empty set = no department memberships.
    Uses the shared dept_access helpers (same semantics as other departments).
    """
    if dept_access.is_workspace_ceo(principal):
        return None
    by_type = await dept_access.accessible_department_ids_by_type(
        db, principal, list(dept_catalog.VALID_DEPARTMENT_TYPES),
    )
    out: set[str] = set()
    for ids in by_type.values():
        if ids:
            out.update(ids)
    return out


async def _calendar_department_names(workspace_id: str) -> dict[str, str]:
    rows = await dept_access.list_enabled_departments(db, workspace_id)
    return {d["department_id"]: d["name"] for d in rows if d.get("department_id")}


def _enrich_helm_event_scope_labels(event: dict, dept_names: dict[str, str]) -> dict:
    """Attach visibility + human label for UI (mutates and returns the row)."""
    if event.get("source") == "deadline":
        event["visibility"] = event.get("visibility") or "department"
        did = (event.get("department_id") or "").strip()
        if did and not event.get("department_name"):
            event["department_name"] = dept_names.get(did) or ""
        if event.get("department_name"):
            event["scope_label"] = event["department_name"]
        return event
    if event.get("source") != "helm":
        return event
    vis = _helm_event_visibility(event)
    event["visibility"] = vis
    if vis == "personal":
        event["scope_label"] = "Personal"
        event.pop("department_name", None)
    else:
        did = (event.get("department_id") or "").strip()
        name = (event.get("department_name") or "").strip() or dept_names.get(did) or "Department"
        event["department_name"] = name
        event["scope_label"] = name
    return event


def can_view_helm_calendar_event(
    principal: dict,
    event: dict | None,
    *,
    accessible_department_ids: Optional[set[str]] = None,
) -> bool:
    """Whether principal may see this Trenston-created helm event on GET /calendar.

    - personal (default for legacy rows): creator only — CEO does NOT see others'
    - department: CEO sees all; members see only their department(s)
    """
    if not event or event.get("source") not in (None, "helm"):
        return False
    vis = _helm_event_visibility(event)
    if vis == "personal":
        creator = _helm_event_creator_id(event)
        return bool(creator) and creator == principal.get("user_id")
    dept_id = (event.get("department_id") or "").strip()
    if not dept_id:
        return False
    if accessible_department_ids is None:
        return True
    return dept_id in accessible_department_ids


async def _principal_calendar_department_ids(principal: dict) -> Optional[set[str]]:
    """Department ids used for edit/delete membership overlap (manage path).

    ``None`` means CEO/owner (all departments). Empty set means no memberships.
    Prefer :func:`_calendar_accessible_department_ids` for read visibility.
    """
    return await _calendar_accessible_department_ids(principal)


async def _validate_calendar_event_scope(
    payload: "CalendarEventInput",
    principal: dict,
) -> tuple[str, Optional[str]]:
    """Return (visibility, department_id) after validating membership."""
    vis = payload.visibility
    if vis == "personal":
        return "personal", None
    dept_id = (payload.department_id or "").strip()
    if not dept_id:
        raise HTTPException(
            status_code=400,
            detail="department_id is required when visibility is department",
        )
    dept = await db.departments.find_one(
        {
            "department_id": dept_id,
            "workspace_id": principal["workspace_id"],
            "enabled": True,
        },
        {"_id": 0, "department_id": 1, "name": 1, "type": 1},
    )
    if not dept:
        raise HTTPException(status_code=400, detail="Department not found or not enabled")
    if not dept_access.is_workspace_ceo(principal):
        if not await dept_access.is_department_member(db, principal["user_id"], dept_id):
            raise HTTPException(
                status_code=403,
                detail="You must be a member of that department to create a department event",
            )
    return "department", dept_id


def can_manage_helm_calendar_event(
    principal: dict,
    event: dict | None,
    *,
    accessible_department_ids: Optional[set[str]] = None,
) -> bool:
    """Whether principal may edit/delete this Trenston calendar event.

    Pack calendar:write (CEO/owner/exec) → any helm event.
    Otherwise (with calendar section grant already required by the route):
      - events they personally created, or
      - department-scoped events (explicit visibility=department, or legacy
        rows that still carry department_id(s)) tied to a department they
        belong to.
    Explicit personal events are creator-only (plus pack writers above).
    Legacy unscoped events (no creator, no department) stay editable by anyone
    who already has calendar write, so older workspaces are not locked out.
    """
    if not event or event.get("source") not in (None, "helm"):
        return False
    if _has_pack_calendar_write(principal):
        return True
    creator = _helm_event_creator_id(event)
    if creator and creator == principal.get("user_id"):
        return True
    explicit_vis = (event.get("visibility") or "").strip().lower()
    if explicit_vis == "personal":
        return False
    event_depts = _helm_event_department_ids(event)
    if explicit_vis == "department" or event_depts:
        if not event_depts:
            return False
        if accessible_department_ids is None:
            # Caller didn't load memberships — treat as no department overlap.
            return False
        if event_depts & accessible_department_ids:
            return True
        return False
    if not creator:
        return True
    return False


def _annotate_helm_event_permissions(
    principal: dict,
    events: list,
    *,
    can_write: bool,
    accessible_department_ids: Optional[set[str]] = None,
) -> list:
    """Attach can_edit for UI; deadline/google rows stay non-editable."""
    out = []
    for ev in events or []:
        row = dict(ev)
        if not can_write:
            row["can_edit"] = False
        elif row.get("source") == "helm" and not str(row.get("id") or "").startswith("deadline_"):
            row["can_edit"] = can_manage_helm_calendar_event(
                principal, row, accessible_department_ids=accessible_department_ids,
            )
        else:
            row["can_edit"] = False
        out.append(row)
    return out


def _build_helm_event(
    payload: CalendarEventInput,
    event_id: Optional[str] = None,
    google_event_id: Optional[str] = None,
    *,
    created_by: Optional[str] = None,
    visibility: Optional[str] = None,
    department_id: Optional[str] = None,
    department_name: Optional[str] = None,
    preserve: Optional[dict] = None,
) -> dict:
    try:
        day = datetime.strptime(payload.date.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    eid = event_id or f"helm_{uuid.uuid4().hex[:10]}"
    extra = {}
    if google_event_id:
        extra["google_event_id"] = google_event_id
    creator = (created_by or _helm_event_creator_id(preserve) or "").strip()
    if creator:
        extra["created_by"] = creator

    vis = visibility
    dept_id = department_id
    dept_name = department_name
    if vis is None and preserve is not None:
        vis = _helm_event_visibility(preserve)
        if vis == "department":
            dept_id = (preserve.get("department_id") or "").strip() or None
            dept_name = (preserve.get("department_name") or "").strip() or None
        else:
            dept_id = None
            dept_name = None
    if vis is None:
        vis = getattr(payload, "visibility", None) or "personal"
    if vis == "department":
        did = (dept_id or getattr(payload, "department_id", None) or "").strip()
        if not did:
            raise HTTPException(
                status_code=400,
                detail="department_id is required when visibility is department",
            )
        extra["visibility"] = "department"
        extra["department_id"] = did
        extra["department_ids"] = [did]
        if dept_name:
            extra["department_name"] = dept_name
    else:
        extra["visibility"] = "personal"
        # Personal events intentionally omit department_id / department_ids.

    if payload.all_day:
        start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        end = datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=timezone.utc)
        return {
            "id": eid, "title": payload.title.strip(), "date": day.isoformat(),
            "time": "", "duration": 0, "attendees": 0, "type": payload.type or "Internal",
            "prep": None, "importance": "medium", "source": "helm",
            "start_at": start.isoformat(), "end_at": end.isoformat(), "all_day": True,
            **extra,
        }
    parts = (payload.time or "09:00").split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    start = datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)
    duration = max(int(payload.duration or 30), 15)
    end = start + timedelta(minutes=duration)
    return {
        "id": eid, "title": payload.title.strip(), "date": day.isoformat(),
        "time": f"{hour:02d}:{minute:02d}", "duration": duration, "attendees": 0,
        "type": payload.type or "Internal", "prep": None, "importance": "medium", "source": "helm",
        "start_at": start.isoformat(), "end_at": end.isoformat(), "all_day": False,
        **extra,
    }


async def _maybe_push_google_event(
    workspace: dict,
    ev: dict,
    payload: CalendarEventInput,
    principal: dict | None = None,
) -> dict:
    if not payload.push_to_google:
        return ev
    if not principal or not principal.get("user_id"):
        ev["google_push_error"] = "reconnect"
        return ev
    ws_id = workspace.get("workspace_id") or principal.get("workspace_id") or ""
    tokens = await _user_google_tokens(ws_id, principal["user_id"])
    if not tokens or not gcal.has_scope(tokens, "calendar.events"):
        ev["google_push_error"] = "reconnect"
        return ev
    try:
        gid, refreshed = await gcal.create_calendar_event(
            tokens, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
            title=ev["title"], start_iso=ev["start_at"], end_iso=ev["end_at"],
            all_day=bool(ev.get("all_day")), date=ev.get("date"),
        )
        await _store_user_google_tokens(ws_id, principal["user_id"], refreshed)
        if gid:
            ev["google_event_id"] = gid
    except Exception:
        logger.exception("Google Calendar insert failed")
        ev["google_push_error"] = "failed"
    return ev


@api_router.post("/calendar/events")
async def create_calendar_event(
    payload: CalendarEventInput,
    principal=Depends(require_section("calendar", "calendar:write")),
):
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="Title is required")
    vis, dept_id = await _validate_calendar_event_scope(payload, principal)
    dept_name = None
    if dept_id:
        names = await _calendar_department_names(principal["workspace_id"])
        dept_name = names.get(dept_id)
    c = await get_ws(principal["workspace_id"])
    cal = dict(c.get("calendar") or {})
    events = list(cal.get("helm_events") or [])
    ev = _build_helm_event(
        payload,
        created_by=principal["user_id"],
        visibility=vis,
        department_id=dept_id,
        department_name=dept_name,
    )
    ev = await _maybe_push_google_event(c, ev, payload, principal)
    events.append(ev)
    cal["helm_events"] = events
    await db.workspaces.update_one({"workspace_id": c["workspace_id"]}, {"$set": {"calendar": cal}})
    invalidate_workspace_list_cache(principal["workspace_id"], "calendar")
    await log_activity(principal, "calendar", "event.create", f"Added calendar event: {ev['title']}")
    return {"ok": True, "event": ev}


@api_router.patch("/calendar/events/{event_id}")
async def edit_calendar_event(
    event_id: str,
    payload: CalendarEventInput,
    principal=Depends(require_section("calendar", "calendar:write")),
):
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="Title is required")
    vis, dept_id = await _validate_calendar_event_scope(payload, principal)
    dept_name = None
    if dept_id:
        names = await _calendar_department_names(principal["workspace_id"])
        dept_name = names.get(dept_id)
    c = await get_ws(principal["workspace_id"])
    cal = dict(c.get("calendar") or {})
    events = list(cal.get("helm_events") or [])
    member_depts = await _principal_calendar_department_ids(principal)
    access_depts = set() if member_depts is None else set(member_depts)
    found = None
    for i, ev in enumerate(events):
        if ev.get("id") == event_id and ev.get("source") == "helm":
            if not can_manage_helm_calendar_event(
                principal, ev, accessible_department_ids=access_depts,
            ):
                raise HTTPException(
                    status_code=403,
                    detail="You can only edit calendar events you created or that belong to your department",
                )
            events[i] = _build_helm_event(
                payload,
                event_id=event_id,
                google_event_id=ev.get("google_event_id"),
                created_by=_helm_event_creator_id(ev),
                visibility=vis,
                department_id=dept_id,
                department_name=dept_name,
                preserve=ev,
            )
            found = events[i]
            gid = ev.get("google_event_id")
            if gid:
                tokens = await _user_google_tokens(c["workspace_id"], principal["user_id"])
                if tokens and gcal.has_scope(tokens, "calendar.events"):
                    try:
                        refreshed = await gcal.patch_calendar_event(
                            tokens, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, gid,
                            title=found["title"], start_iso=found["start_at"], end_iso=found["end_at"],
                            all_day=bool(found.get("all_day")), date=found.get("date"),
                        )
                        await _store_user_google_tokens(c["workspace_id"], principal["user_id"], refreshed)
                    except Exception:
                        logger.exception("Google Calendar patch failed")
            break
    if not found:
        raise HTTPException(status_code=404, detail="Event not found")
    cal["helm_events"] = events
    await db.workspaces.update_one({"workspace_id": c["workspace_id"]}, {"$set": {"calendar": cal}})
    invalidate_workspace_list_cache(principal["workspace_id"], "calendar")
    return {"ok": True, "event": found}


@api_router.delete("/calendar/events/{event_id}")
async def delete_calendar_event(
    event_id: str,
    principal=Depends(require_section("calendar", "calendar:write")),
):
    c = await get_ws(principal["workspace_id"])
    cal = dict(c.get("calendar") or {})
    existing = [e for e in (cal.get("helm_events") or []) if e.get("id") == event_id]
    if not existing:
        raise HTTPException(status_code=404, detail="Event not found")
    member_depts = await _principal_calendar_department_ids(principal)
    access_depts = set() if member_depts is None else set(member_depts)
    if not can_manage_helm_calendar_event(
        principal, existing[0], accessible_department_ids=access_depts,
    ):
        raise HTTPException(
            status_code=403,
            detail="You can only delete calendar events you created or that belong to your department",
        )
    events = [e for e in (cal.get("helm_events") or []) if e.get("id") != event_id]
    gid = existing[0].get("google_event_id")
    if gid:
        tokens = await _user_google_tokens(c["workspace_id"], principal["user_id"])
        if tokens and gcal.has_scope(tokens, "calendar.events"):
            try:
                refreshed = await gcal.delete_calendar_event(tokens, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, gid)
                await _store_user_google_tokens(c["workspace_id"], principal["user_id"], refreshed)
            except Exception:
                logger.exception("Google Calendar delete failed")
    cal["helm_events"] = events
    await db.workspaces.update_one({"workspace_id": c["workspace_id"]}, {"$set": {"calendar": cal}})
    invalidate_workspace_list_cache(principal["workspace_id"], "calendar")
    return {"ok": True}


@api_router.get("/people")
async def people(principal=Depends(get_principal)):
    cache_key = _list_cache_key("people", principal["workspace_id"], principal["user_id"])
    cached = simple_cache.peek(cache_key)
    if cached is not None:
        return cached
    c = await sync_members_into_people(principal["workspace_id"])
    data = dict(c["people"])
    roster = list(data.get("people") or [])
    data["people"] = roster
    mem_ids = {
        m["membership_id"]
        for m in await db.memberships.find(
            {"workspace_id": principal["workspace_id"], "status": {"$in": ["active", "invited"]}},
            {"_id": 0, "membership_id": 1},
        ).to_list(200)
    }
    stale_links = False
    for p in roster:
        mid = p.get("membership_id")
        if mid and mid not in mem_ids:
            # Access revoked but roster row still carried a stale membership_id.
            p.pop("membership_id", None)
            stale_links = True
            mid = None
        p["has_access"] = bool(mid and mid in mem_ids)
    if stale_links:
        people_doc = dict(c.get("people") or {})
        people_doc["people"] = roster
        await db.workspaces.update_one(
            {"workspace_id": principal["workspace_id"]},
            {"$set": {"people": people_doc}},
        )
    by_user = await dept_access.department_names_by_user_id(db, principal["workspace_id"])
    for p in roster:
        dept_access.attach_real_departments(p, by_user.get(p.get("user_id") or "") or [])
    data["unassigned_count"] = sum(1 for p in roster if not (p.get("departments") or []))

    # HR employment overlay (read-only) when HR is enabled.
    hr_dept = await dept_migrate.get_enabled_department(
        db, principal["workspace_id"], dept_catalog.TYPE_HR,
    )
    if hr_dept:
        linked_uids = [p.get("user_id") for p in roster if p.get("user_id")]
        hr_by_user: dict = {}
        if linked_uids:
            hr_rows = await db.hr_employees.find(
                {
                    "workspace_id": principal["workspace_id"],
                    "linked_user_id": {"$in": linked_uids},
                },
                {"_id": 0},
            ).to_list(2000)
            hr_by_user = {
                r["linked_user_id"]: r
                for r in hr_rows
                if r.get("linked_user_id")
            }
            manager_ids = [r.get("manager_user_id") for r in hr_by_user.values()]
            managers = await _users_by_ids(manager_ids, {"_id": 0, "user_id": 1, "name": 1})
            for p in roster:
                hr = hr_by_user.get(p.get("user_id") or "")
                if not hr:
                    continue
                p["hr_status"] = hr.get("status")
                p["hr_start_date"] = hr.get("start_date")
                mid = hr.get("manager_user_id")
                mgr = managers.get(mid) if mid else None
                p["hr_manager_name"] = ((mgr or {}).get("name") or "").strip() or None
                p["hr_employee_id"] = hr.get("id")

    # Workload badges — batched per department type, not per person.
    workload_uids = [p.get("user_id") for p in roster if p.get("user_id")]
    workload = await helm_work_items.workload_counts_by_user(
        db, principal["workspace_id"], workload_uids,
    )
    for p in roster:
        uid = p.get("user_id")
        if not uid:
            continue
        counts = workload.get(uid) or {"open_item_count": 0, "overdue_item_count": 0}
        p["open_item_count"] = counts["open_item_count"]
        p["overdue_item_count"] = counts["overdue_item_count"]

    data["can_write"] = await can_section_write(principal, "people", "people:write")
    data["can_invite_to_access"] = "members:invite" in perms_for(principal["pack"])
    simple_cache.put(cache_key, data, _DEPT_LIST_CACHE_TTL_SECONDS)
    return data


class PersonInput(BaseModel):
    name: str
    role: str = ""
    # Legacy free-text label — ignored. Real departments live in department_members.
    department: Optional[str] = None
    tenure: str = ""
    invite_to_access: bool = False
    email: Optional[EmailStr] = None
    pack: str = "member"


def _person_fields(payload: PersonInput):
    return {
        "name": payload.name.strip(),
        "role": payload.role.strip(),
        "tenure": payload.tenure.strip() or "New",
    }


@api_router.post("/people")
async def add_person(payload: PersonInput, request: Request, principal=Depends(require_section("people", "people:write"))):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    invite = bool(payload.invite_to_access)
    email = _normalize_email(str(payload.email)) if payload.email else ""
    if invite:
        if "members:invite" not in perms_for(principal["pack"]):
            raise HTTPException(status_code=403, detail="You do not have permission to invite to Team & Access")
        if not email:
            raise HTTPException(status_code=400, detail="Email is required to include in Team & Access")
        pack = _require_assignable_pack(payload.pack)
        existing = await db.memberships.find_one({"workspace_id": principal["workspace_id"], "email": email})
        if existing:
            raise HTTPException(status_code=400, detail="Already a member or invited; they should already be on the roster")
        await _enforce_seat_available(principal["workspace_id"])

    c = await get_ws(principal["workspace_id"])
    people = c["people"]
    person = {"id": f"p_{uuid.uuid4().hex[:8]}", **_person_fields(payload)}
    if email:
        person["email"] = email

    invite_meta = None
    if invite:
        role = "member"
        existing_user = await db.users.find_one({"email": email}, {"_id": 0})
        membership = {
            "membership_id": f"mem_{uuid.uuid4().hex[:12]}", "workspace_id": principal["workspace_id"],
            "user_id": existing_user["user_id"] if existing_user else None, "email": email,
            "role": role, "pack": pack,
            "status": "active" if existing_user else "invited",
            "invite_token": uuid.uuid4().hex, "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await db.memberships.insert_one(membership)
        except Exception:
            await _release_seat_reservation(principal["workspace_id"])
            raise
        person["membership_id"] = membership["membership_id"]
        person["user_id"] = membership.get("user_id")
        person["has_access"] = True
        ws = c
        app_url = APP_URL or FRONTEND_URL or str(request.base_url).rstrip("/")
        email_result = await send_invite_email(
            email, principal.get("name") or "Your team lead", ws["name"],
            PACK_LABEL.get(pack, "Member"), app_url,
        )
        invite_meta = {"auto_joined": bool(existing_user), "email_sent": email_result.get("sent", False)}

    people["people"].append(person)
    headcount = len(people["people"])
    await db.workspaces.update_one({"workspace_id": c["workspace_id"]},
                                   {"$set": {"people": people, "employees": headcount}})
    invalidate_workspace_list_cache(principal["workspace_id"], "people", "reports")
    summary = f"Added {person['name']}" + (f" · {person['role']}" if person['role'] else "") + f", headcount now {headcount}"
    if invite:
        summary += " · invited to Team & Access"
    await log_activity(principal, "people", "person.add", summary, {"headcount": headcount})
    by_user = await dept_access.department_names_by_user_id(db, principal["workspace_id"])
    dept_access.attach_real_departments(person, by_user.get(person.get("user_id") or "") or [])
    out = {"ok": True, "person": person}
    if invite_meta:
        out.update(invite_meta)
    return out


@api_router.patch("/people/{person_id}")
async def edit_person(person_id: str, payload: PersonInput, principal=Depends(require_section("people", "people:write"))):
    c = await get_ws(principal["workspace_id"])
    people = c["people"]
    found = None
    for p in people["people"]:
        if p["id"] == person_id:
            fields = _person_fields(payload)
            p.update(fields)
            if payload.email:
                p["email"] = _normalize_email(str(payload.email))
            found = p
            break
    if not found:
        raise HTTPException(status_code=404, detail="Person not found")
    await db.workspaces.update_one({"workspace_id": c["workspace_id"]}, {"$set": {"people": people}})
    invalidate_workspace_list_cache(principal["workspace_id"], "people", "reports")
    await log_activity(principal, "people", "person.edit", f"Updated {found['name']}'s profile")
    return {"ok": True}


@api_router.delete("/people/{person_id}")
async def remove_person(person_id: str, principal=Depends(require_section("people", "people:write"))):
    c = await get_ws(principal["workspace_id"])
    people = c["people"]
    person = next((p for p in people["people"] if p["id"] == person_id), None)
    if person and person.get("membership_id"):
        still = await db.memberships.find_one(
            {
                "membership_id": person["membership_id"],
                "workspace_id": principal["workspace_id"],
                "status": {"$in": ["active", "invited"]},
            },
            {"_id": 0, "membership_id": 1},
        )
        if still:
            raise HTTPException(
                status_code=400,
                detail="This person has Team & Access login. Remove them from Team & Access first",
            )
        # Stale membership_id after access was revoked — clear before deleting.
        person.pop("membership_id", None)
    people["people"] = [p for p in people["people"] if p["id"] != person_id]
    headcount = len(people["people"])
    await db.workspaces.update_one({"workspace_id": c["workspace_id"]},
                                   {"$set": {"people": people, "employees": headcount}})
    invalidate_workspace_list_cache(principal["workspace_id"], "people", "reports")
    if person:
        await log_activity(principal, "people", "person.delete",
                           f"Removed {person['name']}, headcount now {headcount}", {"headcount": headcount})
    return {"ok": True}


# ------------------------- Department framework -------------------------
class EnableDepartmentInput(BaseModel):
    type: str


class DepartmentMemberInput(BaseModel):
    user_id: str
    role: str = "member"


async def _department_in_workspace(department_id: str, workspace_id: str) -> dict:
    doc = await db.departments.find_one(
        {"department_id": department_id, "workspace_id": workspace_id},
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Department not found")
    return doc


@api_router.get("/departments")
async def list_departments(response: Response, principal=Depends(get_principal)):
    """Catalog of all 7 types with enabled + current-user membership annotations."""
    ws_id = principal["workspace_id"]
    user_id = principal["user_id"]
    cache_key = f"departments:{ws_id}:user:{user_id}"

    async def loader():
        enabled_rows = await db.departments.find(
            {"workspace_id": ws_id, "enabled": True},
            {"_id": 0},
        ).to_list(50)
        by_type = {d["type"]: d for d in enabled_rows}
        my_rows = await db.department_members.find(
            {"user_id": user_id},
            {"_id": 0},
        ).to_list(100)
        my_by_dept = {m["department_id"]: m for m in my_rows}
        is_ceo = dept_access.is_workspace_ceo(principal)

        out = []
        for entry in dept_catalog.DEPARTMENT_CATALOG:
            dtype = entry["type"]
            enabled_doc = by_type.get(dtype)
            membership = None
            if enabled_doc:
                membership = my_by_dept.get(enabled_doc["department_id"])
            out.append({
                "type": dtype,
                "name": entry["name"],
                "icon": entry["icon"],
                "enabled": bool(enabled_doc),
                "department_id": enabled_doc["department_id"] if enabled_doc else None,
                "is_member": bool(membership),
                "member_role": (membership or {}).get("role"),
                "visible_in_nav": bool(enabled_doc) and (is_ceo or bool(membership)),
            })
        return {
            "departments": out,
            "is_ceo": is_ceo,
            "can_manage": is_ceo,
        }

    data = await simple_cache.get_or_set(cache_key, 60.0, loader)
    # Private short cache — catalog/membership churn is low; never public/shared.
    response.headers["Cache-Control"] = "private, max-age=30"
    return data


@api_router.post("/departments")
async def enable_department(payload: EnableDepartmentInput, principal=Depends(get_principal)):
    if not dept_access.is_workspace_ceo(principal):
        raise HTTPException(status_code=403, detail="Only the CEO can enable departments")
    dtype = (payload.type or "").strip().lower()
    if dtype not in dept_catalog.VALID_DEPARTMENT_TYPES:
        raise HTTPException(status_code=400, detail="Unknown department type")
    existing = await db.departments.find_one(
        {"workspace_id": principal["workspace_id"], "type": dtype},
        {"_id": 0},
    )
    if existing and existing.get("enabled"):
        raise HTTPException(status_code=409, detail="Department already enabled")
    # Re-enable a soft-disabled row (same department_id) so deals/entries stay linked.
    dept, created_or_reenabled = await dept_migrate.ensure_enabled_department(
        db, principal["workspace_id"], dtype,
    )
    department_id = dept["department_id"]
    name = dept.get("name") or dept_catalog.default_name(dtype)
    if created_or_reenabled and existing and existing.get("disabled_at"):
        await db.departments.update_one(
            {"department_id": department_id, "workspace_id": principal["workspace_id"]},
            {"$unset": {"disabled_at": ""}},
        )
    if dtype == dept_catalog.TYPE_HR:
        await _ensure_hr_onboarding_template(
            principal["workspace_id"], department_id,
        )
        await _ensure_hr_offboarding_template(
            principal["workspace_id"], department_id,
        )
    await _product_event(
        principal["workspace_id"], principal["user_id"],
        helm_analytics.EVENT_DEPARTMENT_ENABLED,
        {"department": dtype, "department_id": department_id},
    )
    invalidate_departments_cache(principal["workspace_id"])
    return {
        "ok": True,
        "department": {
            "department_id": department_id,
            "type": dtype,
            "name": name,
            "enabled": True,
        },
    }


@api_router.delete("/departments/{department_id}")
async def disable_department(department_id: str, principal=Depends(get_principal)):
    if not dept_access.is_workspace_ceo(principal):
        raise HTTPException(status_code=403, detail="Only the CEO can disable departments")
    doc = await _department_in_workspace(department_id, principal["workspace_id"])
    # Clear department-owned feature data (stages, queues, HR template, etc.).
    # Core workspace records (deals / financial entries) are left intact and keep
    # department_id — soft-disable so re-enable reuses the same id.
    cleared = await dept_access.clear_department_feature_data(db, department_id)
    await db.department_members.delete_many({"department_id": department_id})
    now = datetime.now(timezone.utc).isoformat()
    await db.departments.update_one(
        {"department_id": department_id, "workspace_id": principal["workspace_id"]},
        {"$set": {"enabled": False, "disabled_at": now}},
    )
    invalidate_departments_cache(principal["workspace_id"])
    return {"ok": True, "type": doc.get("type"), "cleared": cleared}


@api_router.get("/departments/{department_id}/members")
async def list_department_members(department_id: str, principal=Depends(get_principal)):
    doc = await _department_in_workspace(department_id, principal["workspace_id"])
    if not doc.get("enabled"):
        raise HTTPException(status_code=404, detail="Department not found")
    if not await dept_access.can_access_department(db, principal, doc):
        raise HTTPException(status_code=403, detail="You do not have access to this department")
    rows = await db.department_members.find({"department_id": department_id}, {"_id": 0}).to_list(200)
    users_by_id = await _users_by_ids(
        [m.get("user_id") for m in rows],
        {"_id": 0, "user_id": 1, "name": 1, "email": 1, "picture": 1},
    )
    out = []
    for m in rows:
        u = users_by_id.get(m["user_id"])
        out.append({
            "user_id": m["user_id"],
            "role": m.get("role") or "member",
            "created_at": m.get("created_at"),
            "name": (u or {}).get("name"),
            "email": (u or {}).get("email"),
            "picture": (u or {}).get("picture"),
        })
    out.sort(key=lambda x: ((x.get("name") or x.get("email") or "").lower(), x["user_id"]))
    return {
        "department_id": department_id,
        "type": doc["type"],
        "name": doc.get("name") or dept_catalog.default_name(doc["type"]),
        "members": out,
        "can_manage": await dept_access.can_manage_department_members(db, principal, department_id),
    }


@api_router.post("/departments/{department_id}/members")
async def add_department_member(
    department_id: str,
    payload: DepartmentMemberInput,
    principal=Depends(get_principal),
):
    doc = await _department_in_workspace(department_id, principal["workspace_id"])
    if not doc.get("enabled"):
        raise HTTPException(status_code=404, detail="Department not found")
    if not await dept_access.can_manage_department_members(db, principal, department_id):
        raise HTTPException(status_code=403, detail="Only the CEO or a department lead can add members")
    role = (payload.role or "member").strip().lower()
    if role not in dept_catalog.DEPARTMENT_MEMBER_ROLES:
        raise HTTPException(status_code=400, detail="Role must be member or lead")
    user_id = (payload.user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    ws_mem = await db.memberships.find_one(
        {"workspace_id": principal["workspace_id"], "user_id": user_id, "status": "active"},
        {"_id": 0},
    )
    if not ws_mem:
        raise HTTPException(status_code=400, detail="User is not an active member of this workspace")
    existing = await db.department_members.find_one(
        {"department_id": department_id, "user_id": user_id},
        {"_id": 0},
    )
    if existing:
        await db.department_members.update_one(
            {"department_id": department_id, "user_id": user_id},
            {"$set": {"role": role}},
        )
        invalidate_departments_cache(principal["workspace_id"])
        return {"ok": True, "updated": True, "role": role}
    await db.department_members.insert_one({
        "department_id": department_id,
        "user_id": user_id,
        "role": role,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    invalidate_departments_cache(principal["workspace_id"])
    return {"ok": True, "updated": False, "role": role}


@api_router.delete("/departments/{department_id}/members/{user_id}")
async def remove_department_member(
    department_id: str,
    user_id: str,
    principal=Depends(get_principal),
):
    doc = await _department_in_workspace(department_id, principal["workspace_id"])
    if not doc.get("enabled"):
        raise HTTPException(status_code=404, detail="Department not found")
    if not await dept_access.can_manage_department_members(db, principal, department_id):
        raise HTTPException(status_code=403, detail="Only the CEO or a department lead can remove members")
    result = await db.department_members.delete_one(
        {"department_id": department_id, "user_id": user_id},
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Membership not found")
    invalidate_departments_cache(principal["workspace_id"])
    return {"ok": True}


@api_router.get("/departments/by-type/{dept_type}")
async def get_department_by_type(dept_type: str, principal=Depends(get_principal)):
    """Resolve an enabled department by catalog type; enforce access for placeholder pages."""
    dtype = (dept_type or "").strip().lower()
    if dtype not in dept_catalog.VALID_DEPARTMENT_TYPES:
        raise HTTPException(status_code=404, detail="Unknown department type")
    doc = await db.departments.find_one(
        {"workspace_id": principal["workspace_id"], "type": dtype, "enabled": True},
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Department is not enabled")
    if not await dept_access.can_access_department(db, principal, doc):
        raise HTTPException(status_code=403, detail="You do not have access to this department")
    membership = await dept_access.get_department_membership(db, doc["department_id"], principal["user_id"])
    await _product_event(
        principal["workspace_id"], principal["user_id"],
        helm_analytics.EVENT_DEPARTMENT_PAGE_VIEWED,
        {"department": dtype},
    )
    return {
        "department_id": doc["department_id"],
        "type": doc["type"],
        "name": doc.get("name") or dept_catalog.default_name(doc["type"]),
        "icon": (dept_catalog.catalog_entry(doc["type"]) or {}).get("icon"),
        "is_ceo": dept_access.is_workspace_ceo(principal),
        "is_member": bool(membership),
        "member_role": (membership or {}).get("role"),
        "placeholder": dtype in dept_catalog.PLACEHOLDER_SHELL_TYPES,
        "can_manage_members": await dept_access.can_manage_department_members(
            db, principal, doc["department_id"],
        ),
    }


# ------------------------- Production work-order queue -------------------------
# Flat queue with fixed statuses (mirrors Procurement). No stage templates / Kanban.
PRODUCTION_WORK_ORDER_STATUSES = frozenset({
    "awaiting_materials", "in_production", "quality_check", "completed",
})
PRODUCTION_OPEN_STATUSES = frozenset({
    "awaiting_materials", "in_production", "quality_check",
})
PRODUCTION_PRIORITIES = frozenset({"low", "normal", "high"})
PRODUCTION_BLOCKED_CATEGORIES = frozenset({"material", "labor", "machine", "quality", "other"})
PROCUREMENT_OPEN_FOR_LINK = frozenset({"requested", "approved", "ordered"})
MAINTENANCE_OPEN_FOR_LINK = frozenset({"reported", "diagnosed", "in_repair"})


async def _production_department(principal: dict) -> dict:
    """Enabled Production department for this workspace, with access enforced."""
    doc = await db.departments.find_one(
        {
            "workspace_id": principal["workspace_id"],
            "type": dept_catalog.TYPE_PRODUCTION,
            "enabled": True,
        },
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Production department is not enabled")
    if not await dept_access.can_access_department(db, principal, doc):
        raise HTTPException(status_code=403, detail="You do not have access to Production")
    return doc


def _can_lead_production(principal: dict, membership: dict | None) -> bool:
    if dept_access.is_workspace_ceo(principal):
        return True
    return bool(membership) and membership.get("role") == "lead"


def _can_update_production_order(principal: dict, membership: dict | None, order: dict) -> bool:
    """Lead/CEO can update any order; members only when assigned (or unassigned)."""
    if _can_lead_production(principal, membership):
        return True
    assigned = list(order.get("assigned_user_ids") or [])
    if not assigned:
        return True
    return principal["user_id"] in assigned


async def _enrich_assignee_ids(user_ids: list, users: dict | None = None) -> list:
    ids = [u for u in (user_ids or []) if u]
    lookup = users if users is not None else await _users_by_ids(ids)
    return [_user_card(uid, lookup.get(uid)) for uid in ids]


def _normalize_blocked_reason(raw, *, require: bool) -> Optional[dict]:
    if raw is None:
        if require:
            raise HTTPException(
                status_code=400,
                detail="blocked_reason.category is required when blocked is true",
            )
        return None
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="blocked_reason must be an object")
    category = str(raw.get("category") or "").strip().lower()
    detail = str(raw.get("detail") or "").strip()[:500]
    if require and not category:
        raise HTTPException(
            status_code=400,
            detail="blocked_reason.category is required when blocked is true",
        )
    if category and category not in PRODUCTION_BLOCKED_CATEGORIES:
        raise HTTPException(status_code=400, detail="Invalid blocked_reason.category")
    if not category and not detail:
        return None
    if not category:
        raise HTTPException(status_code=400, detail="blocked_reason.category is required")
    return {"category": category, "detail": detail}


async def _get_work_order(department_id: str, work_order_id: str) -> dict:
    doc = await db.production_work_orders.find_one(
        {"id": work_order_id, "department_id": department_id},
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Work order not found")
    return doc


async def _enrich_work_order(
    order: dict,
    users: dict | None = None,
    procurement_by_id: dict | None = None,
    maintenance_by_id: dict | None = None,
) -> dict:
    out = {k: v for k, v in order.items() if k != "_id"}
    # Old records may lack unit — surface empty, never invent "units".
    if "unit" not in out or out.get("unit") is None:
        out["unit"] = ""
    else:
        out["unit"] = str(out.get("unit") or "").strip()
    if "input_unit" not in out or out.get("input_unit") is None:
        out["input_unit"] = ""
    out["yield_tracking_enabled"] = bool(out.get("yield_tracking_enabled"))
    out["assignees"] = await _enrich_assignee_ids(out.get("assigned_user_ids") or [], users)
    link = out.get("linked_procurement_request_id")
    if link:
        req = None
        if procurement_by_id is not None:
            req = procurement_by_id.get(link)
        else:
            req = await db.procurement_requests.find_one(
                {"id": link, "workspace_id": out.get("workspace_id")},
                {"_id": 0, "id": 1, "item": 1, "status": 1, "quantity": 1},
            )
        out["linked_procurement"] = (
            {"id": req["id"], "item": req.get("item") or "", "status": req.get("status"), "quantity": req.get("quantity")}
            if req else None
        )
    else:
        out["linked_procurement"] = None
    mt_link = out.get("linked_maintenance_ticket_id")
    if mt_link:
        ticket = None
        if maintenance_by_id is not None:
            ticket = maintenance_by_id.get(mt_link)
        else:
            ticket = await db.maintenance_tickets.find_one(
                {"id": mt_link, "workspace_id": out.get("workspace_id")},
                {"_id": 0, "id": 1, "equipment_name": 1, "status": 1, "priority": 1},
            )
        out["linked_maintenance"] = (
            {
                "id": ticket["id"],
                "equipment_name": ticket.get("equipment_name") or "",
                "status": ticket.get("status"),
                "priority": ticket.get("priority"),
            }
            if ticket else None
        )
    else:
        out["linked_maintenance"] = None
    return out


async def _validate_procurement_link(workspace_id: str, request_id: str) -> dict:
    req = await db.procurement_requests.find_one(
        {"id": request_id, "workspace_id": workspace_id},
        {"_id": 0},
    )
    if not req:
        raise HTTPException(status_code=400, detail="Procurement request not found in this workspace")
    if req.get("status") not in PROCUREMENT_OPEN_FOR_LINK:
        raise HTTPException(
            status_code=400,
            detail="Can only link open procurement requests (requested, approved, or ordered)",
        )
    return req


async def _validate_maintenance_link(workspace_id: str, ticket_id: str) -> dict:
    ticket = await db.maintenance_tickets.find_one(
        {"id": ticket_id, "workspace_id": workspace_id},
        {"_id": 0},
    )
    if not ticket:
        raise HTTPException(status_code=400, detail="Maintenance ticket not found in this workspace")
    if ticket.get("status") not in MAINTENANCE_OPEN_FOR_LINK:
        raise HTTPException(
            status_code=400,
            detail="Can only link open maintenance tickets (reported, diagnosed, or in_repair)",
        )
    return ticket


class ProductionWorkOrderCreate(BaseModel):
    reference: str
    product: str = ""
    quantity_planned: Optional[float] = None
    customer: str = ""
    priority: str = "normal"
    due_date: str = ""
    linked_procurement_request_id: Optional[str] = None
    linked_maintenance_ticket_id: Optional[str] = None
    source_deal_id: Optional[str] = None
    assigned_user_ids: list[str] = []
    notes: str = ""
    blocked: bool = False
    blocked_reason: Optional[dict] = None
    unit: str = ""
    yield_tracking_enabled: bool = False
    expected_yield_pct: Optional[float] = None
    input_unit: str = ""


class ProductionWorkOrderPatch(BaseModel):
    reference: Optional[str] = None
    product: Optional[str] = None
    quantity_planned: Optional[float] = None
    quantity_produced: Optional[float] = None
    customer: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None
    status: Optional[str] = None
    blocked: Optional[bool] = None
    blocked_reason: Optional[dict] = None
    linked_procurement_request_id: Optional[str] = None
    linked_maintenance_ticket_id: Optional[str] = None
    source_deal_id: Optional[str] = None
    assigned_user_ids: Optional[list[str]] = None
    notes: Optional[str] = None
    unit: Optional[str] = None
    yield_tracking_enabled: Optional[bool] = None
    expected_yield_pct: Optional[float] = None
    input_unit: Optional[str] = None


class ProductionDailyLogInput(BaseModel):
    date: str
    target_quantity: Optional[float] = None
    actual_quantity: Optional[float] = None
    unit: str = ""
    overtime_hours: Optional[float] = None
    input_quantity: Optional[float] = None
    input_unit: str = ""
    notes: str = ""


class ProductionSettingsInput(BaseModel):
    overtime_rate_per_hour: Optional[float] = None


@api_router.get("/production/work-orders")
async def list_production_work_orders(
    principal=Depends(get_principal),
    status: Optional[str] = Query(None),
):
    dept = await _production_department(principal)
    status_key = (status or "").strip().lower() or "all"
    cache_key = _list_cache_key(
        "production", principal["workspace_id"], principal["user_id"],
        dept["department_id"], status_key,
    )
    cached = simple_cache.peek(cache_key)
    if cached is not None:
        return cached
    filt: dict = {"department_id": dept["department_id"]}
    if status is not None:
        st = status.strip().lower()
        if st not in PRODUCTION_WORK_ORDER_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status filter")
        filt["status"] = st
    rows = await db.production_work_orders.find(filt, {"_id": 0}).sort("created_at", -1).to_list(1000)
    rows = helm_freshness.annotate_possibly_stale(rows, dept_type=dept_catalog.TYPE_PRODUCTION)
    assignee_ids = []
    link_ids = []
    maint_ids = []
    for r in rows:
        assignee_ids.extend(r.get("assigned_user_ids") or [])
        if r.get("linked_procurement_request_id"):
            link_ids.append(r["linked_procurement_request_id"])
        if r.get("linked_maintenance_ticket_id"):
            maint_ids.append(r["linked_maintenance_ticket_id"])
    users = await _users_by_ids(assignee_ids)
    procurement_by_id = {}
    if link_ids:
        proc_rows = await db.procurement_requests.find(
            {"id": {"$in": list(set(link_ids))}, "workspace_id": principal["workspace_id"]},
            {"_id": 0, "id": 1, "item": 1, "status": 1, "quantity": 1},
        ).to_list(1000)
        procurement_by_id = {p["id"]: p for p in proc_rows}
    maintenance_by_id = {}
    if maint_ids:
        mt_rows = await db.maintenance_tickets.find(
            {"id": {"$in": list(set(maint_ids))}, "workspace_id": principal["workspace_id"]},
            {"_id": 0, "id": 1, "equipment_name": 1, "status": 1, "priority": 1},
        ).to_list(1000)
        maintenance_by_id = {t["id"]: t for t in mt_rows}
    orders = [
        await _enrich_work_order(r, users, procurement_by_id, maintenance_by_id) for r in rows
    ]
    # Attach per-WO daily log rollups (independent targets — never shared across WOs).
    wo_ids = [o.get("id") for o in orders if o.get("id")]
    logs_by_wo: dict[str, list] = {wid: [] for wid in wo_ids}
    if wo_ids:
        log_rows = await db.production_daily_logs.find(
            {"workspace_id": principal["workspace_id"], "work_order_id": {"$in": wo_ids}},
            {"_id": 0},
        ).sort("date", 1).to_list(5000)
        for log in log_rows:
            logs_by_wo.setdefault(log.get("work_order_id"), []).append(log)
    for o in orders:
        wid = o.get("id")
        o["daily_rollup"] = prod_daily.rollup_work_order_logs(
            logs_by_wo.get(wid) or [],
            quantity_planned=o.get("quantity_planned"),
            yield_tracking_enabled=bool(o.get("yield_tracking_enabled")),
            expected_yield_pct=o.get("expected_yield_pct"),
        )
    today_summary = prod_daily.department_day_summary(orders, logs_by_wo)
    week_ago = (datetime.now(timezone.utc).date() - timedelta(days=7)).isoformat()
    week_logs = [
        log for logs in logs_by_wo.values() for log in logs
        if (log.get("date") or "") >= week_ago
    ]
    overtime_week = prod_daily.period_overtime_rollup(week_logs)
    overtime_rate = float(dept.get("overtime_rate_per_hour") or 0) or None
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    is_lead = _can_lead_production(principal, membership)
    cycle = decision_engine.compute_average_cycle_time(rows)
    # Open procurement / maintenance for linking — scoped to departments the user can see.
    proc_ids = await dept_access.accessible_department_ids(
        db, principal, dept_catalog.TYPE_PROCUREMENT,
    )
    maint_ids_access = await dept_access.accessible_department_ids(
        db, principal, dept_catalog.TYPE_ENGINEERING_MAINTENANCE,
    )
    proc_filt = dept_access.apply_department_filter(
        {
            "workspace_id": principal["workspace_id"],
            "status": {"$in": list(PROCUREMENT_OPEN_FOR_LINK)},
        },
        proc_ids,
    )
    maint_filt = dept_access.apply_department_filter(
        {
            "workspace_id": principal["workspace_id"],
            "status": {"$in": list(MAINTENANCE_OPEN_FOR_LINK)},
        },
        maint_ids_access,
    )
    open_proc = await db.procurement_requests.find(
        proc_filt,
        {"_id": 0, "id": 1, "item": 1, "status": 1, "quantity": 1},
    ).sort("created_at", -1).to_list(500)
    open_maint = await db.maintenance_tickets.find(
        maint_filt,
        {"_id": 0, "id": 1, "equipment_name": 1, "status": 1, "priority": 1},
    ).sort("created_at", -1).to_list(500)
    payload_out = {
        "department_id": dept["department_id"],
        "name": dept.get("name") or "Production",
        "work_orders": orders,
        "statuses": sorted(PRODUCTION_WORK_ORDER_STATUSES),
        "priorities": sorted(PRODUCTION_PRIORITIES),
        "blocked_categories": sorted(PRODUCTION_BLOCKED_CATEGORIES),
        "open_procurement_requests": open_proc,
        "open_maintenance_tickets": open_maint,
        "average_cycle_time": cycle,
        "is_ceo": dept_access.is_workspace_ceo(principal),
        "is_lead": is_lead,
        "my_user_id": principal["user_id"],
        "today_summary": today_summary,
        "overtime_week": overtime_week,
        "overtime_rate_per_hour": overtime_rate,
        "common_units": list(prod_daily.COMMON_UNITS),
    }
    simple_cache.put(cache_key, payload_out, _DEPT_LIST_CACHE_TTL_SECONDS)
    return payload_out


@api_router.post("/production/work-orders")
async def create_production_work_order(payload: ProductionWorkOrderCreate, principal=Depends(get_principal)):
    dept = await _production_department(principal)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    reference = (payload.reference or "").strip()
    if not reference:
        raise HTTPException(status_code=400, detail="reference is required")
    priority = (payload.priority or "normal").strip().lower()
    if priority not in PRODUCTION_PRIORITIES:
        raise HTTPException(status_code=400, detail="Invalid priority")
    assignees = [u for u in (payload.assigned_user_ids or []) if u]
    if assignees and not _can_lead_production(principal, membership):
        raise HTTPException(
            status_code=403,
            detail="Only a production lead or CEO can assign work orders",
        )
    linked = (payload.linked_procurement_request_id or "").strip() or None
    linked_req = None
    if linked:
        linked_req = await _validate_procurement_link(principal["workspace_id"], linked)
    linked_mt = (payload.linked_maintenance_ticket_id or "").strip() or None
    if linked_mt:
        await _validate_maintenance_link(principal["workspace_id"], linked_mt)
    status = "in_production"
    if linked_req and linked_req.get("status") not in ("delivered", "rejected"):
        status = "awaiting_materials"
    blocked = bool(payload.blocked)
    blocked_reason = _normalize_blocked_reason(payload.blocked_reason, require=blocked)
    if not blocked:
        blocked_reason = None
    qty_planned = payload.quantity_planned
    if qty_planned is not None:
        try:
            qty_planned = float(qty_planned)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="quantity_planned must be a number")
        if qty_planned < 0:
            raise HTTPException(status_code=400, detail="quantity_planned cannot be negative")
    now = datetime.now(timezone.utc).isoformat()
    order = {
        "id": f"pwo_{uuid.uuid4().hex[:10]}",
        "department_id": dept["department_id"],
        "workspace_id": principal["workspace_id"],
        "reference": reference[:200],
        "product": (payload.product or "").strip()[:200],
        "quantity_planned": qty_planned,
        "quantity_produced": None,
        "customer": (payload.customer or "").strip()[:200],
        "priority": priority,
        "due_date": (payload.due_date or "").strip()[:32],
        "status": status,
        "blocked": blocked,
        "blocked_reason": blocked_reason,
        "linked_procurement_request_id": linked,
        "linked_maintenance_ticket_id": linked_mt,
        "source_deal_id": (payload.source_deal_id or "").strip() or None,
        "assigned_user_ids": assignees,
        "notes": (payload.notes or "").strip()[:2000],
        "unit": "",
        "yield_tracking_enabled": bool(payload.yield_tracking_enabled),
        "expected_yield_pct": None,
        "input_unit": (payload.input_unit or "").strip()[:32],
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
    }
    try:
        order["unit"] = prod_daily.normalize_unit(payload.unit, required=False, field="unit")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if payload.expected_yield_pct is not None:
        try:
            ey = float(payload.expected_yield_pct)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="expected_yield_pct must be a number")
        if ey < 0 or ey > 100:
            raise HTTPException(status_code=400, detail="expected_yield_pct must be 0–100")
        order["expected_yield_pct"] = ey
    await db.production_work_orders.insert_one(dict(order))
    invalidate_workspace_list_cache(principal["workspace_id"], "production", "me_work", "calendar")
    return {"ok": True, "work_order": await _enrich_work_order(order)}


@api_router.patch("/production/work-orders/{work_order_id}")
async def patch_production_work_order(
    work_order_id: str,
    payload: ProductionWorkOrderPatch,
    principal=Depends(get_principal),
):
    dept = await _production_department(principal)
    order = await _get_work_order(dept["department_id"], work_order_id)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    if not _can_update_production_order(principal, membership, order):
        raise HTTPException(status_code=403, detail="You are not assigned to this work order")

    upd: dict = {}
    if payload.reference is not None:
        ref = payload.reference.strip()
        if not ref:
            raise HTTPException(status_code=400, detail="reference is required")
        upd["reference"] = ref[:200]
    if payload.product is not None:
        upd["product"] = payload.product.strip()[:200]
    if payload.quantity_planned is not None:
        try:
            upd["quantity_planned"] = float(payload.quantity_planned)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="quantity_planned must be a number")
        if upd["quantity_planned"] < 0:
            raise HTTPException(status_code=400, detail="quantity_planned cannot be negative")
    if payload.quantity_produced is not None:
        try:
            upd["quantity_produced"] = float(payload.quantity_produced)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="quantity_produced must be a number")
        if upd["quantity_produced"] < 0:
            raise HTTPException(status_code=400, detail="quantity_produced cannot be negative")
    if payload.customer is not None:
        upd["customer"] = payload.customer.strip()[:200]
    if payload.priority is not None:
        pr = payload.priority.strip().lower()
        if pr not in PRODUCTION_PRIORITIES:
            raise HTTPException(status_code=400, detail="Invalid priority")
        upd["priority"] = pr
    if payload.due_date is not None:
        upd["due_date"] = payload.due_date.strip()[:32]
    if payload.notes is not None:
        upd["notes"] = payload.notes.strip()[:2000]
    if payload.unit is not None:
        try:
            upd["unit"] = prod_daily.normalize_unit(payload.unit, required=True, field="unit")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    if payload.input_unit is not None:
        upd["input_unit"] = prod_daily.normalize_unit(payload.input_unit, required=False, field="input_unit")
    if payload.yield_tracking_enabled is not None:
        upd["yield_tracking_enabled"] = bool(payload.yield_tracking_enabled)
    if payload.expected_yield_pct is not None:
        try:
            ey = float(payload.expected_yield_pct)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="expected_yield_pct must be a number")
        if ey < 0 or ey > 100:
            raise HTTPException(status_code=400, detail="expected_yield_pct must be 0–100")
        upd["expected_yield_pct"] = ey
    if payload.assigned_user_ids is not None:
        if not _can_lead_production(principal, membership):
            raise HTTPException(
                status_code=403,
                detail="Only a production lead or CEO can change assignees",
            )
        upd["assigned_user_ids"] = [u for u in payload.assigned_user_ids if u]
    linked_req = None
    link_cleared = False
    if payload.linked_procurement_request_id is not None:
        link = payload.linked_procurement_request_id.strip()
        if link:
            linked_req = await _validate_procurement_link(principal["workspace_id"], link)
            upd["linked_procurement_request_id"] = link
        else:
            upd["linked_procurement_request_id"] = None
            link_cleared = True
    if payload.linked_maintenance_ticket_id is not None:
        mt = payload.linked_maintenance_ticket_id.strip()
        if mt:
            await _validate_maintenance_link(principal["workspace_id"], mt)
            upd["linked_maintenance_ticket_id"] = mt
        else:
            upd["linked_maintenance_ticket_id"] = None
    if payload.source_deal_id is not None:
        sid = payload.source_deal_id.strip()
        upd["source_deal_id"] = sid or None

    next_status = order.get("status")
    if payload.status is not None:
        st = payload.status.strip().lower()
        if st not in PRODUCTION_WORK_ORDER_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status")
        upd["status"] = st
        next_status = st
    elif linked_req is not None and next_status != "completed":
        # Linking an open procurement request means we're waiting on materials —
        # match create_production_work_order so the Procurement blocking badge appears.
        upd["status"] = "awaiting_materials"
        next_status = "awaiting_materials"
    elif link_cleared and next_status == "awaiting_materials":
        # Dropping the link while still marked awaiting materials → resume production.
        upd["status"] = "in_production"
        next_status = "in_production"

    next_blocked = bool(order.get("blocked", False))
    if payload.blocked is not None:
        next_blocked = bool(payload.blocked)
        upd["blocked"] = next_blocked

    if next_blocked:
        reason_src = (
            payload.blocked_reason
            if payload.blocked_reason is not None
            else order.get("blocked_reason")
        )
        upd["blocked_reason"] = _normalize_blocked_reason(reason_src, require=True)
    elif payload.blocked is False:
        upd["blocked_reason"] = None
    elif payload.blocked_reason is not None:
        upd["blocked_reason"] = _normalize_blocked_reason(payload.blocked_reason, require=False)

    # Completing requires quantity_produced
    if next_status == "completed":
        qty_produced = upd.get("quantity_produced", order.get("quantity_produced"))
        if qty_produced is None:
            raise HTTPException(
                status_code=400,
                detail="quantity_produced is required when completing a work order",
            )

    helm_dept_drafts.apply_status_completion(order, upd, done_status="completed")

    if not upd:
        return {"ok": True, "work_order": await _enrich_work_order(order)}
    upd["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.production_work_orders.update_one(
        {"id": work_order_id, "department_id": dept["department_id"]},
        {"$set": upd},
    )
    invalidate_workspace_list_cache(principal["workspace_id"], "production", "me_work", "calendar")
    return {"ok": True, "work_order": await _enrich_work_order({**order, **upd})}


@api_router.delete("/production/work-orders/{work_order_id}")
async def delete_production_work_order(work_order_id: str, principal=Depends(get_principal)):
    dept = await _production_department(principal)
    order = await _get_work_order(dept["department_id"], work_order_id)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    if not _can_update_production_order(principal, membership, order):
        raise HTTPException(status_code=403, detail="You are not assigned to this work order")
    invalidate_workspace_list_cache(principal["workspace_id"], "production", "me_work", "calendar")
    await db.production_work_orders.delete_one(
        {"id": work_order_id, "department_id": dept["department_id"]},
    )
    await db.production_daily_logs.delete_many(
        {"work_order_id": work_order_id, "workspace_id": principal["workspace_id"]},
    )
    return {"ok": True}


@api_router.get("/production/settings")
async def get_production_settings(principal=Depends(get_principal)):
    dept = await _production_department(principal)
    rate = dept.get("overtime_rate_per_hour")
    try:
        rate_f = float(rate) if rate is not None else None
    except (TypeError, ValueError):
        rate_f = None
    return {
        "overtime_rate_per_hour": rate_f,
        "common_units": list(prod_daily.COMMON_UNITS),
        "can_manage": dept_access.is_workspace_ceo(principal) or (
            (await dept_access.get_department_membership(db, dept["department_id"], principal["user_id"]) or {}).get("role") == "lead"
        ),
    }


@api_router.put("/production/settings")
async def put_production_settings(payload: ProductionSettingsInput, principal=Depends(get_principal)):
    dept = await _production_department(principal)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    if not _can_lead_production(principal, membership):
        raise HTTPException(status_code=403, detail="Only a production lead or CEO can change settings")
    upd = {}
    if payload.overtime_rate_per_hour is not None:
        try:
            rate = float(payload.overtime_rate_per_hour)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="overtime_rate_per_hour must be a number")
        if rate < 0:
            raise HTTPException(status_code=400, detail="overtime_rate_per_hour cannot be negative")
        upd["overtime_rate_per_hour"] = rate
    if not upd:
        raise HTTPException(status_code=400, detail="No changes provided")
    await db.departments.update_one(
        {"department_id": dept["department_id"]},
        {"$set": upd},
    )
    invalidate_departments_cache(principal["workspace_id"])
    invalidate_workspace_list_cache(principal["workspace_id"], "production")
    return {"ok": True, **upd}


@api_router.get("/production/work-orders/{work_order_id}/daily-logs")
async def list_production_daily_logs(work_order_id: str, principal=Depends(get_principal)):
    dept = await _production_department(principal)
    order = await _get_work_order(dept["department_id"], work_order_id)
    rows = await db.production_daily_logs.find(
        {"work_order_id": work_order_id, "workspace_id": principal["workspace_id"]},
        {"_id": 0},
    ).sort("date", -1).to_list(366)
    expected = order.get("expected_yield_pct") if order.get("yield_tracking_enabled") else None
    logs = [prod_daily.enrich_daily_log(r, expected_yield_pct=expected) for r in rows]
    return {
        "work_order_id": work_order_id,
        "yield_tracking_enabled": bool(order.get("yield_tracking_enabled")),
        "expected_yield_pct": order.get("expected_yield_pct"),
        "unit": order.get("unit") or "",
        "input_unit": order.get("input_unit") or "",
        "logs": logs,
        "rollup": prod_daily.rollup_work_order_logs(
            rows,
            quantity_planned=order.get("quantity_planned"),
            yield_tracking_enabled=bool(order.get("yield_tracking_enabled")),
            expected_yield_pct=order.get("expected_yield_pct"),
        ),
    }


@api_router.post("/production/work-orders/{work_order_id}/daily-logs")
async def upsert_production_daily_log(
    work_order_id: str,
    payload: ProductionDailyLogInput,
    principal=Depends(get_principal),
):
    dept = await _production_department(principal)
    order = await _get_work_order(dept["department_id"], work_order_id)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    if not _can_update_production_order(principal, membership, order):
        raise HTTPException(status_code=403, detail="You are not assigned to this work order")
    try:
        day = prod_daily.normalize_log_date(payload.date)
        target = prod_daily.parse_nonneg_float(payload.target_quantity, field="target_quantity")
        actual = prod_daily.parse_nonneg_float(payload.actual_quantity, field="actual_quantity")
        ot = prod_daily.parse_nonneg_float(payload.overtime_hours, field="overtime_hours")
        in_qty = prod_daily.parse_nonneg_float(payload.input_quantity, field="input_quantity")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if target is None and actual is None:
        raise HTTPException(status_code=400, detail="Enter a target and/or actual quantity for the day")
    if not order.get("yield_tracking_enabled"):
        in_qty = None
    try:
        unit = prod_daily.normalize_unit(
            payload.unit or order.get("unit") or "",
            required=True,
            field="unit",
        )
        input_unit = prod_daily.normalize_unit(
            payload.input_unit or order.get("input_unit") or "",
            required=False,
            field="input_unit",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    rate = dept.get("overtime_rate_per_hour")
    try:
        rate_f = float(rate) if rate is not None else None
    except (TypeError, ValueError):
        rate_f = None
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": f"pdl_{uuid.uuid4().hex[:10]}",
        "work_order_id": work_order_id,
        "department_id": dept["department_id"],
        "workspace_id": principal["workspace_id"],
        "date": day,
        "target_quantity": target,
        "actual_quantity": actual,
        "unit": unit,
        "overtime_hours": ot,
        "overtime_rate_per_hour": rate_f,
        "input_quantity": in_qty,
        "input_unit": input_unit if order.get("yield_tracking_enabled") else "",
        "notes": (payload.notes or "").strip()[:1000],
        "logged_by": principal["user_id"],
        "created_at": now,
        "updated_at": now,
    }
    query = {
        "work_order_id": work_order_id,
        "date": day,
        "workspace_id": principal["workspace_id"],
    }
    set_fields = {k: v for k, v in doc.items() if k not in ("id", "created_at")}
    result = await db.production_daily_logs.update_one(
        query,
        {"$set": set_fields, "$setOnInsert": {"id": doc["id"], "created_at": now}},
        upsert=True,
    )
    final = await db.production_daily_logs.find_one(query, {"_id": 0})
    was_update = bool(result.matched_count) and not result.upserted_id
    invalidate_workspace_list_cache(principal["workspace_id"], "production")
    expected = order.get("expected_yield_pct") if order.get("yield_tracking_enabled") else None
    return {
        "ok": True,
        "log": prod_daily.enrich_daily_log(final or doc, expected_yield_pct=expected),
        "updated": was_update,
    }


@api_router.delete("/production/daily-logs/{log_id}")
async def delete_production_daily_log(log_id: str, principal=Depends(get_principal)):
    dept = await _production_department(principal)
    log = await db.production_daily_logs.find_one(
        {"id": log_id, "workspace_id": principal["workspace_id"]},
        {"_id": 0},
    )
    if not log:
        raise HTTPException(status_code=404, detail="Daily log not found")
    order = await _get_work_order(dept["department_id"], log["work_order_id"])
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    if not _can_update_production_order(principal, membership, order):
        raise HTTPException(status_code=403, detail="You are not assigned to this work order")
    await db.production_daily_logs.delete_one({"id": log_id})
    invalidate_workspace_list_cache(principal["workspace_id"], "production")
    return {"ok": True}


# ------------------------- Procurement request queue -------------------------
PROCUREMENT_STATUSES = frozenset({
    "requested", "approved", "ordered", "delivered", "rejected",
})
PROCUREMENT_CLOSED_STATUSES = frozenset({"delivered", "rejected"})
PROCUREMENT_APPROVAL_STATUSES = frozenset({"approved", "rejected"})
PROCUREMENT_PRIORITIES = frozenset({"low", "normal", "high"})


async def _procurement_department(principal: dict) -> dict:
    """Enabled Procurement department for this workspace, with access enforced."""
    doc = await db.departments.find_one(
        {
            "workspace_id": principal["workspace_id"],
            "type": dept_catalog.TYPE_PROCUREMENT,
            "enabled": True,
        },
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Procurement department is not enabled")
    if not await dept_access.can_access_department(db, principal, doc):
        raise HTTPException(status_code=403, detail="You do not have access to Procurement")
    return doc


def _can_lead_procurement(principal: dict, membership: dict | None) -> bool:
    if dept_access.is_workspace_ceo(principal):
        return True
    return bool(membership) and membership.get("role") == "lead"


def _blocking_production_order_entry(wo: dict) -> dict:
    return {
        "work_order_id": wo.get("id"),
        "reference": wo.get("reference") or "",
        "due_date": wo.get("due_date") or "",
    }


def _production_order_blocks_procurement(wo: dict) -> bool:
    """True when a work order is actively waiting on / blocked by materials."""
    if wo.get("status") == "awaiting_materials":
        return True
    return bool(wo.get("blocked"))


async def _blocking_production_orders_by_request(
    workspace_id: str,
    request_ids: list[str],
) -> dict[str, list]:
    """Live lookup: procurement request id → blocking production work orders."""
    ids = [rid for rid in request_ids if rid]
    if not ids or not workspace_id:
        return {}
    rows = await db.production_work_orders.find(
        {
            "workspace_id": workspace_id,
            "linked_procurement_request_id": {"$in": ids},
            "$or": [
                {"status": "awaiting_materials"},
                {"blocked": True},
            ],
        },
        {
            "_id": 0,
            "id": 1,
            "reference": 1,
            "due_date": 1,
            "linked_procurement_request_id": 1,
            "status": 1,
            "blocked": 1,
        },
    ).to_list(2000)
    by_request: dict[str, list] = {}
    for wo in rows:
        if not _production_order_blocks_procurement(wo):
            continue
        rid = wo.get("linked_procurement_request_id")
        if not rid:
            continue
        by_request.setdefault(rid, []).append(_blocking_production_order_entry(wo))
    return by_request


async def _enrich_procurement_request(
    req: dict,
    users: dict | None = None,
    *,
    blocking_by_request: dict | None = None,
) -> dict:
    out = {k: v for k, v in req.items() if k != "_id"}
    uids = [out.get("requested_by"), out.get("approved_by")]
    lookup = users if users is not None else await _users_by_ids(uids)
    for field, label in (("requested_by", "requester"), ("approved_by", "approver")):
        uid = out.get(field)
        info = None
        if uid:
            info = _user_card(uid, lookup.get(uid))
        out[label] = info
    rid = out.get("id")
    if blocking_by_request is not None:
        out["blocking_production_orders"] = list(blocking_by_request.get(rid) or [])
    else:
        ws = out.get("workspace_id")
        if ws and rid:
            mapping = await _blocking_production_orders_by_request(ws, [rid])
            out["blocking_production_orders"] = list(mapping.get(rid) or [])
        else:
            out["blocking_production_orders"] = []
    out = proc_metrics.attach_lead_time_metrics(out)
    return out


async def _enrich_procurement_requests(rows: list, workspace_id: str | None = None) -> list:
    ids = []
    for r in rows:
        ids.append(r.get("requested_by"))
        ids.append(r.get("approved_by"))
    users = await _users_by_ids(ids)
    ws = workspace_id or (rows[0].get("workspace_id") if rows else None)
    blocking = {}
    if ws:
        blocking = await _blocking_production_orders_by_request(
            ws, [r.get("id") for r in rows if r.get("id")],
        )
    return [
        await _enrich_procurement_request(r, users, blocking_by_request=blocking)
        for r in rows
    ]




def _procurement_queue_sort_key(req: dict) -> tuple:
    """Single source of truth for Procurement queue ordering.

    Precedence: blocking production → overdue → priority → oldest first.
    """
    blocking = 0 if req.get("blocking_production_orders") else 1
    overdue = 0 if _procurement_request_is_overdue(req) else 1
    priority_rank = {"high": 0, "normal": 1, "low": 2}
    pr = priority_rank.get((req.get("priority") or "normal"), 1)
    created = req.get("created_at") or ""
    return (blocking, overdue, pr, created)


def _procurement_request_is_overdue(req: dict, *, today=None) -> bool:
    if req.get("status") != "ordered":
        return False
    raw = (req.get("expected_delivery_date") or "").strip()
    if not raw:
        return False
    try:
        due = datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        return False
    today = today or datetime.now(timezone.utc).date()
    return due < today


def _normalize_expected_delivery_date(raw) -> str:
    """Optional YYYY-MM-DD (or empty). Rejects unparseable values."""
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    # Accept date-only or ISO datetime; store as YYYY-MM-DD.
    try:
        if "T" in s:
            s = s.split("T", 1)[0]
        datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="expected_delivery_date must be YYYY-MM-DD")
    return s[:10]

class ProcurementRequestCreate(BaseModel):
    item: str
    quantity: float = 1
    vendor_name: str = ""
    cost: Optional[float] = None
    notes: str = ""
    expected_delivery_date: str = ""
    priority: str = "normal"


class ProcurementRequestPatch(BaseModel):
    item: Optional[str] = None
    quantity: Optional[float] = None
    vendor_name: Optional[str] = None
    cost: Optional[float] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    expected_delivery_date: Optional[str] = None
    actual_delivery_date: Optional[str] = None
    priority: Optional[str] = None




@api_router.get("/procurement/vendor-suggestions")
async def procurement_vendor_suggestions(
    item: str = Query("", min_length=0),
    principal=Depends(get_principal),
):
    """Historical vendor memory for an item — no vendor entity, just past requests."""
    dept = await _procurement_department(principal)
    needle = (item or "").strip().lower()
    if len(needle) < 2:
        return {"suggestions": []}
    rows = await db.procurement_requests.find(
        {"department_id": dept["department_id"]},
        {
            "_id": 0, "item": 1, "vendor_name": 1, "cost": 1, "created_at": 1,
            "ordered_at": 1, "expected_delivery_date": 1, "actual_delivery_date": 1,
            "vendor_selected_at": 1,
        },
    ).sort("created_at", -1).to_list(2000)
    groups: dict[str, list] = {}
    for r in rows:
        it = str(r.get("item") or "").lower()
        if needle not in it:
            continue
        vendor = (r.get("vendor_name") or "").strip()
        if not vendor:
            continue
        groups.setdefault(vendor, []).append(r)
    suggestions = []
    for vendor, hist in groups.items():
        hist_sorted = sorted(hist, key=lambda x: x.get("created_at") or "", reverse=True)
        costs = []
        for h in hist_sorted:
            if h.get("cost") is not None:
                try:
                    costs.append(float(h["cost"]))
                except (TypeError, ValueError):
                    pass
        last = hist_sorted[0]
        last_cost = None
        if last.get("cost") is not None:
            try:
                last_cost = float(last["cost"])
            except (TypeError, ValueError):
                last_cost = None
        price_changed = False
        # Compare latest cost to the average of up to 3 prior orders (exclude last).
        prior_costs = costs[1:4]
        if last_cost is not None and prior_costs:
            avg = sum(prior_costs) / len(prior_costs)
            if avg > 0 and abs(last_cost - avg) / avg > 0.15:
                price_changed = True
        perf = proc_metrics.vendor_performance(hist_sorted)
        suggestions.append({
            "vendor_name": vendor,
            "last_cost": last_cost,
            "last_ordered_at": last.get("created_at") or "",
            "times_used": len(hist_sorted),
            "price_changed": price_changed,
            "avg_fulfillment_delay_days": perf["avg_fulfillment_delay_days"],
            "avg_fulfillment_days": perf["avg_fulfillment_days"],
            "delay_sample_count": perf["delay_sample_count"],
            "fulfillment_sample_count": perf["fulfillment_sample_count"],
        })
    suggestions.sort(key=lambda s: (s["times_used"], s.get("last_ordered_at") or ""), reverse=True)
    return {"suggestions": suggestions[:10]}


@api_router.get("/procurement/requests")
async def list_procurement_requests(
    principal=Depends(get_principal),
    status: Optional[str] = Query(None),
):
    dept = await _procurement_department(principal)
    status_key = (status or "").strip().lower() or "all"
    cache_key = _list_cache_key(
        "procurement", principal["workspace_id"], principal["user_id"],
        dept["department_id"], status_key,
    )
    cached = simple_cache.peek(cache_key)
    if cached is not None:
        return cached
    filt: dict = {"department_id": dept["department_id"]}
    if status is not None:
        st = status.strip().lower()
        if st not in PROCUREMENT_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status filter")
        filt["status"] = st
    rows = await db.procurement_requests.find(filt, {"_id": 0}).sort("created_at", -1).to_list(1000)
    rows = helm_freshness.annotate_possibly_stale(rows, dept_type=dept_catalog.TYPE_PROCUREMENT)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    is_lead = _can_lead_procurement(principal, membership)
    items = await _enrich_procurement_requests(
        rows, workspace_id=principal["workspace_id"],
    )
    items.sort(key=_procurement_queue_sort_key)
    # Best-effort backfill: delivered + priced requests should already have an
    # expense row. Idempotent — covers requests delivered before this wiring.
    for row in items:
        if row.get("status") != "delivered":
            continue
        if row.get("cost") is None or row.get("cost") == "":
            continue
        try:
            await _ensure_procurement_expense_entry(row, principal)
        except Exception:
            logger.exception(
                "procurement expense backfill failed for %s", row.get("id"),
            )
    lead_time_summary = proc_metrics.department_lead_time_summary(items)
    month_start, month_end = decision_engine.month_period_bounds()
    spend = proc_spend.spend_rollup(
        items,
        period_start=month_start,
        period_end=month_end,
        budget=dept.get("monthly_budget"),
        budget_entered=bool(dept.get("monthly_budget_entered")),
    )

    payload_out = {
        "department_id": dept["department_id"],
        "name": dept.get("name") or "Procurement",
        "requests": items,
        "statuses": ["requested", "approved", "ordered", "delivered", "rejected"],
        "priorities": ["low", "normal", "high"],
        "is_ceo": dept_access.is_workspace_ceo(principal),
        "is_lead": is_lead,
        "can_approve": is_lead,
        "my_user_id": principal["user_id"],
        "lead_time_summary": lead_time_summary,
        "spend": spend,
        "monthly_budget": dept.get("monthly_budget"),
        "monthly_budget_entered": bool(dept.get("monthly_budget_entered")),
    }
    simple_cache.put(cache_key, payload_out, _DEPT_LIST_CACHE_TTL_SECONDS)
    return payload_out


@api_router.post("/procurement/requests")
async def create_procurement_request(
    payload: ProcurementRequestCreate,
    principal=Depends(get_principal),
):
    dept = await _procurement_department(principal)
    item = (payload.item or "").strip()
    if not item:
        raise HTTPException(status_code=400, detail="Item is required")
    try:
        quantity = float(payload.quantity)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Quantity must be a number")
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be positive")
    cost = payload.cost
    if cost is not None:
        try:
            cost = round(float(cost), 2)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Cost must be a number")
        if cost < 0:
            raise HTTPException(status_code=400, detail="Cost must be non-negative")
    priority = (payload.priority or "normal").strip().lower() or "normal"
    if priority not in PROCUREMENT_PRIORITIES:
        raise HTTPException(status_code=400, detail="Invalid priority")
    now = datetime.now(timezone.utc).isoformat()
    vendor = (payload.vendor_name or "").strip()
    req = {
        "id": f"preq_{uuid.uuid4().hex[:10]}",
        "department_id": dept["department_id"],
        "workspace_id": principal["workspace_id"],
        "item": item,
        "quantity": quantity,
        "vendor_name": vendor,
        "cost": cost,
        "requested_by": principal["user_id"],
        "approved_by": None,
        "status": "requested",
        "notes": (payload.notes or "").strip(),
        "expected_delivery_date": _normalize_expected_delivery_date(payload.expected_delivery_date),
        "priority": priority,
        "vendor_selected_at": now if vendor else None,
        "ordered_at": None,
        "actual_delivery_date": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.procurement_requests.insert_one(dict(req))
    invalidate_workspace_list_cache(principal["workspace_id"], "procurement", "production", "me_work", "calendar")
    return {"ok": True, "request": await _enrich_procurement_request(req)}


@api_router.patch("/procurement/requests/{request_id}")
async def patch_procurement_request(
    request_id: str,
    payload: ProcurementRequestPatch,
    principal=Depends(get_principal),
):
    dept = await _procurement_department(principal)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    is_lead = _can_lead_procurement(principal, membership)
    req = await db.procurement_requests.find_one(
        {"id": request_id, "department_id": dept["department_id"]},
        {"_id": 0},
    )
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    is_owner = req.get("requested_by") == principal["user_id"]
    owner_can_edit_content = is_owner and req.get("status") == "requested"
    can_edit_content = is_lead or owner_can_edit_content

    upd: dict = {}
    content_touched = False

    if payload.item is not None:
        content_touched = True
        item = payload.item.strip()
        if not item:
            raise HTTPException(status_code=400, detail="Item is required")
        upd["item"] = item
    if payload.quantity is not None:
        content_touched = True
        try:
            quantity = float(payload.quantity)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Quantity must be a number")
        if quantity <= 0:
            raise HTTPException(status_code=400, detail="Quantity must be positive")
        upd["quantity"] = quantity
    if payload.vendor_name is not None:
        content_touched = True
        new_vendor = payload.vendor_name.strip()
        upd["vendor_name"] = new_vendor
        prev_vendor = (req.get("vendor_name") or "").strip()
        # One-time lock: stamp only on first empty→non-empty transition.
        if new_vendor and not prev_vendor and not req.get("vendor_selected_at"):
            upd["vendor_selected_at"] = datetime.now(timezone.utc).isoformat()
    if payload.cost is not None:
        content_touched = True
        try:
            cost = round(float(payload.cost), 2)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Cost must be a number")
        if cost < 0:
            raise HTTPException(status_code=400, detail="Cost must be non-negative")
        upd["cost"] = cost
    if payload.notes is not None:
        content_touched = True
        upd["notes"] = payload.notes.strip()
    if payload.priority is not None:
        content_touched = True
        pr = (payload.priority or "").strip().lower()
        if pr not in PROCUREMENT_PRIORITIES:
            raise HTTPException(status_code=400, detail="Invalid priority")
        upd["priority"] = pr
    if payload.expected_delivery_date is not None:
        # Delivery date is operational — leads can always set it; members may set
        # it while they still own the request (or alongside a status move below).
        upd["expected_delivery_date"] = _normalize_expected_delivery_date(payload.expected_delivery_date)
        if not can_edit_content and payload.status is None:
            raise HTTPException(
                status_code=403,
                detail="You can only edit expected delivery date on your own open requests",
            )
    if payload.actual_delivery_date is not None:
        if not is_lead:
            raise HTTPException(
                status_code=403,
                detail="Only a Procurement lead or the CEO can set the actual delivery date",
            )
        upd["actual_delivery_date"] = _normalize_expected_delivery_date(payload.actual_delivery_date) or None

    if content_touched and not can_edit_content:
        raise HTTPException(
            status_code=403,
            detail="You can only edit your own requests while they are still requested",
        )

    if payload.status is not None:
        new_status = payload.status.strip().lower()
        if new_status not in PROCUREMENT_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status")
        if new_status != req.get("status"):
            if new_status in PROCUREMENT_APPROVAL_STATUSES:
                if not is_lead:
                    raise HTTPException(
                        status_code=403,
                        detail="Only a Procurement lead or the CEO can approve or reject requests",
                    )
                upd["status"] = new_status
                if new_status == "approved":
                    upd["approved_by"] = principal["user_id"]
                # rejected leaves approved_by unchanged / None
            else:
                # ordered / delivered / back to requested — members may advance open work
                upd["status"] = new_status
                if new_status == "ordered" and not req.get("ordered_at"):
                    upd["ordered_at"] = datetime.now(timezone.utc).isoformat()
                    # If vendor is already set but never stamped, lock it in at order time.
                    if (req.get("vendor_name") or "").strip() and not req.get("vendor_selected_at"):
                        upd["vendor_selected_at"] = upd["ordered_at"]
                if new_status == "delivered" and not req.get("actual_delivery_date"):
                    upd["actual_delivery_date"] = datetime.now(timezone.utc).date().isoformat()

    helm_dept_drafts.apply_status_completion(req, upd, done_status="delivered")
    if not upd:
        return {"ok": True, "request": await _enrich_procurement_request(req)}

    upd["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.procurement_requests.update_one(
        {"id": request_id, "department_id": dept["department_id"]},
        {"$set": upd},
    )
    updated = {**req, **upd}
    financial_entry = None
    try:
        financial_entry, created = await _ensure_procurement_expense_entry(updated, principal)
        if financial_entry and created:
            currency = await _workspace_currency(principal["workspace_id"])
            await log_activity(
                principal, "financials", "entry.add",
                f"Logged expense from procurement · {financial_entry['name']} "
                f"{fmt_money(financial_entry['amount'], currency)} ({financial_entry['month']})",
                {
                    "type": "expense",
                    "amount": financial_entry["amount"],
                    "month": financial_entry["month"],
                    "source": "procurement",
                    "source_procurement_request_id": request_id,
                },
            )
    except Exception:
        logger.exception(
            "procurement expense sync failed for %s in workspace %s",
            request_id, principal.get("workspace_id"),
        )
    invalidate_workspace_list_cache(principal["workspace_id"], "procurement", "production", "me_work", "calendar")
    return {
        "ok": True,
        "request": await _enrich_procurement_request(updated),
        "financial_entry": financial_entry,
    }


@api_router.delete("/procurement/requests/{request_id}")
async def delete_procurement_request(request_id: str, principal=Depends(get_principal)):
    dept = await _procurement_department(principal)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    is_lead = _can_lead_procurement(principal, membership)
    req = await db.procurement_requests.find_one(
        {"id": request_id, "department_id": dept["department_id"]},
        {"_id": 0},
    )
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    is_owner = req.get("requested_by") == principal["user_id"]
    if is_lead:
        pass
    elif is_owner and req.get("status") == "requested":
        pass
    else:
        raise HTTPException(
            status_code=403,
            detail="Only the requester (while still requested) or a lead/CEO can delete this request",
        )
    invalidate_workspace_list_cache(principal["workspace_id"], "procurement", "production", "me_work", "calendar")
    await db.procurement_requests.delete_one(
        {"id": request_id, "department_id": dept["department_id"]},
    )
    return {"ok": True}


# ------------------------- Legal matter queue -------------------------
LEGAL_STATUSES = frozenset({
    "draft", "internal_review", "counterparty_review", "signed", "filed",
})
LEGAL_MEMBER_STATUSES = frozenset({"draft", "internal_review"})
LEGAL_LEAD_ONLY_STATUSES = frozenset({"counterparty_review", "signed", "filed"})
LEGAL_MATTER_TYPES = frozenset({"contract", "compliance", "other"})
LEGAL_RECURRENCE = frozenset({"annual", "quarterly", "monthly"})


async def _legal_department(principal: dict) -> dict:
    doc = await db.departments.find_one(
        {
            "workspace_id": principal["workspace_id"],
            "type": dept_catalog.TYPE_LEGAL,
            "enabled": True,
        },
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Legal department is not enabled")
    if not await dept_access.can_access_department(db, principal, doc):
        raise HTTPException(status_code=403, detail="You do not have access to Legal")
    return doc


def _can_lead_legal(principal: dict, membership: dict | None) -> bool:
    if dept_access.is_workspace_ceo(principal):
        return True
    return bool(membership) and membership.get("role") == "lead"


async def _enrich_legal_matter(matter: dict, users: dict | None = None) -> dict:
    out = {k: v for k, v in matter.items() if k != "_id"}
    uids = [out.get("assigned_to"), out.get("created_by")]
    lookup = users if users is not None else await _users_by_ids(uids)
    for field, label in (("assigned_to", "assignee"), ("created_by", "creator")):
        uid = out.get(field)
        info = None
        if uid:
            info = _user_card(uid, lookup.get(uid))
        out[label] = info
    doc_ref = out.get("document_ref")
    if isinstance(doc_ref, dict) and doc_ref.get("storage_key"):
        out["has_document"] = True
        out["document"] = {
            "filename": doc_ref.get("filename"),
            "content_type": doc_ref.get("content_type"),
            "uploaded_at": doc_ref.get("uploaded_at"),
            "document_id": doc_ref.get("document_id"),
        }
    else:
        out["has_document"] = False
        out["document"] = None
    return out


async def _enrich_legal_matters(rows: list) -> list:
    ids = []
    for r in rows:
        ids.append(r.get("assigned_to"))
        ids.append(r.get("created_by"))
    users = await _users_by_ids(ids)
    return [await _enrich_legal_matter(r, users) for r in rows]


def _normalize_optional_ymd(raw, *, field_name: str = "due_date") -> str:
    """Optional YYYY-MM-DD (or empty). Rejects unparseable values."""
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    try:
        if "T" in s:
            s = s.split("T", 1)[0]
        datetime.strptime(s[:10], "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} must be YYYY-MM-DD") from exc
    return s[:10]


def _normalize_legal_recurrence(raw, *, matter_type: str) -> Optional[str]:
    """Recurrence only applies to compliance matters; others store null."""
    if (matter_type or "").strip().lower() != "compliance":
        return None
    value = (raw or "").strip().lower()
    if not value:
        return None
    if value not in LEGAL_RECURRENCE:
        raise HTTPException(
            status_code=400,
            detail="recurrence must be annual, quarterly, monthly, or empty",
        )
    return value


def _advance_legal_due_date(due_date: str, recurrence: str) -> str:
    """Advance YYYY-MM-DD by the recurrence interval. Empty in → empty out."""
    raw = (due_date or "").strip()
    if not raw:
        return ""
    try:
        d = datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        return ""
    if recurrence == "annual":
        year, month, day = d.year + 1, d.month, d.day
    elif recurrence == "quarterly":
        month = d.month + 3
        year = d.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        day = d.day
    elif recurrence == "monthly":
        month = d.month + 1
        year = d.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        day = d.day
    else:
        return ""
    # Inline days-in-month — module name `calendar` is shadowed by a route helper.
    if month == 2:
        leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        dim = 29 if leap else 28
    elif month in (4, 6, 9, 11):
        dim = 30
    else:
        dim = 31
    day = min(day, dim)
    return date(year, month, day).isoformat()


async def _spawn_compliance_renewal(filed_matter: dict, principal: dict, dept: dict) -> Optional[dict]:
    """Create the next-cycle compliance matter once when a recurring matter is filed."""
    if (filed_matter.get("matter_type") or "").strip().lower() != "compliance":
        return None
    recurrence = filed_matter.get("recurrence")
    if recurrence not in LEGAL_RECURRENCE:
        return None
    matter_id = filed_matter.get("id")
    if not matter_id:
        return None
    if filed_matter.get("renewed_to_matter_id"):
        existing = await db.legal_matters.find_one(
            {"id": filed_matter["renewed_to_matter_id"], "department_id": dept["department_id"]},
            {"_id": 0},
        )
        return existing
    existing = await db.legal_matters.find_one(
        {"department_id": dept["department_id"], "renewed_from_matter_id": matter_id},
        {"_id": 0},
    )
    if existing:
        await db.legal_matters.update_one(
            {"id": matter_id, "department_id": dept["department_id"]},
            {"$set": {"renewed_to_matter_id": existing["id"]}},
        )
        return existing

    now = datetime.now(timezone.utc).isoformat()
    next_due = _advance_legal_due_date(filed_matter.get("due_date") or "", recurrence)
    child = {
        "id": f"lmat_{uuid.uuid4().hex[:10]}",
        "department_id": dept["department_id"],
        "workspace_id": principal["workspace_id"],
        "title": filed_matter.get("title") or "Compliance renewal",
        "matter_type": "compliance",
        "assigned_to": filed_matter.get("assigned_to") or principal["user_id"],
        "created_by": principal["user_id"],
        "status": "draft",
        "document_ref": None,
        "notes": "",
        "due_date": next_due,
        "recurrence": recurrence,
        "counterparty": (filed_matter.get("counterparty") or "").strip(),
        "renewed_from_matter_id": matter_id,
        "renewed_to_matter_id": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.legal_matters.insert_one(dict(child))
    await db.legal_matters.update_one(
        {"id": matter_id, "department_id": dept["department_id"]},
        {"$set": {"renewed_to_matter_id": child["id"]}},
    )
    child.pop("_id", None)
    return child


class LegalMatterCreate(BaseModel):
    title: str
    matter_type: str = "contract"
    assigned_to: Optional[str] = None
    notes: str = ""
    status: str = "draft"
    due_date: str = ""
    recurrence: Optional[str] = None
    counterparty: str = ""


class LegalMatterPatch(BaseModel):
    title: Optional[str] = None
    matter_type: Optional[str] = None
    assigned_to: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[str] = None
    recurrence: Optional[str] = None
    counterparty: Optional[str] = None


def _normalize_matter_type(raw: str) -> str:
    t = (raw or "other").strip().lower() or "other"
    if t in LEGAL_MATTER_TYPES:
        return t
    # Keep loose free-text but cap length
    return (raw or "other").strip()[:80] or "other"



@api_router.get("/legal/counterparty-suggestions")
async def legal_counterparty_suggestions(
    q: str = Query("", min_length=0),
    principal=Depends(get_principal),
):
    """Historical counterparty memory — distinct past values for this Legal department."""
    dept = await _legal_department(principal)
    needle = (q or "").strip().lower()
    if len(needle) < 1:
        return {"suggestions": []}
    rows = await db.legal_matters.find(
        {"department_id": dept["department_id"]},
        {"_id": 0, "counterparty": 1, "created_at": 1, "updated_at": 1},
    ).sort("created_at", -1).to_list(2000)
    groups: dict[str, list] = {}
    for r in rows:
        name = (r.get("counterparty") or "").strip()
        if not name:
            continue
        if needle not in name.lower():
            continue
        groups.setdefault(name, []).append(r)
    suggestions = []
    for name, hist in groups.items():
        hist_sorted = sorted(
            hist,
            key=lambda x: x.get("updated_at") or x.get("created_at") or "",
            reverse=True,
        )
        last = hist_sorted[0]
        suggestions.append({
            "counterparty": name,
            "matter_count": len(hist_sorted),
            "last_matter_date": (last.get("updated_at") or last.get("created_at") or "")[:10],
        })
    suggestions.sort(
        key=lambda s: (s["matter_count"], s.get("last_matter_date") or ""),
        reverse=True,
    )
    return {"suggestions": suggestions[:10]}


@api_router.get("/legal/matters")
async def list_legal_matters(
    principal=Depends(get_principal),
    status: Optional[str] = Query(None),
    counterparty: Optional[str] = Query(None),
):
    dept = await _legal_department(principal)
    status_key = (status or "").strip().lower() or "all"
    cp_key = (counterparty or "").strip().lower() or "all"
    cache_key = _list_cache_key(
        "legal", principal["workspace_id"], principal["user_id"],
        dept["department_id"], status_key, cp_key,
    )
    cached = simple_cache.peek(cache_key)
    if cached is not None:
        return cached
    filt: dict = {"department_id": dept["department_id"]}
    if status is not None:
        st = status.strip().lower()
        if st not in LEGAL_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status filter")
        filt["status"] = st
    if counterparty is not None:
        cp = counterparty.strip()
        if cp:
            filt["counterparty"] = cp
    rows = await db.legal_matters.find(filt, {"_id": 0}).sort("created_at", -1).to_list(1000)
    rows = helm_freshness.annotate_possibly_stale(rows, dept_type=dept_catalog.TYPE_LEGAL)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    is_lead = _can_lead_legal(principal, membership)
    items = await _enrich_legal_matters(rows)
    payload_out = {
        "department_id": dept["department_id"],
        "name": dept.get("name") or "Legal",
        "matters": items,
        "statuses": ["draft", "internal_review", "counterparty_review", "signed", "filed"],
        "matter_types": sorted(LEGAL_MATTER_TYPES),
        "recurrence_options": sorted(LEGAL_RECURRENCE),
        "is_ceo": dept_access.is_workspace_ceo(principal),
        "is_lead": is_lead,
        "can_reassign": is_lead,
        "can_advance_past_review": is_lead,
        "can_delete": is_lead,
        "my_user_id": principal["user_id"],
    }
    simple_cache.put(cache_key, payload_out, _DEPT_LIST_CACHE_TTL_SECONDS)
    return payload_out


@api_router.post("/legal/matters")
async def create_legal_matter(payload: LegalMatterCreate, principal=Depends(get_principal)):
    dept = await _legal_department(principal)
    title = (payload.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    status = (payload.status or "draft").strip().lower()
    if status not in LEGAL_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    is_lead = _can_lead_legal(principal, membership)
    if status in LEGAL_LEAD_ONLY_STATUSES and not is_lead:
        raise HTTPException(
            status_code=403,
            detail="Only a Legal lead or the CEO can set this status",
        )
    assigned_to = (payload.assigned_to or "").strip() or principal["user_id"]
    now = datetime.now(timezone.utc).isoformat()
    matter = {
        "id": f"lmat_{uuid.uuid4().hex[:10]}",
        "department_id": dept["department_id"],
        "workspace_id": principal["workspace_id"],
        "title": title,
        "matter_type": _normalize_matter_type(payload.matter_type),
        "assigned_to": assigned_to,
        "created_by": principal["user_id"],
        "status": status if status in LEGAL_MEMBER_STATUSES or is_lead else "draft",
        "document_ref": None,
        "notes": (payload.notes or "").strip(),
        "due_date": _normalize_optional_ymd(payload.due_date, field_name="due_date"),
        "counterparty": (payload.counterparty or "").strip()[:200],
        "recurrence": None,
        "renewed_from_matter_id": None,
        "renewed_to_matter_id": None,
        "created_at": now,
        "updated_at": now,
    }
    matter["recurrence"] = _normalize_legal_recurrence(
        payload.recurrence, matter_type=matter["matter_type"],
    )
    if matter["status"] == "filed":
        matter["completed_at"] = now
    await db.legal_matters.insert_one(dict(matter))
    invalidate_workspace_list_cache(principal["workspace_id"], "legal", "me_work", "calendar")
    return {"ok": True, "matter": await _enrich_legal_matter(matter)}


@api_router.patch("/legal/matters/{matter_id}")
async def patch_legal_matter(
    matter_id: str,
    payload: LegalMatterPatch,
    principal=Depends(get_principal),
):
    dept = await _legal_department(principal)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    is_lead = _can_lead_legal(principal, membership)
    matter = await db.legal_matters.find_one(
        {"id": matter_id, "department_id": dept["department_id"]},
        {"_id": 0},
    )
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")

    is_assignee = matter.get("assigned_to") == principal["user_id"]
    can_update = is_lead or is_assignee
    if not can_update:
        raise HTTPException(status_code=403, detail="You can only update matters assigned to you")

    upd: dict = {}
    if payload.title is not None:
        title = payload.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="Title is required")
        upd["title"] = title
    if payload.matter_type is not None:
        upd["matter_type"] = _normalize_matter_type(payload.matter_type)
    if payload.notes is not None:
        upd["notes"] = payload.notes.strip()
    if payload.due_date is not None:
        upd["due_date"] = _normalize_optional_ymd(payload.due_date, field_name="due_date")
    if payload.counterparty is not None:
        upd["counterparty"] = payload.counterparty.strip()[:200]

    if payload.assigned_to is not None:
        new_assignee = (payload.assigned_to or "").strip() or None
        if new_assignee != matter.get("assigned_to"):
            if not is_lead:
                raise HTTPException(
                    status_code=403,
                    detail="Only a Legal lead or the CEO can reassign a matter",
                )
            upd["assigned_to"] = new_assignee

    if payload.status is not None:
        new_status = payload.status.strip().lower()
        if new_status not in LEGAL_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status")
        if new_status != matter.get("status"):
            if new_status in LEGAL_LEAD_ONLY_STATUSES and not is_lead:
                raise HTTPException(
                    status_code=403,
                    detail="Only a Legal lead or the CEO can advance past internal review",
                )
            if not is_lead and new_status not in LEGAL_MEMBER_STATUSES:
                raise HTTPException(status_code=403, detail="Invalid status for your role")
            upd["status"] = new_status

    # Resolve recurrence against the post-patch matter type.
    next_type = upd.get("matter_type", matter.get("matter_type") or "other")
    if payload.recurrence is not None or "matter_type" in upd:
        raw_rec = payload.recurrence if payload.recurrence is not None else matter.get("recurrence")
        upd["recurrence"] = _normalize_legal_recurrence(raw_rec, matter_type=next_type)

    helm_dept_drafts.apply_status_completion(matter, upd, done_status="filed")
    if not upd:
        return {"ok": True, "matter": await _enrich_legal_matter(matter)}

    becoming_filed = upd.get("status") == "filed" and matter.get("status") != "filed"
    upd["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.legal_matters.update_one(
        {"id": matter_id, "department_id": dept["department_id"]},
        {"$set": upd},
    )
    invalidate_workspace_list_cache(principal["workspace_id"], "legal", "me_work", "calendar")
    updated = {**matter, **upd}
    renewal = None
    if becoming_filed:
        renewal = await _spawn_compliance_renewal(updated, principal, dept)
        if renewal and renewal.get("id"):
            updated["renewed_to_matter_id"] = renewal["id"]
    out = {"ok": True, "matter": await _enrich_legal_matter(updated)}
    if renewal:
        out["renewal_matter"] = await _enrich_legal_matter(renewal)
    return out


@api_router.post("/legal/matters/{matter_id}/document")
async def upload_legal_matter_document(
    matter_id: str,
    file: UploadFile = File(...),
    principal=Depends(get_principal),
):
    """Attach or replace a document on a legal matter using R2 storage."""
    dept = await _legal_department(principal)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    is_lead = _can_lead_legal(principal, membership)
    matter = await db.legal_matters.find_one(
        {"id": matter_id, "department_id": dept["department_id"]},
        {"_id": 0},
    )
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")
    is_assignee = matter.get("assigned_to") == principal["user_id"]
    if not (is_lead or is_assignee):
        raise HTTPException(status_code=403, detail="You can only attach documents to matters assigned to you")

    if file.content_type not in ALLOWED_DOC_TYPES:
        raise HTTPException(status_code=400, detail="File type not allowed. Upload PDF, PNG, or JPEG.")
    data = await _read_validated_document(file)
    if not doc_storage.r2_configured():
        raise HTTPException(status_code=503, detail="Document storage is not configured")

    filename = (file.filename or "document").replace("/", "_").replace("\\", "_")[:200]
    try:
        storage_key = await asyncio.to_thread(
            doc_storage.upload_document,
            principal["workspace_id"], data, filename, file.content_type,
        )
    except Exception as exc:
        logger.exception("legal matter document upload failed")
        raise HTTPException(status_code=500, detail="Could not store document") from exc

    # Best-effort cleanup of previous file
    old_ref = matter.get("document_ref") or {}
    old_key = old_ref.get("storage_key") if isinstance(old_ref, dict) else None
    if old_key and old_key != storage_key and doc_storage.r2_configured():
        try:
            await asyncio.to_thread(doc_storage.delete_document, old_key)
        except Exception:
            logger.exception("failed to delete previous legal matter document %s", old_key)

    now = datetime.now(timezone.utc).isoformat()
    doc_id = f"ldoc_{uuid.uuid4().hex[:12]}"
    document_ref = {
        "document_id": doc_id,
        "storage_key": storage_key,
        "filename": filename,
        "content_type": file.content_type,
        "uploaded_by": principal["user_id"],
        "uploaded_at": now,
    }
    await db.legal_matters.update_one(
        {"id": matter_id, "department_id": dept["department_id"]},
        {"$set": {"document_ref": document_ref, "updated_at": now}},
    )
    updated = {**matter, "document_ref": document_ref, "updated_at": now}
    return {"ok": True, "matter": await _enrich_legal_matter(updated)}


@api_router.get("/legal/matters/{matter_id}/document")
async def get_legal_matter_document(
    matter_id: str,
    background_tasks: BackgroundTasks,
    principal=Depends(get_principal),
):
    """Return metadata + presigned URL for the matter's current document.

    Same access bar as upload: Legal department access plus lead or assignee.
    """
    dept = await _legal_department(principal)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    is_lead = _can_lead_legal(principal, membership)
    matter = await db.legal_matters.find_one(
        {"id": matter_id, "department_id": dept["department_id"]},
        {"_id": 0},
    )
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")
    is_assignee = matter.get("assigned_to") == principal["user_id"]
    if not (is_lead or is_assignee):
        raise HTTPException(
            status_code=403,
            detail="You can only open documents on matters assigned to you",
        )
    doc_ref = matter.get("document_ref")
    if not isinstance(doc_ref, dict) or not doc_ref.get("storage_key"):
        raise HTTPException(status_code=404, detail="No document attached")
    if not doc_storage.r2_configured():
        raise HTTPException(status_code=503, detail="Document storage is not configured")
    try:
        presigned_url = await asyncio.to_thread(
            doc_storage.get_presigned_url, doc_ref["storage_key"],
        )
    except Exception as exc:
        logger.exception("presigned url failed for legal matter %s", matter_id)
        raise HTTPException(status_code=500, detail="Could not generate download URL") from exc
    background_tasks.add_task(
        _audit_document_access,
        principal,
        "legal",
        "document.download",
        f"Opened legal document · {doc_ref.get('filename') or matter_id}",
        {"matter_id": matter_id, "document_id": doc_ref.get("document_id")},
    )
    return {
        "document_id": doc_ref.get("document_id"),
        "filename": doc_ref.get("filename"),
        "content_type": doc_ref.get("content_type"),
        "uploaded_at": doc_ref.get("uploaded_at"),
        "presigned_url": presigned_url,
    }


@api_router.delete("/legal/matters/{matter_id}")
async def delete_legal_matter(matter_id: str, principal=Depends(get_principal)):
    dept = await _legal_department(principal)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    if not _can_lead_legal(principal, membership):
        raise HTTPException(status_code=403, detail="Only a Legal lead or the CEO can delete matters")
    matter = await db.legal_matters.find_one(
        {"id": matter_id, "department_id": dept["department_id"]},
        {"_id": 0},
    )
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")
    doc_ref = matter.get("document_ref") or {}
    storage_key = doc_ref.get("storage_key") if isinstance(doc_ref, dict) else None
    await db.legal_matters.delete_one(
        {"id": matter_id, "department_id": dept["department_id"]},
    )
    invalidate_workspace_list_cache(principal["workspace_id"], "legal", "me_work", "calendar")
    if storage_key and doc_storage.r2_configured():
        try:
            await asyncio.to_thread(doc_storage.delete_document, storage_key)
        except Exception:
            logger.exception("failed to delete legal matter document %s", storage_key)
    return {"ok": True}


# ------------------------- Engineering & Maintenance ticket queue -------------------------
MAINTENANCE_STATUSES = frozenset({"reported", "diagnosed", "in_repair", "resolved"})
MAINTENANCE_PRIORITIES = frozenset({"low", "medium", "high"})
_MAINT_PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


async def _maintenance_department(principal: dict) -> dict:
    doc = await db.departments.find_one(
        {
            "workspace_id": principal["workspace_id"],
            "type": dept_catalog.TYPE_ENGINEERING_MAINTENANCE,
            "enabled": True,
        },
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(
            status_code=404,
            detail="Engineering & Maintenance department is not enabled",
        )
    if not await dept_access.can_access_department(db, principal, doc):
        raise HTTPException(
            status_code=403,
            detail="You do not have access to Engineering & Maintenance",
        )
    return doc


def _can_lead_maintenance(principal: dict, membership: dict | None) -> bool:
    if dept_access.is_workspace_ceo(principal):
        return True
    return bool(membership) and membership.get("role") == "lead"


async def _blocking_production_orders_by_maintenance_ticket(
    workspace_id: str,
    ticket_ids: list[str],
) -> dict[str, list]:
    """Live lookup: maintenance ticket id → blocked production work orders."""
    ids = [tid for tid in ticket_ids if tid]
    if not ids or not workspace_id:
        return {}
    rows = await db.production_work_orders.find(
        {
            "workspace_id": workspace_id,
            "linked_maintenance_ticket_id": {"$in": ids},
            "blocked": True,
        },
        {
            "_id": 0,
            "id": 1,
            "reference": 1,
            "due_date": 1,
            "linked_maintenance_ticket_id": 1,
            "blocked": 1,
        },
    ).to_list(2000)
    by_ticket: dict[str, list] = {}
    for wo in rows:
        if not wo.get("blocked"):
            continue
        tid = wo.get("linked_maintenance_ticket_id")
        if not tid:
            continue
        by_ticket.setdefault(tid, []).append(_blocking_production_order_entry(wo))
    return by_ticket


async def _enrich_maintenance_ticket(
    ticket: dict,
    users: dict | None = None,
    *,
    blocking_by_ticket: dict | None = None,
    reliability_by_name: dict | None = None,
) -> dict:
    out = {k: v for k, v in ticket.items() if k != "_id"}
    uids = [out.get("reported_by"), out.get("assigned_technician")]
    lookup = users if users is not None else await _users_by_ids(uids)
    for field, label in (("reported_by", "reporter"), ("assigned_technician", "technician")):
        uid = out.get(field)
        info = None
        if uid:
            info = _user_card(uid, lookup.get(uid))
        out[label] = info
    tid = out.get("id")
    if blocking_by_ticket is not None:
        out["blocking_production_orders"] = list(blocking_by_ticket.get(tid) or [])
    else:
        ws = out.get("workspace_id")
        if ws and tid:
            mapping = await _blocking_production_orders_by_maintenance_ticket(ws, [tid])
            out["blocking_production_orders"] = list(mapping.get(tid) or [])
        else:
            out["blocking_production_orders"] = []
    eq_key = decision_engine._equipment_name_key(out.get("equipment_name"))
    rel = (reliability_by_name or {}).get(eq_key) if eq_key else None
    out["recent_repairs_90d"] = int(rel["ticket_count_90d"]) if rel else 0
    out["is_chronic_equipment"] = bool(rel["is_chronic"]) if rel else False
    return out


async def _enrich_maintenance_tickets(rows: list, workspace_id: str | None = None) -> list:
    ids = []
    for r in rows:
        ids.append(r.get("reported_by"))
        ids.append(r.get("assigned_technician"))
    users = await _users_by_ids(ids)
    ws = workspace_id or (rows[0].get("workspace_id") if rows else None)
    blocking = {}
    if ws:
        blocking = await _blocking_production_orders_by_maintenance_ticket(
            ws, [r.get("id") for r in rows if r.get("id")],
        )
    reliability = decision_engine.equipment_reliability_by_name(rows)
    return [
        await _enrich_maintenance_ticket(
            r, users, blocking_by_ticket=blocking, reliability_by_name=reliability,
        )
        for r in rows
    ]


def _sort_maintenance_tickets(rows: list) -> list:
    """Blocking production first, then unresolved, then high → medium → low, then oldest."""
    def key(t):
        blocking = 0 if t.get("blocking_production_orders") else 1
        resolved = 1 if t.get("status") == "resolved" else 0
        pri = _MAINT_PRIORITY_RANK.get(t.get("priority") or "medium", 9)
        created = t.get("created_at") or ""
        return (blocking, resolved, pri, created)

    return sorted(rows, key=key)


class MaintenanceTicketCreate(BaseModel):
    equipment_name: str
    description: str = ""
    priority: str = "medium"
    notes: str = ""
    assigned_technician: Optional[str] = None


class MaintenanceTicketPatch(BaseModel):
    equipment_name: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    assigned_technician: Optional[str] = None
    cost: Optional[float] = None


@api_router.get("/maintenance/tickets")
async def list_maintenance_tickets(
    principal=Depends(get_principal),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
):
    dept = await _maintenance_department(principal)
    status_key = (status or "").strip().lower() or "all"
    pri_key = (priority or "").strip().lower() or "all"
    cache_key = _list_cache_key(
        "maintenance", principal["workspace_id"], principal["user_id"],
        dept["department_id"], status_key, pri_key,
    )
    cached = simple_cache.peek(cache_key)
    if cached is not None:
        return cached
    filt: dict = {"department_id": dept["department_id"]}
    if status is not None:
        st = status.strip().lower()
        if st not in MAINTENANCE_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status filter")
        filt["status"] = st
    if priority is not None:
        pr = priority.strip().lower()
        if pr not in MAINTENANCE_PRIORITIES:
            raise HTTPException(status_code=400, detail="Invalid priority filter")
        filt["priority"] = pr
    rows = await db.maintenance_tickets.find(filt, {"_id": 0}).to_list(1000)
    rows = helm_freshness.annotate_possibly_stale(
        rows, dept_type=dept_catalog.TYPE_ENGINEERING_MAINTENANCE,
    )
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    is_lead = _can_lead_maintenance(principal, membership)
    items = await _enrich_maintenance_tickets(
        rows, workspace_id=principal["workspace_id"],
    )
    items = _sort_maintenance_tickets(items)
    month_start, month_end = decision_engine.month_period_bounds()
    downtime = decision_engine.compute_downtime(
        rows, period_start=month_start, period_end=month_end,
    )
    # Operational rollups (spares / schedules / contracts / overhead).
    spare_rows = await db.maintenance_spares.find(
        {"department_id": dept["department_id"]}, {"_id": 0},
    ).to_list(2000)
    below = maint_ops.spares_below_threshold(spare_rows)
    sched_rows = await db.maintenance_schedules.find(
        {"department_id": dept["department_id"]}, {"_id": 0},
    ).to_list(2000)
    overdue_sched = maint_ops.overdue_schedules(sched_rows)
    contract_rows = await db.maintenance_contracts.find(
        {"department_id": dept["department_id"]}, {"_id": 0},
    ).to_list(2000)
    needing_renewal = maint_ops.contracts_needing_attention(contract_rows)
    # Overhead: ticket costs resolved this month + ledger.
    resolved_month = await db.maintenance_tickets.find(
        {
            "department_id": dept["department_id"],
            "status": "resolved",
            "$or": [
                {"resolved_at": {"$gte": month_start.isoformat(), "$lt": month_end.isoformat()}},
                {
                    "resolved_at": {"$exists": False},
                    "updated_at": {"$gte": month_start.isoformat(), "$lt": month_end.isoformat()},
                },
            ],
        },
        {"_id": 0, "cost": 1},
    ).to_list(5000)
    ticket_costs = []
    for t in resolved_month:
        if t.get("cost") is None:
            continue
        try:
            ticket_costs.append(float(t["cost"]))
        except (TypeError, ValueError):
            pass
    ledger = await db.maintenance_costs.find(
        {"department_id": dept["department_id"], "month": month_start.strftime("%Y-%m")},
        {"_id": 0, "amount": 1},
    ).to_list(2000)
    ledger_costs = []
    for row in ledger:
        try:
            ledger_costs.append(float(row.get("amount") or 0))
        except (TypeError, ValueError):
            pass
    overhead = maint_ops.overhead_rollup(
        ticket_costs=ticket_costs,
        ledger_costs=ledger_costs,
        budget=dept.get("monthly_budget"),
        budget_entered=bool(dept.get("monthly_budget_entered")),
    )
    overhead["period"] = month_start.strftime("%Y-%m")
    overhead["period_label"] = month_start.strftime("%B %Y")
    payload_out = {
        "department_id": dept["department_id"],
        "name": dept.get("name") or "Engineering & Maintenance",
        "tickets": items,
        "statuses": ["reported", "diagnosed", "in_repair", "resolved"],
        "priorities": ["low", "medium", "high"],
        "downtime_summary": {
            **downtime,
            "period": month_start.strftime("%Y-%m"),
            "period_label": month_start.strftime("%B %Y"),
        },
        "spares_below_threshold_count": len(below),
        "spares_below_threshold": below[:20],
        "overdue_schedules_count": len(overdue_sched),
        "overdue_schedules": overdue_sched[:20],
        "contracts_needing_renewal_count": len(needing_renewal),
        "contracts_needing_renewal": needing_renewal[:20],
        "overhead": overhead,
        "is_ceo": dept_access.is_workspace_ceo(principal),
        "is_lead": is_lead,
        "can_assign": is_lead,
        "can_delete": is_lead,
        "my_user_id": principal["user_id"],
    }
    simple_cache.put(cache_key, payload_out, _DEPT_LIST_CACHE_TTL_SECONDS)
    return payload_out


@api_router.get("/maintenance/equipment-history")
async def maintenance_equipment_history(
    equipment_name: str = Query(""),
    principal=Depends(get_principal),
):
    """Exact-match (case-insensitive) repair history for one equipment name."""
    dept = await _maintenance_department(principal)
    needle = (equipment_name or "").strip()
    if not needle:
        return decision_engine.build_equipment_history([], "")
    # Filter in Mongo so live typeahead does not scan the whole department.
    rows = await db.maintenance_tickets.find(
        {
            "department_id": dept["department_id"],
            "equipment_name": {
                "$regex": f"^{re.escape(needle)}$",
                "$options": "i",
            },
        },
        {
            "_id": 0,
            "id": 1,
            "equipment_name": 1,
            "description": 1,
            "status": 1,
            "priority": 1,
            "created_at": 1,
            "updated_at": 1,
            "completed_at": 1,
        },
    ).to_list(2000)
    return decision_engine.build_equipment_history(rows, needle)


@api_router.post("/maintenance/tickets")
async def create_maintenance_ticket(
    payload: MaintenanceTicketCreate,
    principal=Depends(get_principal),
):
    dept = await _maintenance_department(principal)
    equipment = (payload.equipment_name or "").strip()
    if not equipment:
        raise HTTPException(status_code=400, detail="Equipment name is required")
    priority = (payload.priority or "medium").strip().lower()
    if priority not in MAINTENANCE_PRIORITIES:
        raise HTTPException(status_code=400, detail="Invalid priority")
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    is_lead = _can_lead_maintenance(principal, membership)
    assigned = None
    if is_lead and payload.assigned_technician is not None:
        assigned = (payload.assigned_technician or "").strip() or None
    now = datetime.now(timezone.utc).isoformat()
    ticket = {
        "id": f"mtkt_{uuid.uuid4().hex[:10]}",
        "department_id": dept["department_id"],
        "workspace_id": principal["workspace_id"],
        "equipment_name": equipment,
        "description": (payload.description or "").strip(),
        "reported_by": principal["user_id"],
        "assigned_technician": assigned,
        "priority": priority,
        "status": "reported",
        "notes": (payload.notes or "").strip(),
        "created_at": now,
        "updated_at": now,
    }
    await db.maintenance_tickets.insert_one(dict(ticket))
    invalidate_workspace_list_cache(principal["workspace_id"], "maintenance", "production", "me_work", "calendar")
    return {"ok": True, "ticket": await _enrich_maintenance_ticket(ticket)}


@api_router.patch("/maintenance/tickets/{ticket_id}")
async def patch_maintenance_ticket(
    ticket_id: str,
    payload: MaintenanceTicketPatch,
    principal=Depends(get_principal),
):
    dept = await _maintenance_department(principal)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    is_lead = _can_lead_maintenance(principal, membership)
    ticket = await db.maintenance_tickets.find_one(
        {"id": ticket_id, "department_id": dept["department_id"]},
        {"_id": 0},
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    is_tech = ticket.get("assigned_technician") == principal["user_id"]
    can_update = is_lead or is_tech
    if not can_update:
        raise HTTPException(
            status_code=403,
            detail="You can only update tickets assigned to you",
        )

    upd: dict = {}
    if payload.equipment_name is not None:
        name = payload.equipment_name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Equipment name is required")
        upd["equipment_name"] = name
    if payload.description is not None:
        upd["description"] = payload.description.strip()
    if payload.notes is not None:
        upd["notes"] = payload.notes.strip()
    if payload.priority is not None:
        pr = payload.priority.strip().lower()
        if pr not in MAINTENANCE_PRIORITIES:
            raise HTTPException(status_code=400, detail="Invalid priority")
        upd["priority"] = pr
    if payload.status is not None:
        st = payload.status.strip().lower()
        if st not in MAINTENANCE_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status")
        upd["status"] = st
    if payload.cost is not None:
        try:
            cost = float(payload.cost)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="cost must be a number")
        if cost < 0:
            raise HTTPException(status_code=400, detail="cost cannot be negative")
        upd["cost"] = round(cost, 2)
    helm_dept_drafts.apply_status_completion(ticket, upd, done_status="resolved")

    if payload.assigned_technician is not None:
        new_tech = (payload.assigned_technician or "").strip() or None
        if new_tech != ticket.get("assigned_technician"):
            if not is_lead:
                raise HTTPException(
                    status_code=403,
                    detail="Only a lead or the CEO can assign a technician",
                )
            upd["assigned_technician"] = new_tech

    if not upd:
        return {"ok": True, "ticket": await _enrich_maintenance_ticket(ticket)}

    # Stamp resolved_at when transitioning to resolved (for overhead month rollups).
    becoming_resolved = (
        upd.get("status") == "resolved" and ticket.get("status") != "resolved"
    )
    if becoming_resolved and "resolved_at" not in upd:
        upd["resolved_at"] = datetime.now(timezone.utc).isoformat()

    upd["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.maintenance_tickets.update_one(
        {"id": ticket_id, "department_id": dept["department_id"]},
        {"$set": upd},
    )

    # Best-effort: resolving a ticket updates matching schedule last_done_at.
    if becoming_resolved:
        try:
            eq_name = (upd.get("equipment_name") or ticket.get("equipment_name") or "").strip()
            if eq_name:
                done_at = upd.get("resolved_at") or upd.get("updated_at")
                await db.maintenance_schedules.update_many(
                    {
                        "department_id": dept["department_id"],
                        "equipment_name": {
                            "$regex": f"^{re.escape(eq_name)}$",
                            "$options": "i",
                        },
                    },
                    {"$set": {"last_done_at": done_at, "updated_at": upd["updated_at"]}},
                )
        except Exception:
            logger.exception(
                "schedule auto-update failed for ticket %s", ticket_id,
            )

    invalidate_workspace_list_cache(principal["workspace_id"], "maintenance", "production", "me_work", "calendar")
    return {"ok": True, "ticket": await _enrich_maintenance_ticket({**ticket, **upd})}


@api_router.delete("/maintenance/tickets/{ticket_id}")
async def delete_maintenance_ticket(ticket_id: str, principal=Depends(get_principal)):
    dept = await _maintenance_department(principal)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    if not _can_lead_maintenance(principal, membership):
        raise HTTPException(
            status_code=403,
            detail="Only a lead or the CEO can delete tickets",
        )
    result = await db.maintenance_tickets.delete_one(
        {"id": ticket_id, "department_id": dept["department_id"]},
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Ticket not found")
    invalidate_workspace_list_cache(principal["workspace_id"], "maintenance", "production", "me_work", "calendar")
    return {"ok": True}


# ------------------------- HR onboarding / employees / offboarding -------------------------
HR_DEFAULT_TEMPLATE_STEPS = ("Offer", "Paperwork", "Orientation", "Active")
HR_DEFAULT_OFFBOARDING_STEPS = (
    "Revoke Trenston/system access",
    "Collect company equipment",
    "Process final pay",
    "Conduct exit interview",
    "Update employee status to departed",
)
HR_STEP_STATUSES = frozenset({"not_started", "in_progress", "done"})
HR_OVERALL_STATUSES = frozenset({"in_progress", "active"})
HR_EMPLOYEE_STATUSES = frozenset({"active", "on_leave", "departed"})


async def _hr_department(principal: dict) -> dict:
    doc = await db.departments.find_one(
        {
            "workspace_id": principal["workspace_id"],
            "type": dept_catalog.TYPE_HR,
            "enabled": True,
        },
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="HR department is not enabled")
    if not await dept_access.can_access_department(db, principal, doc):
        raise HTTPException(status_code=403, detail="You do not have access to HR")
    return doc


def _can_lead_hr(principal: dict, membership: dict | None) -> bool:
    if dept_access.is_workspace_ceo(principal):
        return True
    return bool(membership) and membership.get("role") == "lead"


def _default_hr_template_steps() -> list[dict]:
    return [
        {"id": f"hstep_{uuid.uuid4().hex[:8]}", "name": name, "order": i}
        for i, name in enumerate(HR_DEFAULT_TEMPLATE_STEPS)
    ]


def _default_hr_offboarding_steps() -> list[dict]:
    return [
        {"id": f"hofstep_{uuid.uuid4().hex[:8]}", "name": name, "order": i}
        for i, name in enumerate(HR_DEFAULT_OFFBOARDING_STEPS)
    ]


async def _ensure_hr_onboarding_template(workspace_id: str, department_id: str) -> dict:
    """Return existing template or create the default Offer→…→Active checklist."""
    existing = await db.hr_onboarding_template.find_one(
        {"department_id": department_id},
        {"_id": 0},
    )
    if existing:
        return existing
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": f"hrtpl_{uuid.uuid4().hex[:10]}",
        "department_id": department_id,
        "workspace_id": workspace_id,
        "steps": _default_hr_template_steps(),
        "created_at": now,
        "updated_at": now,
    }
    await db.hr_onboarding_template.insert_one(dict(doc))
    return doc


async def _ensure_hr_offboarding_template(workspace_id: str, department_id: str) -> dict:
    """Return existing offboarding template or create the default checklist."""
    existing = await db.hr_offboarding_template.find_one(
        {"department_id": department_id},
        {"_id": 0},
    )
    if existing:
        return existing
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": f"hoftpl_{uuid.uuid4().hex[:10]}",
        "department_id": department_id,
        "workspace_id": workspace_id,
        "steps": _default_hr_offboarding_steps(),
        "created_at": now,
        "updated_at": now,
    }
    await db.hr_offboarding_template.insert_one(dict(doc))
    return doc


def _derive_overall_status(steps: list) -> str:
    if steps and all((s.get("status") == "done") for s in steps):
        return "active"
    return "in_progress"


async def _ensure_employee_from_onboarding(
    inst: dict, principal: dict,
) -> tuple[Optional[dict], bool]:
    """Create at most one hr_employees row when onboarding completes (overall=active).

    Duplicate-guarded by source_onboarding_instance_id (same pattern as won-deal
    → financial_entries via source_deal_id). Never stores sensitive HR fields.
    """
    instance_id = inst.get("id")
    department_id = inst.get("department_id")
    if not instance_id or not department_id:
        return None, False
    existing = await db.hr_employees.find_one(
        {
            "department_id": department_id,
            "source_onboarding_instance_id": instance_id,
        },
        {"_id": 0},
    )
    if existing:
        return existing, False

    now = datetime.now(timezone.utc).isoformat()
    name = (inst.get("hire_name") or "").strip() or "Employee"
    emp = {
        "id": f"hremp_{uuid.uuid4().hex[:10]}",
        "department_id": department_id,
        "workspace_id": inst.get("workspace_id") or principal["workspace_id"],
        "name": name[:200],
        "role": "",
        "start_date": now[:10],
        "status": "active",
        "manager_user_id": None,
        "linked_user_id": None,
        "department_names": "",
        "source_onboarding_instance_id": instance_id,
        "created_at": now,
        "updated_at": now,
        "departed_at": None,
    }
    try:
        await db.hr_employees.insert_one(dict(emp))
    except Exception as exc:
        msg = str(exc).lower()
        if "duplicate" in msg or "e11000" in msg:
            existing = await db.hr_employees.find_one(
                {
                    "department_id": department_id,
                    "source_onboarding_instance_id": instance_id,
                },
                {"_id": 0},
            )
            return existing, False
        raise
    invalidate_workspace_list_cache(principal["workspace_id"], "hr", "me_work", "people")
    emp.pop("_id", None)
    return emp, True


async def _mark_employee_departed(employee_id: str, department_id: str, now: str) -> None:
    await db.hr_employees.update_one(
        {"id": employee_id, "department_id": department_id},
        {"$set": {"status": "departed", "departed_at": now, "updated_at": now}},
    )


def _public_hr_employee(row: dict) -> dict:
    """Strip internal Mongo id; never expose sensitive employment data (none stored)."""
    return {k: v for k, v in row.items() if k != "_id"}


async def _enrich_hr_instance(inst: dict, users: dict | None = None) -> dict:
    out = {k: v for k, v in inst.items() if k != "_id"}
    step_uids = [(s or {}).get("assigned_to") for s in (out.get("steps") or [])]
    lookup = users if users is not None else await _users_by_ids(step_uids)
    steps = []
    for step in out.get("steps") or []:
        s = dict(step)
        uid = s.get("assigned_to")
        assignee = None
        if uid:
            assignee = _user_card(uid, lookup.get(uid))
        s["assignee"] = assignee
        steps.append(s)
    out["steps"] = steps
    done = sum(1 for s in steps if s.get("status") == "done")
    out["progress"] = {"done": done, "total": len(steps)}
    return out


async def _enrich_hr_instances(rows: list) -> list:
    ids = []
    for inst in rows:
        for step in inst.get("steps") or []:
            ids.append((step or {}).get("assigned_to"))
    users = await _users_by_ids(ids)
    return [await _enrich_hr_instance(r, users) for r in rows]


def _sort_hr_instances(rows: list) -> list:
    """In-progress first, then newest."""
    def key(r):
        closed = 1 if r.get("overall_status") == "active" else 0
        return (closed, r.get("created_at") or "")
    return sorted(rows, key=key)


class HrTemplatePatch(BaseModel):
    steps: list


class HrOnboardingCreate(BaseModel):
    hire_name: str
    hire_email: str = ""


class HrOnboardingPatch(BaseModel):
    step_id: str
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    hire_name: Optional[str] = None
    hire_email: Optional[str] = None


@api_router.get("/hr/template")
async def get_hr_template(principal=Depends(get_principal)):
    cache_key = _list_cache_key("hr", principal["workspace_id"], principal["user_id"], "template")
    cached = simple_cache.peek(cache_key)
    if cached is not None:
        return cached
    dept = await _hr_department(principal)
    tmpl = await _ensure_hr_onboarding_template(principal["workspace_id"], dept["department_id"])
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    is_lead = _can_lead_hr(principal, membership)
    payload_out = {
        "department_id": dept["department_id"],
        "name": dept.get("name") or "HR",
        "template": {k: v for k, v in tmpl.items() if k != "_id"},
        "is_lead": is_lead,
        "can_edit_template": is_lead,
        "my_user_id": principal["user_id"],
    }
    simple_cache.put(cache_key, payload_out, _DEPT_LIST_CACHE_TTL_SECONDS)
    return payload_out


@api_router.patch("/hr/template")
async def patch_hr_template(payload: HrTemplatePatch, principal=Depends(get_principal)):
    dept = await _hr_department(principal)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    if not _can_lead_hr(principal, membership):
        raise HTTPException(status_code=403, detail="Only an HR lead or the CEO can edit the template")
    tmpl = await _ensure_hr_onboarding_template(principal["workspace_id"], dept["department_id"])
    raw_steps = payload.steps if isinstance(payload.steps, list) else []
    cleaned = []
    for i, raw in enumerate(raw_steps):
        if not isinstance(raw, dict):
            continue
        name = (raw.get("name") or "").strip()
        if not name:
            continue
        step_id = (raw.get("id") or "").strip() or f"hstep_{uuid.uuid4().hex[:8]}"
        cleaned.append({"id": step_id, "name": name[:120], "order": i})
    if not cleaned:
        raise HTTPException(status_code=400, detail="Template must have at least one step")
    now = datetime.now(timezone.utc).isoformat()
    await db.hr_onboarding_template.update_one(
        {"id": tmpl["id"], "department_id": dept["department_id"]},
        {"$set": {"steps": cleaned, "updated_at": now}},
    )
    updated = {**tmpl, "steps": cleaned, "updated_at": now}
    invalidate_workspace_list_cache(principal["workspace_id"], "hr")
    return {"ok": True, "template": {k: v for k, v in updated.items() if k != "_id"}}


@api_router.get("/hr/onboarding")
async def list_hr_onboarding(
    principal=Depends(get_principal),
    overall_status: Optional[str] = Query(None),
):
    status_key = (overall_status or "").strip().lower() or "all"
    cache_key = _list_cache_key(
        "hr", principal["workspace_id"], principal["user_id"], "onboarding", status_key,
    )
    cached = simple_cache.peek(cache_key)
    if cached is not None:
        return cached
    dept = await _hr_department(principal)
    await _ensure_hr_onboarding_template(principal["workspace_id"], dept["department_id"])
    filt: dict = {"department_id": dept["department_id"]}
    if overall_status is not None:
        st = overall_status.strip().lower()
        if st not in HR_OVERALL_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid overall_status filter")
        filt["overall_status"] = st
    rows = await db.hr_onboarding_instances.find(filt, {"_id": 0}).to_list(1000)
    rows = _sort_hr_instances(rows)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    is_lead = _can_lead_hr(principal, membership)
    items = await _enrich_hr_instances(rows)
    items = helm_freshness.annotate_possibly_stale(items, dept_type=dept_catalog.TYPE_HR)
    payload_out = {
        "department_id": dept["department_id"],
        "name": dept.get("name") or "HR",
        "instances": items,
        "is_lead": is_lead,
        "can_create": is_lead,
        "can_delete": is_lead,
        "my_user_id": principal["user_id"],
        "step_statuses": sorted(HR_STEP_STATUSES),
    }
    simple_cache.put(cache_key, payload_out, _DEPT_LIST_CACHE_TTL_SECONDS)
    return payload_out


@api_router.post("/hr/onboarding")
async def create_hr_onboarding(payload: HrOnboardingCreate, principal=Depends(get_principal)):
    dept = await _hr_department(principal)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    if not _can_lead_hr(principal, membership):
        raise HTTPException(status_code=403, detail="Only an HR lead or the CEO can start onboarding")
    hire_name = (payload.hire_name or "").strip()
    if not hire_name:
        raise HTTPException(status_code=400, detail="Hire name is required")
    tmpl = await _ensure_hr_onboarding_template(principal["workspace_id"], dept["department_id"])
    steps = []
    for s in sorted(tmpl.get("steps") or [], key=lambda x: x.get("order", 0)):
        steps.append({
            "id": f"histep_{uuid.uuid4().hex[:8]}",
            "name": s.get("name") or "Step",
            "order": int(s.get("order") or 0),
            "status": "not_started",
            "assigned_to": None,
        })
    if not steps:
        raise HTTPException(status_code=400, detail="Template has no steps. Edit the template first")
    now = datetime.now(timezone.utc).isoformat()
    inst = {
        "id": f"hronb_{uuid.uuid4().hex[:10]}",
        "department_id": dept["department_id"],
        "workspace_id": principal["workspace_id"],
        "hire_name": hire_name,
        "hire_email": (payload.hire_email or "").strip().lower(),
        "steps": steps,
        "overall_status": "in_progress",
        "created_by": principal["user_id"],
        "created_at": now,
        "updated_at": now,
    }
    await db.hr_onboarding_instances.insert_one(dict(inst))
    invalidate_workspace_list_cache(principal["workspace_id"], "hr", "me_work")
    return {"ok": True, "instance": await _enrich_hr_instance(inst)}


@api_router.patch("/hr/onboarding/{instance_id}")
async def patch_hr_onboarding(
    instance_id: str,
    payload: HrOnboardingPatch,
    principal=Depends(get_principal),
):
    dept = await _hr_department(principal)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    is_lead = _can_lead_hr(principal, membership)
    inst = await db.hr_onboarding_instances.find_one(
        {"id": instance_id, "department_id": dept["department_id"]},
        {"_id": 0},
    )
    if not inst:
        raise HTTPException(status_code=404, detail="Onboarding instance not found")

    steps = [dict(s) for s in (inst.get("steps") or [])]
    step_id = (payload.step_id or "").strip()
    step = next((s for s in steps if s.get("id") == step_id), None)
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    is_assignee = step.get("assigned_to") == principal["user_id"]
    if not is_lead and not is_assignee:
        raise HTTPException(
            status_code=403,
            detail="You can only update steps assigned to you",
        )

    upd_top: dict = {}
    if payload.hire_name is not None or payload.hire_email is not None:
        if not is_lead:
            raise HTTPException(status_code=403, detail="Only a lead or CEO can edit hire details")
        if payload.hire_name is not None:
            name = payload.hire_name.strip()
            if not name:
                raise HTTPException(status_code=400, detail="Hire name is required")
            upd_top["hire_name"] = name
        if payload.hire_email is not None:
            upd_top["hire_email"] = payload.hire_email.strip().lower()

    if payload.assigned_to is not None:
        new_assignee = (payload.assigned_to or "").strip() or None
        if new_assignee != step.get("assigned_to") and not is_lead:
            raise HTTPException(status_code=403, detail="Only a lead or CEO can reassign steps")
        if is_lead:
            step["assigned_to"] = new_assignee

    if payload.status is not None:
        st = payload.status.strip().lower()
        if st not in HR_STEP_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid step status")
        step["status"] = st

    overall = _derive_overall_status(steps)
    now = datetime.now(timezone.utc).isoformat()
    set_fields = {"steps": steps, "overall_status": overall, "updated_at": now, **upd_top}
    helm_dept_drafts.apply_status_completion(
        inst, set_fields, done_status="active", status_key="overall_status", now_iso=now,
    )
    await db.hr_onboarding_instances.update_one(
        {"id": instance_id, "department_id": dept["department_id"]},
        {"$set": set_fields},
    )
    updated = {**inst, **set_fields}
    if overall == "active":
        await _ensure_employee_from_onboarding(updated, principal)
    invalidate_workspace_list_cache(principal["workspace_id"], "hr", "me_work", "people")
    return {"ok": True, "instance": await _enrich_hr_instance(updated)}


@api_router.delete("/hr/onboarding/{instance_id}")
async def delete_hr_onboarding(instance_id: str, principal=Depends(get_principal)):
    dept = await _hr_department(principal)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    if not _can_lead_hr(principal, membership):
        raise HTTPException(status_code=403, detail="Only an HR lead or the CEO can delete onboarding")
    result = await db.hr_onboarding_instances.delete_one(
        {"id": instance_id, "department_id": dept["department_id"]},
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Onboarding instance not found")
    invalidate_workspace_list_cache(principal["workspace_id"], "hr", "me_work", "people")
    return {"ok": True}


class HrEmployeeCreate(BaseModel):
    name: str
    role: str = ""
    start_date: str = ""
    status: str = "active"
    manager_user_id: Optional[str] = None
    linked_user_id: Optional[str] = None
    department_names: str = ""


class HrEmployeePatch(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    start_date: Optional[str] = None
    status: Optional[str] = None
    manager_user_id: Optional[str] = None
    linked_user_id: Optional[str] = None
    department_names: Optional[str] = None


@api_router.get("/hr/employees")
async def list_hr_employees(
    principal=Depends(get_principal),
    status: Optional[str] = Query(None),
):
    """Employment records — no medical, government ID, compensation, or protected characteristics."""
    status_key = (status or "").strip().lower() or "all"
    cache_key = _list_cache_key(
        "hr", principal["workspace_id"], principal["user_id"], "employees", status_key,
    )
    cached = simple_cache.peek(cache_key)
    if cached is not None:
        return cached
    dept = await _hr_department(principal)
    filt: dict = {"department_id": dept["department_id"]}
    if status is not None:
        st = status.strip().lower()
        if st not in HR_EMPLOYEE_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status filter")
        filt["status"] = st
    rows = await db.hr_employees.find(filt, {"_id": 0}).to_list(2000)
    rows.sort(key=lambda r: (
        0 if r.get("status") == "active" else 1 if r.get("status") == "on_leave" else 2,
        (r.get("name") or "").lower(),
    ))
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    is_lead = _can_lead_hr(principal, membership)
    payload_out = {
        "department_id": dept["department_id"],
        "name": dept.get("name") or "HR",
        "employees": [_public_hr_employee(r) for r in rows],
        "is_lead": is_lead,
        "can_create": is_lead,
        "can_edit": is_lead,
        "my_user_id": principal["user_id"],
        "statuses": sorted(HR_EMPLOYEE_STATUSES),
    }
    simple_cache.put(cache_key, payload_out, _DEPT_LIST_CACHE_TTL_SECONDS)
    return payload_out


@api_router.get("/hr/summary")
async def hr_summary(principal=Depends(get_principal)):
    """Headcount and leave backlog for the HR page — no confidential hr_records."""
    cache_key = _list_cache_key("hr", principal["workspace_id"], principal["user_id"], "summary")
    cached = simple_cache.peek(cache_key)
    if cached is not None:
        return cached
    dept = await _hr_department(principal)
    dept_id = dept["department_id"]
    employees = await db.hr_employees.find(
        {"department_id": dept_id}, {"_id": 0},
    ).to_list(5000)
    headcount = {"active": 0, "on_leave": 0, "departed": 0}
    now = datetime.now(timezone.utc)
    cutoff_90 = now - timedelta(days=90)
    departed_last_90_days = 0
    for emp in employees:
        st = (emp.get("status") or "").strip().lower()
        if st in headcount:
            headcount[st] += 1
        if st == "departed":
            departed_at = _parse_iso_dt(emp.get("departed_at"))
            if departed_at is not None and departed_at >= cutoff_90:
                departed_last_90_days += 1
    leave_rows = await db.hr_leave_requests.find(
        {"department_id": dept_id, "status": "pending"}, {"_id": 0},
    ).to_list(5000)
    payload_out = {
        "department_id": dept_id,
        "name": dept.get("name") or "HR",
        "headcount": headcount,
        "pending_leave_requests": len(leave_rows),
        "departed_last_90_days": departed_last_90_days,
    }
    simple_cache.put(cache_key, payload_out, _DEPT_LIST_CACHE_TTL_SECONDS)
    return payload_out


@api_router.post("/hr/employees")
async def create_hr_employee(payload: HrEmployeeCreate, principal=Depends(get_principal)):
    """Manual employee record (e.g. existing staff). Prefer completing onboarding for new hires."""
    dept = await _hr_department(principal)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    if not _can_lead_hr(principal, membership):
        raise HTTPException(status_code=403, detail="Only an HR lead or the CEO can add employees")
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    st = (payload.status or "active").strip().lower()
    if st not in HR_EMPLOYEE_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    now = datetime.now(timezone.utc).isoformat()
    start = (payload.start_date or "").strip()[:10] or now[:10]
    emp = {
        "id": f"hremp_{uuid.uuid4().hex[:10]}",
        "department_id": dept["department_id"],
        "workspace_id": principal["workspace_id"],
        "name": name[:200],
        "role": (payload.role or "").strip()[:120],
        "start_date": start,
        "status": st,
        "manager_user_id": (payload.manager_user_id or "").strip() or None,
        "linked_user_id": (payload.linked_user_id or "").strip() or None,
        "department_names": (payload.department_names or "").strip()[:200],
        "source_onboarding_instance_id": None,
        "created_at": now,
        "updated_at": now,
        "departed_at": now if st == "departed" else None,
    }
    await db.hr_employees.insert_one(dict(emp))
    invalidate_workspace_list_cache(principal["workspace_id"], "hr", "me_work", "people")
    emp.pop("_id", None)
    return {"ok": True, "employee": _public_hr_employee(emp)}


@api_router.patch("/hr/employees/{employee_id}")
async def patch_hr_employee(
    employee_id: str,
    payload: HrEmployeePatch,
    principal=Depends(get_principal),
):
    dept = await _hr_department(principal)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    if not _can_lead_hr(principal, membership):
        raise HTTPException(status_code=403, detail="Only an HR lead or the CEO can edit employees")
    emp = await db.hr_employees.find_one(
        {"id": employee_id, "department_id": dept["department_id"]},
        {"_id": 0},
    )
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    now = datetime.now(timezone.utc).isoformat()
    upd: dict = {"updated_at": now}
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name is required")
        upd["name"] = name[:200]
    if payload.role is not None:
        upd["role"] = payload.role.strip()[:120]
    if payload.start_date is not None:
        upd["start_date"] = (payload.start_date or "").strip()[:10]
    if payload.department_names is not None:
        upd["department_names"] = payload.department_names.strip()[:200]
    if payload.manager_user_id is not None:
        upd["manager_user_id"] = (payload.manager_user_id or "").strip() or None
    if payload.linked_user_id is not None:
        upd["linked_user_id"] = (payload.linked_user_id or "").strip() or None
    if payload.status is not None:
        st = payload.status.strip().lower()
        if st not in HR_EMPLOYEE_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status")
        upd["status"] = st
        if st == "departed" and not emp.get("departed_at"):
            upd["departed_at"] = now
        elif st != "departed":
            upd["departed_at"] = None
    await db.hr_employees.update_one(
        {"id": employee_id, "department_id": dept["department_id"]},
        {"$set": upd},
    )
    invalidate_workspace_list_cache(principal["workspace_id"], "hr", "me_work", "people")
    return {"ok": True, "employee": _public_hr_employee({**emp, **upd})}


class HrOffboardingCreate(BaseModel):
    employee_id: str


class HrOffboardingPatch(BaseModel):
    step_id: str
    status: Optional[str] = None
    assigned_to: Optional[str] = None


@api_router.get("/hr/offboarding/template")
async def get_hr_offboarding_template(principal=Depends(get_principal)):
    cache_key = _list_cache_key("hr", principal["workspace_id"], principal["user_id"], "offboarding_template")
    cached = simple_cache.peek(cache_key)
    if cached is not None:
        return cached
    dept = await _hr_department(principal)
    tmpl = await _ensure_hr_offboarding_template(principal["workspace_id"], dept["department_id"])
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    is_lead = _can_lead_hr(principal, membership)
    payload_out = {
        "department_id": dept["department_id"],
        "name": dept.get("name") or "HR",
        "template": {k: v for k, v in tmpl.items() if k != "_id"},
        "is_lead": is_lead,
        "can_edit_template": is_lead,
        "my_user_id": principal["user_id"],
    }
    simple_cache.put(cache_key, payload_out, _DEPT_LIST_CACHE_TTL_SECONDS)
    return payload_out


@api_router.patch("/hr/offboarding/template")
async def patch_hr_offboarding_template(payload: HrTemplatePatch, principal=Depends(get_principal)):
    dept = await _hr_department(principal)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    if not _can_lead_hr(principal, membership):
        raise HTTPException(status_code=403, detail="Only an HR lead or the CEO can edit the template")
    tmpl = await _ensure_hr_offboarding_template(principal["workspace_id"], dept["department_id"])
    raw_steps = payload.steps if isinstance(payload.steps, list) else []
    cleaned = []
    for i, raw in enumerate(raw_steps):
        if not isinstance(raw, dict):
            continue
        name = (raw.get("name") or "").strip()
        if not name:
            continue
        step_id = (raw.get("id") or "").strip() or f"hofstep_{uuid.uuid4().hex[:8]}"
        cleaned.append({"id": step_id, "name": name[:120], "order": i})
    if not cleaned:
        raise HTTPException(status_code=400, detail="Template must have at least one step")
    now = datetime.now(timezone.utc).isoformat()
    await db.hr_offboarding_template.update_one(
        {"id": tmpl["id"], "department_id": dept["department_id"]},
        {"$set": {"steps": cleaned, "updated_at": now}},
    )
    updated = {**tmpl, "steps": cleaned, "updated_at": now}
    invalidate_workspace_list_cache(principal["workspace_id"], "hr")
    return {"ok": True, "template": {k: v for k, v in updated.items() if k != "_id"}}


@api_router.get("/hr/offboarding")
async def list_hr_offboarding(
    principal=Depends(get_principal),
    overall_status: Optional[str] = Query(None),
    employee_id: Optional[str] = Query(None),
):
    status_key = (overall_status or "").strip().lower() or "all"
    emp_key = (employee_id or "").strip() or "all"
    cache_key = _list_cache_key(
        "hr", principal["workspace_id"], principal["user_id"], "offboarding", status_key, emp_key,
    )
    cached = simple_cache.peek(cache_key)
    if cached is not None:
        return cached
    dept = await _hr_department(principal)
    await _ensure_hr_offboarding_template(principal["workspace_id"], dept["department_id"])
    filt: dict = {"department_id": dept["department_id"]}
    if overall_status is not None:
        st = overall_status.strip().lower()
        if st not in HR_OVERALL_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid overall_status filter")
        filt["overall_status"] = st
    if employee_id is not None:
        eid = employee_id.strip()
        if eid:
            filt["employee_id"] = eid
    rows = await db.hr_offboarding_instances.find(filt, {"_id": 0}).to_list(1000)
    rows = _sort_hr_instances(rows)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    is_lead = _can_lead_hr(principal, membership)
    items = await _enrich_hr_instances(rows)
    payload_out = {
        "department_id": dept["department_id"],
        "name": dept.get("name") or "HR",
        "instances": items,
        "is_lead": is_lead,
        "can_create": is_lead,
        "can_delete": is_lead,
        "my_user_id": principal["user_id"],
        "step_statuses": sorted(HR_STEP_STATUSES),
    }
    simple_cache.put(cache_key, payload_out, _DEPT_LIST_CACHE_TTL_SECONDS)
    return payload_out


@api_router.post("/hr/offboarding")
async def create_hr_offboarding(payload: HrOffboardingCreate, principal=Depends(get_principal)):
    dept = await _hr_department(principal)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    if not _can_lead_hr(principal, membership):
        raise HTTPException(status_code=403, detail="Only an HR lead or the CEO can start offboarding")
    employee_id = (payload.employee_id or "").strip()
    if not employee_id:
        raise HTTPException(status_code=400, detail="employee_id is required")
    emp = await db.hr_employees.find_one(
        {"id": employee_id, "department_id": dept["department_id"]},
        {"_id": 0},
    )
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    open_existing = await db.hr_offboarding_instances.find_one(
        {
            "department_id": dept["department_id"],
            "employee_id": employee_id,
            "overall_status": "in_progress",
        },
        {"_id": 0},
    )
    if open_existing:
        raise HTTPException(status_code=409, detail="Offboarding already in progress for this employee")
    tmpl = await _ensure_hr_offboarding_template(principal["workspace_id"], dept["department_id"])
    steps = []
    for s in sorted(tmpl.get("steps") or [], key=lambda x: x.get("order", 0)):
        steps.append({
            "id": f"hoistep_{uuid.uuid4().hex[:8]}",
            "name": s.get("name") or "Step",
            "order": int(s.get("order") or 0),
            "status": "not_started",
            "assigned_to": None,
        })
    if not steps:
        raise HTTPException(status_code=400, detail="Template has no steps. Edit the template first")
    now = datetime.now(timezone.utc).isoformat()
    inst = {
        "id": f"hroff_{uuid.uuid4().hex[:10]}",
        "department_id": dept["department_id"],
        "workspace_id": principal["workspace_id"],
        "employee_id": employee_id,
        "employee_name": emp.get("name") or "",
        "steps": steps,
        "overall_status": "in_progress",
        "created_by": principal["user_id"],
        "created_at": now,
        "updated_at": now,
    }
    await db.hr_offboarding_instances.insert_one(dict(inst))
    invalidate_workspace_list_cache(principal["workspace_id"], "hr", "me_work")
    # Employee status stays as-is until all offboarding steps are done.
    return {"ok": True, "instance": await _enrich_hr_instance(inst)}


@api_router.patch("/hr/offboarding/{instance_id}")
async def patch_hr_offboarding(
    instance_id: str,
    payload: HrOffboardingPatch,
    principal=Depends(get_principal),
):
    dept = await _hr_department(principal)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    is_lead = _can_lead_hr(principal, membership)
    inst = await db.hr_offboarding_instances.find_one(
        {"id": instance_id, "department_id": dept["department_id"]},
        {"_id": 0},
    )
    if not inst:
        raise HTTPException(status_code=404, detail="Offboarding instance not found")

    steps = [dict(s) for s in (inst.get("steps") or [])]
    step_id = (payload.step_id or "").strip()
    step = next((s for s in steps if s.get("id") == step_id), None)
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    is_assignee = step.get("assigned_to") == principal["user_id"]
    if not is_lead and not is_assignee:
        raise HTTPException(
            status_code=403,
            detail="You can only update steps assigned to you",
        )

    if payload.assigned_to is not None:
        new_assignee = (payload.assigned_to or "").strip() or None
        if new_assignee != step.get("assigned_to") and not is_lead:
            raise HTTPException(status_code=403, detail="Only a lead or CEO can reassign steps")
        if is_lead:
            step["assigned_to"] = new_assignee

    if payload.status is not None:
        st = payload.status.strip().lower()
        if st not in HR_STEP_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid step status")
        step["status"] = st

    overall = _derive_overall_status(steps)
    now = datetime.now(timezone.utc).isoformat()
    set_fields = {"steps": steps, "overall_status": overall, "updated_at": now}
    helm_dept_drafts.apply_status_completion(
        inst, set_fields, done_status="active", status_key="overall_status", now_iso=now,
    )
    await db.hr_offboarding_instances.update_one(
        {"id": instance_id, "department_id": dept["department_id"]},
        {"$set": set_fields},
    )
    if overall == "active" and inst.get("employee_id"):
        await _mark_employee_departed(inst["employee_id"], dept["department_id"], now)
    updated = {**inst, **set_fields}
    invalidate_workspace_list_cache(principal["workspace_id"], "hr", "me_work", "people")
    return {"ok": True, "instance": await _enrich_hr_instance(updated)}


@api_router.delete("/hr/offboarding/{instance_id}")
async def delete_hr_offboarding(instance_id: str, principal=Depends(get_principal)):
    dept = await _hr_department(principal)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    if not _can_lead_hr(principal, membership):
        raise HTTPException(status_code=403, detail="Only an HR lead or the CEO can delete offboarding")
    result = await db.hr_offboarding_instances.delete_one(
        {"id": instance_id, "department_id": dept["department_id"]},
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Offboarding instance not found")
    invalidate_workspace_list_cache(principal["workspace_id"], "hr", "me_work", "people")
    return {"ok": True}


HR_LEAVE_TYPES = frozenset({"vacation", "sick", "personal", "other"})
HR_LEAVE_STATUSES = frozenset({"pending", "approved", "denied", "canceled"})
HR_LEAVE_TYPE_LABELS = {
    "vacation": "Vacation",
    "sick": "Sick",
    "personal": "Personal",
    "other": "Other",
}


class HrLeaveCreate(BaseModel):
    employee_id: str
    type: str = "vacation"
    start_date: str
    end_date: str
    note: str = ""


class HrLeavePatch(BaseModel):
    status: str


def _leave_title(employee_name: str, leave_type: str) -> str:
    label = HR_LEAVE_TYPE_LABELS.get(leave_type, leave_type or "Leave")
    name = (employee_name or "").strip() or "Employee"
    return f"{name}: {label}"


async def _hr_employee_for_leave(employee_id: str, department_id: str) -> dict:
    emp = await db.hr_employees.find_one(
        {"id": employee_id, "department_id": department_id},
        {"_id": 0},
    )
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return emp


def _can_request_leave_for_employee(
    principal: dict, membership: dict | None, emp: dict,
) -> bool:
    if _can_lead_hr(principal, membership):
        return True
    linked = (emp.get("linked_user_id") or "").strip()
    return bool(linked) and linked == principal["user_id"]


@api_router.get("/hr/leave-requests")
async def list_hr_leave_requests(
    principal=Depends(get_principal),
    status: Optional[str] = Query(None),
    employee_id: Optional[str] = Query(None),
):
    status_key = (status or "").strip().lower() or "all"
    emp_key = (employee_id or "").strip() or "all"
    cache_key = _list_cache_key(
        "hr", principal["workspace_id"], principal["user_id"], "leave", status_key, emp_key,
    )
    cached = simple_cache.peek(cache_key)
    if cached is not None:
        return cached
    dept = await _hr_department(principal)
    filt: dict = {"department_id": dept["department_id"]}
    if status is not None:
        st = status.strip().lower()
        if st not in HR_LEAVE_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status filter")
        filt["status"] = st
    if employee_id is not None:
        eid = employee_id.strip()
        if eid:
            filt["employee_id"] = eid
    rows = await db.hr_leave_requests.find(filt, {"_id": 0}).to_list(2000)
    # Pending first, then by start_date ascending within group
    rows.sort(key=lambda r: (
        0 if r.get("status") == "pending" else 1,
        r.get("start_date") or "",
        r.get("created_at") or "",
    ))
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    is_lead = _can_lead_hr(principal, membership)
    payload_out = {
        "department_id": dept["department_id"],
        "name": dept.get("name") or "HR",
        "requests": [{k: v for k, v in r.items() if k != "_id"} for r in rows],
        "is_lead": is_lead,
        "can_approve": is_lead,
        "my_user_id": principal["user_id"],
        "types": sorted(HR_LEAVE_TYPES),
        "statuses": sorted(HR_LEAVE_STATUSES),
    }
    simple_cache.put(cache_key, payload_out, _DEPT_LIST_CACHE_TTL_SECONDS)
    return payload_out


@api_router.post("/hr/leave-requests")
async def create_hr_leave_request(payload: HrLeaveCreate, principal=Depends(get_principal)):
    dept = await _hr_department(principal)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    # Any HR member can create (for self / linked employee); leads may create for anyone.
    if not membership and not dept_access.is_workspace_ceo(principal):
        raise HTTPException(status_code=403, detail="You do not have access to HR")
    employee_id = (payload.employee_id or "").strip()
    if not employee_id:
        raise HTTPException(status_code=400, detail="employee_id is required")
    emp = await _hr_employee_for_leave(employee_id, dept["department_id"])
    if not _can_request_leave_for_employee(principal, membership, emp):
        raise HTTPException(
            status_code=403,
            detail="You can only request leave for an employee linked to your account",
        )
    leave_type = (payload.type or "vacation").strip().lower()
    if leave_type not in HR_LEAVE_TYPES:
        raise HTTPException(status_code=400, detail="Invalid leave type")
    start = _parse_calendar_day(payload.start_date)
    end = _parse_calendar_day(payload.end_date)
    if not start or not end:
        raise HTTPException(status_code=400, detail="start_date and end_date must be YYYY-MM-DD")
    if end < start:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": f"hrleave_{uuid.uuid4().hex[:10]}",
        "employee_id": employee_id,
        "employee_name": (emp.get("name") or "").strip(),
        "department_id": dept["department_id"],
        "workspace_id": principal["workspace_id"],
        "type": leave_type,
        "start_date": start,
        "end_date": end,
        "note": (payload.note or "").strip()[:500],
        "status": "pending",
        "requested_by": principal["user_id"],
        "decided_by": None,
        "title": _leave_title(emp.get("name") or "", leave_type),
        "created_at": now,
        "updated_at": now,
    }
    await db.hr_leave_requests.insert_one(dict(doc))
    invalidate_workspace_list_cache(principal["workspace_id"], "hr", "me_work")
    doc.pop("_id", None)
    return {"ok": True, "request": doc}


@api_router.patch("/hr/leave-requests/{request_id}")
async def patch_hr_leave_request(
    request_id: str,
    payload: HrLeavePatch,
    principal=Depends(get_principal),
):
    """Approve/deny (HR lead/CEO) or cancel own pending request (requester)."""
    dept = await _hr_department(principal)
    membership = await dept_access.get_department_membership(
        db, dept["department_id"], principal["user_id"],
    )
    is_lead = _can_lead_hr(principal, membership)
    row = await db.hr_leave_requests.find_one(
        {"id": request_id, "department_id": dept["department_id"]},
        {"_id": 0},
    )
    if not row:
        raise HTTPException(status_code=404, detail="Leave request not found")
    st = (payload.status or "").strip().lower()
    now = datetime.now(timezone.utc).isoformat()

    if st == "canceled":
        if row.get("status") != "pending":
            raise HTTPException(status_code=400, detail="Only pending leave requests can be canceled")
        is_requester = row.get("requested_by") == principal["user_id"]
        if not is_requester:
            raise HTTPException(
                status_code=403,
                detail="You can only cancel your own leave request",
            )
        upd = {
            "status": "canceled",
            "updated_at": now,
        }
        await db.hr_leave_requests.update_one(
            {"id": request_id, "department_id": dept["department_id"]},
            {"$set": upd},
        )
        invalidate_workspace_list_cache(principal["workspace_id"], "hr", "me_work")
        return {"ok": True, "request": {**row, **upd}}

    if st not in ("approved", "denied"):
        raise HTTPException(status_code=400, detail="status must be approved, denied, or canceled")
    if not is_lead:
        raise HTTPException(status_code=403, detail="Only an HR lead or the CEO can approve or deny leave")
    if row.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Only pending leave requests can be decided")
    upd = {
        "status": st,
        "decided_by": principal["user_id"],
        "updated_at": now,
    }
    await db.hr_leave_requests.update_one(
        {"id": request_id, "department_id": dept["department_id"]},
        {"$set": upd},
    )
    invalidate_workspace_list_cache(principal["workspace_id"], "hr", "me_work")
    return {"ok": True, "request": {**row, **upd}}


# ------------------------- Ask Trenston -------------------------
# Static instructions — identical on every Ask call across all workspaces.
# Cached via Anthropic prompt caching (cache_control ephemeral). Company name
# and the live snapshot are appended as a separate uncached system block.
STATIC_ASK_TRENSTON_INSTRUCTIONS = (
    "You are Trenston, the CEO's executive AI chief-of-staff. "
    "Answer like a sharp, trusted operator: direct, quantified, decisive. "
    "Use the live company snapshot provided. Keep answers tight. "
    "Write plainly. Avoid em dashes. Prefer periods, commas, or plain connecting words instead, "
    "unless a sentence genuinely cannot be split any other way. "
    "Never treat missing figures as zero. Follow every instructions_for_missing_data "
    "block in the snapshot (company_profile, financials, pipeline, onboarding, "
    "production, procurement, legal, maintenance, risks). "
    "If a field is null or listed in unknown_fields, say the data is not in Trenston yet. "
    "Do not infer it and do not describe it as zero. "
    "Only state a number, date, or figure that appears literally in the snapshot. "
    "Never invent, estimate, or round into a figure that is not present. "
    "If financials.access is \"restricted\", the user does not have access to financial "
    "data in Trenston. Tell them clearly they cannot see revenue, burn, runway, or related "
    "figures and should ask someone with Financials access. Do not invent numbers, "
    "describe them as zero, or estimate them from pipeline deal values or other clues. "
    "If pipeline, onboarding, production, procurement, legal, or maintenance has "
    "access \"restricted\", the user is not a member of that department. Say you do "
    "not have access to that department's data. Do not invent deals, hires, work "
    "orders, tickets, or legal matters. "
    "When possibly_stale_count is greater than zero, say those open records may be "
    "outdated rather than treating every count as freshly updated. "
    "data_as_of is the latest underlying sync or department update, not the time of "
    "this answer. Prefer it when describing how current the picture is."
)

# Ask Trenston output ceiling — lower than stream_text's default (1600) to cap
# worst-case cost while still fitting a solid multi-paragraph CEO answer.
ASK_TRENSTON_MAX_TOKENS = 1000


class AskInput(BaseModel):
    message: str


@api_router.get("/ask/history")
async def ask_history(principal=Depends(get_principal)):
    msgs = await db.chat_messages.find({"workspace_id": principal["workspace_id"], "user_id": principal["user_id"]}, {"_id": 0}).sort("created_at", 1).to_list(200)
    return {"messages": msgs}


@api_router.post("/ask")
async def ask_helm(payload: AskInput, principal=Depends(require_pro_perm("ask:use"))):
    c = await get_ws(principal["workspace_id"])
    if not helm_llm.anthropic_configured():
        raise HTTPException(status_code=503, detail="AI is not configured (ANTHROPIC_API_KEY)")
    ask_limit = helm_plans.ask_helm_monthly_limit(c.get("plan"))
    period = plan_usage.current_usage_period(c)
    # Enforce after we know the message will consume a real model turn (see below).
    now = datetime.now(timezone.utc)
    await db.chat_messages.insert_one({"workspace_id": c["workspace_id"], "user_id": principal["user_id"], "role": "user", "content": payload.message, "created_at": now.isoformat(), "day": now.date().isoformat()})
    has_fin_access = await can_access_financials(principal)

    # Hard deny finance questions without the grant — do not call the model with
    # (or without) numbers; the model cannot enforce a permission boundary.
    if not has_fin_access and message_requests_financials(payload.message):
        denied = FINANCIALS_ACCESS_DENIED_MESSAGE

        async def deny_gen():
            try:
                yield denied
            finally:
                await db.chat_messages.insert_one({
                    "workspace_id": c["workspace_id"],
                    "user_id": principal["user_id"],
                    "role": "assistant",
                    "content": denied,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "day": datetime.now(timezone.utc).date().isoformat(),
                })

        return StreamingResponse(
            deny_gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    if BILLING_ENFORCED and ask_limit > 0:
        ok = await plan_usage.acquire_period_ask_slot(
            db, c["workspace_id"], period["key"], ask_limit,
        )
        if not ok:
            reset_label = period["end"].strftime("%b %d, %Y")
            raise HTTPException(
                status_code=429,
                detail=(
                    f"You've used your {ask_limit} Ask Trenston messages this billing period. "
                    f"Your allowance resets on {reset_label}. Upgrade for a higher limit."
                ),
            )
    await _product_event(
        c["workspace_id"], principal["user_id"], helm_analytics.EVENT_ASK_HELM, {},
    )

    fin = await compute_financials(c["workspace_id"]) if has_fin_access else {}

    ask_dept_specs = (
        (dept_catalog.TYPE_SALES, "deals"),
        (dept_catalog.TYPE_HR, "hr_onboarding_instances"),
        (dept_catalog.TYPE_PRODUCTION, "production_work_orders"),
        (dept_catalog.TYPE_PROCUREMENT, "procurement_requests"),
        (dept_catalog.TYPE_LEGAL, "legal_matters"),
        (dept_catalog.TYPE_ENGINEERING_MAINTENANCE, "maintenance_tickets"),
    )
    ask_types = [t for t, _ in ask_dept_specs]
    access_by_type, enabled_by_type = await asyncio.gather(
        dept_access.accessible_department_ids_by_type(db, principal, ask_types),
        dept_migrate.get_enabled_departments_by_type(db, c["workspace_id"], ask_types),
    )
    slice_results = await asyncio.gather(*[
        _ask_helm_department_slice(
            principal, dtype, coll,
            enabled_dept=enabled_by_type.get(dtype),
            access_ids=access_by_type.get(dtype, []),
        )
        for dtype, coll in ask_dept_specs
    ])
    (
        (deals, sales_enabled, sales_visible),
        (onboarding_rows, hr_enabled, hr_visible),
        (production_rows, production_enabled, production_visible),
        (procurement_rows, procurement_enabled, procurement_visible),
        (legal_rows, legal_enabled, legal_visible),
        (maintenance_rows, maintenance_enabled, maintenance_visible),
    ) = slice_results

    context = ask_context_for_synthesis(
        c,
        fin,
        deals=deals,
        sales_tracked=sales_visible,
        onboarding_instances=onboarding_rows,
        hr_tracked=hr_visible,
        financials_visible=has_fin_access,
        sales_visible=sales_visible,
        hr_visible=hr_visible,
        sales_enabled=sales_enabled,
        hr_enabled=hr_enabled,
        production_rows=production_rows,
        production_enabled=production_enabled,
        production_visible=production_visible,
        procurement_rows=procurement_rows,
        procurement_enabled=procurement_enabled,
        procurement_visible=procurement_visible,
        legal_rows=legal_rows,
        legal_enabled=legal_enabled,
        legal_visible=legal_visible,
        maintenance_rows=maintenance_rows,
        maintenance_enabled=maintenance_enabled,
        maintenance_visible=maintenance_visible,
    )
    # Defense in depth: never put real figures/queues in the prompt without access.
    if not has_fin_access:
        context["financials"] = _ask_dept_restricted(
            "Financial figures are not shared with this user's role.",
        )
    if sales_enabled and not sales_visible:
        context["pipeline"] = _ask_dept_restricted(
            "Sales pipeline is not shared with this user's role.",
        )
    if hr_enabled and not hr_visible:
        context["onboarding"] = _ask_dept_restricted(
            "HR onboarding data is not shared with this user's role.",
        )
    if production_enabled and not production_visible:
        context["production"] = _ask_dept_restricted(
            "Production data is not shared with this user's role.",
        )
    if procurement_enabled and not procurement_visible:
        context["procurement"] = _ask_dept_restricted(
            "Procurement data is not shared with this user's role.",
        )
    if legal_enabled and not legal_visible:
        context["legal"] = _ask_dept_restricted(
            "Legal data is not shared with this user's role.",
        )
    if maintenance_enabled and not maintenance_visible:
        context["maintenance"] = _ask_dept_restricted(
            "Engineering & Maintenance data is not shared with this user's role.",
        )
    freshness = await helm_freshness.resolve_workspace_data_as_of(db, c)
    context["data_as_of"] = freshness.get("data_as_of")
    context["data_freshness_sources"] = freshness.get("sources") or {}
    # Compact JSON (no indent) — same data, fewer tokens. Static instructions are
    # prompt-cached; only the company name + snapshot vary per call.
    snapshot_json = json.dumps(context, separators=(",", ":"))
    system = [
        {
            "type": "text",
            "text": STATIC_ASK_TRENSTON_INSTRUCTIONS,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": (
                f"You are advising {c['name']}. "
                f"Current company snapshot:\n{snapshot_json}"
            ),
        },
    ]

    async def gen():
        collected = ""
        try:
            async for chunk in helm_llm.stream_text(
                system, payload.message, max_tokens=ASK_TRENSTON_MAX_TOKENS,
            ):
                collected += chunk
                yield chunk
        except Exception:
            logger.exception("chat stream error")
            if not collected:
                collected = "I hit an error reaching my reasoning engine. Please try again."
                yield collected
        finally:
            await db.chat_messages.insert_one({"workspace_id": c["workspace_id"], "user_id": principal["user_id"], "role": "assistant", "content": collected, "created_at": datetime.now(timezone.utc).isoformat(), "day": datetime.now(timezone.utc).date().isoformat()})

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


api_router.add_api_route("/ai/ask-helm", ask_helm, methods=["POST"])
api_router.add_api_route("/ai/ask-kalun", ask_helm, methods=["POST"])


# ------------------------- Integrations -------------------------
GOOGLE_SCOPES = [
    "openid", "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


def _integration_tokens(workspace: dict, field: str) -> Optional[dict]:
    """Decrypt stored QuickBooks/Xero/HubSpot/SAP (workspace-shared) credentials."""
    try:
        return cred_crypto.unseal_credentials(workspace.get(field))
    except cred_crypto.CredentialCryptoError:
        logger.exception("Failed to decrypt %s for workspace %s", field, workspace.get("workspace_id"))
        return None


def _workspace_accounting_sync(workspace: dict) -> dict:
    """Which accounting systems are connected for Financials sync (not Google)."""
    providers = []
    if cred_crypto.credentials_present(workspace.get("quickbooks_tokens")):
        providers.append({"id": "quickbooks", "label": "QuickBooks"})
    if cred_crypto.credentials_present(workspace.get("xero_tokens")):
        providers.append({"id": "xero", "label": "Xero"})
    if cred_crypto.credentials_present(workspace.get("sap_b1_credentials")):
        providers.append({"id": "sap_b1", "label": "SAP Business One"})
    labels = [p["label"] for p in providers]
    if len(labels) == 0:
        label = ""
    elif len(labels) == 1:
        label = labels[0]
    elif len(labels) == 2:
        label = f"{labels[0]} and {labels[1]}"
    else:
        label = f"{', '.join(labels[:-1])}, and {labels[-1]}"
    return {"connected": bool(providers), "providers": providers, "label": label}


async def _store_integration_tokens(
    workspace_id: str,
    field: str,
    tokens: Optional[dict],
    *,
    extra_set: Optional[dict] = None,
    extra_unset: Optional[dict] = None,
    connected_by_user_id: Optional[str] = None,
):
    """Encrypt credentials before writing to the workspace document.

    Used for company-shared grants (QuickBooks, Xero, HubSpot, SAP). Google
    Calendar/Gmail tokens are per-user — see ``_store_user_google_tokens``.

    When tokens are saved, stamp who connected them so use of the grant can be
    limited to that person (and workspace owners). Clearing tokens clears the stamp.
    """
    if field == "google_tokens":
        raise ValueError(
            "google_tokens must be stored per-user via _store_user_google_tokens; "
            "do not write them onto the workspace document"
        )
    sealed = cred_crypto.seal_credentials(tokens) if tokens else None
    sets = {**(extra_set or {})}
    unsets = {**(extra_unset or {})}
    by_field = _INTEGRATION_CONNECTED_BY.get(field)
    at_field = _INTEGRATION_CONNECTED_AT.get(field)
    if tokens:
        sets[field] = sealed
        if connected_by_user_id and by_field:
            sets[by_field] = connected_by_user_id
        if connected_by_user_id and at_field:
            sets[at_field] = datetime.now(timezone.utc).isoformat()
    else:
        sets[field] = None
        if by_field:
            unsets[by_field] = ""
        if at_field:
            unsets[at_field] = ""
    update: dict = {"$set": sets}
    if unsets:
        update["$unset"] = unsets
    await db.workspaces.update_one({"workspace_id": workspace_id}, update)


async def _user_google_row(workspace_id: str, user_id: str) -> Optional[dict]:
    """Raw ``user_google_tokens`` document for this member in this workspace."""
    if not workspace_id or not user_id:
        return None
    return await db.user_google_tokens.find_one(
        {"workspace_id": workspace_id, "user_id": user_id},
        {"_id": 0},
    )


async def _user_google_tokens_present(workspace_id: str, user_id: str) -> bool:
    """True when this user has a Google connection row (sealed blob present)."""
    row = await _user_google_row(workspace_id, user_id)
    return bool(row and cred_crypto.credentials_present(row.get("google_tokens")))


async def _user_google_tokens(workspace_id: str, user_id: str) -> Optional[dict]:
    """Decrypt this user's Google Calendar/Gmail tokens. None if not connected.

    Gmail and Calendar share the same per-user OAuth grant on purpose — both
    are personal Google data for the calling teammate, not a workspace-wide
    shared mailbox or calendar.
    """
    row = await _user_google_row(workspace_id, user_id)
    if not row:
        return None
    try:
        return cred_crypto.unseal_credentials(row.get("google_tokens"))
    except cred_crypto.CredentialCryptoError:
        logger.exception(
            "Failed to decrypt user Google tokens for %s in %s", user_id, workspace_id,
        )
        return None


async def _store_user_google_tokens(
    workspace_id: str, user_id: str, tokens: Optional[dict],
) -> None:
    """Upsert or clear this user's Google OAuth tokens (Calendar + Gmail)."""
    if not workspace_id or not user_id:
        return
    if tokens:
        sealed = cred_crypto.seal_credentials(tokens)
        await db.user_google_tokens.update_one(
            {"workspace_id": workspace_id, "user_id": user_id},
            {
                "$set": {
                    "workspace_id": workspace_id,
                    "user_id": user_id,
                    "google_tokens": sealed,
                    "connected_at": datetime.now(timezone.utc).isoformat(),
                },
            },
            upsert=True,
        )
        return
    await db.user_google_tokens.delete_one(
        {"workspace_id": workspace_id, "user_id": user_id},
    )


async def _require_user_google_tokens(principal: dict) -> dict:
    """Return the calling user's Google tokens or 400 if they have not connected."""
    tokens = await _user_google_tokens(principal["workspace_id"], principal["user_id"])
    if not tokens:
        raise HTTPException(
            status_code=400,
            detail="Connect your Google account on Integrations to use Calendar and Gmail",
        )
    return tokens


def _is_workspace_owner_principal(principal: dict) -> bool:
    return principal.get("role") == "owner" or principal.get("pack") == "owner" or pack_of(principal) == "owner"


def _can_use_integration_tokens(principal: dict, workspace: dict, field: str) -> bool:
    """Shared OAuth grants (QB/Xero/HubSpot/SAP) — connector or workspace owner."""
    if field == "google_tokens":
        # Google is per-user; callers must use _user_google_tokens instead.
        return False
    if not workspace or not _integration_tokens(workspace, field):
        return False
    by_field = _INTEGRATION_CONNECTED_BY.get(field)
    connected_by = (workspace.get(by_field) if by_field else None) or None
    if not connected_by:
        # Legacy unstamped connection: owners only until someone reconnects.
        return _is_workspace_owner_principal(principal)
    if principal.get("user_id") == connected_by:
        return True
    return _is_workspace_owner_principal(principal)


def _require_integration_token_use(principal: dict, workspace: dict, field: str) -> dict:
    if field == "google_tokens":
        raise HTTPException(
            status_code=400,
            detail="Connect your Google account on Integrations to use Calendar and Gmail",
        )
    tokens = _integration_tokens(workspace, field)
    if not tokens:
        raise HTTPException(status_code=400, detail="Integration is not connected")
    if not _can_use_integration_tokens(principal, workspace, field):
        raise HTTPException(
            status_code=403,
            detail="Only the teammate who connected this integration (or a workspace owner) can use it",
        )
    return tokens


def _provider_config(provider: str):
    redirect = _oauth_callback_uri(provider)
    if provider == "google":
        return {
            "configured": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
            "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect, "scope": " ".join(GOOGLE_SCOPES),
            "extra": {"access_type": "offline", "prompt": "consent"},
            "token_field": "google_tokens",
        }
    if provider == "quickbooks":
        return {
            "configured": bool(QB_CLIENT_ID and QB_CLIENT_SECRET),
            "auth_uri": "https://appcenter.intuit.com/connect/oauth2",
            "token_uri": "https://oauth2.platform.intuit.com/oauth2/v1/tokens/bearer",
            "client_id": QB_CLIENT_ID, "client_secret": QB_CLIENT_SECRET,
            "redirect_uri": redirect, "scope": "com.intuit.quickbooks.accounting",
            "extra": {}, "token_field": "quickbooks_tokens",
        }
    if provider == "xero":
        return {
            "configured": bool(XERO_CLIENT_ID and XERO_CLIENT_SECRET),
            "auth_uri": xero_sync.AUTH_URL,
            "token_uri": xero_sync.TOKEN_URL,
            "client_id": XERO_CLIENT_ID, "client_secret": XERO_CLIENT_SECRET,
            "redirect_uri": redirect, "scope": xero_sync.XERO_SCOPES,
            "extra": {}, "token_field": "xero_tokens",
        }
    if provider == "hubspot":
        return {
            "configured": bool(HUBSPOT_CLIENT_ID and HUBSPOT_CLIENT_SECRET),
            "auth_uri": hubspot_sync.AUTH_URL,
            "token_uri": hubspot_sync.TOKEN_URL,
            "client_id": HUBSPOT_CLIENT_ID, "client_secret": HUBSPOT_CLIENT_SECRET,
            "redirect_uri": redirect, "scope": hubspot_sync.HUBSPOT_SCOPES,
            "extra": {}, "token_field": "hubspot_tokens",
        }
    return None


@api_router.get("/integrations")
async def integrations(principal=Depends(get_principal)):
    c = await get_ws(principal["workspace_id"])
    my_google_row = await _user_google_row(principal["workspace_id"], principal["user_id"])
    my_google_sealed = (my_google_row or {}).get("google_tokens")
    ints = integ_catalog.merge_integrations(
        c,
        google_configured=bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
        qb_configured=bool(QB_CLIENT_ID and QB_CLIENT_SECRET),
        xero_configured=bool(XERO_CLIENT_ID and XERO_CLIENT_SECRET),
        hubspot_configured=bool(HUBSPOT_CLIENT_ID and HUBSPOT_CLIENT_SECRET),
        anthropic_configured=helm_llm.anthropic_configured(),
        r2_configured=doc_storage.r2_configured(),
        resend_configured=bool(RESEND_API_KEY),
        paddle_ready=bool(PADDLE_CLIENT_TOKEN and helm_plans.any_paddle_price_configured()),
        clerk_configured=clerk_auth.clerk_configured(),
        user_google_tokens=my_google_sealed,
    )
    xero_pending: list = []
    xero_tokens = _integration_tokens(c, "xero_tokens")
    if xero_tokens and not xero_tokens.get("tenant_id"):
        xero_pending = list(xero_tokens.get("pending_tenants") or [])
    google_connected = cred_crypto.credentials_present(my_google_sealed)
    connection_owners = {
        "google": principal["user_id"] if google_connected else None,
        "quickbooks": c.get("quickbooks_tokens_connected_by"),
        "xero": c.get("xero_tokens_connected_by"),
        "hubspot": c.get("hubspot_tokens_connected_by"),
        "sap_b1": c.get("sap_b1_credentials_connected_by"),
    }
    can_use = {
        "google": google_connected,
        "quickbooks": _can_use_integration_tokens(principal, c, "quickbooks_tokens"),
        "xero": _can_use_integration_tokens(principal, c, "xero_tokens"),
        "hubspot": _can_use_integration_tokens(principal, c, "hubspot_tokens"),
        "sap_b1": _can_use_integration_tokens(principal, c, "sap_b1_credentials"),
    }
    can_manage = "integrations:manage" in perms_for(principal["pack"])
    out = {
        "integrations": ints,
        "is_pro": workspace_is_pro(c),
        "billing_enforced": BILLING_ENFORCED,
        "integrations_enabled": workspace_allows(c, helm_plans.FEATURE_INTEGRATIONS),
        "can_manage": "integrations:manage" in perms_for(principal["pack"]),
        "can_connect_google": True,
        "connection_owners": connection_owners,
        "can_use_connection": can_use,
        "slack_webhook_configured": bool((c.get("slack_webhook_url") or "").strip()),
        "slack_webhook_url": (c.get("slack_webhook_url") or "") if can_manage else "",
        "xero_pending_tenants": xero_pending if can_manage else [],
    }
    if can_manage:
        # Owner-only diagnostics — no secrets, helps debug Connect failures.
        out["encryption_ready"] = cred_crypto.encryption_key_is_fernet()
        out["oauth_redirect_uris"] = {
            "quickbooks": _oauth_callback_uri("quickbooks"),
            "google": _oauth_callback_uri("google"),
            "xero": _oauth_callback_uri("xero"),
            "hubspot": _oauth_callback_uri("hubspot"),
        }
        out["quickbooks_env"] = QB_ENV
    return out


class SlackWebhookInput(BaseModel):
    webhook_url: str = ""


@api_router.put("/integrations/slack-webhook")
async def update_slack_webhook(payload: SlackWebhookInput, principal=Depends(require_integration_provider("slack"))):
    url = (payload.webhook_url or "").strip()
    if url and not url.startswith("https://hooks.slack.com/"):
        raise HTTPException(status_code=400, detail="Webhook URL must start with https://hooks.slack.com/")
    await db.workspaces.update_one(
        {"workspace_id": principal["workspace_id"]},
        {"$set": {"slack_webhook_url": url}},
    )
    await log_activity(
        principal, "integrations", "slack.webhook",
        "Updated Slack alert webhook" if url else "Cleared Slack alert webhook",
    )
    return {"ok": True, "slack_webhook_configured": bool(url)}


@api_router.post("/integrations/{integration_id}/toggle")
async def toggle_integration(integration_id: str, principal=Depends(get_principal)):
    if "integrations:manage" not in perms_for(principal["pack"]):
        raise HTTPException(
            status_code=403,
            detail={
                "reason": "permission",
                "message": "You do not have permission for this action",
            },
        )
    spec = next((i for i in integ_catalog.INTEGRATION_CATALOG if i["id"] == integration_id), None)
    if not spec:
        raise HTTPException(status_code=404, detail="Unknown integration")
    provider = (integration_id or "").strip().lower()
    if provider and provider != "google" and BILLING_ENFORCED:
        c = await get_ws(principal["workspace_id"])
        if not workspace_allows_provider(c, provider):
            raise HTTPException(status_code=403, detail=_plan_provider_denied_detail(provider))
    if spec.get("kind") in ("oauth", "coming_soon"):
        raise HTTPException(
            status_code=400,
            detail="Use Connect or Disconnect for this integration.",
        )
    raise HTTPException(status_code=400, detail="Integration toggle is not supported")


@api_router.get("/integrations/{provider}/connect")
async def integration_connect(provider: str, request: Request, principal=Depends(get_principal)):
    """Start OAuth. Google is per-user (any member); company ledgers require integrations:manage + plan."""
    if provider != "google" and "integrations:manage" not in perms_for(principal["pack"]):
        raise HTTPException(status_code=403, detail="Only workspace owners can connect this integration")
    if provider != "google" and BILLING_ENFORCED:
        c = await get_ws(principal["workspace_id"])
        if not workspace_allows_provider(c, provider):
            raise HTTPException(status_code=403, detail=_plan_provider_denied_detail(provider))
    cfg = _provider_config(provider)
    if not cfg:
        raise HTTPException(status_code=404, detail="Unknown provider")
    if not cfg["configured"]:
        missing = {
            "google": "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET",
            "quickbooks": "QUICKBOOKS_CLIENT_ID / QUICKBOOKS_CLIENT_SECRET",
            "xero": "XERO_CLIENT_ID / XERO_CLIENT_SECRET",
            "hubspot": "HUBSPOT_CLIENT_ID / HUBSPOT_CLIENT_SECRET",
        }.get(provider, "OAuth credentials")
        return {
            "configured": False,
            "message": f"Not configured yet. Set {missing} on the API host, then reconnect.",
            "redirect_uri": cfg["redirect_uri"],
        }
    nonce = secrets.token_urlsafe(24)
    state = _sign_state(provider, principal["workspace_id"], principal["user_id"], nonce)
    await db.oauth_states.insert_one({
        "state_hash": hashlib.sha256(state.encode()).hexdigest(),
        "provider": provider,
        "workspace_id": principal["workspace_id"],
        "user_id": principal["user_id"],
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
    })
    params = {"client_id": cfg["client_id"], "redirect_uri": cfg["redirect_uri"], "response_type": "code",
              "scope": cfg["scope"], "state": state, **cfg.get("extra", {})}
    return {"configured": True, "authorization_url": f"{cfg['auth_uri']}?{urlencode(params)}"}


def _oauth_datetime_expired(expires_at) -> bool:
    """True when an oauth_states.expires_at value is missing or in the past.

    Mongo may return naive datetimes; comparing those to aware UTC used to 500
    the Google callback after the user clicked Allow.
    """
    if expires_at is None:
        return True
    now = datetime.now(timezone.utc)
    parsed = expires_at
    if isinstance(expires_at, str):
        try:
            parsed = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            return True
    if not isinstance(parsed, datetime):
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed < now


_OAUTH_TOKEN_SCALAR_KEYS = (
    "access_token",
    "refresh_token",
    "token_type",
    "expires_in",
    "expiry",
    "obtained_at",
    "realmId",
    "tenant_id",
    "tenant_name",
    "scope",
)


def sanitize_oauth_token_payload(raw) -> dict:
    """Keep JSON-safe OAuth fields; drop id_token and other provider extras."""
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    for key in _OAUTH_TOKEN_SCALAR_KEYS:
        value = raw.get(key)
        if value is None:
            continue
        if key == "scope" and isinstance(value, (list, tuple)):
            out[key] = " ".join(str(item) for item in value if item)
        elif isinstance(value, (str, int, float, bool)):
            out[key] = value
    pending = raw.get("pending_tenants")
    if isinstance(pending, list):
        cleaned = []
        for tenant in pending:
            if not isinstance(tenant, dict):
                continue
            tid = tenant.get("tenant_id")
            if not tid:
                continue
            cleaned.append({
                "tenant_id": str(tid),
                "tenant_name": str(tenant.get("tenant_name") or ""),
            })
        if cleaned:
            out["pending_tenants"] = cleaned
    return out


def _integrations_oauth_redirect() -> str:
    frontend = (APP_URL or public_api_origin()).rstrip("/")
    return f"{frontend}/app/integrations"


_SAFE_OAUTH_REASONS = frozenset({
    "invalid_client",
    "invalid_grant",
    "invalid_request",
    "unauthorized_client",
    "unsupported_grant_type",
    "access_denied",
    "bad_json",
    "missing_token",
    "provider_error",
    "network",
    "seal",
    "store",
})


def _oauth_error_reason_from_token_response(response) -> str:
    """Map provider token-endpoint failures to a short safe reason for the UI."""
    try:
        payload = response.json()
    except Exception:
        payload = None
    if isinstance(payload, dict):
        err = str(payload.get("error") or "").strip().lower()
        if err in _SAFE_OAUTH_REASONS:
            return err
        if err:
            return "provider_error"
    status = getattr(response, "status_code", None)
    if isinstance(status, int) and status >= 400:
        return f"http_{status}"
    return "provider_error"


def _oauth_fail_redirect(integrations_path: str, *, error: str, provider: str, reason: str = "") -> RedirectResponse:
    q = f"error={error}&provider={provider}"
    safe = (reason or "").strip().lower()
    if safe.startswith("http_") and safe[5:].isdigit():
        q += f"&reason={safe}"
    elif safe in _SAFE_OAUTH_REASONS:
        q += f"&reason={safe}"
    return RedirectResponse(f"{integrations_path}?{q}")


@api_router.get("/oauth/{provider}/callback")
async def oauth_callback(provider: str, request: Request, code: Optional[str] = None, state: Optional[str] = None, realmId: Optional[str] = None):
    integrations_path = _integrations_oauth_redirect()
    try:
        return await _complete_oauth_callback(provider, code, state, realmId, integrations_path)
    except Exception:
        logger.exception("oauth callback failed for %s", provider)
        return _oauth_fail_redirect(integrations_path, error="token", provider=provider, reason="network")


async def _complete_oauth_callback(
    provider: str,
    code: Optional[str],
    state: Optional[str],
    realmId: Optional[str],
    integrations_path: str,
):
    cfg = _provider_config(provider)
    if not cfg or not code or not state:
        return _oauth_fail_redirect(integrations_path, error="oauth", provider=provider)
    verified = _verify_state(state)
    if not verified or verified[0] != provider:
        return _oauth_fail_redirect(integrations_path, error="state", provider=provider)
    workspace_id, user_id, _nonce = verified[1:]
    state_row = await db.oauth_states.find_one_and_delete({
        "state_hash": hashlib.sha256(state.encode()).hexdigest(),
        "provider": provider,
        "workspace_id": workspace_id,
        "user_id": user_id,
    })
    if not state_row or _oauth_datetime_expired(state_row.get("expires_at")):
        return _oauth_fail_redirect(integrations_path, error="state", provider=provider)
    membership = await db.memberships.find_one({
        "workspace_id": workspace_id,
        "user_id": user_id,
        "status": "active",
    }, {"_id": 0, "role": 1, "pack": 1, "permissions": 1})
    if not membership:
        return _oauth_fail_redirect(integrations_path, error="state", provider=provider)
    # Google is per-user — any active member may complete their own connect.
    # Company ledgers (QB/Xero/HubSpot) still require integrations:manage.
    if provider != "google" and "integrations:manage" not in perms_for(pack_of(membership)):
        return _oauth_fail_redirect(integrations_path, error="state", provider=provider)

    async def _persist_tokens(payload: dict):
        try:
            await _store_integration_tokens(
                workspace_id, cfg["token_field"], payload, connected_by_user_id=user_id,
            )
        except cred_crypto.CredentialCryptoError:
            logger.exception("oauth token seal failed for %s", provider)
            return _oauth_fail_redirect(integrations_path, error="save", provider=provider, reason="seal")
        except Exception:
            logger.exception("oauth token store failed for %s", provider)
            return _oauth_fail_redirect(integrations_path, error="save", provider=provider, reason="store")
        return None

    try:
        async with httpx.AsyncClient(timeout=30.0) as hc:
            if provider in ("quickbooks", "xero"):
                # Intuit and Xero require HTTP Basic auth for token exchange
                tr = await hc.post(
                    cfg["token_uri"],
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": cfg["redirect_uri"],
                    },
                    auth=(cfg["client_id"], cfg["client_secret"]),
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )
            elif provider == "hubspot":
                tr = await hc.post(
                    cfg["token_uri"],
                    data={
                        "grant_type": "authorization_code",
                        "client_id": cfg["client_id"],
                        "client_secret": cfg["client_secret"],
                        "redirect_uri": cfg["redirect_uri"],
                        "code": code,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            else:
                tr = await hc.post(
                    cfg["token_uri"],
                    data={
                        "code": code,
                        "client_id": cfg["client_id"],
                        "client_secret": cfg["client_secret"],
                        "redirect_uri": cfg["redirect_uri"],
                        "grant_type": "authorization_code",
                    },
                    headers={"Accept": "application/json"},
                )
        if tr.status_code >= 400:
            reason = _oauth_error_reason_from_token_response(tr)
            logger.error(
                "oauth token exchange %s failed with status %s reason=%s: %s",
                provider, tr.status_code, reason, (tr.text or "")[:300],
            )
            return _oauth_fail_redirect(
                integrations_path, error="token", provider=provider, reason=reason,
            )
        try:
            tokens = tr.json()
        except Exception:
            logger.error("oauth token response was not JSON for %s", provider)
            return _oauth_fail_redirect(
                integrations_path, error="token", provider=provider, reason="bad_json",
            )
        if not isinstance(tokens, dict) or tokens.get("error"):
            reason = "provider_error"
            if isinstance(tokens, dict):
                err = str(tokens.get("error") or "").strip().lower()
                if err in _SAFE_OAUTH_REASONS:
                    reason = err
            logger.error("oauth token response contained an error for %s reason=%s", provider, reason)
            return _oauth_fail_redirect(
                integrations_path, error="token", provider=provider, reason=reason,
            )
        tokens = sanitize_oauth_token_payload(tokens)
        if not tokens.get("access_token"):
            logger.error("oauth token response missing access_token for %s", provider)
            return _oauth_fail_redirect(
                integrations_path, error="token", provider=provider, reason="missing_token",
            )
        if realmId:
            tokens["realmId"] = realmId
        tokens["obtained_at"] = datetime.now(timezone.utc).isoformat()
        if provider == "google":
            await _store_user_google_tokens(workspace_id, user_id, tokens)
            return RedirectResponse(f"{integrations_path}?connected=google")
        if provider == "xero":
            try:
                tenants = await xero_sync.fetch_xero_connections(tokens.get("access_token") or "")
            except Exception:
                logger.exception("xero connections lookup failed")
                return _oauth_fail_redirect(
                    integrations_path, error="token", provider=provider, reason="network",
                )
            if not tenants:
                return _oauth_fail_redirect(integrations_path, error="xero_org", provider=provider)
            if len(tenants) == 1:
                tokens["tenant_id"] = tenants[0]["tenant_id"]
                tokens["tenant_name"] = tenants[0]["tenant_name"]
                tokens.pop("pending_tenants", None)
                store_err = await _persist_tokens(tokens)
                if store_err:
                    return store_err
                return RedirectResponse(f"{integrations_path}?connected=xero")
            tokens["pending_tenants"] = tenants
            tokens.pop("tenant_id", None)
            tokens.pop("tenant_name", None)
            tokens = sanitize_oauth_token_payload(tokens)
            store_err = await _persist_tokens(tokens)
            if store_err:
                return store_err
            return RedirectResponse(f"{integrations_path}?xero_select=1")
        store_err = await _persist_tokens(tokens)
        if store_err:
            return store_err
    except Exception:
        logger.exception("oauth token exchange failed for %s", provider)
        return _oauth_fail_redirect(
            integrations_path, error="token", provider=provider, reason="network",
        )
    return RedirectResponse(f"{integrations_path}?connected={provider}")


@api_router.post("/integrations/{provider}/disconnect")
async def integration_disconnect(provider: str, principal=Depends(get_principal)):
    """Disconnect. Google clears only the calling user's tokens; others need integrations:manage."""
    if provider == "google":
        await _store_user_google_tokens(principal["workspace_id"], principal["user_id"], None)
        return {"ok": True}
    if "integrations:manage" not in perms_for(principal["pack"]):
        raise HTTPException(status_code=403, detail="Only workspace owners can disconnect this integration")
    field = {
        "quickbooks": "quickbooks_tokens",
        "xero": "xero_tokens",
        "hubspot": "hubspot_tokens",
        "sap_b1": "sap_b1_credentials",
    }.get(provider)
    if not field:
        raise HTTPException(status_code=404, detail="Unknown provider")
    unset = None
    if provider == "quickbooks":
        unset = {"qb_last_synced_at": ""}
    elif provider == "xero":
        unset = {"xero_last_synced_at": ""}
    elif provider == "hubspot":
        unset = {"hubspot_last_synced_at": ""}
    elif provider == "sap_b1":
        unset = {"sap_b1_last_synced_at": ""}
    await _store_integration_tokens(principal["workspace_id"], field, None, extra_unset=unset)
    return {"ok": True}


class XeroTenantInput(BaseModel):
    tenant_id: str



class SapB1ConnectInput(BaseModel):
    service_layer_url: str
    company_db: str
    username: str
    password: str


@api_router.post("/integrations/sap_b1/connect")
async def sap_b1_connect(payload: SapB1ConnectInput, principal=Depends(require_integration_provider("sap_b1"))):
    """Validate Service Layer login and store sealed credentials on the workspace."""
    ws_id = principal["workspace_id"]
    try:
        creds = await sap_b1_sync.login(
            service_layer_url=payload.service_layer_url,
            company_db=payload.company_db,
            username=payload.username,
            password=payload.password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except sap_b1_sync.SapB1AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc) or "SAP Business One login rejected") from exc
    except sap_b1_sync.SapB1Error as exc:
        raise HTTPException(status_code=502, detail=str(exc) or "SAP Business One connection failed") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not reach SAP Service Layer") from exc

    await _store_integration_tokens(
        ws_id, "sap_b1_credentials", creds, connected_by_user_id=principal["user_id"],
    )
    await log_activity(
        principal, "integrations", "sap_b1.connect",
        f"Connected SAP Business One ({creds.get('company_db')})",
        {"company_db": creds.get("company_db")},
    )
    return {"ok": True, "company_db": creds.get("company_db"), "service_layer_url": creds.get("service_layer_url")}


async def _run_sap_b1_sync_for_workspace(c: dict, principal: dict, *, source: str = "sap_b1_sync") -> dict:
    ws_id = c["workspace_id"]
    creds = _integration_tokens(c, "sap_b1_credentials")
    if not creds:
        raise HTTPException(status_code=400, detail="SAP Business One is not connected. Connect it in Integrations first.")
    try:
        live = await sap_b1_sync.ensure_session(creds)
    except sap_b1_sync.SapB1AuthError as exc:
        await _store_integration_tokens(ws_id, "sap_b1_credentials", None, extra_unset={"sap_b1_last_synced_at": ""})
        raise HTTPException(status_code=401, detail="SAP Business One session expired. Reconnect in Integrations.") from exc
    await _store_integration_tokens(ws_id, "sap_b1_credentials", live)
    since = c.get("sap_b1_last_synced_at")
    txns, complete = await sap_b1_sync.fetch_sap_transactions(live, since)
    synced_count = await _upsert_accounting_sync_entries(
        ws_id=ws_id, principal=principal, txns=txns, source=source,
    )
    last_synced_at = None
    if complete:
        last_synced_at = datetime.now(timezone.utc).isoformat()
        await db.workspaces.update_one({"workspace_id": ws_id}, {"$set": {"sap_b1_last_synced_at": last_synced_at}})
    return {"synced_count": synced_count, "last_synced_at": last_synced_at, "complete": complete}


@api_router.post("/integrations/sap_b1/sync")
async def sap_b1_sync_endpoint(principal=Depends(require_integration_provider("sap_b1"))):
    ws_id = principal["workspace_id"]
    c = await get_ws(ws_id)
    _require_integration_token_use(principal, c, "sap_b1_credentials")
    try:
        result = await _run_sap_b1_sync_for_workspace(c, principal, source="sap_b1_sync")
        await log_activity(
            principal, "integrations", "sap_b1.sync",
            f"Synced {result['synced_count']} transaction{'s' if result['synced_count'] != 1 else ''} from SAP Business One",
            {"synced_count": result["synced_count"]},
        )
        return result
    except sap_b1_sync.SapB1AuthError as exc:
        await _store_integration_tokens(ws_id, "sap_b1_credentials", None, extra_unset={"sap_b1_last_synced_at": ""})
        raise HTTPException(
            status_code=401,
            detail="SAP Business One connection expired. Please reconnect in Integrations.",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("SAP B1 sync failed for %s", ws_id)
        raise HTTPException(status_code=502, detail="SAP Business One sync failed. Try again shortly.") from exc


@api_router.post("/integrations/xero/select-tenant")
async def xero_select_tenant(payload: XeroTenantInput, principal=Depends(require_integration_provider("xero"))):
    """Pick which Xero organisation to sync when the user has access to more than one."""
    ws_id = principal["workspace_id"]
    c = await get_ws(ws_id)
    tokens = _require_integration_token_use(principal, c, "xero_tokens")
    if not tokens:
        raise HTTPException(status_code=400, detail="Xero is not connected. Connect it in Integrations first.")
    tenant_id = (payload.tenant_id or "").strip()
    pending = list(tokens.get("pending_tenants") or [])
    match = next((t for t in pending if t.get("tenant_id") == tenant_id), None)
    if not match and tokens.get("tenant_id") == tenant_id:
        match = {"tenant_id": tenant_id, "tenant_name": tokens.get("tenant_name") or "Xero organisation"}
    if not match and pending:
        raise HTTPException(status_code=400, detail="Choose an organisation from the list returned after Connect.")
    if not match:
        try:
            tokens = await xero_sync.refresh_xero_token(tokens)
            pending = await xero_sync.fetch_xero_connections(tokens.get("access_token") or "")
        except xero_sync.XeroAuthError as exc:
            await _store_integration_tokens(ws_id, "xero_tokens", None, extra_unset={"xero_last_synced_at": ""})
            raise HTTPException(status_code=401, detail="Xero connection expired. Please reconnect.") from exc
        match = next((t for t in pending if t.get("tenant_id") == tenant_id), None)
        if not match:
            raise HTTPException(status_code=400, detail="Unknown Xero organisation for this connection.")
    tokens["tenant_id"] = match["tenant_id"]
    tokens["tenant_name"] = match.get("tenant_name") or "Xero organisation"
    tokens.pop("pending_tenants", None)
    await _store_integration_tokens(ws_id, "xero_tokens", tokens)
    await log_activity(
        principal, "integrations", "xero.tenant",
        f"Selected Xero organisation {tokens['tenant_name']}",
        {"tenant_id": tokens["tenant_id"]},
    )
    return {"ok": True, "tenant_id": tokens["tenant_id"], "tenant_name": tokens["tenant_name"]}


async def _upsert_accounting_sync_entries(
    *,
    ws_id: str,
    principal: dict,
    txns: list,
    source: str,
) -> int:
    """Shared QuickBooks/Xero upsert into financial_entries (identical downstream shape)."""
    synced_count = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    finance_dept_id = await dept_migrate.finance_department_id(db, ws_id)
    txn_ids = _unique_ids(t.get("qb_txn_id") for t in txns)
    existing_by_id = {}
    if txn_ids:
        existing_rows = await db.financial_entries.find(
            {"workspace_id": ws_id, "qb_txn_id": {"$in": txn_ids}},
            {"_id": 0, "id": 1, "qb_txn_id": 1},
        ).to_list(len(txn_ids))
        existing_by_id = {e["qb_txn_id"]: e for e in existing_rows if e.get("qb_txn_id")}

    for txn in txns:
        txn.pop("_qb_raw_type", None)
        txn.pop("_xero_raw_type", None)
        txn.pop("_sap_raw_type", None)
        qb_txn_id = txn.pop("qb_txn_id")
        existing = existing_by_id.get(qb_txn_id)
        fields = {
            "type": txn["type"],
            "category": txn["category"],
            "name": normalize_entry_name(txn.get("name"), txn.get("category")),
            "amount": txn["amount"],
            "is_credit": bool(txn.get("is_credit") or txn.get("is_refund")),
            "month": txn["month"],
            "note": txn.get("note", ""),
            "recurring": txn.get("recurring", False),
            "source": source,
        }
        if existing:
            await db.financial_entries.update_one(
                {"workspace_id": ws_id, "qb_txn_id": qb_txn_id},
                {"$set": fields},
            )
        else:
            entry = {
                "id": f"fe_{uuid.uuid4().hex[:10]}",
                "workspace_id": ws_id,
                "department_id": finance_dept_id,
                "qb_txn_id": qb_txn_id,
                "created_by": principal["user_id"],
                "created_at": now_iso,
                **fields,
            }
            await db.financial_entries.insert_one(entry)
        synced_count += 1
    if synced_count:
        invalidate_financials_cache(ws_id)
    return synced_count


def _system_accounting_principal(workspace: dict, token_field: str) -> dict:
    """Actor for cron syncs — prefer the teammate who connected the grant."""
    by_field = _INTEGRATION_CONNECTED_BY.get(token_field)
    connected_by = (workspace.get(by_field) if by_field else None) or "system:accounting-sync"
    return {
        "user_id": connected_by,
        "workspace_id": workspace["workspace_id"],
        "role": "owner",
        "pack": "owner",
    }


async def _run_quickbooks_sync_for_workspace(c: dict, principal: dict, *, source: str = "quickbooks_sync") -> dict:
    """Refresh + fetch + upsert QuickBooks. Raises QuickBooksAuthError on expired grants."""
    ws_id = c["workspace_id"]
    tokens = _integration_tokens(c, "quickbooks_tokens")
    if not tokens:
        raise HTTPException(status_code=400, detail="QuickBooks is not connected. Connect it in Integrations first.")
    realm_id = tokens.get("realmId")
    if not realm_id:
        raise HTTPException(status_code=400, detail="QuickBooks company (realmId) is missing. Reconnect QuickBooks.")

    tokens = await qb_sync.refresh_qb_token(tokens)
    await _store_integration_tokens(ws_id, "quickbooks_tokens", tokens)
    since = c.get("qb_last_synced_at")
    txns, complete = await qb_sync.fetch_qb_transactions(tokens, realm_id, since)
    synced_count = await _upsert_accounting_sync_entries(
        ws_id=ws_id, principal=principal, txns=txns, source=source,
    )
    last_synced_at = None
    if complete:
        last_synced_at = datetime.now(timezone.utc).isoformat()
        await db.workspaces.update_one({"workspace_id": ws_id}, {"$set": {"qb_last_synced_at": last_synced_at}})
    return {"synced_count": synced_count, "last_synced_at": last_synced_at, "complete": complete}


async def _run_xero_sync_for_workspace(c: dict, principal: dict, *, source: str = "xero_sync") -> dict:
    """Refresh + fetch + upsert Xero. Raises XeroAuthError on expired grants."""
    ws_id = c["workspace_id"]
    tokens = _integration_tokens(c, "xero_tokens")
    if not tokens:
        raise HTTPException(status_code=400, detail="Xero is not connected. Connect it in Integrations first.")
    tenant_id = tokens.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Choose a Xero organisation before syncing.")

    tokens = await xero_sync.refresh_xero_token(tokens)
    await _store_integration_tokens(ws_id, "xero_tokens", tokens)
    since = c.get("xero_last_synced_at")
    txns, complete = await xero_sync.fetch_xero_transactions(tokens, tenant_id, since)
    synced_count = await _upsert_accounting_sync_entries(
        ws_id=ws_id, principal=principal, txns=txns, source=source,
    )
    last_synced_at = None
    if complete:
        last_synced_at = datetime.now(timezone.utc).isoformat()
        await db.workspaces.update_one({"workspace_id": ws_id}, {"$set": {"xero_last_synced_at": last_synced_at}})
    return {"synced_count": synced_count, "last_synced_at": last_synced_at, "complete": complete}


@api_router.post("/integrations/quickbooks/sync")
async def quickbooks_sync(principal=Depends(require_integration_provider("quickbooks"))):
    ws_id = principal["workspace_id"]
    c = await get_ws(ws_id)
    _require_integration_token_use(principal, c, "quickbooks_tokens")
    try:
        result = await _run_quickbooks_sync_for_workspace(c, principal, source="quickbooks_sync")
        await log_activity(
            principal, "integrations", "quickbooks.sync",
            f"Synced {result['synced_count']} transaction{'s' if result['synced_count'] != 1 else ''} from QuickBooks",
            {"synced_count": result["synced_count"]},
        )
        return {"ok": True, **result}
    except qb_sync.QuickBooksAuthError as exc:
        logger.warning("QuickBooks auth failed for %s: %s", ws_id, exc)
        await _store_integration_tokens(ws_id, "quickbooks_tokens", None, extra_unset={"qb_last_synced_at": ""})
        raise HTTPException(
            status_code=401,
            detail="QuickBooks connection expired. Please reconnect in Integrations.",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("QuickBooks sync failed for %s", ws_id)
        raise HTTPException(status_code=502, detail="QuickBooks sync failed. Try again shortly.") from exc


@api_router.post("/integrations/xero/sync")
async def xero_sync_endpoint(principal=Depends(require_integration_provider("xero"))):
    ws_id = principal["workspace_id"]
    c = await get_ws(ws_id)
    _require_integration_token_use(principal, c, "xero_tokens")
    try:
        result = await _run_xero_sync_for_workspace(c, principal, source="xero_sync")
        await log_activity(
            principal, "integrations", "xero.sync",
            f"Synced {result['synced_count']} transaction{'s' if result['synced_count'] != 1 else ''} from Xero",
            {"synced_count": result["synced_count"]},
        )
        return {"ok": True, **result}
    except xero_sync.XeroAuthError as exc:
        logger.warning("Xero auth failed for %s: %s", ws_id, exc)
        await _store_integration_tokens(ws_id, "xero_tokens", None, extra_unset={"xero_last_synced_at": ""})
        raise HTTPException(
            status_code=401,
            detail="Xero connection expired. Please reconnect in Integrations.",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Xero sync failed for %s", ws_id)
        raise HTTPException(status_code=502, detail="Xero sync failed. Try again shortly.") from exc


async def run_accounting_auto_sync() -> dict:
    """Cron: sync every workspace with a live QuickBooks or Xero connection."""
    cursor = db.workspaces.find(
        {
            "$or": [
                {"quickbooks_tokens": {"$exists": True, "$ne": None}},
                {"xero_tokens": {"$exists": True, "$ne": None}},
                {"sap_b1_credentials": {"$exists": True, "$ne": None}},
            ],
        },
        {"_id": 0},
    )
    workspaces = await cursor.to_list(2000)
    stats = {
        "workspaces_scanned": len(workspaces),
        "quickbooks_ok": 0,
        "quickbooks_skipped": 0,
        "quickbooks_auth_errors": 0,
        "quickbooks_errors": 0,
        "xero_ok": 0,
        "xero_skipped": 0,
        "xero_auth_errors": 0,
        "xero_errors": 0,
        "sap_b1_ok": 0,
        "sap_b1_skipped": 0,
        "sap_b1_auth_errors": 0,
        "sap_b1_errors": 0,
        "transactions_synced": 0,
    }
    for c in workspaces:
        ws_id = c.get("workspace_id") or ""
        if cred_crypto.credentials_present(c.get("quickbooks_tokens")):
            try:
                principal = _system_accounting_principal(c, "quickbooks_tokens")
                result = await _run_quickbooks_sync_for_workspace(
                    c, principal, source="quickbooks_auto_sync",
                )
                stats["quickbooks_ok"] += 1
                stats["transactions_synced"] += int(result.get("synced_count") or 0)
            except HTTPException as exc:
                if exc.status_code == 400:
                    stats["quickbooks_skipped"] += 1
                else:
                    stats["quickbooks_errors"] += 1
                    logger.warning("QuickBooks auto-sync skipped for %s: %s", ws_id, exc.detail)
            except qb_sync.QuickBooksAuthError as exc:
                stats["quickbooks_auth_errors"] += 1
                logger.warning("QuickBooks auto-sync auth failed for %s: %s", ws_id, exc)
                await _store_integration_tokens(ws_id, "quickbooks_tokens", None, extra_unset={"qb_last_synced_at": ""})
            except Exception:
                stats["quickbooks_errors"] += 1
                logger.exception("QuickBooks auto-sync failed for %s", ws_id)

        if cred_crypto.credentials_present(c.get("xero_tokens")):
            tokens = _integration_tokens(c, "xero_tokens") or {}
            if not tokens.get("tenant_id"):
                stats["xero_skipped"] += 1
                continue
            try:
                principal = _system_accounting_principal(c, "xero_tokens")
                result = await _run_xero_sync_for_workspace(
                    c, principal, source="xero_auto_sync",
                )
                stats["xero_ok"] += 1
                stats["transactions_synced"] += int(result.get("synced_count") or 0)
            except HTTPException as exc:
                if exc.status_code == 400:
                    stats["xero_skipped"] += 1
                else:
                    stats["xero_errors"] += 1
                    logger.warning("Xero auto-sync skipped for %s: %s", ws_id, exc.detail)
            except xero_sync.XeroAuthError as exc:
                stats["xero_auth_errors"] += 1
                logger.warning("Xero auto-sync auth failed for %s: %s", ws_id, exc)
                await _store_integration_tokens(ws_id, "xero_tokens", None, extra_unset={"xero_last_synced_at": ""})
            except Exception:
                stats["xero_errors"] += 1
                logger.exception("Xero auto-sync failed for %s", ws_id)


        if cred_crypto.credentials_present(c.get("sap_b1_credentials")):
            try:
                principal = _system_accounting_principal(c, "sap_b1_credentials")
                result = await _run_sap_b1_sync_for_workspace(
                    c, principal, source="sap_b1_auto_sync",
                )
                stats["sap_b1_ok"] += 1
                stats["transactions_synced"] += int(result.get("synced_count") or 0)
            except HTTPException as exc:
                if exc.status_code == 400:
                    stats["sap_b1_skipped"] += 1
                else:
                    stats["sap_b1_errors"] += 1
                    logger.warning("SAP B1 auto-sync skipped for %s: %s", ws_id, exc.detail)
            except sap_b1_sync.SapB1AuthError as exc:
                stats["sap_b1_auth_errors"] += 1
                logger.warning("SAP B1 auto-sync auth failed for %s: %s", ws_id, exc)
                await _store_integration_tokens(ws_id, "sap_b1_credentials", None, extra_unset={"sap_b1_last_synced_at": ""})
            except Exception:
                stats["sap_b1_errors"] += 1
                logger.exception("SAP B1 auto-sync failed for %s", ws_id)

    return stats


@api_router.post("/integrations/hubspot/sync")
async def hubspot_sync_endpoint(principal=Depends(require_integration_provider("hubspot"))):
    ws_id = principal["workspace_id"]
    c = await get_ws(ws_id)
    tokens = _require_integration_token_use(principal, c, "hubspot_tokens")
    if not tokens:
        raise HTTPException(status_code=400, detail="HubSpot is not connected. Connect it in Integrations first.")

    try:
        tokens = await hubspot_sync.refresh_hubspot_token(tokens)
        await _store_integration_tokens(ws_id, "hubspot_tokens", tokens)

        since = c.get("hubspot_last_synced_at")
        deals, complete = await hubspot_sync.fetch_deals(tokens, since)
        synced_count = await _upsert_hubspot_deals(ws_id=ws_id, principal=principal, deals=deals)
        last_synced_at = None
        if complete:
            last_synced_at = datetime.now(timezone.utc).isoformat()
            await db.workspaces.update_one({"workspace_id": ws_id}, {"$set": {"hubspot_last_synced_at": last_synced_at}})
        await log_activity(
            principal, "integrations", "hubspot.sync",
            f"Synced {synced_count} deal{'s' if synced_count != 1 else ''} from HubSpot",
            {"synced_count": synced_count, "complete": complete},
        )
        return {"ok": True, "synced_count": synced_count, "last_synced_at": last_synced_at, "complete": complete}

    except hubspot_sync.HubSpotAuthError as exc:
        logger.warning("HubSpot auth failed for %s: %s", ws_id, exc)
        await _store_integration_tokens(ws_id, "hubspot_tokens", None, extra_unset={"hubspot_last_synced_at": ""})
        raise HTTPException(
            status_code=401,
            detail="HubSpot connection expired. Please reconnect in Integrations.",
        ) from exc
    except Exception as exc:
        logger.exception("HubSpot sync failed for %s", ws_id)
        raise HTTPException(status_code=502, detail="HubSpot sync failed. Try again shortly.") from exc


async def _upsert_hubspot_deals(*, ws_id: str, principal: dict, deals: list) -> int:
    """Upsert HubSpot deals into the deals collection (Pipeline-compatible shape)."""
    synced_count = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    sales_dept_id = await dept_migrate.sales_department_id(db, ws_id)
    creator_name = (principal.get("name") or principal.get("email") or "HubSpot").strip()
    hs_ids = _unique_ids(d.get("hubspot_deal_id") for d in deals)
    existing_by_hs = {}
    if hs_ids:
        existing_rows = await db.deals.find(
            {"workspace_id": ws_id, "hubspot_deal_id": {"$in": hs_ids}},
            {"_id": 0, "id": 1, "hubspot_deal_id": 1},
        ).to_list(len(hs_ids))
        existing_by_hs = {e["hubspot_deal_id"]: e for e in existing_rows if e.get("hubspot_deal_id")}

    for raw in deals:
        hs_id = raw.get("hubspot_deal_id")
        if not hs_id:
            continue
        stage = raw.get("stage") if raw.get("stage") in DEAL_STAGES else "lead"
        fields = {
            "name": raw.get("name") or f"HubSpot deal {hs_id}",
            "company": raw.get("company") or "",
            "value": round(float(raw.get("value") or 0), 2),
            "stage": stage,
            "owner_name": (raw.get("owner_name") or "").strip() or creator_name,
            "close_date": raw.get("close_date") or "",
            "source": "hubspot_sync",
            "hubspot_deal_id": hs_id,
            "updated_at": now_iso,
            "department_id": sales_dept_id,
        }
        existing = existing_by_hs.get(hs_id)
        if existing:
            await db.deals.update_one(
                {"workspace_id": ws_id, "hubspot_deal_id": hs_id},
                {"$set": fields},
            )
        else:
            entry = {
                "id": f"deal_{uuid.uuid4().hex[:8]}",
                "workspace_id": ws_id,
                "created_by_user_id": principal["user_id"],
                "created_by_name": creator_name,
                "created_at": now_iso,
                **fields,
            }
            await db.deals.insert_one(entry)
        synced_count += 1
    return synced_count


@api_router.get("/integrations/google/calendar-events")
async def google_calendar_events(principal=Depends(get_principal)):
    tokens = await _require_user_google_tokens(principal)
    try:
        meetings, _, _, refreshed = await gcal.fetch_today_calendar(
            tokens, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, max_results=20,
        )
        if refreshed is not tokens:
            await _store_user_google_tokens(principal["workspace_id"], principal["user_id"], refreshed)
        return {"events": meetings, "live": True}
    except gcal.GoogleAuthError as exc:
        await _store_user_google_tokens(principal["workspace_id"], principal["user_id"], None)
        raise HTTPException(status_code=401, detail=str(exc)) from exc


class GmailDraftInput(BaseModel):
    thread_id: str = ""
    to_email: str = ""
    subject: str = ""
    snippet: str = ""


@api_router.get("/integrations/google/picker")
async def google_picker_config(principal=Depends(get_principal)):
    """Short-lived OAuth token + picker keys for Drive file picker (browser only)."""
    api_key = os.environ.get("GOOGLE_PICKER_API_KEY", "").strip()
    app_id = os.environ.get("GOOGLE_CLOUD_PROJECT_NUMBER", "").strip()
    tokens = await _user_google_tokens(principal["workspace_id"], principal["user_id"])
    if not tokens:
        return {"configured": False, "needs_reconnect": False, "access_denied": False}
    if not gcal.has_scope(tokens, "drive.file"):
        return {"configured": False, "needs_reconnect": True}
    if not api_key or not app_id:
        return {"configured": False, "needs_reconnect": False}
    try:
        refreshed = await gcal.refresh_google_token(tokens, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET)
        await _store_user_google_tokens(principal["workspace_id"], principal["user_id"], refreshed)
    except gcal.GoogleAuthError:
        return {"configured": False, "needs_reconnect": True}
    return {
        "configured": True,
        "api_key": api_key,
        "app_id": app_id,
        "client_id": GOOGLE_CLIENT_ID,
        "access_token": refreshed.get("access_token"),
    }


@api_router.post("/integrations/google/gmail-draft")
async def google_gmail_draft(payload: GmailDraftInput, principal=Depends(get_principal)):
    tokens = await _require_user_google_tokens(principal)
    if not gcal.has_scope(tokens, "gmail.compose"):
        raise HTTPException(status_code=400, detail="Reconnect Google to create Gmail drafts")
    subject = (payload.subject or "Follow up").strip()[:200]
    to_email = (payload.to_email or "").strip()[:200]
    snippet = (payload.snippet or "").strip()[:500]
    # AI drafts a real reply; on Anthropic failure we fall back to the template so
    # the Gmail draft still opens instead of 500ing the briefing button.
    try:
        body = await helm_llm.draft_gmail_reply(
            subject=subject, to_email=to_email, snippet=snippet,
        )
    except Exception:
        logger.exception("Gmail AI draft failed — using template fallback")
        body = helm_llm.fallback_gmail_draft_body(subject=subject, snippet=snippet)
    try:
        draft_id, url, refreshed = await gcal.create_gmail_draft(
            tokens, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
            to_email=to_email or "me",
            subject=subject,
            body=body,
            thread_id=(payload.thread_id or "").strip(),
        )
        await _store_user_google_tokens(principal["workspace_id"], principal["user_id"], refreshed)
    except gcal.GoogleAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Gmail draft failed")
        raise HTTPException(status_code=500, detail="Could not create Gmail draft") from exc
    return {"draft_id": draft_id, "url": url}


# ------------------------- Payments -------------------------
async def get_billing_status(workspace_id: str, pack: str):
    c = await get_ws(workspace_id)
    limits = await get_workspace_plan_limits(workspace_id)
    plan = limits["plan"]
    sub_status = c.get("subscription_status") or c.get("billing_status")
    has_customer = bool(c.get("paddle_customer_id"))
    period = plan_usage.current_usage_period(c)
    lifetime_limit = limits["ai_extracts_lifetime"]
    if lifetime_limit > 0:
        extracts_used = plan_usage.get_lifetime_extract_count(c)
        extracts_limit = lifetime_limit
        extracts_kind = "lifetime"
    else:
        extracts_used = await plan_usage.get_period_extract_count(db, workspace_id, period["key"])
        extracts_limit = limits["ai_extracts_mo"]
        extracts_kind = "period"
    seats_used = await _seat_count(workspace_id)
    seats_limit = limits["seats_limit"]
    ask_limit = limits["ask_helm_mo"]
    ask_used = await plan_usage.get_period_ask_count(db, workspace_id, period["key"]) if ask_limit > 0 else 0
    plans = helm_plans.public_plan_list()
    client_ready = bool(PADDLE_CLIENT_TOKEN)
    for row in plans:
        if row["id"] != helm_plans.PLAN_FREE:
            row["checkout_available"] = bool(row["checkout_available"] and client_ready)
    pending = c.get("pending_plan")
    return {
        "current_plan": plan,
        "legacy_plan": c.get("plan"),
        "plan_label": limits["plan_label"],
        "is_paid": limits["is_paid"],
        "pro_only": False,
        "billing_enforced": BILLING_ENFORCED,
        "requires_activation": False,
        "trial_days": TRIAL_DAYS,
        "pro_price": limits["price"] if limits["is_paid"] else helm_plans.PLANS[helm_plans.PLAN_STARTER]["price"],
        "price": limits["price"],
        "plans": plans,
        "features": dict(limits["features"]),
        "seats_used": seats_used,
        "seats_limit": seats_limit,
        "ai_extracts_used": extracts_used,
        "ai_extracts_limit": extracts_limit,
        "ai_extracts_kind": extracts_kind,
        "ask_helm_used": ask_used,
        "ask_helm_limit": ask_limit,
        "ask_helm_mo": ask_limit,
        "usage_period_key": period["key"],
        "usage_period_start": period["start"].isoformat(),
        "usage_period_end": period["end"].isoformat(),
        "pending_plan": helm_plans.normalize_plan(pending) if pending else None,
        "pending_plan_effective_at": c.get("pending_plan_effective_at"),
        "can_manage": "billing:manage" in perms_for(pack),
        "paddle_ready": client_ready and helm_plans.any_paddle_price_configured(),
        "subscription_status": sub_status,
        "billing_provider": c.get("billing_provider"),
        "portal_available": has_customer and bool(PADDLE_API_KEY),
        "demo_reset_enabled": DEMO_RESET_ENABLED,
        "canceled_at": c.get("canceled_at"),
    }


@api_router.get("/billing/plans")
async def billing_plans(response: Response, principal=Depends(get_principal)):
    # Plan limits + billing snapshot: private short cache only (never public).
    response.headers["Cache-Control"] = "private, max-age=30"
    return await get_billing_status(principal["workspace_id"], principal["pack"])


@api_router.get("/billing/status")
async def billing_status(principal=Depends(get_principal)):
    return await get_billing_status(principal["workspace_id"], principal["pack"])


class SchedulePlanInput(BaseModel):
    plan: str


@api_router.post("/billing/schedule-plan")
async def schedule_plan_change(payload: SchedulePlanInput, principal=Depends(require("billing:manage"))):
    """Schedule a downgrade for the end of the current billing period (no mid-cycle refunds)."""
    c = await get_ws(principal["workspace_id"])
    current = workspace_plan_id(c)
    target = helm_plans.normalize_plan(payload.plan)
    if target == current:
        await db.workspaces.update_one(
            {"workspace_id": principal["workspace_id"]},
            {"$unset": {"pending_plan": "", "pending_plan_effective_at": ""}},
        )
        invalidate_plan_cache(principal["workspace_id"])
        return {"ok": True, "current_plan": current, "pending_plan": None}
    if helm_plans.is_upgrade(current, target):
        raise HTTPException(
            status_code=400,
            detail="Upgrades require Paddle checkout. Use the Upgrade button on Billing.",
        )
    period = plan_usage.current_usage_period(c)
    effective_at = period["end"].isoformat()
    await db.workspaces.update_one(
        {"workspace_id": principal["workspace_id"]},
        {"$set": {"pending_plan": target, "pending_plan_effective_at": effective_at}},
    )
    invalidate_plan_cache(principal["workspace_id"])
    return {
        "ok": True,
        "current_plan": current,
        "pending_plan": target,
        "pending_plan_effective_at": effective_at,
        "message": f"Downgrade to {helm_plans.plan_def(target)['label']} takes effect at the end of the current billing period. No refund for the remaining period.",
    }


@api_router.post("/demo/reset-plan")
async def reset_plan(principal=Depends(require("billing:manage"))):
    if not DEMO_RESET_ENABLED:
        raise HTTPException(status_code=403, detail="Demo reset is disabled")
    await db.workspaces.update_one({"workspace_id": principal["workspace_id"]}, {
        "$set": {"plan": "free", "subscription_status": None, "billing_status": None},
        "$unset": {
            "paddle_subscription_id": "", "paddle_customer_id": "",
            "pending_plan": "", "pending_plan_effective_at": "",
        },
    })
    invalidate_plan_cache(principal["workspace_id"])
    return {"ok": True}


# ------------------------- Paddle Billing -------------------------
def _verify_paddle_signature(raw: bytes, signature: str) -> bool:
    """Verify Paddle-Signature (ts=<unix>;h1=<hex>[;h1=...]) over `ts:<raw body>`."""
    if not signature or not PADDLE_WEBHOOK_SECRET:
        return False
    parts = {}
    for part in signature.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            parts.setdefault(k, []).append(v)
    ts = (parts.get("ts") or [None])[0]
    h1s = parts.get("h1") or []
    if not ts or not h1s:
        return False
    try:
        if abs(datetime.now(timezone.utc).timestamp() - int(ts)) > 300:
            return False
    except ValueError:
        return False
    signed = f"{ts}:".encode() + raw
    expected = hmac.new(PADDLE_WEBHOOK_SECRET.encode(), signed, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, h) for h in h1s)


class PaddleConfigInput(BaseModel):
    plan: str = helm_plans.PLAN_STARTER


@api_router.post("/billing/paddle/config")
async def paddle_config(request: Request, principal=Depends(require("billing:manage"))):
    if not PADDLE_CLIENT_TOKEN:
        raise HTTPException(status_code=400, detail="Paddle is not configured")
    try:
        raw = await request.json()
    except Exception:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    target = helm_plans.normalize_plan(raw.get("plan") or helm_plans.PLAN_STARTER)
    if target == helm_plans.PLAN_FREE:
        raise HTTPException(status_code=400, detail="Free plan does not require checkout")
    price_id = helm_plans.paddle_price_id_for(target)
    if not price_id:
        raise HTTPException(
            status_code=400,
            detail=f"Checkout for {helm_plans.plan_def(target)['label']} is not configured yet. Set the Paddle price ID env var",
        )
    nonce = uuid.uuid4().hex
    await db.paddle_intents.insert_one({
        "_id": nonce,
        "workspace_id": principal["workspace_id"],
        "user_id": principal["user_id"],
        "price_id": price_id,
        "plan": target,
        "used": False,
        "created_at": datetime.now(timezone.utc),
    })
    return {
        "client_token": PADDLE_CLIENT_TOKEN,
        "price_id": price_id,
        "plan": target,
        "trial_days": TRIAL_DAYS,
        "environment": PADDLE_ENV,
        "checkout_nonce": nonce,
        "workspace_id": principal["workspace_id"],
        "user_id": principal["user_id"],
        "email": principal.get("email"),
    }


def _paddle_trial_fields(data: dict, status: str, existing: dict | None = None) -> dict:
    """Persist trial end from Paddle. Only clear the once-flag when the end date changes."""
    if status != "trialing":
        return {}
    out = {}
    end = helm_retention.trial_end_from_paddle_payload(data)
    if not end:
        return out
    out["trial_ends_at"] = end
    if existing is not None and existing.get("trial_ends_at") != end:
        out["trial_reminder_sent"] = False
    return out


async def _maybe_mark_referral_converted(workspace_id: str | None, subscription_status: str | None):
    """Flip referral status to converted when a referred company starts paying."""
    if not workspace_id:
        return
    ws = await db.workspaces.find_one(
        {"workspace_id": workspace_id},
        {"_id": 0, "workspace_id": 1, "plan": 1, "referred_by": 1, "referral_id": 1, "subscription_status": 1},
    )
    if not ws:
        return
    if not helm_referrals.should_mark_converted(subscription_status or ws.get("subscription_status"), ws.get("plan")):
        return
    try:
        await helm_referrals.mark_referral_converted(db, ws)
    except Exception:
        logger.exception("referral conversion update failed for %s", workspace_id)


def _paddle_price_id_from_event(data: dict | None) -> Optional[str]:
    """Best-effort price id from a Paddle Billing subscription/transaction payload."""
    data = data or {}
    items = data.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            price = item.get("price") if isinstance(item.get("price"), dict) else {}
            pid = str(price.get("id") or item.get("price_id") or "").strip()
            if pid:
                return pid
    details = data.get("details") if isinstance(data.get("details"), dict) else {}
    for item in details.get("line_items") or []:
        if not isinstance(item, dict):
            continue
        price = item.get("price") if isinstance(item.get("price"), dict) else {}
        pid = str(price.get("id") or item.get("price_id") or "").strip()
        if pid:
            return pid
    return None


async def _paddle_provision(event, status: str = "active"):
    data = event.get("data") or {}
    custom = data.get("custom_data") or {}
    nonce = custom.get("checkout_nonce")
    workspace_id = custom.get("workspace_id")
    user_id = custom.get("user_id")
    sub_id = data.get("subscription_id") or data.get("id")
    now_iso = event.get("occurred_at") or datetime.now(timezone.utc).isoformat()
    event_price_id = _paddle_price_id_from_event(data)

    # Recovery path: subscription reactivated / updated without checkout nonce
    # (e.g. past_due → active, or portal plan change). Bind by paddle_subscription_id.
    if not (nonce and workspace_id and user_id):
        if not sub_id or status not in ("active", "trialing"):
            return
        prev = await db.workspaces.find_one(
            {"paddle_subscription_id": sub_id},
            {"_id": 0, "workspace_id": 1, "subscription_status": 1, "plan": 1},
        )
        recovery = {
            "subscription_status": status,
            "billing_status": status,
            "paddle_last_event_at": now_iso,
        }
        if data.get("customer_id"):
            recovery["paddle_customer_id"] = data["customer_id"]
        # Portal upgrades/downgrades send subscription.updated without checkout nonce —
        # map the live Paddle price onto Helm plan entitlements.
        mapped_plan = helm_plans.plan_for_paddle_price(event_price_id)
        if mapped_plan:
            recovery["plan"] = mapped_plan
        recovery.update(_paddle_trial_fields(data, status))
        await db.workspaces.update_one(
            {"paddle_subscription_id": sub_id},
            {"$set": recovery, "$unset": {"canceled_at": ""}},
        )
        if prev:
            if mapped_plan:
                invalidate_plan_cache(prev.get("workspace_id"))
            await helm_analytics.emit_billing_funnel(
                db, prev.get("workspace_id"), user_id,
                prev.get("subscription_status"), status, mapped_plan or prev.get("plan"),
            )
            await _maybe_mark_referral_converted(prev.get("workspace_id"), status)
        return

    intent = await db.paddle_intents.find_one({"_id": nonce})
    if not intent or intent.get("workspace_id") != workspace_id or intent.get("user_id") != user_id:
        return
    if intent.get("used"):
        # Replay / reused checkout nonce — do not re-provision entitlements.
        return
    # Prefer the live event price when present (covers mid-checkout price changes),
    # then the intent, then Starter.
    plan = (
        helm_plans.plan_for_paddle_price(event_price_id)
        or intent.get("plan")
        or helm_plans.plan_for_paddle_price(intent.get("price_id"))
        or helm_plans.PLAN_STARTER
    )
    plan = helm_plans.normalize_plan(plan)
    if plan == helm_plans.PLAN_FREE:
        plan = helm_plans.PLAN_STARTER
    set_fields = {
        "plan": plan, "billing_provider": "paddle",
        "paddle_subscription_id": sub_id,
        "paddle_customer_id": data.get("customer_id"),
        "paddle_last_event_at": now_iso,
        "subscription_status": status, "billing_status": status,
        "subscription_started_at": now_iso,
    }
    # Anchor usage periods on first provision only
    existing = await db.workspaces.find_one(
        {"workspace_id": workspace_id},
        {"_id": 0, "billing_period_start": 1, "trial_ends_at": 1, "subscription_status": 1},
    )
    if not (existing or {}).get("billing_period_start"):
        set_fields["billing_period_start"] = now_iso
    set_fields.update(_paddle_trial_fields(data, status, existing))
    await db.workspaces.update_one({"workspace_id": workspace_id}, {"$set": set_fields, "$unset": {
        "canceled_at": "", "pending_plan": "", "pending_plan_effective_at": "",
    }})
    invalidate_plan_cache(workspace_id)
    await db.paddle_intents.update_one({"_id": nonce}, {"$set": {"used": True}})
    await helm_analytics.emit_billing_funnel(
        db, workspace_id, user_id,
        (existing or {}).get("subscription_status"),
        status,
        plan,
    )
    await _maybe_mark_referral_converted(workspace_id, status)


async def _paddle_downgrade(event, status: str):
    data = event.get("data") or {}
    sub_id = data.get("id")
    filt = {"paddle_subscription_id": sub_id} if sub_id else {}
    if not filt:
        return
    now = event.get("occurred_at") or datetime.now(timezone.utc).isoformat()
    prev = await db.workspaces.find_one(
        filt, {"_id": 0, "workspace_id": 1, "subscription_status": 1, "plan": 1},
    )
    if status in ("canceled", "cancelled"):
        await db.workspaces.update_one(filt, {
            "$set": {
                "plan": "free", "subscription_status": status, "billing_status": status,
                "canceled_at": now, "paddle_last_event_at": now,
            },
            "$unset": {"paddle_subscription_id": ""},
        })
    else:
        await db.workspaces.update_one(filt, {
            "$set": {"subscription_status": status, "billing_status": status, "paddle_last_event_at": now},
        })
    if prev and prev.get("workspace_id"):
        invalidate_plan_cache(prev["workspace_id"])
        await helm_analytics.emit_billing_funnel(
            db, prev.get("workspace_id"), None,
            prev.get("subscription_status"), status, prev.get("plan"),
        )


@api_router.post("/payments/paddle/portal")
async def paddle_portal(principal=Depends(require("billing:manage"))):
    c = await get_ws(principal["workspace_id"])
    customer_id = c.get("paddle_customer_id")
    if not customer_id:
        raise HTTPException(status_code=400, detail="Subscribe first to manage billing")
    if not PADDLE_API_KEY:
        raise HTTPException(status_code=400, detail="Paddle is not configured")
    body = {}
    if c.get("paddle_subscription_id"):
        body["subscription_ids"] = [c["paddle_subscription_id"]]
    try:
        async with httpx.AsyncClient() as hc:
            r = await hc.post(
                f"{PADDLE_API_BASE}/customers/{customer_id}/portal-sessions",
                headers={"Authorization": f"Bearer {PADDLE_API_KEY}", "Content-Type": "application/json"},
                json=body,
            )
        if r.status_code >= 400:
            logger.error("paddle portal error: %s", r.text[:500])
            raise HTTPException(status_code=502, detail="Could not open billing portal")
        payload = r.json().get("data") or {}
        url = (payload.get("urls") or {}).get("general", {}).get("overview")
        if not url:
            raise HTTPException(status_code=502, detail="Portal URL not returned")
        return {"url": url}
    except HTTPException:
        raise
    except Exception:
        logger.exception("paddle portal failed")
        raise HTTPException(status_code=502, detail="Could not open billing portal")


@api_router.post("/webhook/paddle")
async def paddle_webhook(request: Request):
    raw = await request.body()
    sig = request.headers.get("Paddle-Signature", "")
    if not raw or not _verify_paddle_signature(raw, sig):
        raise HTTPException(status_code=400, detail="Invalid Paddle signature")
    event = json.loads(raw)
    event_id = event.get("event_id")
    event_type = event.get("event_type")
    if not event_id:
        raise HTTPException(status_code=400, detail="Missing event_id")
    try:
        await db.paddle_events.insert_one({"_id": event_id, "type": event_type, "received_at": datetime.now(timezone.utc)})
    except Exception as e:
        if "e11000" in str(e).lower() or "duplicate key" in str(e).lower():
            return {"received": True}
        raise
    if event_type == "transaction.completed":
        await _paddle_provision(event, status="active")
    elif event_type in ("subscription.created", "subscription.activated", "subscription.updated", "subscription.trialing"):
        status = (event.get("data") or {}).get("status") or "active"
        if status in ("active", "trialing"):
            await _paddle_provision(event, status=status)
    elif event_type in ("subscription.canceled", "subscription.cancelled"):
        await _paddle_downgrade(event, "canceled")
    elif event_type == "subscription.paused":
        await _paddle_downgrade(event, "paused")
    elif event_type in ("subscription.past_due", "subscription.past-due"):
        await _paddle_downgrade(event, "past_due")
    return {"received": True}


# ------------------------- GDPR / account -------------------------
_WORKSPACE_COLLECTIONS = (
    "financial_entries", "deals", "documents", "report_documents", "report_digests", "activities", "updates",
    "chat_messages", "private_notes", "paddle_intents", "payment_transactions",
    "document_rate_events", "insights_rate_events", "ask_helm_rate_events",
    "document_ai_usage",
    "oauth_states",
    "product_events",
    "production_work_orders",
    "procurement_requests", "legal_matters",
    "maintenance_tickets", "hr_onboarding_template", "hr_onboarding_instances",
    "hr_employees", "hr_offboarding_template", "hr_offboarding_instances",
    "hr_leave_requests",
    "department_report_drafts",
)

# Per-provider stamp: who connected the shared workspace OAuth grant.
# Google is per-user (user_google_tokens) — not stamped on the workspace.
_INTEGRATION_CONNECTED_BY = {
    "quickbooks_tokens": "quickbooks_tokens_connected_by",
    "xero_tokens": "xero_tokens_connected_by",
    "hubspot_tokens": "hubspot_tokens_connected_by",
    "sap_b1_credentials": "sap_b1_credentials_connected_by",
}
_INTEGRATION_CONNECTED_AT = {
    "quickbooks_tokens": "quickbooks_tokens_connected_at",
    "xero_tokens": "xero_tokens_connected_at",
    "hubspot_tokens": "hubspot_tokens_connected_at",
    "sap_b1_credentials": "sap_b1_credentials_connected_at",
}

_EXPORT_ROW_CAP = 5000


def _strip_sensitive(doc: dict) -> dict:
    if not doc:
        return doc
    out = {k: v for k, v in doc.items() if k not in (
        "password", "password_hash", "oauth_session_token_enc",
        "google_tokens", "quickbooks_tokens", "xero_tokens", "hubspot_tokens", "sap_b1_credentials",
    )}
    return out


async def require_workspace(user=Depends(get_user)):
    ws_id = user.get("active_workspace_id")
    membership = None
    if ws_id:
        membership = await db.memberships.find_one(
            {"user_id": user["user_id"], "workspace_id": ws_id, "status": "active"}, {"_id": 0})
    if not membership:
        membership = await db.memberships.find_one(
            {"user_id": user["user_id"], "status": "active"}, {"_id": 0})
    if not membership:
        raise HTTPException(status_code=403, detail="No workspace")
    return membership["workspace_id"]


async def get_membership(user=Depends(get_user), workspace_id: str = Depends(require_workspace)):
    m = await db.memberships.find_one(
        {"user_id": user["user_id"], "workspace_id": workspace_id, "status": "active"}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=403, detail="No workspace membership")
    return m


async def _export_workspace_package(ws_id: str) -> dict:
    """Full workspace data package for a DSAR / owner export (tokens stripped)."""
    ws = await db.workspaces.find_one({"workspace_id": ws_id}, {"_id": 0})
    departments = await db.departments.find({"workspace_id": ws_id}, {"_id": 0}).to_list(200)
    dept_ids = [d["department_id"] for d in departments if d.get("department_id")]
    department_members = []
    if dept_ids:
        department_members = await db.department_members.find(
            {"department_id": {"$in": dept_ids}}, {"_id": 0},
        ).to_list(5000)
    memberships = await db.memberships.find({"workspace_id": ws_id}, {"_id": 0}).to_list(500)
    collections = {}
    for coll in _WORKSPACE_COLLECTIONS:
        rows = await db[coll].find({"workspace_id": ws_id}, {"_id": 0}).to_list(_EXPORT_ROW_CAP)
        collections[coll] = [_strip_sensitive(r) for r in rows]
        if len(rows) >= _EXPORT_ROW_CAP:
            collections[f"{coll}__truncated"] = True
    return {
        "workspace": _strip_sensitive(ws) if ws else None,
        "memberships": memberships,
        "departments": departments,
        "department_members": department_members,
        "collections": collections,
    }


@api_router.get("/account/export")
async def export_account(user=Depends(get_user)):
    """GDPR-oriented export: account profile plus owned workspace data packages."""
    user_doc = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    memberships = await db.memberships.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(100)
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": _strip_sensitive(user_doc),
        "memberships": memberships,
        "my_updates": await db.updates.find(
            {"user_id": user["user_id"]}, {"_id": 0},
        ).to_list(_EXPORT_ROW_CAP),
        "my_chat_messages": await db.chat_messages.find(
            {"user_id": user["user_id"]}, {"_id": 0},
        ).to_list(_EXPORT_ROW_CAP),
        "my_private_notes": await db.private_notes.find(
            {"user_id": user["user_id"]}, {"_id": 0},
        ).to_list(_EXPORT_ROW_CAP),
        "my_google_connections": [
            _strip_sensitive(r) for r in await db.user_google_tokens.find(
                {"user_id": user["user_id"]}, {"_id": 0},
            ).to_list(_EXPORT_ROW_CAP)
        ],
        "my_product_events": await db.product_events.find(
            {"user_id": user["user_id"]}, {"_id": 0},
        ).to_list(_EXPORT_ROW_CAP),
    }
    admin_ws = [
        m["workspace_id"] for m in memberships
        if m.get("status") == "active" and (m.get("role") == "owner" or pack_of(m) == "owner")
    ]
    payload["owned_workspaces"] = [
        await _export_workspace_package(ws_id) for ws_id in admin_ws
    ]
    # Keep a light summary for non-owned memberships (no other tenants' data).
    member_ws = [
        m["workspace_id"] for m in memberships
        if m.get("status") == "active" and m["workspace_id"] not in admin_ws
    ]
    if member_ws:
        by_ws = await _docs_by_key(db.workspaces, "workspace_id", member_ws, {"_id": 0, "workspace_id": 1, "name": 1, "plan": 1})
        payload["member_workspaces"] = [
            {"workspace_id": wid, "name": (by_ws.get(wid) or {}).get("name"), "plan": (by_ws.get(wid) or {}).get("plan")}
            for wid in member_ws
        ]
    return payload


class AppearanceInput(BaseModel):
    appearance: str


APPEARANCE_VALUES = frozenset({"light", "dark", "system"})


def _normalize_appearance(value) -> str:
    raw = str(value or "light").strip().lower()
    return raw if raw in APPEARANCE_VALUES else "light"


@api_router.patch("/account/appearance")
async def update_appearance(body: AppearanceInput, user=Depends(get_user)):
    """Persist cockpit light/dark/system preference on the user document."""
    appearance = str(body.appearance or "").strip().lower()
    if appearance not in APPEARANCE_VALUES:
        raise HTTPException(status_code=400, detail="appearance must be light, dark, or system")
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"appearance": appearance}},
    )
    return {"appearance": appearance}




class AgeConfirmInput(BaseModel):
    confirmed: bool = True


@api_router.patch("/account/age-confirmation")
async def confirm_age(payload: AgeConfirmInput, user=Depends(get_user)):
    """Record that the account holder confirmed they are 18+ (or guardian-supervised)."""
    if not payload.confirmed:
        raise HTTPException(status_code=400, detail="Age confirmation is required to use Trenston")
    now = datetime.now(timezone.utc).isoformat()
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"age_confirmed": True, "age_confirmed_at": now}},
    )
    return {"age_confirmed": True, "age_confirmed_at": now}

@api_router.delete("/account")
async def delete_account(user=Depends(get_user)):
    memberships = await db.memberships.find(
        {"user_id": user["user_id"], "status": "active"}, {"_id": 0}).to_list(50)
    owned = [m for m in memberships if m.get("role") == "owner" or pack_of(m) == "owner"]
    sole_owner = []
    for m in owned:
        others = await db.memberships.find(
            {"workspace_id": m["workspace_id"], "status": "active", "user_id": {"$ne": user["user_id"]}},
            {"_id": 0},
        ).to_list(50)
        other_owners = [o for o in others if o.get("role") == "owner" or pack_of(o) == "owner"]
        if not other_owners:
            sole_owner.append(m["workspace_id"])
    if sole_owner:
        raise HTTPException(
            status_code=400,
            detail="Transfer or delete workspace first",
        )
    uid = user["user_id"]
    await db.memberships.delete_many({"user_id": uid})
    await db.user_sessions.delete_many({"user_id": uid})
    await db.chat_messages.delete_many({"user_id": uid})
    await db.updates.delete_many({"user_id": uid})
    await db.private_notes.delete_many({"user_id": uid})
    await db.user_google_tokens.delete_many({"user_id": uid})
    await db.product_events.delete_many({"user_id": uid})
    # Anonymize activity rows rather than deleting the company audit trail.
    await db.activities.update_many(
        {"actor_user_id": uid},
        {"$set": {"actor_user_id": None, "actor_name": "Deleted user"}},
    )
    await db.users.delete_one({"user_id": uid})
    return {"ok": True}


async def _delete_workspace_data(ws_id: str):
    # Delete private objects before their Mongo references. If object storage is
    # unavailable, fail visibly so the owner can retry instead of silently
    # leaving inaccessible customer files behind.
    document_rows = await db.documents.find(
        {"workspace_id": ws_id}, {"_id": 0, "storage_key": 1},
    ).to_list(10000)
    report_doc_rows = await db.report_documents.find(
        {"workspace_id": ws_id}, {"_id": 0, "storage_key": 1},
    ).to_list(10000)
    legal_rows = await db.legal_matters.find(
        {"workspace_id": ws_id}, {"_id": 0, "document_ref": 1},
    ).to_list(10000)
    storage_keys = {
        row.get("storage_key")
        for row in document_rows
        if row.get("storage_key")
    }
    storage_keys.update(
        row.get("storage_key")
        for row in report_doc_rows
        if row.get("storage_key")
    )
    for row in legal_rows:
        ref = row.get("document_ref") or {}
        if isinstance(ref, dict) and ref.get("storage_key"):
            storage_keys.add(ref["storage_key"])
    if storage_keys:
        if not doc_storage.r2_configured():
            raise HTTPException(
                status_code=503,
                detail="Document storage is unavailable; workspace deletion was not completed. Try again shortly.",
            )
        for key in storage_keys:
            try:
                await asyncio.to_thread(doc_storage.delete_document, key)
            except Exception as exc:
                logger.exception("workspace deletion could not remove private object %s", key)
                raise HTTPException(
                    status_code=503,
                    detail="A private document could not be deleted; workspace deletion was not completed. Try again shortly.",
                ) from exc

    departments = await db.departments.find(
        {"workspace_id": ws_id}, {"_id": 0, "department_id": 1},
    ).to_list(1000)
    department_ids = [d["department_id"] for d in departments if d.get("department_id")]
    if department_ids:
        await db.department_members.delete_many({"department_id": {"$in": department_ids}})
    for coll in _WORKSPACE_COLLECTIONS:
        await db[coll].delete_many({"workspace_id": ws_id})
    await db.user_google_tokens.delete_many({"workspace_id": ws_id})
    await db.departments.delete_many({"workspace_id": ws_id})
    await db.memberships.delete_many({"workspace_id": ws_id})
    await db.referrals.delete_many({"referred_workspace_id": ws_id})
    await db.workspaces.delete_one({"workspace_id": ws_id})


async def _delete_workspace_handler(principal: dict):
    membership = await db.memberships.find_one(
        {"user_id": principal["user_id"], "workspace_id": principal["workspace_id"], "status": "active"},
        {"_id": 0},
    )
    if not membership or (membership.get("role") != "owner" and pack_of(membership) != "owner"):
        raise HTTPException(status_code=403, detail="Only workspace owners can delete the workspace")
    await _delete_workspace_data(principal["workspace_id"])
    return {"ok": True}


@api_router.delete("/workspace")
async def delete_workspace(principal=Depends(require("billing:manage"))):
    return await _delete_workspace_handler(principal)


@api_router.delete("/workspaces/current")
async def delete_workspace_current(principal=Depends(require("billing:manage"))):
    return await _delete_workspace_handler(principal)


async def _mongo_ping() -> bool:
    try:
        await asyncio.wait_for(db.command("ping", maxTimeMS=2000), timeout=3.0)
        return True
    except Exception:
        return False


async def _require_mongo() -> None:
    if await _mongo_ping():
        return
    await _connect_mongo_at_startup()
    if not await _mongo_ping():
        raise HTTPException(
            status_code=503,
            detail="Database unavailable. Check MONGO_URL and Atlas Network Access on Render.",
        )


async def _probe_mongo_candidates() -> list[dict]:
    results: list[dict] = []
    for url in _mongo_candidate_urls():
        probe = _make_mongo_client(url)
        ok = False
        err: str | None = None
        try:
            await asyncio.wait_for(probe.admin.command("ping", maxTimeMS=2000), timeout=3.0)
            ok = True
        except Exception as exc:
            err = type(exc).__name__
        finally:
            probe.close()
        results.append({
            "source": _mongo_source_label(url),
            "url": _redact_mongo_url(url),
            "ok": ok,
            "error": err,
        })
    return results


@api_router.get("/setup/status")
async def setup_status(request: Request):
    """Production readiness probe — boolean health only (no infra inventory)."""
    _require_setup_secret(request)
    mongo_ok = await _mongo_ping()
    clerk_ok = False
    if clerk_auth.clerk_configured():
        try:
            clerk_ok = bool(await clerk_auth.clerk_api_ok())
        except Exception:
            clerk_ok = False
    r2 = await asyncio.to_thread(doc_storage.probe_r2)
    return {
        "ok": bool(mongo_ok and clerk_auth.clerk_configured()),
        "mongo": bool(mongo_ok),
        "clerk_configured": clerk_auth.clerk_configured(),
        "clerk_api_ok": clerk_ok,
        "r2": r2,
    }


@api_router.get("/setup/google-oauth")
async def setup_google_oauth(request: Request):
    """Clerk Google OAuth readiness — verifies redirect URI is registered in Google Cloud."""
    _require_setup_secret(request)
    if not clerk_auth.clerk_configured():
        raise HTTPException(status_code=400, detail="Clerk is not configured")
    return await clerk_auth.clerk_google_oauth_status()


@api_router.post("/setup/clerk-sync")
async def setup_clerk_sync(request: Request):
    """Force Clerk instance sync (allowed_origins + development_origin for Vercel)."""
    _require_setup_secret(request)
    if not clerk_auth.clerk_configured():
        raise HTTPException(status_code=400, detail="Clerk is not configured")
    result = await clerk_auth.sync_clerk_instance()
    if not result.get("synced"):
        raise HTTPException(status_code=503, detail=result)
    return result


@api_router.post("/admin/cleanup-orphaned-documents")
async def cleanup_orphaned_documents_admin(request: Request):
    """Delete uncommitted document uploads older than DOC_ORPHAN_RETENTION_DAYS (default 7)."""
    _require_setup_secret(request)
    return await document_cleanup.cleanup_orphaned_documents(db)


# Cap for proactive cron sweeps (same order as retention / department drafts).
MAX_PROACTIVE_CRON_WORKSPACES = 400


async def run_daily_alerts_cron() -> dict:
    """Cron: regenerate insights for every workspace and fire high-severity email/Slack.

    Uses _generate_insights(..., raise_on_rate_limit=False), which already calls
    _notify_high_severity_alerts and respects notified_signal_ids debounce.
    One workspace failure does not stop the rest of the run.
    """
    workspaces = await db.workspaces.find(
        {},
        {"_id": 0, "workspace_id": 1, "name": 1},
    ).to_list(MAX_PROACTIVE_CRON_WORKSPACES)
    stats = {
        "workspaces_scanned": len(workspaces),
        "ok": 0,
        "skipped": 0,
        "errors": 0,
        "new_alerts": 0,
    }
    for ws in workspaces:
        wid = (ws.get("workspace_id") or "").strip()
        if not wid:
            continue
        try:
            result = await _generate_insights(wid, raise_on_rate_limit=False)
            if result.get("skipped"):
                stats["skipped"] += 1
                continue
            stats["ok"] += 1
            notify = result.get("notifications") or {}
            stats["new_alerts"] += int(notify.get("new_alerts") or 0)
        except Exception:
            stats["errors"] += 1
            logger.exception("daily alerts cron failed for workspace %s", wid)
    return stats


def _iso_week_key(now: datetime | None = None) -> str:
    """UTC ISO week id for weekly digest debounce (e.g. 2026-W38)."""
    now = now or datetime.now(timezone.utc)
    return now.strftime("%G-W%V")


def _weekly_digest_email_html(*, workspace_name: str, app_url: str, unsubscribe_url: str = "") -> str:
    import email_compliance as ec

    name = html.escape(workspace_name or "your company")
    link = html.escape((app_url or "").rstrip("/") + "/app/reports", quote=True)
    footer = (
        ec.marketing_footer_html(unsubscribe_url=unsubscribe_url)
        if unsubscribe_url
        else """\
<tr><td style="padding:20px 36px 30px 36px;border-top:1px solid rgba(255,255,255,0.06);">
<p style="color:#52525b;font-size:12px;margin:0;line-height:1.6;">Know what matters before your first meeting.</p>
</td></tr>"""
    )
    return f"""\
<!DOCTYPE html><html><body style="margin:0;padding:0;background:#09090b;font-family:'Helvetica Neue',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#09090b;padding:40px 0;">
<tr><td align="center">
<table width="480" cellpadding="0" cellspacing="0" style="background:#121214;border:1px solid rgba(255,255,255,0.08);border-radius:14px;overflow:hidden;">
<tr><td style="padding:32px 36px 8px 36px;">
<p style="color:#c9a962;font-size:11px;letter-spacing:2px;text-transform:uppercase;margin:0;">Weekly pack</p>
<h1 style="color:#ffffff;font-size:24px;font-weight:400;margin:10px 0 0 0;line-height:1.3;">This week's briefing for<br><span style="color:#c9a962;">{name}</span></h1>
<p style="color:#a1a1aa;font-size:15px;line-height:1.6;margin:18px 0 0 0;">Your Trenston weekly pack is attached as a PDF. No need to log in to read it — open the attachment, or review it in the app when you are ready.</p>
<table cellpadding="0" cellspacing="0" style="margin:28px 0 8px 0;"><tr>
<td style="background:#c9a962;border-radius:8px;">
<a href="{link}" style="display:inline-block;padding:12px 26px;color:#09090b;font-size:14px;font-weight:600;text-decoration:none;">Open Reports in Trenston &rarr;</a>
</td></tr></table>
</td></tr>
{footer}
</table>
</td></tr></table></body></html>"""


async def run_weekly_digest_cron() -> dict:
    """Cron: generate weekly pack PDF and email it to CEO/owner recipients.

    Kept as a separate runner (and Render cron) from daily alerts so schedules stay
    independent — daily at a fixed UTC morning hour, weekly on Mondays.
    Debounces with weekly_digest_emailed_week (ISO week) so a re-run the same week
    does not re-send. Respects the same plan gate as /api/reports/weekly-pack.
    Commercial: CAN-SPAM footer + immediate email_suppressions check per recipient.
    """
    import weekly_pack_export as pack_pdf
    import email_compliance as ec

    workspaces = await db.workspaces.find({}, {"_id": 0}).to_list(MAX_PROACTIVE_CRON_WORKSPACES)
    week = _iso_week_key()
    app_url = _app_base_url()
    api_base = public_api_origin()
    stats = {
        "workspaces_scanned": len(workspaces),
        "week": week,
        "sent": 0,
        "skipped_already": 0,
        "skipped_plan": 0,
        "skipped_no_recipients": 0,
        "skipped_suppressed": 0,
        "skipped_empty": 0,
        "send_failed": 0,
        "errors": 0,
    }
    for c in workspaces:
        wid = (c.get("workspace_id") or "").strip()
        if not wid:
            continue
        try:
            if (c.get("weekly_digest_emailed_week") or "") == week:
                stats["skipped_already"] += 1
                continue
            if not workspace_allows(c, helm_plans.FEATURE_ADVANCED_REPORTS):
                stats["skipped_plan"] += 1
                continue
            recipients = await _alert_recipient_emails(wid)
            if not recipients:
                stats["skipped_no_recipients"] += 1
                continue
            sendable = await ec.filter_unsuppressed(db, recipients)
            if not sendable:
                stats["skipped_suppressed"] += 1
                continue
            pack = await _generate_weekly_pack_content(wid)
            content = (pack.get("content") or "").strip()
            if not content:
                stats["skipped_empty"] += 1
                continue
            ws_name = pack.get("workspace_name") or c.get("name") or "Company"
            pdf = pack_pdf.render_weekly_pack_pdf(content, workspace_name=ws_name)
            filename = pack_pdf.pdf_filename(ws_name)
            any_sent = False
            for addr in sendable:
                unsub = ec.unsubscribe_url(app_url, addr, secret=SESSION_SECRET)
                one_click = ec.api_unsubscribe_url(api_base, addr, secret=SESSION_SECRET)
                email_result = await send_resend_email(
                    to=[addr],
                    subject=f"Your Trenston weekly pack: {ws_name}",
                    html=_weekly_digest_email_html(
                        workspace_name=ws_name,
                        app_url=app_url,
                        unsubscribe_url=unsub,
                    ),
                    attachments=[{
                        "filename": filename,
                        "content": pdf,
                        "content_type": "application/pdf",
                    }],
                    headers=ec.list_unsubscribe_headers(one_click),
                )
                if email_result.get("sent"):
                    any_sent = True
            if any_sent:
                await db.workspaces.update_one(
                    {"workspace_id": wid},
                    {"$set": {
                        "weekly_digest_emailed_week": week,
                        "weekly_digest_emailed_at": datetime.now(timezone.utc).isoformat(),
                    }},
                )
                stats["sent"] += 1
            else:
                stats["send_failed"] += 1
        except Exception:
            stats["errors"] += 1
            logger.exception("weekly digest cron failed for workspace %s", wid)
    return stats


def _daily_briefing_date_key(now: datetime | None = None) -> str:
    """UTC calendar date for daily briefing debounce (YYYY-MM-DD)."""
    now = now or datetime.now(timezone.utc)
    return now.date().isoformat()


def _daily_briefing_email_html(*, workspace_name: str, data: dict, app_url: str, unsubscribe_url: str = "") -> str:
    import ops_briefing as ob
    return ob.daily_briefing_email_html(
        workspace_name=workspace_name,
        data=data,
        app_url=app_url,
        unsubscribe_url=unsubscribe_url,
    )


async def run_daily_briefing_cron() -> dict:
    """Cron: email a morning ops snapshot to CEO/owner recipients.

    Separate from weekly pack digest and from daily insights alerts. Debounces
    with daily_briefing_emailed_date (UTC ISO date) so a re-run the same day
    does not double-send. Recipients + suppression list match the weekly digest.
    Fixed UTC morning hour (v1 — no per-workspace timezone field yet).
    """
    import email_compliance as ec

    workspaces = await db.workspaces.find({}, {"_id": 0}).to_list(MAX_PROACTIVE_CRON_WORKSPACES)
    day = _daily_briefing_date_key()
    app_url = _app_base_url()
    api_base = public_api_origin()
    stats = {
        "workspaces_scanned": len(workspaces),
        "day": day,
        "sent": 0,
        "skipped_already": 0,
        "skipped_no_recipients": 0,
        "skipped_suppressed": 0,
        "skipped_empty": 0,
        "send_failed": 0,
        "errors": 0,
    }
    for c in workspaces:
        wid = (c.get("workspace_id") or "").strip()
        if not wid:
            continue
        try:
            if (c.get("daily_briefing_emailed_date") or "") == day:
                stats["skipped_already"] += 1
                continue
            recipients = await _alert_recipient_emails(wid)
            if not recipients:
                stats["skipped_no_recipients"] += 1
                continue
            sendable = await ec.filter_unsuppressed(db, recipients)
            if not sendable:
                stats["skipped_suppressed"] += 1
                continue
            data = await assemble_ops_briefing_data(wid)
            if not data.get("has_content"):
                stats["skipped_empty"] += 1
                continue
            ws_name = c.get("name") or "Company"
            any_sent = False
            for addr in sendable:
                unsub = ec.unsubscribe_url(app_url, addr, secret=SESSION_SECRET)
                one_click = ec.api_unsubscribe_url(api_base, addr, secret=SESSION_SECRET)
                email_result = await send_resend_email(
                    to=[addr],
                    subject=f"Trenston morning briefing: {ws_name}",
                    html=_daily_briefing_email_html(
                        workspace_name=ws_name,
                        data=data,
                        app_url=app_url,
                        unsubscribe_url=unsub,
                    ),
                    headers=ec.list_unsubscribe_headers(one_click),
                )
                if email_result.get("sent"):
                    any_sent = True
            if any_sent:
                await db.workspaces.update_one(
                    {"workspace_id": wid},
                    {"$set": {
                        "daily_briefing_emailed_date": day,
                        "daily_briefing_emailed_at": datetime.now(timezone.utc).isoformat(),
                    }},
                )
                stats["sent"] += 1
            else:
                stats["send_failed"] += 1
        except Exception:
            stats["errors"] += 1
            logger.exception("daily briefing cron failed for workspace %s", wid)
    return stats


@api_router.post("/internal/run-retention-checks")
async def internal_run_retention_checks(request: Request):
    """Daily Render cron: trial-ending reminder + inactivity nudge. Shared-secret header required."""
    _require_internal_cron(request)
    result = await helm_retention.run_retention_checks(
        db,
        trial_days=TRIAL_DAYS,
        app_base_url=_app_base_url(),
        send_email=send_notification_email,
        recipient_emails=_alert_recipient_emails,
        signing_secret=SESSION_SECRET,
        api_base_url=public_api_origin(),
    )
    try:
        drafts = await helm_dept_drafts.run_department_drafts(db)
        result = {**result, "department_drafts": drafts}
    except Exception:
        logger.exception("department report drafts cron failed")
        result = {**result, "department_drafts": {"error": True}}
    return result


@api_router.post("/internal/run-accounting-sync")
async def internal_run_accounting_sync(request: Request):
    """Hourly Render cron: pull QuickBooks/Xero transactions into Financials. Shared-secret header required."""
    _require_internal_cron(request)
    return await run_accounting_auto_sync()


@api_router.post("/internal/run-daily-alerts")
async def internal_run_daily_alerts(request: Request):
    """Daily Render cron: refresh insights + high-severity email/Slack. Shared-secret header required.

    Schedule is fixed UTC (not yet per-workspace timezone).
    """
    _require_internal_cron(request)
    return await run_daily_alerts_cron()


@api_router.post("/internal/run-weekly-digest")
async def internal_run_weekly_digest(request: Request):
    """Weekly Render cron: email weekly pack PDF to CEO/owner. Shared-secret header required."""
    _require_internal_cron(request)
    return await run_weekly_digest_cron()


@api_router.post("/internal/run-daily-briefing")
async def internal_run_daily_briefing(request: Request):
    """Daily Render cron: morning ops briefing email to CEO/owner. Shared-secret header required.

    Separate from weekly pack digest. Fixed UTC morning hour (v1 — no per-workspace timezone).
    """
    _require_internal_cron(request)
    return await run_daily_briefing_cron()


async def _apply_unsubscribe_token(token: str, *, source: str) -> dict:
    import email_compliance as ec

    parsed = ec.parse_unsubscribe_token(token, secret=SESSION_SECRET)
    result = await ec.suppress_email(
        db,
        parsed["email"],
        parsed["category"],
        source=source,
    )
    return {
        **result,
        "label": ec.category_label(parsed["category"]),
        "ok": True,
    }


@api_router.get("/email/unsubscribe")
async def email_unsubscribe_get(token: str = ""):
    """One-click unsubscribe (email link). Suppresses immediately, then redirects to confirmation."""
    import email_compliance as ec

    frontend = _app_base_url() or TRENSTON_CANONICAL_ORIGIN
    try:
        result = await _apply_unsubscribe_token(token, source="link_get")
        dest = (
            f"{frontend}/unsubscribe?status=ok"
            f"&category={quote(result.get('category') or ec.CATEGORY_COMMERCIAL, safe='')}"
        )
        return RedirectResponse(url=dest, status_code=303)
    except ValueError:
        return RedirectResponse(url=f"{frontend}/unsubscribe?status=invalid", status_code=303)
    except Exception:
        logger.exception("unsubscribe GET failed")
        return RedirectResponse(url=f"{frontend}/unsubscribe?status=error", status_code=303)


@api_router.post("/email/unsubscribe")
async def email_unsubscribe_post(request: Request, token: str = ""):
    """RFC 8058 one-click List-Unsubscribe-Post and SPA confirmation POST.

    Accepts token via query string (mail-client one-click) or JSON body {"token": "..."}.
    Honored immediately — writes email_suppressions before responding.
    """
    body_token = ""
    try:
        content_type = (request.headers.get("content-type") or "").lower()
        if "application/json" in content_type:
            payload = await request.json()
            if isinstance(payload, dict):
                body_token = str(payload.get("token") or "")
        elif "application/x-www-form-urlencoded" in content_type:
            form = await request.form()
            body_token = str(form.get("token") or "")
    except Exception:
        body_token = ""
    raw = (token or body_token or "").strip()
    try:
        result = await _apply_unsubscribe_token(raw, source="one_click_post")
        return JSONResponse(result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@api_router.get("/internal/analytics-summary")
async def internal_analytics_summary(principal=Depends(require_analytics_admin)):
    """Operator-only first-party usage aggregates. Not a customer feature."""
    return await helm_analytics.analytics_summary(db)


@api_router.get("/health")
async def health():
    """Liveness probe for Render — must return 200 within 5s even when Mongo is down."""
    mongo_ok = await _mongo_ping()
    return {
        "status": "ok",
        "mongo": mongo_ok,
        "mongo_source": MONGO_SOURCE,
        "cache": simple_cache.stats(),
    }


@api_router.get("/")
async def root():
    return {"service": "Trenston CEO Operating System"}


_serve_static = should_serve_static()
if not _serve_static:

    @app.get("/")
    async def api_root():
        """Friendly response when someone opens the Render host directly (API-only)."""
        return {
            "service": "Trenston CEO Operating System API",
            "message": "This URL is the API backend. Open your Vercel app to use Trenston.",
            "health": "/api/health",
            "auth": "/api/auth/config",
            "frontend": FRONTEND_URL or None,
        }


dept_ops_wiring.register(
    api_router,
    db=db,
    get_principal=get_principal,
    invalidate_workspace_list_cache=invalidate_workspace_list_cache,
    invalidate_departments_cache=invalidate_departments_cache,
)
app.include_router(api_router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Apply conservative browser and cache controls to every response."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=(), payment=()",
    )
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    if ENVIRONMENT == "production":
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
    return response


_cors_origins = list(dict.fromkeys(
    CORS_ORIGINS + clerk_auth.helm_frontend_origins()
)) or (clerk_auth.helm_frontend_origins() or ["http://localhost:3000"])
_cors_regex = CORS_ORIGIN_REGEX
if not _cors_regex and any("emergentagent.com" in o for o in _cors_origins):
    _cors_regex = r"https://.*\.emergentagent\.com"
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=_cors_origins,
    allow_origin_regex=_cors_regex,
    allow_methods=["*"],
    allow_headers=["*"],
)

if _serve_static:
    mount_static_frontend(app)


async def _ensure_indexes():
    # Scrub legacy null external ids before (re)creating unique indexes.
    await _scrub_null_financial_external_ids()
    specs = [
        (db.users, [("email", 1)], {"unique": True}),
        (db.users, [("google_sub", 1)], {"unique": True, "sparse": True}),
        (db.users, [("clerk_id", 1)], {"unique": True, "sparse": True}),
        (db.memberships, [("user_id", 1), ("workspace_id", 1)], {}),
        (db.memberships, [("email", 1), ("status", 1)], {}),
        (db.workspaces, [("workspace_id", 1)], {"unique": True}),
        (db.workspaces, [("join_code", 1)], {"unique": True, "sparse": True}),
        (db.user_sessions, [("session_token", 1)], {"unique": True}),
        (db.user_sessions, [("expires_at", 1)], {"expireAfterSeconds": 0}),
        (db.user_sessions, [("user_id", 1)], {}),
        (db.paddle_events, [("_id", 1)], {"unique": True}),
        (db.paddle_intents, [("_id", 1)], {"unique": True}),
        (db.paddle_intents, [("created_at", 1)], {"expireAfterSeconds": 3600}),
        (db.deals, [("workspace_id", 1)], {}),
        (db.deals, [("workspace_id", 1), ("department_id", 1)], {}),
        (db.deals, [("workspace_id", 1), ("updated_at", -1), ("id", -1)], {}),
        (db.deals, [("workspace_id", 1), ("hubspot_deal_id", 1)], {"unique": True, "sparse": True}),
        (db.financial_entries, [("workspace_id", 1)], {}),
        (db.financial_entries, [("workspace_id", 1), ("department_id", 1)], {}),
        (db.financial_entries, [("workspace_id", 1), ("department_id", 1), ("month", -1)], {}),
        # Partial unique indexes: sparse unique still indexes explicit null, which
        # collides on a second manual row that stored qb_txn_id/source_deal_id: null.
        (db.financial_entries, [("workspace_id", 1), ("qb_txn_id", 1)], {
            "unique": True,
            "name": "ws_qb_txn_id_partial",
            "partialFilterExpression": {"qb_txn_id": {"$type": "string"}},
        }),
        (db.financial_entries, [("workspace_id", 1), ("source_deal_id", 1)], {
            "unique": True,
            "name": "ws_source_deal_id_partial",
            "partialFilterExpression": {"source_deal_id": {"$type": "string"}},
        }),
        (db.financial_entries, [("workspace_id", 1), ("source_procurement_request_id", 1)], {
            "unique": True,
            "name": "ws_source_procurement_request_id_partial",
            "partialFilterExpression": {"source_procurement_request_id": {"$type": "string"}},
        }),
        (db.documents, [("workspace_id", 1)], {}),
        (db.documents, [("workspace_id", 1), ("uploaded_at", -1)], {}),
        (db.documents, [("id", 1)], {"unique": True}),
        (db.documents, [("status", 1), ("uploaded_at", 1)], {}),
        (db.report_documents, [("workspace_id", 1), ("report_date", 1)], {}),
        (db.report_documents, [("workspace_id", 1), ("uploaded_at", -1)], {}),
        (db.report_documents, [("id", 1)], {"unique": True}),
        (db.report_digests, [("workspace_id", 1), ("date", 1)], {"unique": True}),
        (db.document_rate_events, [("created_at", 1)], {"expireAfterSeconds": 3600}),
        (db.document_rate_events, [("workspace_id", 1), ("action", 1)], {}),
        # Window-keyed acquire counters — expire so stale windows cannot lock a workspace out.
        (db.document_rate_buckets, [("expires_at", 1)], {"expireAfterSeconds": 0}),
        (db.insights_rate_events, [("created_at", 1)], {"expireAfterSeconds": 86400}),
        (db.insights_rate_events, [("workspace_id", 1)], {}),
        (db.insights_rate_buckets, [("expires_at", 1)], {"expireAfterSeconds": 0}),
        (db.ask_helm_rate_events, [("created_at", 1)], {"expireAfterSeconds": doc_rate_limit.ASK_HELM_WINDOW_SECONDS}),
        (db.ask_helm_rate_buckets, [("expires_at", 1)], {"expireAfterSeconds": 0}),
        (db.document_ai_usage, [("created_at", 1)], {"expireAfterSeconds": doc_rate_limit.DOCUMENT_AI_WINDOW_SECONDS}),
        (db.document_ai_usage, [("workspace_id", 1)], {}),
        (db.join_rate_events, [("created_at", 1)], {"expireAfterSeconds": doc_rate_limit.JOIN_WINDOW_SECONDS}),
        (db.join_rate_events, [("client_ip", 1)], {}),
        (db.join_rate_buckets, [("created_at", 1)], {"expireAfterSeconds": doc_rate_limit.JOIN_WINDOW_SECONDS * 2}),
        (db.oauth_states, [("state_hash", 1)], {"unique": True}),
        (db.oauth_states, [("expires_at", 1)], {"expireAfterSeconds": 0}),
        (db.ask_helm_rate_events, [("workspace_id", 1)], {}),
        (db.activities, [("workspace_id", 1), ("created_at", -1)], {}),
        (db.updates, [("workspace_id", 1), ("day", 1), ("updated_at", -1)], {}),
        (db.updates, [("user_id", 1)], {}),
        (db.chat_messages, [("workspace_id", 1), ("user_id", 1), ("created_at", 1)], {}),
        (db.chat_messages, [("user_id", 1)], {}),
        (db.private_notes, [("workspace_id", 1), ("user_id", 1), ("created_at", -1)], {}),
        (db.user_google_tokens, [("workspace_id", 1), ("user_id", 1)], {"unique": True}),
        (db.user_google_tokens, [("user_id", 1)], {}),
        (db.departments, [("workspace_id", 1), ("type", 1)], {"unique": True}),
        (db.departments, [("department_id", 1)], {"unique": True}),
        (db.department_members, [("department_id", 1), ("user_id", 1)], {"unique": True}),
        (db.department_members, [("user_id", 1)], {}),
        (db.production_work_orders, [("id", 1)], {"unique": True}),
        (db.production_work_orders, [("department_id", 1), ("created_at", -1)], {}),
        (db.production_work_orders, [("department_id", 1), ("status", 1)], {}),
        (db.production_work_orders, [("workspace_id", 1)], {}),
        (db.production_work_orders, [("department_id", 1), ("due_date", 1)], {}),
        (db.production_work_orders, [("linked_procurement_request_id", 1)], {}),
        (db.production_work_orders, [("linked_maintenance_ticket_id", 1)], {}),
        (db.production_daily_logs, [("id", 1)], {"unique": True}),
        (db.production_daily_logs, [("work_order_id", 1), ("date", 1)], {"unique": True}),
        (db.production_daily_logs, [("workspace_id", 1), ("date", -1)], {}),
        (db.production_daily_logs, [("department_id", 1), ("date", -1)], {}),
        (db.sales_order_book, [("id", 1)], {"unique": True}),
        (db.sales_order_book, [("department_id", 1), ("updated_at", -1)], {}),
        (db.sales_order_book, [("workspace_id", 1), ("expected_close_month", 1)], {}),
        (db.sales_order_book, [("workspace_id", 1), ("created_at", -1)], {}),
        (db.sales_targets, [("workspace_id", 1), ("month", 1)], {"unique": True}),
        (db.maintenance_spares, [("id", 1)], {"unique": True}),
        (db.maintenance_spares, [("department_id", 1)], {}),
        (db.maintenance_spares, [("workspace_id", 1), ("created_at", -1)], {}),
        (db.maintenance_schedules, [("id", 1)], {"unique": True}),
        (db.maintenance_schedules, [("department_id", 1), ("equipment_name", 1)], {}),
        (db.maintenance_schedules, [("workspace_id", 1), ("created_at", -1)], {}),
        (db.maintenance_contracts, [("id", 1)], {"unique": True}),
        (db.maintenance_contracts, [("department_id", 1)], {}),
        (db.maintenance_contracts, [("workspace_id", 1), ("created_at", -1)], {}),
        (db.maintenance_costs, [("id", 1)], {"unique": True}),
        (db.maintenance_costs, [("department_id", 1), ("month", 1)], {}),
        (db.maintenance_costs, [("workspace_id", 1), ("created_at", -1)], {}),
        (db.procurement_requests, [("id", 1)], {"unique": True}),
        (db.procurement_requests, [("department_id", 1), ("created_at", -1)], {}),
        (db.procurement_requests, [("department_id", 1), ("status", 1)], {}),
        (db.procurement_requests, [("workspace_id", 1)], {}),
        (db.procurement_requests, [("department_id", 1), ("expected_delivery_date", 1)], {}),
        (db.legal_matters, [("id", 1)], {"unique": True}),
        (db.legal_matters, [("department_id", 1), ("created_at", -1)], {}),
        (db.legal_matters, [("department_id", 1), ("status", 1)], {}),
        (db.legal_matters, [("workspace_id", 1)], {}),
        (db.legal_matters, [("department_id", 1), ("due_date", 1)], {}),
        (db.legal_matters, [("department_id", 1), ("assigned_to", 1)], {}),
        (db.legal_matters, [("department_id", 1), ("updated_at", -1)], {}),
        (db.maintenance_tickets, [("id", 1)], {"unique": True}),
        (db.maintenance_tickets, [("department_id", 1), ("status", 1)], {}),
        (db.maintenance_tickets, [("department_id", 1), ("priority", 1)], {}),
        (db.maintenance_tickets, [("workspace_id", 1)], {}),
        (db.hr_onboarding_template, [("department_id", 1)], {"unique": True}),
        (db.hr_onboarding_template, [("id", 1)], {"unique": True}),
        (db.hr_onboarding_instances, [("id", 1)], {"unique": True}),
        (db.hr_onboarding_instances, [("department_id", 1), ("overall_status", 1)], {}),
        (db.hr_onboarding_instances, [("workspace_id", 1)], {}),
        (db.hr_employees, [("id", 1)], {"unique": True}),
        (db.hr_employees, [("department_id", 1), ("status", 1)], {}),
        (db.hr_employees, [("workspace_id", 1)], {}),
        (db.hr_employees, [("source_onboarding_instance_id", 1)], {"unique": True, "sparse": True}),
        (db.hr_offboarding_template, [("department_id", 1)], {"unique": True}),
        (db.hr_offboarding_template, [("id", 1)], {"unique": True}),
        (db.hr_offboarding_instances, [("id", 1)], {"unique": True}),
        (db.hr_offboarding_instances, [("department_id", 1), ("overall_status", 1)], {}),
        (db.hr_offboarding_instances, [("department_id", 1), ("employee_id", 1)], {}),
        (db.hr_offboarding_instances, [("workspace_id", 1)], {}),
        (db.hr_leave_requests, [("id", 1)], {"unique": True}),
        (db.hr_leave_requests, [("department_id", 1), ("status", 1)], {}),
        (db.hr_leave_requests, [("department_id", 1), ("employee_id", 1)], {}),
        (db.hr_leave_requests, [("workspace_id", 1)], {}),
        (db.hr_leave_requests, [("department_id", 1), ("start_date", 1)], {}),
        (db.department_report_drafts, [("id", 1)], {"unique": True}),
        (db.department_report_drafts, [("workspace_id", 1), ("status", 1)], {}),
        (db.department_report_drafts, [("workspace_id", 1), ("department_type", 1), ("week_start", 1)], {"unique": True}),
        (db.product_events, [("event_type", 1), ("created_at", -1)], {}),
        (db.product_events, [("workspace_id", 1), ("event_type", 1)], {}),
        (db.product_events, [("event_type", 1), ("metadata.once_key", 1)], {}),
        (db.users, [("referral_code", 1)], {"unique": True, "sparse": True}),
        (db.referrals, [("referrer_user_id", 1), ("created_at", -1)], {}),
        (db.referrals, [("referral_id", 1)], {"unique": True, "sparse": True}),
        (db.referrals, [("referred_workspace_id", 1)], {"sparse": True}),
        (db.workspaces, [("referred_by", 1)], {"sparse": True}),
    ]
    for collection, keys, opts in specs:
        try:
            await asyncio.wait_for(collection.create_index(keys, **opts), timeout=1.5)
        except Exception:
            logger.debug("index ensure skipped for %s", keys, exc_info=True)


async def _connect_mongo_at_startup() -> None:
    """Probe candidate URLs and bind to the first reachable Mongo (fixes stale Atlas env on Render)."""
    global client, db, mongo_url, MONGO_SOURCE
    candidates = _mongo_candidate_urls()
    if not candidates:
        logger.error("No Mongo URL configured — set MONGO_URL or sync render.yaml")
        return

    for attempt in range(1, 6):
        for url in candidates:
            probe = _make_mongo_client(url)
            try:
                await asyncio.wait_for(
                    probe.admin.command("ping", maxTimeMS=3000),
                    timeout=5.0,
                )
            except Exception as exc:
                probe.close()
                logger.warning(
                    "Mongo unreachable attempt %d (%s): %s",
                    attempt, _redact_mongo_url(url), exc,
                )
                continue
            if probe is not client:
                client.close()
            client = probe
            db = client[DB_NAME]
            mongo_url = url
            MONGO_SOURCE = _mongo_source_label(url)
            logger.info("Mongo connected via %s (%s)", MONGO_SOURCE, _redact_mongo_url(url))
            return
        if attempt < 5:
            await asyncio.sleep(min(2 * attempt, 8))

    logger.error("Mongo unavailable after probing %d candidate URL(s)", len(candidates))


@app.on_event("startup")
async def startup():
    if ENVIRONMENT == "production":
        cred_crypto.assert_encryption_ready()
    await _connect_mongo_at_startup()
    # Do not block Render health checks — indexes / migrations run after listen.
    asyncio.create_task(_ensure_indexes())
    asyncio.create_task(_run_sales_finance_migration())
    asyncio.create_task(_backfill_financial_entry_names())
    asyncio.create_task(_seal_plaintext_integration_tokens())
    asyncio.create_task(clerk_auth.sync_clerk_instance())
    if clerk_auth.clerk_configured():
        asyncio.create_task(clerk_auth.prefetch_jwks())


async def _run_sales_finance_migration() -> None:
    """Idempotent fold of Sales + Accounting/Finance into the department system."""
    try:
        await dept_migrate.migrate_all_workspaces_sales_finance(db)
    except Exception:
        logger.exception("sales/finance department migration failed")


async def _backfill_financial_entry_names() -> None:
    """Set name = category on legacy ledger rows that have no item name. Idempotent."""
    try:
        cursor = db.financial_entries.find(
            {"$or": [{"name": {"$exists": False}}, {"name": None}, {"name": ""}]},
            {"_id": 1, "category": 1},
        )
        updated = 0
        async for doc in cursor:
            label = normalize_entry_name(None, doc.get("category"))
            await db.financial_entries.update_one({"_id": doc["_id"]}, {"$set": {"name": label}})
            updated += 1
        if updated:
            logger.info("backfilled name on %s financial entries", updated)
    except Exception:
        logger.exception("financial entry name backfill failed")


async def _scrub_null_financial_external_ids() -> None:
    """Drop explicit null external ids so sparse unique indexes stop colliding.

    Legacy rows sometimes stored qb_txn_id/source_deal_id: null; Mongo sparse
    unique indexes still index null, so a second null insert 500s.
    """
    try:
        qb = await db.financial_entries.update_many(
            {"qb_txn_id": None}, {"$unset": {"qb_txn_id": ""}},
        )
        deal = await db.financial_entries.update_many(
            {"source_deal_id": None}, {"$unset": {"source_deal_id": ""}},
        )
        proc = await db.financial_entries.update_many(
            {"source_procurement_request_id": None},
            {"$unset": {"source_procurement_request_id": ""}},
        )
        # Drop legacy sparse indexes once partial ones exist (best-effort).
        for name in (
            "workspace_id_1_qb_txn_id_1",
            "workspace_id_1_source_deal_id_1",
            "workspace_id_1_source_procurement_request_id_1",
        ):
            try:
                await db.financial_entries.drop_index(name)
            except Exception:
                pass
        touched = (qb.modified_count or 0) + (deal.modified_count or 0) + (proc.modified_count or 0)
        if touched:
            logger.info("scrubbed null external ids on %s financial entries", touched)
    except Exception:
        logger.exception("financial external-id scrub failed")


_INTEGRATION_TOKEN_FIELDS = ("quickbooks_tokens", "xero_tokens", "hubspot_tokens", "sap_b1_credentials")


async def _seal_plaintext_integration_tokens() -> None:
    """Encrypt leftover plaintext OAuth blobs. Idempotent; does not fail boot."""
    try:
        cred_crypto.encrypt_credential("startup-seal-probe")
    except cred_crypto.CredentialCryptoError:
        logger.warning("skip token seal: INTEGRATION_ENCRYPTION_KEY is not usable")
        return
    try:
        cursor = db.workspaces.find(
            {"$or": [{field: {"$type": "object"}} for field in _INTEGRATION_TOKEN_FIELDS]},
            {"_id": 1, "workspace_id": 1, **{field: 1 for field in _INTEGRATION_TOKEN_FIELDS}},
        )
        updated = 0
        async for doc in cursor:
            patch = {}
            for field in _INTEGRATION_TOKEN_FIELDS:
                raw = doc.get(field)
                if not cred_crypto.needs_reencryption(raw):
                    continue
                sealed = cred_crypto.seal_credentials(raw)
                opened = cred_crypto.unseal_credentials(sealed)
                if opened != dict(raw):
                    logger.error("token seal round-trip mismatch for %s %s", doc.get("workspace_id"), field)
                    continue
                patch[field] = sealed
            if patch:
                await db.workspaces.update_one({"_id": doc["_id"]}, {"$set": patch})
                updated += 1
        if updated:
            logger.info("sealed plaintext integration tokens on %s workspace(s)", updated)
        # Drop unused workspace-level google_tokens (Google is per-user now).
        cleared = await db.workspaces.update_many(
            {"google_tokens": {"$ne": None}},
            {"$unset": {
                "google_tokens": "",
                "google_tokens_connected_by": "",
                "google_tokens_connected_at": "",
            }},
        )
        if cleared.modified_count:
            logger.info("cleared legacy workspace google_tokens on %s workspace(s)", cleared.modified_count)
        # Seal per-user Google tokens if any plaintext slipped in.
        user_updated = 0
        async for row in db.user_google_tokens.find(
            {"google_tokens": {"$type": "object"}},
            {"_id": 1, "google_tokens": 1},
        ):
            raw = row.get("google_tokens")
            if not cred_crypto.needs_reencryption(raw):
                continue
            sealed = cred_crypto.seal_credentials(raw)
            opened = cred_crypto.unseal_credentials(sealed)
            if opened != dict(raw):
                logger.error("user Google token seal round-trip mismatch for %s", row.get("_id"))
                continue
            await db.user_google_tokens.update_one({"_id": row["_id"]}, {"$set": {"google_tokens": sealed}})
            user_updated += 1
        if user_updated:
            logger.info("sealed plaintext user Google tokens on %s row(s)", user_updated)
    except Exception:
        logger.exception("plaintext integration token seal failed")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
