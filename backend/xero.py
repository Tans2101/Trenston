"""Xero Accounting — token refresh and invoice/bill sync.

Maps into the same financial_entries shape as QuickBooks (`qb_txn_id` key
included) so Decision Engine, Reports, and finance_recurrence treat both
sources identically.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from integration_errors import (
    IntegrationRetryableError,
    force_token_refresh,
    refresh_http_post,
)

logger = logging.getLogger(__name__)

XERO_CLIENT_ID = os.environ.get("XERO_CLIENT_ID", "")
XERO_CLIENT_SECRET = os.environ.get("XERO_CLIENT_SECRET", "")

TOKEN_URL = "https://identity.xero.com/connect/token"
AUTH_URL = "https://login.xero.com/identity/connect/authorize"
CONNECTIONS_URL = "https://api.xero.com/connections"
API_BASE = "https://api.xero.com/api.xro/2.0"

# Granular read scopes (Xero retired broad accounting.transactions.read for new apps
# from 2 Mar 2026; existing apps must migrate by Sep 2027). Existing connections must
# reconnect to pick up these scopes.
# https://devblog.xero.com/upcoming-changes-to-xero-accounting-api-scopes-705c5a9621a0
XERO_SCOPES = (
    "offline_access "
    "openid profile email "
    "accounting.invoices.read "
    "accounting.banktransactions.read "
    "accounting.manualjournals.read"
)

_DATE_MS_RE = re.compile(r"/Date\((-?\d+)")

# Keep under Xero's ~60 calls/min; serialize with a small delay between requests.
XERO_MIN_INTERVAL_SEC = 1.05
XERO_MAX_RETRIES_429 = 3
_last_xero_call_at = 0.0


class XeroAuthError(Exception):
    """Refresh token invalid or revoked — user must reconnect."""


class XeroRetryableError(IntegrationRetryableError):
    """Transient Xero/network failure — keep tokens."""


class XeroPermissionsError(Exception):
    """Tenant still connected but the call lacks permission — do not wipe tokens."""


def _token_needs_refresh(tokens: dict) -> bool:
    obtained = tokens.get("obtained_at")
    if not obtained:
        return True
    try:
        obtained_dt = datetime.fromisoformat(obtained.replace("Z", "+00:00"))
    except ValueError:
        return True
    expires_in = int(tokens.get("expires_in", 1800))
    return obtained_dt + timedelta(seconds=max(expires_in - 300, 0)) <= datetime.now(timezone.utc)


async def refresh_xero_token(tokens: dict, *, force: bool = False) -> dict:
    """Return valid tokens, refreshing via Xero when the access token is near expiry."""
    if not force and not _token_needs_refresh(tokens):
        return tokens
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise XeroAuthError("Missing refresh token")
    if not XERO_CLIENT_ID or not XERO_CLIENT_SECRET:
        raise XeroAuthError("Xero OAuth is not configured")

    resp = await refresh_http_post(
        provider="Xero",
        url=TOKEN_URL,
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        auth=(XERO_CLIENT_ID, XERO_CLIENT_SECRET),
        headers={"Accept": "application/json"},
        auth_error_cls=XeroAuthError,
        retryable_error_cls=XeroRetryableError,
    )

    updated = {**tokens, **resp.json()}
    updated["obtained_at"] = datetime.now(timezone.utc).isoformat()
    # Preserve org selection across refresh.
    for key in ("tenant_id", "tenant_name", "pending_tenants"):
        if key in tokens and key not in updated:
            updated[key] = tokens[key]
    if tokens.get("tenant_id"):
        updated["tenant_id"] = tokens["tenant_id"]
    if tokens.get("tenant_name"):
        updated["tenant_name"] = tokens["tenant_name"]
    return updated


async def fetch_xero_connections(access_token: str) -> list[dict[str, str]]:
    """List Xero organisations (tenants) the token can access."""
    if not access_token:
        raise XeroAuthError("Missing access token")
    try:
        async with httpx.AsyncClient(timeout=30.0) as hc:
            resp = await hc.get(
                CONNECTIONS_URL,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
    except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
        raise XeroRetryableError("Xero connections temporarily unavailable") from exc
    if resp.status_code == 401:
        raise XeroAuthError("Xero access token rejected")
    if resp.status_code >= 500:
        raise XeroRetryableError(f"Xero connections temporarily unavailable ({resp.status_code})")
    if resp.status_code != 200:
        raise RuntimeError(f"Xero connections failed ({resp.status_code}): {resp.text[:300]}")
    rows = resp.json() or []
    out: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if (row.get("tenantType") or "ORGANISATION").upper() not in ("ORGANISATION", "ORGANIZATION"):
            continue
        tid = str(row.get("tenantId") or "").strip()
        if not tid:
            continue
        out.append({
            "tenant_id": tid,
            "tenant_name": str(row.get("tenantName") or "Xero organisation").strip(),
            "connection_id": str(row.get("id") or ""),
        })
    return out


def _parse_xero_date(inv: dict) -> str:
    """Return YYYY-MM-DD from DateString or /Date(ms)/."""
    raw = inv.get("DateString") or ""
    if isinstance(raw, str) and len(raw) >= 10 and raw[4] == "-":
        return raw[:10]
    dated = str(inv.get("Date") or "")
    m = _DATE_MS_RE.search(dated)
    if m:
        try:
            ms = int(m.group(1))
            return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        except (ValueError, OSError, OverflowError):
            pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _line_category(inv: dict) -> str:
    for line in inv.get("LineItems") or []:
        if not isinstance(line, dict):
            continue
        for key in ("AccountCode", "Description", "ItemCode"):
            val = line.get(key)
            if val:
                return str(val)[:80]
    return ""


def _line_description(inv: dict) -> str:
    for line in inv.get("LineItems") or []:
        if not isinstance(line, dict):
            continue
        desc = line.get("Description")
        if desc:
            return str(desc).strip()[:120]
    return ""


def map_xero_invoice(inv: dict) -> Optional[dict]:
    """Map a Xero Invoice (ACCREC/ACCPAY) to financial_entries fields (QB-compatible).

    Only AUTHORISED and PAID count — SUBMITTED (awaiting approval), DRAFT, DELETED,
    VOIDED are excluded.
    """
    import accounting_map as amap

    status = (inv.get("Status") or "").upper()
    if status in ("DRAFT", "DELETED", "VOIDED", "SUBMITTED"):
        return None
    if status not in ("AUTHORISED", "PAID"):
        return None
    inv_type = (inv.get("Type") or "").upper()
    if inv_type not in ("ACCREC", "ACCPAY"):
        return None

    date_full = _parse_xero_date(inv)
    month = date_full[:7]
    amount, is_credit = amap.normalize_mapped_amount(inv.get("Total"))
    invoice_id = str(inv.get("InvoiceID") or inv.get("InvoiceNumber") or "")
    if not invoice_id:
        return None
    # Stable dedupe key (no date).
    qb_txn_id = f"xero_invoice_{invoice_id}"

    contact = ((inv.get("Contact") or {}) if isinstance(inv.get("Contact"), dict) else {}).get("Name") or ""
    number = inv.get("InvoiceNumber") or ""
    ref = inv.get("Reference") or ""

    category = amap.fallback_category(_line_category(inv))
    line_desc = _line_description(inv)
    name = (contact or line_desc or number or category).strip()[:120]
    extras = [p for p in [number, ref, line_desc] if p and p != name]
    note = " · ".join(extras)

    currency = str(inv.get("CurrencyCode") or "").upper() or None
    amount_net, _ = amap.normalize_mapped_amount(inv.get("SubTotal") if inv.get("SubTotal") is not None else amount)
    amount_home = amap.apply_exchange_rate(amount, inv.get("CurrencyRate"))
    money = {"currency": currency, "amount_net": amount_net, "amount_home": amount_home}

    if inv_type == "ACCPAY":
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
            "_xero_raw_type": "bill",
            **money,
        }

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
        "_xero_raw_type": "invoice",
        **money,
    }


def map_xero_bank_transaction(txn: dict) -> Optional[dict]:
    """Map BankTransactions. RECEIVE=revenue, SPEND=expense.

    RECEIVE-OVERPAYMENT / SPEND-OVERPAYMENT / *-PREPAYMENT are skipped — they are
    balance-sheet /$ prepayment constructs, not P&L until applied.
    """
    import accounting_map as amap

    status = (txn.get("Status") or "").upper()
    if status in ("DELETED", "VOIDED", "DRAFT"):
        return None
    txn_type = (txn.get("Type") or "").upper()
    # Skip overpayments/prepayments (balance sheet until applied to invoices).
    if txn_type in (
        "RECEIVE-OVERPAYMENT", "SPEND-OVERPAYMENT",
        "RECEIVE-PREPAYMENT", "SPEND-PREPAYMENT",
        "RECEIVE-TRANSFER", "SPEND-TRANSFER",
    ):
        return None
    if txn_type not in ("RECEIVE", "SPEND"):
        return None

    date_full = _parse_xero_date(txn)
    month = date_full[:7]
    amount, is_credit = amap.normalize_mapped_amount(txn.get("Total"))
    tid = str(txn.get("BankTransactionID") or "")
    if not tid or amount <= 0:
        return None
    contact = ((txn.get("Contact") or {}) if isinstance(txn.get("Contact"), dict) else {}).get("Name") or ""
    ref = txn.get("Reference") or ""
    category = amap.fallback_category(_line_category(txn))
    name = (contact or ref or category).strip()[:120]
    amount_net, _ = amap.normalize_mapped_amount(
        txn.get("SubTotal") if txn.get("SubTotal") is not None else amount
    )
    return {
        "type": "revenue" if txn_type == "RECEIVE" else "expense",
        "category": category,
        "name": name,
        "amount": amount,
        "is_credit": is_credit,
        "month": month,
        "note": (ref or "")[:500],
        "qb_txn_id": f"xero_bank_{tid}",
        "recurring": False,
        "_xero_raw_type": "bank_receive" if txn_type == "RECEIVE" else "bank_spend",
        "currency": str(txn.get("CurrencyCode") or "").upper() or None,
        "amount_net": amount_net,
        "amount_home": amap.apply_exchange_rate(amount, txn.get("CurrencyRate")),
    }


def map_xero_credit_note(cn: dict) -> Optional[dict]:
    """ACCRECCREDIT reduces revenue; ACCPAYCREDIT reduces expenses."""
    import accounting_map as amap

    status = (cn.get("Status") or "").upper()
    if status in ("DRAFT", "DELETED", "VOIDED", "SUBMITTED"):
        return None
    if status not in ("AUTHORISED", "PAID"):
        return None
    cn_type = (cn.get("Type") or "").upper()
    if cn_type not in ("ACCRECCREDIT", "ACCPAYCREDIT"):
        return None
    date_full = _parse_xero_date(cn)
    month = date_full[:7]
    amount, _ = amap.normalize_mapped_amount(cn.get("Total"))
    cid = str(cn.get("CreditNoteID") or cn.get("CreditNoteNumber") or "")
    if not cid or amount <= 0:
        return None
    contact = ((cn.get("Contact") or {}) if isinstance(cn.get("Contact"), dict) else {}).get("Name") or ""
    number = cn.get("CreditNoteNumber") or ""
    category = amap.fallback_category(_line_category(cn))
    name = (contact or number or category).strip()[:120]
    return {
        "type": "revenue" if cn_type == "ACCRECCREDIT" else "expense",
        "category": category,
        "name": name,
        "amount": amount,
        "is_credit": True,
        "month": month,
        "note": (number or "")[:500],
        "qb_txn_id": f"xero_cn_{cid}",
        "recurring": False,
        "_xero_raw_type": "credit_note",
        "currency": str(cn.get("CurrencyCode") or "").upper() or None,
        "amount_net": amap.normalize_mapped_amount(
            cn.get("SubTotal") if cn.get("SubTotal") is not None else amount
        )[0],
        "amount_home": amap.apply_exchange_rate(amount, cn.get("CurrencyRate")),
    }


_XERO_PL_ACCOUNT_TYPES = frozenset({
    "REVENUE", "SALES", "OTHERINCOME",
    "EXPENSE", "OVERHEADS", "DIRECTCOSTS", "DEPRECIATN",
})


def map_xero_manual_journal(mj: dict) -> list[dict]:
    """Map ManualJournal P&L lines only (posted journals)."""
    import accounting_map as amap

    status = (mj.get("Status") or "").upper()
    if status not in ("POSTED",):
        return []
    mid = str(mj.get("ManualJournalID") or "")
    if not mid:
        return []
    date_full = _parse_xero_date(mj)
    month = date_full[:7]
    narration = (mj.get("Narration") or "").strip()
    out: list[dict] = []
    for idx, line in enumerate(mj.get("JournalLines") or []):
        if not isinstance(line, dict):
            continue
        acct_type = str(line.get("AccountType") or "").upper().replace(" ", "")
        # Also accept AccountCode-only lines tagged via LineAmount + common type field.
        if acct_type and acct_type not in _XERO_PL_ACCOUNT_TYPES:
            # Some payloads use Account.Type nested
            nested = ((line.get("Account") or {}) if isinstance(line.get("Account"), dict) else {})
            acct_type = str(nested.get("Type") or acct_type).upper().replace(" ", "")
        if acct_type and acct_type not in _XERO_PL_ACCOUNT_TYPES:
            continue
        if not acct_type:
            # Without account type we cannot safely classify — skip.
            continue
        amount, _ = amap.normalize_mapped_amount(line.get("LineAmount"))
        if amount <= 0:
            continue
        is_income = acct_type in ("REVENUE", "SALES", "OTHERINCOME")
        # Positive LineAmount is debit in Xero manual journals; credit is negative.
        raw = float(line.get("LineAmount") or 0)
        if is_income:
            entry_type = "revenue"
            is_credit = raw > 0  # debit to income reduces revenue
        else:
            entry_type = "expense"
            is_credit = raw < 0  # credit to expense reduces expense
        category = amap.fallback_category(
            line.get("AccountCode") or line.get("Description") or ""
        )
        name = (line.get("Description") or narration or category).strip()[:120]
        out.append({
            "type": entry_type,
            "category": category,
            "name": name,
            "amount": amount,
            "is_credit": is_credit,
            "month": month,
            "note": (narration or "")[:500],
            "qb_txn_id": f"xero_mj_{mid}_{idx}",
            "recurring": False,
            "_xero_raw_type": "manual_journal",
            "currency": str(mj.get("CurrencyCode") or "").upper() or None,
            "amount_net": amount,
            "amount_home": amap.apply_exchange_rate(amount, 1.0),
        })
    return out


def _since_where_clause(since: Optional[str]) -> str:
    if not since:
        return ""
    day = since[:10]
    try:
        dt = datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        return ""
    return f' AND Date>=DateTime({dt.year},{dt.month},{dt.day})'


XERO_PAGE_SIZE = 100  # Xero returns at most 100 invoices per page
XERO_MAX_PAGES = 100


async def _throttle_xero() -> None:
    """Keep calls under ~60/min."""
    global _last_xero_call_at
    now = time.monotonic()
    wait = XERO_MIN_INTERVAL_SEC - (now - _last_xero_call_at)
    if wait > 0:
        await asyncio.sleep(wait)
    _last_xero_call_at = time.monotonic()


async def _xero_get(
    hc: httpx.AsyncClient,
    url: str,
    *,
    headers: dict,
    params: Optional[dict] = None,
) -> httpx.Response:
    """GET with 429 Retry-After backoff (max 3 retries) and call pacing."""
    last_exc: Optional[Exception] = None
    for attempt in range(XERO_MAX_RETRIES_429 + 1):
        await _throttle_xero()
        try:
            resp = await hc.get(url, params=params, headers=headers)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
            raise XeroRetryableError("Xero temporarily unavailable") from exc
        if resp.status_code != 429:
            return resp
        retry_after = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
        try:
            delay = float(retry_after) if retry_after else (2 ** attempt)
        except ValueError:
            delay = float(2 ** attempt)
        delay = min(max(delay, 1.0), 60.0)
        logger.warning("Xero 429 — sleeping %.1fs (attempt %s)", delay, attempt + 1)
        last_exc = XeroRetryableError("Xero rate limited")
        if attempt >= XERO_MAX_RETRIES_429:
            break
        await asyncio.sleep(delay)
    raise last_exc or XeroRetryableError("Xero rate limited")


async def _fetch_collection_once(
    access_token: str,
    tenant_id: str,
    *,
    path: str,
    result_key: str,
    where: str,
    since: Optional[str],
    include_voided: bool = False,
) -> tuple[list[dict], bool, Optional[int]]:
    """Page through a Xero collection. Returns (rows, complete, failing_status).

    Incremental sync uses If-Modified-Since (not Date filters). When include_voided
    is True, VOIDED/DELETED rows are returned so callers can delete matching entries.
    """
    where_full = where
    # Date filters only for full syncs; incremental relies on If-Modified-Since.
    if not since:
        where_full = where + _since_where_clause(since)
    url = f"{API_BASE}/{path}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Xero-tenant-id": tenant_id,
        "Accept": "application/json",
    }
    if since:
        # RFC 1123 or ISO — Xero accepts ISO-8601.
        headers["If-Modified-Since"] = since.replace("Z", "") if "T" in since else f"{since[:10]}T00:00:00"
    all_rows: list[dict] = []
    async with httpx.AsyncClient(timeout=60.0) as hc:
        for page in range(1, XERO_MAX_PAGES + 1):
            params: dict = {"page": page}
            if where_full:
                params["where"] = where_full
                params["order"] = "Date ASC"
            if include_voided:
                params["includeArchived"] = "true"
            resp = await _xero_get(hc, url, headers=headers, params=params)
            if resp.status_code == 401:
                return [], False, 401
            if resp.status_code == 403:
                return [], False, 403
            if resp.status_code == 304:
                return [], True, None
            if resp.status_code >= 500:
                raise XeroRetryableError(
                    f"Xero {path} temporarily unavailable ({resp.status_code})"
                )
            if resp.status_code != 200:
                raise RuntimeError(f"Xero {path} failed ({resp.status_code}): {resp.text[:300]}")
            rows = resp.json().get(result_key) or []
            if not isinstance(rows, list):
                rows = []
            all_rows.extend(rows)
            if len(rows) < XERO_PAGE_SIZE:
                return all_rows, True, None
        return all_rows, False, None


async def _handle_xero_403(tokens: dict, tenant_id: str) -> None:
    """On 403, wipe only when the tenant is no longer in /connections."""
    connections = await fetch_xero_connections(tokens.get("access_token") or "")
    tenant_ids = {c["tenant_id"] for c in connections}
    if tenant_id not in tenant_ids:
        raise XeroAuthError("Xero tenant access denied. Reconnect and pick an organisation")
    raise XeroPermissionsError(
        "Xero permissions are insufficient for this organisation. Check app scopes."
    )


async def _fetch_collection(
    tokens: dict,
    tenant_id: str,
    *,
    path: str,
    result_key: str,
    where: str,
    since: Optional[str],
    label: str,
    include_voided: bool = False,
) -> tuple[list[dict], bool, dict]:
    """Fetch a collection; on 401 force one refresh and retry once."""
    access_token = tokens.get("access_token") or ""
    rows, complete, status = await _fetch_collection_once(
        access_token, tenant_id, path=path, result_key=result_key, where=where,
        since=since, include_voided=include_voided,
    )
    if status == 403:
        await _handle_xero_403(tokens, tenant_id)
    if status != 401:
        return rows, complete, tokens
    logger.info("Xero 401 on %s — forcing token refresh and retrying once", label)
    tokens = await refresh_xero_token(force_token_refresh(tokens), force=True)
    rows, complete, status = await _fetch_collection_once(
        tokens.get("access_token") or "", tenant_id,
        path=path, result_key=result_key, where=where, since=since,
        include_voided=include_voided,
    )
    if status == 403:
        await _handle_xero_403(tokens, tenant_id)
    if status == 401:
        raise XeroAuthError("Xero access token rejected")
    return rows, complete, tokens


async def fetch_xero_transactions(
    tokens: dict,
    tenant_id: str,
    since: Optional[str] = None,
) -> tuple[list[dict], bool, dict, list[str]]:
    """Fetch invoices, bills, bank txns, credit notes, and manual journals.

    Returns (mapped_rows, complete, tokens, deleted_qb_txn_ids).
    Do not advance xero_last_synced_at when complete is False.
    Incremental runs use If-Modified-Since and also pull VOIDED/DELETED to remove
    matching financial_entries.
    """
    if not tokens.get("access_token"):
        raise XeroAuthError("Missing access token")

    mapped: list[dict] = []
    deleted: list[str] = []
    all_ok = True

    def _collect_deletes(rows: list[dict], id_key: str, prefix: str) -> None:
        for row in rows:
            status = (row.get("Status") or "").upper()
            if status in ("DELETED", "VOIDED"):
                rid = str(row.get(id_key) or "")
                if rid:
                    deleted.append(f"{prefix}{rid}")

    # Active docs — exclude voided/deleted/draft/submitted at query for full sync;
    # for incremental, loosen filters so modified voided rows still arrive via IMS.
    inv_where = (
        'Status!="DELETED" AND Status!="DRAFT" AND Status!="VOIDED" AND Status!="SUBMITTED"'
        if not since else ""
    )
    for inv_type in ("ACCREC", "ACCPAY"):
        where = f'Type=="{inv_type}"' + (f" AND {inv_where}" if inv_where else "")
        rows, ok, tokens = await _fetch_collection(
            tokens, tenant_id,
            path="Invoices", result_key="Invoices", where=where, since=since,
            label=f"Invoices:{inv_type}", include_voided=bool(since),
        )
        all_ok = all_ok and ok
        _collect_deletes(rows, "InvoiceID", "xero_invoice_")
        for inv in rows:
            row = map_xero_invoice(inv)
            if row:
                mapped.append(row)

    banks, b_ok, tokens = await _fetch_collection(
        tokens, tenant_id,
        path="BankTransactions", result_key="BankTransactions",
        where='Status!="DELETED" AND Status!="VOIDED"' if not since else "",
        since=since, label="BankTransactions", include_voided=bool(since),
    )
    all_ok = all_ok and b_ok
    _collect_deletes(banks, "BankTransactionID", "xero_bank_")
    for txn in banks:
        row = map_xero_bank_transaction(txn)
        if row:
            mapped.append(row)

    notes, n_ok, tokens = await _fetch_collection(
        tokens, tenant_id,
        path="CreditNotes", result_key="CreditNotes",
        where=(
            'Status!="DELETED" AND Status!="DRAFT" AND Status!="VOIDED" AND Status!="SUBMITTED"'
            if not since else ""
        ),
        since=since, label="CreditNotes", include_voided=bool(since),
    )
    all_ok = all_ok and n_ok
    _collect_deletes(notes, "CreditNoteID", "xero_cn_")
    for cn in notes:
        row = map_xero_credit_note(cn)
        if row:
            mapped.append(row)

    journals, j_ok, tokens = await _fetch_collection(
        tokens, tenant_id,
        path="ManualJournals", result_key="ManualJournals",
        where='Status=="POSTED"' if not since else "",
        since=since, label="ManualJournals", include_voided=bool(since),
    )
    all_ok = all_ok and j_ok
    for mj in journals:
        status = (mj.get("Status") or "").upper()
        mid = str(mj.get("ManualJournalID") or "")
        if status in ("DELETED", "VOIDED", "DRAFT") and mid:
            deleted.append(f"xero_mj_{mid}_")
            continue
        mapped.extend(map_xero_manual_journal(mj))

    return mapped, all_ok, tokens, deleted
