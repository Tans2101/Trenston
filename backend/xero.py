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
    "accounting.invoices.read "          # Invoices + CreditNotes
    "accounting.banktransactions.read "
    "accounting.manualjournals.read "
    "accounting.settings.read"           # /Accounts (Class) for manual journal lines
)

_DATE_MS_RE = re.compile(r"/Date\((-?\d+)")

# Keep under Xero's ~60 calls/min; serialize with a small delay between requests.
XERO_MIN_INTERVAL_SEC = 1.05
XERO_MAX_RETRIES_429 = 3
_last_xero_call_at = 0.0


class XeroAuthError(Exception):
    """Refresh token invalid or revoked — user must reconnect."""


class XeroTransientError(IntegrationRetryableError):
    """Transient Xero/network failure — keep tokens."""


# Back-compat alias for callers that predate the Transient naming.
XeroRetryableError = XeroTransientError


class XeroPermissionError(Exception):
    """Tenant still connected but the call lacks permission — do not wipe tokens."""


# Back-compat alias.
XeroPermissionsError = XeroPermissionError

XERO_PERMISSION_MESSAGE = (
    "Trenston doesn't have permission to read this data in Xero. "
    "Reconnect and approve all permissions."
)


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
        retryable_error_cls=XeroTransientError,
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
        raise XeroTransientError("Xero connections temporarily unavailable") from exc
    if resp.status_code == 401:
        raise XeroAuthError("Xero access token rejected")
    if resp.status_code >= 500:
        raise XeroTransientError(f"Xero connections temporarily unavailable ({resp.status_code})")
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


def _xero_money(doc: dict, amount: float) -> dict:
    """Money contract for a Xero document.

    Xero CurrencyRate is [document currency] PER [base currency]
    (https://developer.xero.com/documentation/best-practices/data-integrity/multicurrency/),
    so home = amount / CurrencyRate. tax_amount = TotalTax, amount_net = SubTotal.
    """
    import accounting_map as amap

    try:
        rate = float(doc.get("CurrencyRate") or 0)
    except (TypeError, ValueError):
        rate = 0.0
    fx_home_per_doc = (1.0 / rate) if rate > 0 else 1.0
    sub_total = doc.get("SubTotal")
    return amap.money_fields(
        amount,
        currency=doc.get("CurrencyCode"),
        fx_rate=fx_home_per_doc,
        tax_amount=doc.get("TotalTax") or 0,
        amount_net=abs(float(sub_total)) if sub_total not in (None, "") else None,
    )


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

    money = _xero_money(inv, amount)

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
    if status != "AUTHORISED":
        return None
    txn_type = (txn.get("Type") or "").upper()
    # Overpayments and prepayments sit on the balance sheet until Xero applies them
    # to invoices/bills via allocations — the allocated invoice is what hits P&L,
    # so counting the bank line too would double-count. Transfers are not P&L.
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
        **_xero_money(txn, amount),
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
        **_xero_money(cn, amount),
    }


def map_xero_manual_journal(mj: dict, account_classes: Optional[dict[str, str]] = None) -> list[dict]:
    """Map POSTED ManualJournal lines on REVENUE / EXPENSE class accounts only.

    ``account_classes`` maps AccountID and AccountCode -> Class, from one /Accounts
    read per sync. Xero LineAmount: debits are positive, credits are negative.
    Revenue: credit (negative) adds revenue, debit reduces it (is_credit).
    Expense: debit (positive) adds expense, credit reduces it (is_credit).
    """
    import accounting_map as amap

    status = (mj.get("Status") or "").upper()
    if status not in ("POSTED",):
        return []
    mid = str(mj.get("ManualJournalID") or "")
    if not mid or not account_classes:
        return []
    date_full = _parse_xero_date(mj)
    month = date_full[:7]
    narration = (mj.get("Narration") or "").strip()
    out: list[dict] = []
    for idx, line in enumerate(mj.get("JournalLines") or []):
        if not isinstance(line, dict):
            continue
        acct_class = (
            account_classes.get(str(line.get("AccountID") or ""))
            or account_classes.get(str(line.get("AccountCode") or ""))
            or ""
        ).upper()
        if acct_class not in ("REVENUE", "EXPENSE"):
            continue
        try:
            raw = float(line.get("LineAmount") or 0)
        except (TypeError, ValueError):
            continue
        amount = round(abs(raw), 2)
        if amount <= 0:
            continue
        if acct_class == "REVENUE":
            entry_type = "revenue"
            is_credit = raw > 0
        else:
            entry_type = "expense"
            is_credit = raw < 0
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
            # Manual journals post in base currency with no document tax.
            **amap.money_fields(amount, currency=mj.get("CurrencyCode")),
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
            raise XeroTransientError("Xero temporarily unavailable") from exc
        if resp.status_code != 429:
            return resp
        retry_after = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
        try:
            delay = float(retry_after) if retry_after else (2 ** attempt)
        except ValueError:
            delay = float(2 ** attempt)
        delay = min(max(delay, 1.0), 60.0)
        logger.warning("Xero 429 — sleeping %.1fs (attempt %s)", delay, attempt + 1)
        last_exc = XeroTransientError("Xero rate limited")
        if attempt >= XERO_MAX_RETRIES_429:
            break
        await asyncio.sleep(delay)
    raise last_exc or XeroTransientError("Xero rate limited")


