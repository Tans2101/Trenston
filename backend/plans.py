"""Helm pricing tiers — Free / Starter / Growth / Business.

Paddle price IDs come from env vars (no hardcoded IDs). Entitlements work
from workspace.plan alone so QA can set plan without checkout.
"""
from __future__ import annotations

import os
from typing import Any, Optional

# Canonical plan ids. Legacy "pro" migrates to Starter (conscious choice — see README.md).
PLAN_FREE = "free"
PLAN_STARTER = "starter"
PLAN_GROWTH = "growth"
PLAN_BUSINESS = "business"
LEGACY_PRO = "pro"

TRIAL_DAYS = 7

PLAN_RANK = {
    PLAN_FREE: 0,
    PLAN_STARTER: 1,
    PLAN_GROWTH: 2,
    PLAN_BUSINESS: 3,
}

FEATURE_AI_EXTRACT = "ai_extract"
FEATURE_ASK_HELM = "ask_helm"
FEATURE_AI_BRIEFING = "ai_briefing"
FEATURE_INTEGRATIONS = "integrations"
FEATURE_ADVANCED_REPORTS = "advanced_reports"
FEATURE_TEAM = "team"
FEATURE_PRIORITY_SUPPORT = "priority_support"

PLANS: dict[str, dict[str, Any]] = {
    PLAN_FREE: {
        "id": PLAN_FREE,
        "label": "Free",
        "price": 0,
        "for": "Small teams trying Helm",
        "seats": 3,
        "ai_extracts_mo": 0,
        "ai_extracts_lifetime": 5,
        "ask_helm_mo": 10,
        "trial_days": 0,
        "paddle_price_env": None,
        "features": {
            FEATURE_AI_EXTRACT: True,
            FEATURE_ASK_HELM: True,
            FEATURE_AI_BRIEFING: True,
            FEATURE_INTEGRATIONS: False,
            FEATURE_ADVANCED_REPORTS: False,
            FEATURE_TEAM: True,
            FEATURE_PRIORITY_SUPPORT: False,
        },
        "includes": [
            "Up to 3 team members",
            "5 free AI extracts to try it, then upgrade",
            "Ask Helm (10 messages/month)",
            "AI morning briefing",
            "Dashboard & decisions",
            "No QuickBooks sync",
        ],
    },
    PLAN_STARTER: {
        "id": PLAN_STARTER,
        "label": "Starter",
        "price": 15,
        "for": "Small businesses",
        "seats": 10,
        "ai_extracts_mo": 30,
        "trial_days": TRIAL_DAYS,
        "paddle_price_env": "PADDLE_PRICE_ID_STARTER",
        "features": {
            FEATURE_AI_EXTRACT: True,
            FEATURE_ASK_HELM: True,
            FEATURE_AI_BRIEFING: True,
            FEATURE_INTEGRATIONS: True,
            FEATURE_ADVANCED_REPORTS: False,
            FEATURE_TEAM: True,
            FEATURE_PRIORITY_SUPPORT: False,
        },
        "includes": [
            "Up to 10 team members",
            "AI document upload (30/billing period)",
            "QuickBooks sync",
            "Ask Helm AI",
            "Calendar",
            "7-day free trial",
        ],
    },
    PLAN_GROWTH: {
        "id": PLAN_GROWTH,
        "label": "Growth",
        "price": 39,
        "for": "Growing businesses",
        "seats": 25,
        "ai_extracts_mo": 150,
        "trial_days": TRIAL_DAYS,
        "paddle_price_env": "PADDLE_PRICE_ID_GROWTH",
        "features": {
            FEATURE_AI_EXTRACT: True,
            FEATURE_ASK_HELM: True,
            FEATURE_AI_BRIEFING: True,
            FEATURE_INTEGRATIONS: True,
            FEATURE_ADVANCED_REPORTS: True,
            FEATURE_TEAM: True,
            FEATURE_PRIORITY_SUPPORT: False,
        },
        "includes": [
            "Up to 25 team members",
            "AI document upload (150/billing period)",
            "Priority QuickBooks sync",
            "Advanced reports & CEO Pack",
            "7-day free trial",
        ],
    },
    PLAN_BUSINESS: {
        "id": PLAN_BUSINESS,
        "label": "Business",
        "price": 99,
        "for": "Larger companies",
        "seats": 50,
        "ai_extracts_mo": 500,
        "trial_days": TRIAL_DAYS,
        "paddle_price_env": "PADDLE_PRICE_ID_BUSINESS",
        "features": {
            FEATURE_AI_EXTRACT: True,
            FEATURE_ASK_HELM: True,
            FEATURE_AI_BRIEFING: True,
            FEATURE_INTEGRATIONS: True,
            FEATURE_ADVANCED_REPORTS: True,
            FEATURE_TEAM: True,
            FEATURE_PRIORITY_SUPPORT: True,
        },
        "includes": [
            "Up to 50 team members",
            "AI document upload (500/billing period)",
            "Priority support",
            "Everything in Growth",
            "7-day free trial",
        ],
    },
}

