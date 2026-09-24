"""QuickBooks Online — token refresh and transaction sync."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from integration_errors import (
    IntegrationRetryableError,
    force_token_refresh,
    refresh_http_post,
)

logger = logging.getLogger(__name__)

QB_CLIENT_ID = (os.environ.get("QUICKBOOKS_CLIENT_ID") or "").strip()
QB_CLIENT_SECRET = (os.environ.get("QUICKBOOKS_CLIENT_SECRET") or "").strip()

# Official Intuit Accounting API: minor versions 1–74 retired Aug 2025; use 75+.
# https://developer.intuit.com/app/developer/qbo/docs/learn/explore-the-quickbooks-online-api/minor-versions
QB_MINOR_VERSION = 75

_QB_ENV_RAW = (os.environ.get("QB_ENVIRONMENT") or os.environ.get("QUICKBOOKS_ENV") or "").strip()
QB_ENV_EXPLICITLY_SET = bool(_QB_ENV_RAW)
QB_ENVIRONMENT = (_QB_ENV_RAW or "sandbox").strip().lower()

TOKEN_URL = "https://oauth2.platform.intuit.com/oauth2/v1/tokens/bearer"
API_BASE = (
    "https://sandbox-quickbooks.api.intuit.com"
    if QB_ENVIRONMENT == "sandbox"
    else "https://quickbooks.api.intuit.com"
)

# Entities synced into financial_entries (entity API name → mapper kind).
QB_SYNC_ENTITIES: tuple[tuple[str, str], ...] = (
    ("Invoice", "invoice"),
    ("SalesReceipt", "sales_receipt"),
    ("CreditMemo", "credit_memo"),
    ("RefundReceipt", "refund_receipt"),
    ("Purchase", "purchase"),
    ("Bill", "bill"),
    ("VendorCredit", "vendor_credit"),
    ("JournalEntry", "journal_entry"),
)

_PL_ACCOUNT_TYPES = frozenset({
    "income",
    "otherincome",
    "expense",
    "otherexpense",
    "costofgoodssold",
    "cogs",
})


class QuickBooksAuthError(Exception):
    """Refresh token invalid or revoked — user must reconnect."""


class QuickBooksRetryableError(IntegrationRetryableError):
    """Transient Intuit/network failure — keep tokens."""


def _is_prod_like() -> bool:
    env = (os.environ.get("ENVIRONMENT") or "").strip().lower()
    if env in ("production", "prod"):
        return True
    if os.environ.get("RENDER"):
        return True
    if (os.environ.get("PROD") or "").strip().lower() in ("1", "true", "yes"):
        return True
    return False


def warn_if_qb_env_missing_in_prod() -> Optional[str]:
    """Log a loud warning when production would silently default to sandbox.

    Returns the warning message when applicable (also for diagnostics).
    """
    if QB_ENV_EXPLICITLY_SET:
        return None
    if not _is_prod_like():
        return None
    msg = (
        "CRITICAL: QUICKBOOKS_ENV / QB_ENVIRONMENT is not set in a production-like "
        "environment (RENDER/ENVIRONMENT/PROD). Defaulting to sandbox would hit the "
        "wrong Intuit host — set QUICKBOOKS_ENV=production (or sandbox) explicitly."
    )
    logger.error(msg)
    return msg


def qb_env_diagnostics() -> dict:
    """Safe fields for Integrations diagnostics."""
    warning = None
    if not QB_ENV_EXPLICITLY_SET and _is_prod_like():
        warning = (
            "QUICKBOOKS_ENV / QB_ENVIRONMENT is unset in production-like env; "
            "refusing silent sandbox default — set the variable explicitly."
        )
    return {
        "quickbooks_env": QB_ENVIRONMENT if QB_ENV_EXPLICITLY_SET else (
            "unset (would default to sandbox)" if _is_prod_like() else "sandbox (default)"
        ),
        "quickbooks_env_explicit": QB_ENV_EXPLICITLY_SET,
        "quickbooks_minorversion": QB_MINOR_VERSION,
        "quickbooks_env_warning": warning,
        "quickbooks_api_base": _api_base() if QB_ENV_EXPLICITLY_SET or not _is_prod_like() else "(blocked: set QUICKBOOKS_ENV)",
    }


def _api_base() -> str:
    # In production-like hosts, never silently use sandbox when env is unset.
    if not QB_ENV_EXPLICITLY_SET and _is_prod_like():
        return "https://quickbooks.api.intuit.com"
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


async def refresh_qb_token(tokens: dict, *, force: bool = False) -> dict:
    """Return valid tokens, refreshing via Intuit when the access token is near expiry."""
    if not force and not _token_needs_refresh(tokens):
        return tokens
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise QuickBooksAuthError("Missing refresh token")
    if not QB_CLIENT_ID or not QB_CLIENT_SECRET:
        raise QuickBooksAuthError("QuickBooks OAuth is not configured")

    resp = await refresh_http_post(
        provider="QuickBooks",
        url=TOKEN_URL,
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        auth=(QB_CLIENT_ID, QB_CLIENT_SECRET),
        headers={"Accept": "application/json"},
        auth_error_cls=QuickBooksAuthError,
        retryable_error_cls=QuickBooksRetryableError,
    )

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
        detail = (
            line.get("AccountBasedExpenseLineDetail")
            or line.get("SalesItemLineDetail")
            or line.get("ItemBasedExpenseLineDetail")
            or line.get("JournalEntryLineDetail")
            or {}
        )
        account = detail.get("AccountRef") or detail.get("ItemRef") or {}
        name = account.get("name")
        if name:
            return str(name)[:80]
    return ""


def _norm_account_type(raw: str) -> str:
    return "".join(ch for ch in (raw or "").lower() if ch.isalnum())


def _is_pl_account_type(account_type: str) -> bool:
    return _norm_account_type(account_type) in _PL_ACCOUNT_TYPES


def _base_mapped_fields(txn: dict, *, qb_id: str, amount: float, is_credit: bool) -> dict:
    txn_date_full = str(txn.get("TxnDate") or "")
    month = txn_date_full[:7] if len(txn_date_full) >= 7 else datetime.now(timezone.utc).strftime("%Y-%m")
    return {
        "amount": amount,
        "is_credit": is_credit,
        "month": month,
        "qb_txn_id": f"{qb_id}_{txn_date_full}",
        "recurring": False,
    }


def map_qb_transaction(txn: dict, txn_type: str) -> Optional[dict]:
    """Map a QuickBooks transaction to financial_entries fields.

    Polarity:
    - Revenue: Invoice, SalesReceipt
    - Credits against revenue: CreditMemo, RefundReceipt (is_credit=True)
    - Expenses: Purchase, Bill
    - Credits against expenses: VendorCredit; Purchase with Credit=true (refund)
    - JournalEntry: expanded via map_qb_journal_entry (P&L lines only)
    """
    import accounting_map as amap

    if txn_type == "journal_entry":
        return None  # handled by map_qb_journal_entry

    amount, is_credit = amap.normalize_mapped_amount(txn.get("TotalAmt"))
    qb_id = str(txn.get("Id") or "")
    if not qb_id or amount <= 0:
        return None

    # Purchase Credit:true is a vendor refund / credit card credit.
    if txn_type == "purchase" and bool(txn.get("Credit")):
        is_credit = True

    # Explicit credit documents always reduce the related P&L bucket.
    if txn_type in ("credit_memo", "refund_receipt", "vendor_credit"):
        is_credit = True

    category = amap.fallback_category(_line_category(txn))
    memo = txn.get("PrivateNote") or ""
    doc = txn.get("DocNumber") or ""
    base = _base_mapped_fields(txn, qb_id=qb_id, amount=amount, is_credit=is_credit)

    if txn_type in ("purchase", "bill", "vendor_credit"):
        vendor = (
            (txn.get("EntityRef") or {}).get("name")
            or (txn.get("VendorRef") or {}).get("name")
            or ""
        )
        name = (vendor or memo or category).strip()[:120]
        extras = [p for p in [doc, memo] if p and p != name]
        return {
            **base,
            "type": "expense",
            "category": category,
            "name": name,
            "note": " · ".join(extras)[:500],
        }

    # invoice, sales_receipt, credit_memo, refund_receipt
    customer = (txn.get("CustomerRef") or {}).get("name") or ""
    name = (customer or doc or category).strip()[:120]
    extras = [p for p in [doc, memo] if p and p != name]
    return {
        **base,
        "type": "revenue",
        "category": category,
        "name": name,
        "note": " · ".join(extras)[:500],
    }


def map_qb_journal_entry(txn: dict) -> list[dict]:
    """Map JournalEntry P&L lines only; PostingType sets credit/debit polarity."""
    import accounting_map as amap

    je_id = str(txn.get("Id") or "")
    if not je_id:
        return []
    txn_date_full = str(txn.get("TxnDate") or "")
    month = txn_date_full[:7] if len(txn_date_full) >= 7 else datetime.now(timezone.utc).strftime("%Y-%m")
    out: list[dict] = []
    for line in txn.get("Line") or []:
        if not isinstance(line, dict):
            continue
        if (line.get("DetailType") or "") != "JournalEntryLineDetail":
            continue
        detail = line.get("JournalEntryLineDetail") or {}
        account = detail.get("AccountRef") or {}
        account_type = (
            detail.get("AccountType")
            or account.get("type")
            or account.get("AccountType")
            or ""
        )
        if not _is_pl_account_type(str(account_type)):
            continue
        amount, _ = amap.normalize_mapped_amount(line.get("Amount"))
        if amount <= 0:
            continue
        posting = (detail.get("PostingType") or "").strip().lower()
        acct_norm = _norm_account_type(str(account_type))
        is_income = acct_norm in ("income", "otherincome")
        # Debit to expense increases expense; Credit to expense is a credit.
        # Credit to income increases revenue; Debit to income is a credit against revenue.
        if is_income:
            entry_type = "revenue"
            is_credit = posting == "debit"
        else:
            entry_type = "expense"
            is_credit = posting == "credit"
        line_id = str(line.get("Id") or len(out))
        category = amap.fallback_category(account.get("name") or line.get("Description") or "")
        name = (line.get("Description") or account.get("name") or category).strip()[:120]
        out.append({
            "type": entry_type,
            "category": category,
            "name": name,
            "amount": amount,
            "is_credit": is_credit,
            "month": month,
            "note": "",
            "qb_txn_id": f"{je_id}_line_{line_id}_{txn_date_full}",
            "recurring": False,
            "_qb_raw_type": "journal_entry",
        })
    return out


QB_PAGE_SIZE = 1000
QB_MAX_PAGES = 100


async def _query_qb_once(
    access_token: str, realm_id: str, entity: str, since: Optional[str],
) -> tuple[list[dict], bool, Optional[int]]:
    """Fetch all pages for an entity. Returns (rows, complete, failing_status).

    failing_status is set when the first page returns a non-success status so
    callers can refresh-and-retry on 401.
    """
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
        try:
            async with httpx.AsyncClient(timeout=45.0) as hc:
                resp = await hc.get(
                    url,
                    params={"query": q, "minorversion": str(QB_MINOR_VERSION)},
                    headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                )
        except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
            raise QuickBooksRetryableError("QuickBooks query temporarily unavailable") from exc
        if resp.status_code == 401:
            return [], False, 401
        if resp.status_code >= 500:
            raise QuickBooksRetryableError(
                f"QuickBooks query temporarily unavailable ({resp.status_code})"
            )
        if resp.status_code != 200:
            raise RuntimeError(f"QuickBooks query failed ({resp.status_code}): {resp.text[:300]}")

        body = resp.json()
        qr = body.get("QueryResponse") or {}
        rows = qr.get(entity) or []
        if isinstance(rows, dict):
            rows = [rows]
        all_rows.extend(rows)
        if len(rows) < QB_PAGE_SIZE:
            return all_rows, True, None
        start += QB_PAGE_SIZE
    return all_rows, False, None


async def _query_qb(
    tokens: dict, realm_id: str, entity: str, since: Optional[str],
) -> tuple[list[dict], bool, dict]:
    """Fetch entity pages; on 401 force one token refresh and retry once."""
    access_token = tokens.get("access_token") or ""
    rows, complete, status = await _query_qb_once(access_token, realm_id, entity, since)
    if status != 401:
        return rows, complete, tokens
    logger.info("QuickBooks 401 on %s — forcing token refresh and retrying once", entity)
    tokens = await refresh_qb_token(force_token_refresh(tokens), force=True)
    access_token = tokens.get("access_token") or ""
    rows, complete, status = await _query_qb_once(access_token, realm_id, entity, since)
    if status == 401:
        raise QuickBooksAuthError("QuickBooks access token rejected")
    return rows, complete, tokens


async def fetch_qb_transactions(
    tokens: dict, realm_id: str, since: Optional[str] = None,
) -> tuple[list[dict], bool, dict]:
    """Fetch supported QuickBooks entities and map to financial_entries rows.

    Returns (mapped_rows, complete, tokens). complete is False when a page safety cap was hit —
    callers must not advance qb_last_synced_at in that case. tokens may be refreshed after a 401 retry.
    """
    if not tokens.get("access_token"):
        raise QuickBooksAuthError("Missing access token")

    mapped: list[dict] = []
    all_complete = True
    for entity, kind in QB_SYNC_ENTITIES:
        rows, complete, tokens = await _query_qb(tokens, realm_id, entity, since)
        all_complete = all_complete and complete
        if kind == "journal_entry":
            for je in rows:
                mapped.extend(map_qb_journal_entry(je))
            continue
        for row in rows:
            mapped_row = map_qb_transaction(row, kind)
            if mapped_row:
                mapped.append({**mapped_row, "_qb_raw_type": kind})
    return mapped, all_complete, tokens
