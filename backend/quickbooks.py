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
        "CRITICAL: QuickBooks environment not set (QUICKBOOKS_ENV / QB_ENVIRONMENT) in a "
        "production-like environment (RENDER/ENVIRONMENT/PROD). The sandbox default is "
        "not used for API calls here (production host is forced) — set QUICKBOOKS_ENV="
        "production (or sandbox) explicitly."
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
    # Boolean flag for the owner diagnostics; the text stays in *_detail.
    return {
        "quickbooks_env": QB_ENVIRONMENT if QB_ENV_EXPLICITLY_SET else (
            "unset (would default to sandbox)" if _is_prod_like() else "sandbox (default)"
        ),
        "quickbooks_env_explicit": QB_ENV_EXPLICITLY_SET,
        "quickbooks_minorversion": QB_MINOR_VERSION,
        "quickbooks_env_warning": bool(warning),
        "quickbooks_env_warning_detail": warning,
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


def _qb_tax_amount(txn: dict) -> float:
    """TxnTaxDetail.TotalTax (default 0).

    Intuit: TotalAmt always includes tax for both TaxExcluded and TaxInclusive
    (GlobalTaxCalculation only changes whether line amounts include tax), so
    net = TotalAmt - TotalTax in every mode; NotApplicable has no TotalTax.
    """
    tax_detail = txn.get("TxnTaxDetail") or {}
    try:
        return abs(float(tax_detail.get("TotalTax") or 0))
    except (TypeError, ValueError):
        return 0.0


def _qb_currency_fields(txn: dict, amount: float, *, tax_amount: float) -> dict:
    """ExchangeRate = home-currency units per one CurrencyRef unit (Intuit)."""
    import accounting_map as amap

    currency_ref = txn.get("CurrencyRef") or {}
    return amap.money_fields(
        amount,
        currency=currency_ref.get("value"),
        fx_rate=txn.get("ExchangeRate"),
        tax_amount=tax_amount,
    )


def _base_mapped_fields(
    txn: dict, *, qb_id: str, txn_type: str, amount: float, is_credit: bool, line_suffix: str = "",
) -> dict:
    txn_date_full = str(txn.get("TxnDate") or "")
    month = txn_date_full[:7] if len(txn_date_full) >= 7 else datetime.now(timezone.utc).strftime("%Y-%m")
    slug = _qb_entity_slug(txn_type)
    provider_id = f"{qb_id}{line_suffix}"
    return {
        "amount": amount,
        "is_credit": is_credit,
        "month": month,
        "qb_txn_id": f"qb_{slug}_{provider_id}",
        "recurring": False,
        **_qb_currency_fields(txn, amount, tax_amount=_qb_tax_amount(txn)),
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


def _account_classification(
    detail: dict, account: dict, account_classes: Optional[dict[str, str]],
) -> str:
    """'revenue' | 'expense' | '' for a JE line.

    Prefer the Account entity's Classification (looked up once per sync by Id);
    fall back to an inline AccountType when a payload carries one.
    """
    acct_id = str(account.get("value") or "")
    if account_classes and acct_id in account_classes:
        cls = (account_classes[acct_id] or "").strip().lower()
        return cls if cls in ("revenue", "expense") else ""
    account_type = detail.get("AccountType") or account.get("type") or account.get("AccountType") or ""
    if not _is_pl_account_type(str(account_type)):
        return ""
    return "revenue" if _norm_account_type(str(account_type)) in ("income", "otherincome") else "expense"


def map_qb_journal_entry(txn: dict, account_classes: Optional[dict[str, str]] = None) -> list[dict]:
    """Map JournalEntry lines on Revenue/Expense accounts only, one row per line.

    Revenue accounts: Credit is +, Debit is a credit (reduces revenue).
    Expense accounts: Debit is +, Credit is a credit (reduces expense).
    """
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
        classification = _account_classification(detail, account, account_classes)
        if not classification:
            continue
        amount, _ = amap.normalize_mapped_amount(line.get("Amount"))
        if amount <= 0:
            continue
        posting = (detail.get("PostingType") or "").strip().lower()
        is_income = classification == "revenue"
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
        # Journal lines carry no document tax — net equals line amount.
        currency_fields = _qb_currency_fields(txn, amount, tax_amount=0.0)
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


# Intuit ChangeDataCapture only looks back 30 days.
QB_CDC_MAX_DAYS = 30


def _qb_is_voided(row: dict) -> bool:
    """Voided QBO transactions keep their Id but are zeroed out.

    Intuit surfaces a void as status/TxnStatus "Voided" (CDC) or TotalAmt 0 with
    PrivateNote "Voided" (regular reads).
    """
    status = str(row.get("status") or row.get("TxnStatus") or "").strip().lower()
    if status == "voided":
        return True
    try:
        total = float(row.get("TotalAmt"))
    except (TypeError, ValueError):
        return False
    return total == 0 and "voided" in str(row.get("PrivateNote") or "").lower()


def _qb_deleted_id(kind: str, entity_id: str) -> str:
    """qb_txn_id (or ``_``-terminated prefix for journal lines) to remove."""
    if kind == "journal_entry":
        return f"qb_journal_{entity_id}_"
    return f"qb_{_qb_entity_slug(kind)}_{entity_id}"


def _since_too_old_for_cdc(since: Optional[str]) -> bool:
    try:
        dt = datetime.fromisoformat(str(since).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt < datetime.now(timezone.utc) - timedelta(days=QB_CDC_MAX_DAYS)


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
                    if status == "deleted" or _qb_is_voided(row):
                        eid = str(row.get("Id") or "")
                        if eid:
                            deleted.append(_qb_deleted_id(kind, eid))
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
    if since and _since_too_old_for_cdc(since):
        # CDC can't see deletions older than 30 days — resync everything instead.
        logger.info("QuickBooks last sync older than %s days — full resync", QB_CDC_MAX_DAYS)
        since = None

    mapped: list[dict] = []
    voided: list[str] = []
    all_complete = True
    account_classes: Optional[dict[str, str]] = None
    for entity, kind in QB_SYNC_ENTITIES:
        rows, complete, tokens = await _query_qb(tokens, realm_id, entity, since)
        all_complete = all_complete and complete
        if kind == "journal_entry":
            if rows and account_classes is None:
                # One full Account read per sync; cached by Id for every JE line.
                accounts, acct_complete, tokens = await _query_qb(tokens, realm_id, "Account", None)
                all_complete = all_complete and acct_complete
                account_classes = {
                    str(a.get("Id")): str(a.get("Classification") or "")
                    for a in accounts if a.get("Id") is not None
                }
            for je in rows:
                if _qb_is_voided(je):
                    voided.append(_qb_deleted_id(kind, str(je.get("Id") or "")))
                    continue
                mapped.extend(map_qb_journal_entry(je, account_classes))
            continue
        for row in rows:
            if _qb_is_voided(row):
                if row.get("Id"):
                    voided.append(_qb_deleted_id(kind, str(row["Id"])))
                continue
            mapped_row = map_qb_transaction(row, kind)
            if mapped_row:
                mapped.append({**mapped_row, "_qb_raw_type": kind})

    deleted, tokens = await _cdc_deleted_ids(tokens, realm_id, since)
    return mapped, all_complete, tokens, list(dict.fromkeys(voided + deleted))


# Loud at import when a production host has no explicit QuickBooks environment.
warn_if_qb_env_missing_in_prod()
