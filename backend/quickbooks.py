"""QuickBooks Online — token refresh and transaction sync."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

QB_CLIENT_ID = (os.environ.get("QUICKBOOKS_CLIENT_ID") or "").strip()
QB_CLIENT_SECRET = (os.environ.get("QUICKBOOKS_CLIENT_SECRET") or "").strip()
QB_ENVIRONMENT = (
    os.environ.get("QB_ENVIRONMENT") or os.environ.get("QUICKBOOKS_ENV") or "sandbox"
).strip().lower()

TOKEN_URL = "https://oauth2.platform.intuit.com/oauth2/v1/tokens/bearer"
API_BASE = (
    "https://sandbox-quickbooks.api.intuit.com"
    if QB_ENVIRONMENT == "sandbox"
    else "https://quickbooks.api.intuit.com"
)


class QuickBooksAuthError(Exception):
    """Refresh token invalid or revoked — user must reconnect."""


def _api_base() -> str:
    return API_BASE


def _token_needs_refresh(tokens: dict) -> bool:
    obtained = tokens.get("obtained_at")
    if not obtained:
        return True
    try:
        obtained_dt = datetime.fromisoformat(obtained.replace("Z", "+00:00"))
    except ValueError:
        return True
    expires_in = int(tokens.get("expires_in", 3600))
    return obtained_dt + timedelta(seconds=max(expires_in - 300, 0)) <= datetime.now(timezone.utc)


async def refresh_qb_token(tokens: dict) -> dict:
    """Return valid tokens, refreshing via Intuit when the access token is near expiry."""
    if not _token_needs_refresh(tokens):
        return tokens
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise QuickBooksAuthError("Missing refresh token")
    if not QB_CLIENT_ID or not QB_CLIENT_SECRET:
        raise QuickBooksAuthError("QuickBooks OAuth is not configured")

    async with httpx.AsyncClient(timeout=30.0) as hc:
        resp = await hc.post(
            TOKEN_URL,
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            auth=(QB_CLIENT_ID, QB_CLIENT_SECRET),
            headers={"Accept": "application/json"},
        )
    if resp.status_code != 200:
        raise QuickBooksAuthError(resp.text[:300] or "Token refresh failed")

    updated = {**tokens, **resp.json()}
    updated["obtained_at"] = datetime.now(timezone.utc).isoformat()
    # Intuit may omit refresh_token / realmId on refresh — keep the prior grant.
    if not updated.get("refresh_token") and refresh_token:
        updated["refresh_token"] = refresh_token
    if tokens.get("realmId") and not updated.get("realmId"):
        updated["realmId"] = tokens["realmId"]
    return updated


def _line_category(txn: dict) -> str:
    for line in txn.get("Line") or []:
        detail = line.get("AccountBasedExpenseLineDetail") or line.get("SalesItemLineDetail") or {}
        account = detail.get("AccountRef") or detail.get("ItemRef") or {}
        name = account.get("name")
        if name:
            return str(name)[:80]
    return ""


def map_qb_transaction(txn: dict, txn_type: str) -> dict:
    """Map a QuickBooks Purchase or Invoice to financial_entries fields."""
    import accounting_map as amap

    txn_date_full = str(txn.get("TxnDate") or "")
    month = txn_date_full[:7] if len(txn_date_full) >= 7 else datetime.now(timezone.utc).strftime("%Y-%m")
    amount, is_credit = amap.normalize_mapped_amount(txn.get("TotalAmt"))
    qb_id = str(txn.get("Id") or "")
    qb_txn_id = f"{qb_id}_{txn_date_full}"

    if txn_type == "purchase":
        vendor = (txn.get("EntityRef") or {}).get("name") or ""
        memo = txn.get("PrivateNote") or ""
        category = amap.fallback_category(_line_category(txn))
        name = (vendor or memo or category).strip()[:120]
        extras = [p for p in [memo] if p and p != name]
        note = " · ".join(extras) if extras else ""
        return {
            "type": "expense",
            "category": category,
            "name": name,
            "amount": amount,
            "is_credit": is_credit,
            "month": month,
            "note": note[:500],
            "qb_txn_id": qb_txn_id,
            "recurring": False,
        }

    customer = (txn.get("CustomerRef") or {}).get("name") or ""
    doc = txn.get("DocNumber") or ""
    memo = txn.get("PrivateNote") or ""
    category = amap.fallback_category(_line_category(txn))
    name = (customer or doc or category).strip()[:120]
    extras = [p for p in [doc, memo] if p and p != name]
    note = " · ".join(extras) if extras else ""
    return {
        "type": "revenue",
        "category": category,
        "name": name,
        "amount": amount,
        "is_credit": is_credit,
        "month": month,
        "note": note[:500],
        "qb_txn_id": qb_txn_id,
        "recurring": False,
    }


QB_PAGE_SIZE = 1000
QB_MAX_PAGES = 100


async def _query_qb(
    access_token: str, realm_id: str, entity: str, since: Optional[str],
) -> tuple[list[dict], bool]:
    """Fetch all pages for an entity. complete=False if the safety page cap is hit."""
    all_rows: list[dict] = []
    start = 1
    for _ in range(QB_MAX_PAGES):
        if since:
            since_date = since[:10]
            q = (
                f"SELECT * FROM {entity} WHERE TxnDate >= '{since_date}' "
                f"STARTPOSITION {start} MAXRESULTS {QB_PAGE_SIZE}"
            )
        else:
            q = f"SELECT * FROM {entity} STARTPOSITION {start} MAXRESULTS {QB_PAGE_SIZE}"

        url = f"{_api_base()}/v3/company/{realm_id}/query"
        async with httpx.AsyncClient(timeout=45.0) as hc:
            resp = await hc.get(
                url,
                params={"query": q, "minorversion": "65"},
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
        if resp.status_code == 401:
            raise QuickBooksAuthError("QuickBooks access token rejected")
        if resp.status_code != 200:
            raise RuntimeError(f"QuickBooks query failed ({resp.status_code}): {resp.text[:300]}")

        body = resp.json()
        qr = body.get("QueryResponse") or {}
        rows = qr.get(entity) or []
        if isinstance(rows, dict):
            rows = [rows]
        all_rows.extend(rows)
        if len(rows) < QB_PAGE_SIZE:
            return all_rows, True
        start += QB_PAGE_SIZE
    return all_rows, False


async def fetch_qb_transactions(
    tokens: dict, realm_id: str, since: Optional[str] = None,
) -> tuple[list[dict], bool]:
    """Fetch Purchase and Invoice objects, optionally since an ISO timestamp (uses date portion).

    Returns (mapped_rows, complete). complete is False when a page safety cap was hit —
    callers must not advance qb_last_synced_at in that case.
    """
    access_token = tokens.get("access_token")
    if not access_token:
        raise QuickBooksAuthError("Missing access token")

    purchases, purchases_complete = await _query_qb(access_token, realm_id, "Purchase", since)
    invoices, invoices_complete = await _query_qb(access_token, realm_id, "Invoice", since)

    mapped = []
    for p in purchases:
        mapped.append({**map_qb_transaction(p, "purchase"), "_qb_raw_type": "purchase"})
    for inv in invoices:
        mapped.append({**map_qb_transaction(inv, "invoice"), "_qb_raw_type": "invoice"})
    return mapped, purchases_complete and invoices_complete