PAID_PLAN_IDS = (PLAN_STARTER, PLAN_GROWTH, PLAN_BUSINESS)

ACTION_FEATURES: dict[str, Optional[str]] = {
    "briefing:generate": FEATURE_AI_BRIEFING,
    "ask:use": FEATURE_ASK_HELM,
    "reports:pack": FEATURE_ADVANCED_REPORTS,
    "integrations:manage": FEATURE_INTEGRATIONS,
    "members:invite": FEATURE_TEAM,
    "members:manage": None,
    "decisions:act": None,
    "tasks:create": None,
    "tasks:move": None,
    "updates:write": None,
    "billing:manage": None,
}


def normalize_plan(plan: str | None) -> str:
    """Map legacy/unknown plans to a canonical id.

    Existing paying workspaces stored as plan=\"pro\" become Starter — see README.md.
    """
    if not plan:
        return PLAN_FREE
    p = str(plan).strip().lower()
    if p == LEGACY_PRO:
        return PLAN_STARTER
    if p in PLANS:
        return p
    return PLAN_FREE


def plan_def(plan: str | None) -> dict[str, Any]:
    return PLANS[normalize_plan(plan)]


def plan_rank(plan: str | None) -> int:
    return PLAN_RANK.get(normalize_plan(plan), 0)


def is_paid_plan(plan: str | None) -> bool:
    return normalize_plan(plan) in PAID_PLAN_IDS


def is_upgrade(from_plan: str | None, to_plan: str | None) -> bool:
    return plan_rank(to_plan) > plan_rank(from_plan)


def is_downgrade(from_plan: str | None, to_plan: str | None) -> bool:
    return plan_rank(to_plan) < plan_rank(from_plan)


def plan_allows(plan: str | None, feature: str, *, billing_enforced: bool = True) -> bool:
    """When billing is off, everything is allowed (dev / soft launch)."""
    if not billing_enforced:
        return True
    return bool(plan_def(plan)["features"].get(feature))


def seats_limit(plan: str | None) -> Optional[int]:
    """None would mean unlimited; all current tiers set an integer cap."""
    return plan_def(plan)["seats"]


def ai_extracts_limit(plan: str | None) -> int:
    """Monthly renewing extract quota. Free uses ai_extracts_lifetime instead."""
    return int(plan_def(plan).get("ai_extracts_mo") or 0)


def ai_extracts_lifetime_limit(plan: str | None) -> int:
    """One-time extract allowance (Free). 0 means not used — fall back to monthly."""
    return int(plan_def(plan).get("ai_extracts_lifetime") or 0)


def ask_helm_monthly_limit(plan: str | None) -> int:
    """0 = no extra monthly cap beyond the feature flag (paid plans)."""
    return int(plan_def(plan).get("ask_helm_mo") or 0)


def paddle_price_id_for(plan: str | None) -> str:
    """Resolve Paddle price id from PADDLE_PRICE_ID_{STARTER,GROWTH,BUSINESS}."""
    pid = normalize_plan(plan)
    if pid == PLAN_FREE:
        return ""
    env_key = PLANS[pid].get("paddle_price_env")
    if not env_key:
        return ""
    return (os.environ.get(env_key) or "").strip()


def plan_for_paddle_price(price_id: str | None) -> Optional[str]:
    if not price_id:
        return None
    for pid in PAID_PLAN_IDS:
        if paddle_price_id_for(pid) == price_id:
            return pid
    return None


def any_paddle_price_configured() -> bool:
    return any(paddle_price_id_for(pid) for pid in PAID_PLAN_IDS)


def public_plan_list() -> list[dict[str, Any]]:
    out = []
    for pid, p in PLANS.items():
        price_id = paddle_price_id_for(pid) if pid != PLAN_FREE else ""
        out.append({
            "id": pid,
            "label": p["label"],
            "price": p["price"],
            "for": p["for"],
            "seats": p["seats"],
            "ai_extracts_mo": p["ai_extracts_mo"],
            "ai_extracts_lifetime": int(p.get("ai_extracts_lifetime") or 0),
            "ask_helm_mo": int(p.get("ask_helm_mo") or 0),
            "trial_days": p["trial_days"],
            "includes": list(p["includes"]),
            "features": dict(p["features"]),
            "checkout_available": bool(price_id) if pid != PLAN_FREE else False,
        })
    return out


def feature_for_action(action: str) -> Optional[str]:
    return ACTION_FEATURES.get(action)
