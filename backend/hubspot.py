"""HubSpot CRM — token refresh and deal sync into Trenston Pipeline."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

HUBSPOT_CLIENT_ID = os.environ.get("HUBSPOT_CLIENT_ID", "")
HUBSPOT_CLIENT_SECRET = os.environ.get("HUBSPOT_CLIENT_SECRET", "")

AUTH_URL = "https://app.hubspot.com/oauth/authorize"
TOKEN_URL = "https://api.hubapi.com/oauth/v1/token"
API_BASE = "https://api.hubapi.com"

# Read deals + company names + pipeline stage labels for mapping into Trenston stages.
HUBSPOT_SCOPES = " ".join([
    "oauth",
    "crm.objects.deals.read",
    "crm.objects.companies.read",
    "crm.schemas.deals.read",
])

DEAL_PROPERTIES = [
    "dealname",
    "amount",
    "dealstage",
    "closedate",
    "hs_lastmodifieddate",
    "pipeline",
]


class HubSpotAuthError(Exception):
    """Refresh token invalid or revoked — user must reconnect."""


def _token_needs_refresh(tokens: dict) -> bool:
    obtained = tokens.get("obtained_at")
    if not obtained:
        return True
    try:
        obtained_dt = datetime.fromisoformat(obtained.replace("Z", "+00:00"))
    except ValueError:
        return True
    expires_in = int(tokens.get("expires_in", 21600))
    return obtained_dt + timedelta(seconds=max(expires_in - 300, 0)) <= datetime.now(timezone.utc)


async def refresh_hubspot_token(tokens: dict) -> dict:
    """Return valid tokens, refreshing via HubSpot when the access token is near expiry."""
    if not _token_needs_refresh(tokens):
        return tokens
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise HubSpotAuthError("Missing refresh token")
    if not HUBSPOT_CLIENT_ID or not HUBSPOT_CLIENT_SECRET:
        raise HubSpotAuthError("HubSpot OAuth is not configured")

    async with httpx.AsyncClient(timeout=30.0) as hc:
        resp = await hc.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": HUBSPOT_CLIENT_ID,
                "client_secret": HUBSPOT_CLIENT_SECRET,
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code != 200:
        raise HubSpotAuthError(resp.text[:300] or "Token refresh failed")

    updated = {**tokens, **resp.json()}
    updated["obtained_at"] = datetime.now(timezone.utc).isoformat()
    if "refresh_token" not in updated and refresh_token:
        updated["refresh_token"] = refresh_token
    return updated


def map_hubspot_stage(stage_label: str, stage_id: str = "") -> str:
    """Map HubSpot pipeline stage labels/ids onto Trenston DEAL_STAGES."""
    text = f"{stage_label or ''} {stage_id or ''}".strip().lower()
    if not text:
        return "lead"
    compact = text.replace(" ", "").replace("_", "").replace("-", "")
    if "closedwon" in compact or compact == "won" or "closed won" in text:
        return "won"
    if "closedlost" in compact or compact == "lost" or "closed lost" in text:
        return "lost"
    if any(k in text for k in ("negotiat", "contractsent", "contract sent")):
        return "negotiation"
    if any(k in text for k in ("proposal", "presentation", "quote")):
        return "proposal"
    if any(k in text for k in ("qualif", "decisionmaker", "decision maker")):
        return "qualified"
    return "lead"


def _parse_close_date(raw: Optional[str]) -> str:
    if not raw:
        return ""
    s = str(raw).strip()
    if len(s) >= 10 and s[4] == "-":
        return s[:10]
    # HubSpot sometimes returns epoch ms
    try:
        ms = int(float(s))
        if ms > 10_000_000_000:
            ms //= 1000
        return datetime.fromtimestamp(ms, tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def map_hubspot_deal(deal: dict, stage_labels: dict[str, str], company_names: dict[str, str]) -> Optional[dict]:
    """Map a HubSpot CRM deal object into Trenston deal fields (+ hubspot_deal_id)."""
    deal_id = str(deal.get("id") or "").strip()
    if not deal_id:
        return None
    props = deal.get("properties") or {}
    name = (props.get("dealname") or "").strip() or f"HubSpot deal {deal_id}"
    stage_id = (props.get("dealstage") or "").strip()
    stage_label = stage_labels.get(stage_id, stage_id)
    try:
        amount = round(float(props.get("amount") or 0), 2)
    except (TypeError, ValueError):
        amount = 0.0

    company = ""
    associations = ((deal.get("associations") or {}).get("companies") or {}).get("results") or []
    for assoc in associations:
        cid = str(assoc.get("id") or "")
        if cid and cid in company_names:
            company = company_names[cid]
            break

    return {
        "hubspot_deal_id": deal_id,
        "name": name[:200],
        "company": (company or "")[:200],
        "value": amount,
        "stage": map_hubspot_stage(stage_label, stage_id),
        "owner_name": "",
        "close_date": _parse_close_date(props.get("closedate")),
        "source": "hubspot_sync",
    }


async def _auth_headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}


async def _fetch_stage_labels(hc: httpx.AsyncClient, access_token: str) -> dict[str, str]:
    resp = await hc.get(
        f"{API_BASE}/crm/v3/pipelines/deals",
        headers=await _auth_headers(access_token),
    )
    if resp.status_code == 401:
        raise HubSpotAuthError("HubSpot access token rejected")
    if resp.status_code != 200:
        # Non-fatal — fall back to raw stage ids
        return {}
    labels: dict[str, str] = {}
    for pipe in resp.json().get("results") or []:
        for stage in pipe.get("stages") or []:
            sid = str(stage.get("id") or "")
            if sid:
                labels[sid] = str(stage.get("label") or sid)
    return labels


async def _fetch_company_names(hc: httpx.AsyncClient, access_token: str, company_ids: list[str]) -> dict[str, str]:
    names: dict[str, str] = {}
    unique = [c for c in dict.fromkeys(company_ids) if c]
    for i in range(0, len(unique), 100):
        chunk = unique[i:i + 100]
        resp = await hc.post(
            f"{API_BASE}/crm/v3/objects/companies/batch/read",
            headers=await _auth_headers(access_token),
            json={"properties": ["name"], "inputs": [{"id": cid} for cid in chunk]},
        )
        if resp.status_code == 401:
            raise HubSpotAuthError("HubSpot access token rejected")
        if resp.status_code != 200:
            continue
        for row in resp.json().get("results") or []:
            cid = str(row.get("id") or "")
            name = ((row.get("properties") or {}).get("name") or "").strip()
            if cid and name:
                names[cid] = name
    return names


async def _fetch_deal_company_ids(hc: httpx.AsyncClient, access_token: str, deal_ids: list[str]) -> dict[str, str]:
    """Map deal_id → first associated company_id."""
    out: dict[str, str] = {}
    unique = [d for d in dict.fromkeys(deal_ids) if d]
    for i in range(0, len(unique), 100):
        chunk = unique[i:i + 100]
        resp = await hc.post(
            f"{API_BASE}/crm/v4/associations/deals/companies/batch/read",
            headers=await _auth_headers(access_token),
            json={"inputs": [{"id": did} for did in chunk]},
        )
        if resp.status_code == 401:
            raise HubSpotAuthError("HubSpot access token rejected")
        if resp.status_code != 200:
            continue
        for row in resp.json().get("results") or []:
            deal_id = str(row.get("from", {}).get("id") or "")
            tos = row.get("to") or []
            if deal_id and tos and not out.get(deal_id):
                out[deal_id] = str(tos[0].get("toObjectId") or tos[0].get("id") or "")
    return out


HUBSPOT_DEAL_PAGE_LIMIT = 100
HUBSPOT_MAX_DEALS = 10000  # safety cap — incomplete sync must not advance last_synced_at


async def _list_or_search_deals(
    hc: httpx.AsyncClient,
    access_token: str,
    since: Optional[str],
) -> tuple[list[dict], bool]:
    results: list[dict] = []
    after: Optional[str] = None
    use_search = bool(since)
    complete = True

    while True:
        if use_search:
            body: dict = {
                "properties": DEAL_PROPERTIES,
                "limit": HUBSPOT_DEAL_PAGE_LIMIT,
            }
            try:
                since_dt = datetime.fromisoformat(str(since).replace("Z", "+00:00"))
                if since_dt.tzinfo is None:
                    since_dt = since_dt.replace(tzinfo=timezone.utc)
                ms = int(since_dt.timestamp() * 1000)
                body["filterGroups"] = [{
                    "filters": [{
                        "propertyName": "hs_lastmodifieddate",
                        "operator": "GTE",
                        "value": str(ms),
                    }],
                }]
            except ValueError:
                use_search = False
                continue
            if after:
                body["after"] = after
            resp = await hc.post(
                f"{API_BASE}/crm/v3/objects/deals/search",
                headers=await _auth_headers(access_token),
                json=body,
            )
        else:
            params: dict = {
                "limit": HUBSPOT_DEAL_PAGE_LIMIT,
                "properties": ",".join(DEAL_PROPERTIES),
            }
            if after:
                params["after"] = after
            resp = await hc.get(
                f"{API_BASE}/crm/v3/objects/deals",
                headers=await _auth_headers(access_token),
                params=params,
            )

        if resp.status_code == 401:
            raise HubSpotAuthError("HubSpot access token rejected")
        if resp.status_code == 403:
            raise HubSpotAuthError("HubSpot deal access denied. Reconnect with CRM scopes")
        if resp.status_code != 200:
            raise RuntimeError(f"HubSpot deals failed ({resp.status_code}): {resp.text[:300]}")

        payload = resp.json()
        batch = payload.get("results") or []
        results.extend(batch)
        after = (payload.get("paging") or {}).get("next", {}).get("after")
        if not after or not batch:
            break
        if len(results) >= HUBSPOT_MAX_DEALS:
            complete = False
            break
    return results, complete


async def fetch_deals(tokens: dict, since: Optional[str] = None) -> tuple[list[dict], bool]:
    """Pull HubSpot deals, optionally modified since an ISO timestamp.

    Returns (mapped_deals, complete). Do not advance hubspot_last_synced_at when complete is False.
    """
    access_token = tokens.get("access_token")
    if not access_token:
        raise HubSpotAuthError("Missing access token")

    async with httpx.AsyncClient(timeout=60.0) as hc:
        stage_labels = await _fetch_stage_labels(hc, access_token)
        results, complete = await _list_or_search_deals(hc, access_token, since)
        deal_ids = [str(d.get("id") or "") for d in results if d.get("id")]
        deal_companies = await _fetch_deal_company_ids(hc, access_token, deal_ids)
        company_names = await _fetch_company_names(hc, access_token, list(deal_companies.values()))

    mapped: list[dict] = []
    for deal in results:
        deal_id = str(deal.get("id") or "")
        # Attach synthetic association so map_hubspot_deal can resolve company
        cid = deal_companies.get(deal_id)
        if cid:
            deal = {
                **deal,
                "associations": {"companies": {"results": [{"id": cid}]}},
            }
        row = map_hubspot_deal(deal, stage_labels, company_names)
        if row:
            mapped.append(row)
    return mapped, complete
