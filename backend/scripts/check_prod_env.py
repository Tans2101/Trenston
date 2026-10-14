#!/usr/bin/env python3
"""Fail fast if critical production env vars are missing. Run on Render build or locally."""
from __future__ import annotations

import os
import sys

ALWAYS_REQUIRED = [
    "DB_NAME",
    "SESSION_SECRET",
    "FRONTEND_URL",
    "APP_URL",
    "CORS_ORIGINS",
    # Fernet key for OAuth/ERP credentials at rest. Missing this used to
    # ship a successful Render build and only fail on the first token save.
    "INTEGRATION_ENCRYPTION_KEY",
]

RECOMMENDED = [
    "ANTHROPIC_API_KEY",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "QUICKBOOKS_CLIENT_ID",
    "QUICKBOOKS_CLIENT_SECRET",
    "XERO_CLIENT_ID",
    "XERO_CLIENT_SECRET",
    "HUBSPOT_CLIENT_ID",
    "HUBSPOT_CLIENT_SECRET",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET_NAME",
    # R2_ENDPOINT is optional when R2_ACCOUNT_ID is set (endpoint is derived).
    "PADDLE_API_KEY",
    "PADDLE_CLIENT_TOKEN",
    "PADDLE_PRICE_ID_STARTER",
    "PADDLE_PRICE_ID_GROWTH",
    "PADDLE_PRICE_ID_BUSINESS",
    "PADDLE_WEBHOOK_SECRET",
    "PADDLE_ENV",
    "RESEND_API_KEY",
    "SENDER_EMAIL",
]


def _mongo_configured() -> bool:
    if (os.environ.get("MONGO_HOST") or "").strip():
        return True
    if (os.environ.get("MONGO_URL") or "").strip():
        return True
    return bool(os.environ.get("RENDER"))


def _auth_configured() -> bool:
    clerk = (os.environ.get("CLERK_SECRET_KEY") or "").strip() and (
        os.environ.get("CLERK_JWKS_URL") or ""
    ).strip()
    google = (os.environ.get("GOOGLE_CLIENT_ID") or "").strip() and (
        os.environ.get("GOOGLE_CLIENT_SECRET") or ""
    ).strip()
    return bool(clerk or google)


def main() -> int:
    missing = [k for k in ALWAYS_REQUIRED if not (os.environ.get(k) or "").strip()]
    if not _mongo_configured():
        missing.append("MONGO_URL (MongoDB Atlas)")
    if not _auth_configured():
        missing.extend(["CLERK_SECRET_KEY+CLERK_JWKS_URL or GOOGLE_CLIENT_ID+GOOGLE_CLIENT_SECRET"])

    weak = []
    for url_key in ("APP_URL", "FRONTEND_URL"):
        raw = os.environ.get(url_key, "")
        if raw and raw != raw.strip():
            weak.append(
                f"{url_key} has leading/trailing whitespace — OAuth Location "
                "headers become relative and browsers show FastAPI {\"detail\":\"Not Found\"}"
            )
    if os.environ.get("SESSION_SECRET", "").strip() in ("", "change-me-in-production", "change-me-to-a-long-random-string"):
        weak.append("SESSION_SECRET looks like a placeholder")
    if os.environ.get("ALLOW_DEMO_LOGIN", "false").lower() in ("1", "true", "yes"):
        weak.append("ALLOW_DEMO_LOGIN is enabled (should be false in production)")
    if os.environ.get("COOKIE_SECURE", "false").lower() not in ("1", "true", "yes"):
        weak.append("COOKIE_SECURE should be true behind HTTPS")

    sk = (os.environ.get("CLERK_SECRET_KEY") or "").strip()
    pk = (os.environ.get("CLERK_PUBLISHABLE_KEY") or "").strip()
    if sk and pk:
        sk_live = sk.startswith("sk_live_")
        sk_test = sk.startswith("sk_test_")
        pk_live = pk.startswith("pk_live_")
        pk_test = pk.startswith("pk_test_")
        if (sk_live and not pk_live) or (sk_test and not pk_test):
            weak.append(
                "CLERK_SECRET_KEY mode does not match CLERK_PUBLISHABLE_KEY "
                "(use sk_live_ + pk_live_ from the same Clerk instance)"
            )
    elif sk and not pk:
        weak.append("CLERK_PUBLISHABLE_KEY unset — Render will derive from CLERK_JWKS_URL at runtime")
    webhook_secret = (
        (os.environ.get("CLERK_WEBHOOK_SIGNING_SECRET") or "").strip()
        or (os.environ.get("CLERK_WEBHOOK_SECRET") or "").strip()
    )
    if sk and not webhook_secret.startswith("whsec_"):
        weak.append(
            "CLERK_WEBHOOK_SIGNING_SECRET unset — Clerk Dashboard user.deleted will not "
            "revoke Trenston sessions until the Svix secret is set (POST /api/webhook/clerk)"
        )
    if (
        os.environ.get("USE_ATLAS_MONGO", "false").lower() not in ("1", "true", "yes")
        and (os.environ.get("MONGO_URL") or "").startswith("mongodb+srv://")
        and os.environ.get("RENDER")
    ):
        weak.append(
            "MONGO_URL is Atlas but USE_ATLAS_MONGO=false — set USE_ATLAS_MONGO=true"
        )

    rec_missing = [k for k in RECOMMENDED if not (os.environ.get(k) or "").strip()]
    r2_endpoint = (os.environ.get("R2_ENDPOINT") or "").strip()
    r2_account = (os.environ.get("R2_ACCOUNT_ID") or "").strip()
    if not r2_endpoint and not r2_account:
        rec_missing.append("R2_ENDPOINT or R2_ACCOUNT_ID")

    integ_key = (os.environ.get("INTEGRATION_ENCRYPTION_KEY") or "").strip()
    if integ_key:
        try:
            from cryptography.fernet import Fernet

            Fernet(integ_key.encode("utf-8"))
        except Exception:
            missing.append("INTEGRATION_ENCRYPTION_KEY (must be a Fernet key, not a passphrase)")

    if missing:
        print("MISSING required env:", ", ".join(missing))
    if weak:
        print("WARNINGS:")
        for w in weak:
            print(" -", w)
    if rec_missing:
        print("Optional not set yet:", ", ".join(rec_missing))

    if missing:
        return 1
    print("Production env check: required keys present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