async def _fetch_collection_once(
    access_token: str,
    tenant_id: str,
    *,
    path: str,
    result_key: str,
    where: str,
    since: Optional[str],
    include_voided: bool = False,
    hc: Optional[httpx.AsyncClient] = None,
) -> tuple[list[dict], bool, Optional[int]]:
    """Page through a Xero collection. Returns (rows, complete, failing_status).

    ``hc`` is the sync's shared client; one is opened only when none is passed.

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
    if hc is None:
        async with httpx.AsyncClient(timeout=60.0) as own:
            return await _fetch_collection_once(
                access_token, tenant_id, path=path, result_key=result_key, where=where,
                since=since, include_voided=include_voided, hc=own,
            )
    all_rows: list[dict] = []
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
            raise XeroTransientError(
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
    raise XeroPermissionError(XERO_PERMISSION_MESSAGE)


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
    hc: Optional[httpx.AsyncClient] = None,
) -> tuple[list[dict], bool, dict]:
    """Fetch a collection; on 401 force one refresh and retry once."""
    access_token = tokens.get("access_token") or ""
    rows, complete, status = await _fetch_collection_once(
        access_token, tenant_id, path=path, result_key=result_key, where=where,
        since=since, include_voided=include_voided, hc=hc,
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
        include_voided=include_voided, hc=hc,
    )
    if status == 403:
        await _handle_xero_403(tokens, tenant_id)
    if status == 401:
        raise XeroAuthError("Xero access token rejected")
    return rows, complete, tokens


async def _fetch_account_classes(
    tokens: dict, tenant_id: str, hc: httpx.AsyncClient,
) -> tuple[Optional[dict[str, str]], dict]:
    """One /Accounts read per sync: AccountID and Code -> Class (REVENUE, EXPENSE, ...).

    Returns (None, tokens) when the grant lacks accounting.settings.read (403 with the
    tenant still connected) so older connections keep syncing everything else.
    """
    url = f"{API_BASE}/Accounts"

    async def _once(access: str) -> httpx.Response:
        return await _xero_get(hc, url, headers={
            "Authorization": f"Bearer {access}",
            "Xero-tenant-id": tenant_id,
            "Accept": "application/json",
        })

    resp = await _once(tokens.get("access_token") or "")
    if resp.status_code == 401:
        tokens = await refresh_xero_token(force_token_refresh(tokens), force=True)
        resp = await _once(tokens.get("access_token") or "")
        if resp.status_code == 401:
            raise XeroAuthError("Xero access token rejected")
    if resp.status_code == 403:
        connections = await fetch_xero_connections(tokens.get("access_token") or "")
        if tenant_id not in {c["tenant_id"] for c in connections}:
            raise XeroAuthError("Xero tenant access denied. Reconnect and pick an organisation")
        logger.warning("Xero /Accounts forbidden — skipping manual journals until reconnect")
        return None, tokens
    if resp.status_code >= 500:
        raise XeroTransientError(f"Xero Accounts temporarily unavailable ({resp.status_code})")
    if resp.status_code != 200:
        raise RuntimeError(f"Xero Accounts failed ({resp.status_code}): {resp.text[:300]}")
    classes: dict[str, str] = {}
    for acct in resp.json().get("Accounts") or []:
        cls = str(acct.get("Class") or "").upper()
        for key in (acct.get("AccountID"), acct.get("Code")):
            if key:
                classes[str(key)] = cls
    return classes, tokens


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

    # Full sync asks Xero for P&L-relevant statuses only. Incremental drops the status
    # filter (If-Modified-Since + includeArchived) so VOIDED/DELETED edits come back
    # and their entries are removed; mappers still keep only the counted statuses.
    authorised_or_paid = '(Status=="AUTHORISED" OR Status=="PAID")'
    async with httpx.AsyncClient(timeout=60.0) as hc:
        for inv_type in ("ACCREC", "ACCPAY"):
            where = f'Type=="{inv_type}"' + ("" if since else f" AND {authorised_or_paid}")
            rows, ok, tokens = await _fetch_collection(
                tokens, tenant_id,
                path="Invoices", result_key="Invoices", where=where, since=since,
                label=f"Invoices:{inv_type}", include_voided=bool(since), hc=hc,
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
            where="" if since else 'Status=="AUTHORISED"',
            since=since, label="BankTransactions", include_voided=bool(since), hc=hc,
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
            where="" if since else authorised_or_paid,
            since=since, label="CreditNotes", include_voided=bool(since), hc=hc,
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
            where="" if since else 'Status=="POSTED"',
            since=since, label="ManualJournals", include_voided=bool(since), hc=hc,
        )
        all_ok = all_ok and j_ok
        account_classes: Optional[dict[str, str]] = None
        if journals:
            account_classes, tokens = await _fetch_account_classes(tokens, tenant_id, hc)
        for mj in journals:
            status = (mj.get("Status") or "").upper()
            mid = str(mj.get("ManualJournalID") or "")
            if status in ("DELETED", "VOIDED", "DRAFT") and mid:
                deleted.append(f"xero_mj_{mid}_")
                continue
            mapped.extend(map_xero_manual_journal(mj, account_classes))

    return mapped, all_ok, tokens, deleted
