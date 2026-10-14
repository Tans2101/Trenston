"""Best-effort token revocation when a workspace disconnects an integration.

Deleting our copy of a grant is not enough: the provider still lists Trenston as an
authorised app, and Intuit's app review expects Disconnect to revoke the token.
Every call here is fire-and-forget: failures are logged, never raised, so a
provider outage can never block a user from disconnecting.
"""
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
QUICKBOOKS_REVOKE_URL = "https://developer.api.intuit.com/v2/oauth2/tokens/revoke"
XERO_REVOKE_URL = "https://identity.xero.com/connect/revocation"
HUBSPOT_REFRESH_TOKEN_URL = "https://api.hubapi.com/oauth/v1/refresh-tokens/"

_TIMEOUT = 10.0


def _token(tokens: Optional[dict]) -> str:
    """Prefer the refresh token: revoking it also invalidates its access tokens."""
    if not isinstance(tokens, dict):
        return ""
    return str(tokens.get("refresh_token") or tokens.get("access_token") or "").strip()


async def revoke_google(tokens: Optional[dict]) -> bool:
    token = _token(tokens)
    if not token:
        return False
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as hc:
            resp = await hc.post(
                GOOGLE_REVOKE_URL,
                data={"token": token},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        # 400 invalid_token means it was already revoked or expired: same outcome.
        return resp.status_code in (200, 400)
    except Exception as exc:  # noqa: BLE001 - best effort
        logger.warning("Google revoke failed: %s", exc)
        return False


async def revoke_quickbooks(tokens: Optional[dict], client_id: str, client_secret: str) -> bool:
    token = _token(tokens)
    if not token or not client_id or not client_secret:
        return False
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as hc:
            resp = await hc.post(
                QUICKBOOKS_REVOKE_URL,
                json={"token": token},
                auth=(client_id, client_secret),
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
        return resp.status_code in (200, 400)
    except Exception as exc:  # noqa: BLE001
        logger.warning("QuickBooks revoke failed: %s", exc)
        return False


async def revoke_xero(tokens: Optional[dict], client_id: str, client_secret: str) -> bool:
    token = _token(tokens)
    if not token or not client_id or not client_secret:
        return False
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as hc:
            resp = await hc.post(
                XERO_REVOKE_URL,
                data={"token": token},
                auth=(client_id, client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        return resp.status_code in (200, 400)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Xero revoke failed: %s", exc)
        return False


async def revoke_hubspot(tokens: Optional[dict]) -> bool:
    refresh = str((tokens or {}).get("refresh_token") or "").strip()
    if not refresh:
        return False
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as hc:
            resp = await hc.delete(f"{HUBSPOT_REFRESH_TOKEN_URL}{quote(refresh, safe='')}")
        return resp.status_code in (200, 204, 404)
    except Exception as exc:  # noqa: BLE001
        logger.warning("HubSpot revoke failed: %s", exc)
        return False
