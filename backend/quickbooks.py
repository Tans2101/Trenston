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


class QuickBooksTransientError(IntegrationRetryableError):
    """Transient Intuit/network failure — keep tokens."""


# Back-compat alias for callers that predate the Transient naming.
QuickBooksRetryableError = QuickBooksTransientError


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
        # Always report the real base used by queries (prod-like unset → production host,
        # never silent sandbox). Warning above tells ops to set the env explicitly.
        "quickbooks_api_base": _api_base(),
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
        retryable_error_cls=QuickBooksTransientError,
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


def _qb_entity_slug(txn_type: str) -> str:
    return {
        "invoice": "invoice",
        "sales_receipt": "salesreceipt",
        "credit_memo": "creditmemo",
        "refund_receipt": "refundreceipt",
        "purchase": "purchase",
        "bill": "bill",
        "vendor_credit": "vendorcredit",
        "journal_entry": "journal",
    }.get(txn_type, txn_type.replace("_", ""))


def _qb_currency_fields(txn: dict, amount: float, amount_net: float) -> dict:
    import accounting_map as amap

    currency_ref = txn.get("CurrencyRef") or {}
    currency = str(currency_ref.get("value") or currency_ref.get("name") or "").upper() or None
    rate = txn.get("ExchangeRate")
    amount_home = amap.apply_exchange_rate(amount, rate)
    return {
        "currency": currency,
        "amount_home": amount_home,
        "amount_net": round(float(amount_net), 2),
    }


def _qb_tax_net(txn: dict, gross: float) -> float:
    tax_detail = txn.get("TxnTaxDetail") or {}
    try:
        tax = float(tax_detail.get("TotalTax") or 0)
    except (TypeError, ValueError):
        tax = 0.0
    net = round(max(gross - abs(tax), 0), 2)
    return net


def _base_mapped_fields(
    txn: dict, *, qb_id: str, txn_type: str, amount: float, is_credit: bool, line_suffix: str = "",
) -> dict:
    txn_date_full = str(txn.get("TxnDate") or "")
    month = txn_date_full[:7] if len(txn_date_full) >= 7 else datetime.now(timezone.utc).strftime("%Y-%m")
    slug = _qb_entity_slug(txn_type)
    provider_id = f"{qb_id}{line_suffix}"
    amount_net = _qb_tax_net(txn, amount)
    return {
        "amount": amount,
        "is_credit": is_credit,
        "month": month,
        "qb_txn_id": f"qb_{slug}_{provider_id}",
        "recurring": False,
        **_qb_currency_fields(txn, amount, amount_net),
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
    base = _base_mapped_fields(txn, qb_id=qb_id, txn_type=txn_type, amount=amount, is_credit=is_credit)

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
        # Journal lines rarely carry TxnTaxDetail — net equals line amount.
        currency_fields = _qb_currency_fields(txn, amount, amount)
        out.append({
            "type": entry_type,
            "category": category,
            "name": name,
            "amount": amount,
            "is_credit": is_credit,
            "month": month,
            "note": "",
            "qb_txn_id": f"qb_journal_{je_id}_{line_id}",
            "recurring": False,
            "_qb_raw_type": "journal_entry",
            **currency_fields,
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
            # Incremental by last-modified time (not TxnDate).
            since_iso = since.replace("Z", "")
            if "T" not in since_iso:
                since_iso = f"{since_iso[:10]}T00:00:00"
            q = (
                f"SELECT * FROM {entity} WHERE MetaData.LastUpdatedTime >= '{since_iso}' "
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
            raise QuickBooksTransientError("QuickBooks query temporarily unavailable") from exc
        if resp.status_code == 401:
            return [], False, 401
        if resp.status_code >= 500:
            raise QuickBooksTransientError(
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


async def _cdc_deleted_ids(
    tokens: dict, realm_id: str, since: Optional[str],
) -> tuple[list[str], dict]:
    """Use ChangeDataCapture to find Deleted/Voided entities since last sync."""
    if not since:
        return [], tokens
    entities = ",".join(name for name, _ in QB_SYNC_ENTITIES)
    since_iso = since.replace("Z", "+00:00")
    url = f"{_api_base()}/v3/company/{realm_id}/cdc"
    access = tokens.get("access_token") or ""

    async def _once(token: str) -> httpx.Response:
        try:
            async with httpx.AsyncClient(timeout=45.0) as hc:
                return await hc.get(
                    url,
                    params={
                        "entities": entities,
                        "changedSince": since_iso,
                        "minorversion": str(QB_MINOR_VERSION),
                    },
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                )
        except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
            raise QuickBooksTransientError("QuickBooks CDC temporarily unavailable") from exc

    resp = await _once(access)
    if resp.status_code == 401:
        tokens = await refresh_qb_token(force_token_refresh(tokens), force=True)
        resp = await _once(tokens.get("access_token") or "")
        if resp.status_code == 401:
            raise QuickBooksAuthError("QuickBooks access token rejected")
    if resp.status_code >= 500:
        raise QuickBooksTransientError(f"QuickBooks CDC temporarily unavailable ({resp.status_code})")
    if resp.status_code != 200:
        # CDC window may be >30 days — log and skip deletes rather than fail the sync.
        logger.warning("QuickBooks CDC skipped (%s): %s", resp.status_code, (resp.text or "")[:200])
        return [], tokens

    deleted: list[str] = []
    payload = resp.json() or {}
    for block in payload.get("CDCResponse") or []:
        for qr in (block.get("QueryResponse") or []):
            if not isinstance(qr, dict):
                continue
            for ent_name, kind in QB_SYNC_ENTITIES:
                rows = qr.get(ent_name) or []
                if isinstance(rows, dict):
                    rows = [rows]
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    status = str(row.get("status") or row.get("statusCode") or "").lower()
                    # Intuit marks deletions with status=Deleted; voided docs often have PrivateNote/TxnStatus.
                    txn_status = str(row.get("TxnStatus") or "").lower()
                    if status == "deleted" or txn_status == "voided" or bool(row.get("sparse") and status == "deleted"):
                        eid = str(row.get("Id") or "")
                        if not eid:
                            continue
                        if kind == "journal_entry":
                            # Without line detail, delete any journal line prefix.
                            deleted.append(f"qb_journal_{eid}_")
                        else:
                            deleted.append(f"qb_{_qb_entity_slug(kind)}_{eid}")
    return deleted, tokens


async def fetch_qb_transactions(
    tokens: dict, realm_id: str, since: Optional[str] = None,
) -> tuple[list[dict], bool, dict, list[str]]:
    """Fetch supported QuickBooks entities and map to financial_entries rows.

    Returns (mapped_rows, complete, tokens, deleted_id_prefixes).
    complete is False when a page safety cap was hit — callers must not advance
    qb_last_synced_at in that case. deleted_id_prefixes are qb_txn_id values (or
    prefixes ending with _) to remove from financial_entries.
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
                # Skip voided journal entries when status is present.
                if str(je.get("TxnStatus") or "").lower() == "voided":
                    continue
                mapped.extend(map_qb_journal_entry(je))
            continue
        for row in rows:
            if str(row.get("TxnStatus") or "").lower() == "voided":
                continue
            mapped_row = map_qb_transaction(row, kind)
            if mapped_row:
                mapped.append({**mapped_row, "_qb_raw_type": kind})

    deleted, tokens = await _cdc_deleted_ids(tokens, realm_id, since)
    return mapped, all_complete, tokens, deleted
