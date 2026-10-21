"""SAP Business One Service Layer — login and A/R + A/P invoice sync.

Maps into the same financial_entries shape as QuickBooks/Xero (`qb_txn_id` key
included) so Decision Engine, Reports, and finance_recurrence treat all three
sources identically.

Credentials are per-workspace (Service Layer URL, CompanyDB, username, password)
— no platform OAuth app required.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx

from integration_errors import IntegrationRetryableError

logger = logging.getLogger(__name__)

PAGE_SIZE = 100
MAX_PAGES = 500  # 50k docs — if hit, return complete=False so last_synced_at is not advanced
SAP_MAX_RETRIES_429 = 3

# Block server-side requests to these ranges (SSRF). Checked via ipaddress —
# never string-prefix matching on hostnames.
_BLOCKED_NETWORKS = (
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / cloud metadata
    ipaddress.ip_network("127.0.0.0/8"),  # loopback
    ipaddress.ip_network("10.0.0.0/8"),  # RFC1918
    ipaddress.ip_network("172.16.0.0/12"),  # RFC1918
    ipaddress.ip_network("192.168.0.0/16"),  # RFC1918
)


class SapB1AuthError(Exception):
    """Login rejected or session expired — user must reconnect."""


class SapB1TransientError(IntegrationRetryableError):
    """Transient Service Layer/network failure — keep credentials."""


# Back-compat alias for callers that predate the Transient naming.
SapB1RetryableError = SapB1TransientError


class SapB1Error(Exception):
    """Non-auth Service Layer failure."""


SAP_CERT_MESSAGE = (
    "Your SAP Service Layer's HTTPS certificate isn't trusted (it is probably self-signed). "
    "Ask your SAP partner to install a certificate from a public authority, then connect again."
)


def _is_certificate_error(exc: BaseException) -> bool:
    """True when a connect failure was caused by TLS certificate verification."""
    seen = 0
    cur: Optional[BaseException] = exc
    while cur is not None and seen < 6:
        text = f"{type(cur).__name__} {cur}".lower()
        if "certificate" in text or "ssl" in text and "verify" in text:
            return True
        cur = cur.__cause__ or cur.__context__
        seen += 1
    return False


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True when the address must not be contacted from the Trenston API."""
    # IPv4-mapped IPv6 (::ffff:x.x.x.x) → check the embedded IPv4.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    # is_private covers RFC1918 + IPv6 ULA; also block loopback/link-local/multicast.
    # (Do not use is_reserved alone — it is broader than our SSRF policy.)
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return True
    for net in _BLOCKED_NETWORKS:
        if ip in net:
            return True
    return False


def _assert_public_service_layer_host(hostname: str) -> None:
    """Resolve hostname and reject private / loopback / link-local targets."""
    host = (hostname or "").strip().lower().rstrip(".")
    if not host:
        raise ValueError("Service Layer URL host is required")
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("Service Layer URL must not target a private or internal address")

    # Literal IP in the URL — check without DNS.
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if _is_blocked_ip(literal):
            raise ValueError("Service Layer URL must not target a private or internal address")
        return

    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Service Layer URL host could not be resolved") from exc
    if not infos:
        raise ValueError("Service Layer URL host could not be resolved")

    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        try:
            addr = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if _is_blocked_ip(addr):
            raise ValueError("Service Layer URL must not target a private or internal address")


def normalize_service_layer_url(url: str) -> str:
    """Return a clean https Service Layer base URL ending with /b1s/v1.

    Rejects plain http and hostnames that resolve to private/internal addresses
    so Connect cannot be used for SSRF.
    """
    raw = (url or "").strip().rstrip("/")
    if not raw:
        raise ValueError("Service Layer URL is required")
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Service Layer URL must be an https address")
    if parsed.username or parsed.password:
        raise ValueError("Service Layer URL must not include credentials")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Service Layer URL host is required")
    _assert_public_service_layer_host(hostname)

    # Rebuild netloc without userinfo; keep non-default port.
    port = parsed.port
    if port and port != 443:
        netloc = f"{hostname}:{port}"
    else:
        netloc = hostname

    path = (parsed.path or "").rstrip("/")
    if path.endswith("/b1s/v1"):
        base = f"https://{netloc}{path}"
    elif path.endswith("/b1s"):
        base = f"https://{netloc}{path}/v1"
    elif path:
        base = f"https://{netloc}{path}/b1s/v1"
    else:
        base = f"https://{netloc}/b1s/v1"
    return base


def _session_headers(session_id: str, route_id: Optional[str] = None) -> dict:
    cookie = f"B1SESSION={session_id}"
    if route_id:
        cookie = f"{cookie}; ROUTEID={route_id}"
    return {
        "Cookie": cookie,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _parse_doc_date(doc: dict) -> str:
    """Return YYYY-MM-DD, or '' when missing — never invent today."""
    raw = str(doc.get("DocDate") or doc.get("TaxDate") or "")[:10]
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        return raw
    return ""


def _line_category(doc: dict) -> str:
    for line in doc.get("DocumentLines") or []:
        if not isinstance(line, dict):
            continue
        for key in ("AccountCode", "ItemDescription", "ItemCode"):
            val = line.get(key)
            if val:
                return str(val)[:80]
    return ""


# kind -> (entry type, is a credit document, source_entity)
SAP_DOC_KINDS: dict[str, tuple[str, bool, str]] = {
    "ar": ("revenue", False, "invoice"),
    "ap": ("expense", False, "purchase_invoice"),
    "ar_cn": ("revenue", True, "credit_memo"),
    "ap_cn": ("expense", True, "purchase_credit_memo"),
}

# Service Layer collection -> kind
SAP_COLLECTIONS: tuple[tuple[str, str], ...] = (
    ("Invoices", "ar"),
    ("PurchaseInvoices", "ap"),
    ("CreditNotes", "ar_cn"),
    ("PurchaseCreditNotes", "ap_cn"),
)


def _is_cancelled(doc: dict) -> bool:
    return str(doc.get("Cancelled") or "tNO").upper() in ("TYES", "Y", "TRUE", "1")


def _num(value) -> Optional[float]:
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _sap_money(doc: dict) -> tuple[float, bool, dict]:
    """(amount in document currency, negative?, money contract).

    SAP B1 totals: DocTotal/VatSum are LOCAL currency, DocTotalFc/VatSumFc are the
    document (foreign) currency and are 0 for local-currency documents, and
    DocTotalSys/VatSumSys are the separate SYSTEM (reporting) currency. The
    workspace home currency is the company's local currency, so home amounts come
    from DocTotal/VatSum; DocRate is local units per one document-currency unit.
    """
    import accounting_map as amap

    local_total = _num(doc.get("DocTotal")) or 0.0
    local_vat = abs(_num(doc.get("VatSum")) or 0.0)
    fc_total = _num(doc.get("DocTotalFc")) or 0.0
    foreign = abs(fc_total) > 0
    doc_total = fc_total if foreign else local_total
    doc_vat = abs(_num(doc.get("VatSumFc")) or 0.0) if foreign else local_vat
    amount, negative = amap.normalize_mapped_amount(doc_total)
    rate = _num(doc.get("DocRate")) if foreign else 1.0
    if foreign and not rate and amount:
        rate = abs(local_total) / amount
    # Foreign docs without DocRate/local totals → quarantine (no invented 1.0).
    if foreign and not rate and not local_total:
        money = amap.money_fields(
            amount,
            currency=doc.get("DocCurrency"),
            fx_rate=None,
            tax_amount=doc_vat,
        )
    else:
        money = amap.money_fields(
            amount,
            currency=doc.get("DocCurrency"),
            fx_rate=rate or (1.0 if not foreign else None),
            tax_amount=doc_vat,
            amount_home=abs(local_total) if local_total else None,
            amount_net_home=(max(abs(local_total) - local_vat, 0.0) if local_total else None),
        )
    return amount, negative, money


def map_sap_document(doc: dict, *, kind: str) -> Optional[dict]:
    """Map an A/R or A/P invoice or credit memo to financial_entries fields.

    kind: "ar" (Invoices -> revenue), "ap" (PurchaseInvoices -> expense),
    "ar_cn" (CreditNotes -> revenue credit), "ap_cn" (PurchaseCreditNotes -> expense credit).
    Negative totals flip polarity; only a zero total is skipped.
    """
    import accounting_map as amap

    spec = SAP_DOC_KINDS.get(kind)
    if not spec:
        return None
    entry_type, credit_doc, source_entity = spec
    if _is_cancelled(doc):
        return None

    date_full = _parse_doc_date(doc)
    if len(date_full) < 10:
        return None
    month = date_full[:7]
    amount, negative, money = _sap_money(doc)
    if amount == 0:
        return None

    doc_entry = doc.get("DocEntry")
    if doc_entry is None:
        return None
    qb_txn_id = f"sap_b1_{kind}_{doc_entry}"

    card = (doc.get("CardName") or "").strip()
    doc_num = doc.get("DocNum")
    comments = (doc.get("Comments") or "").strip()
    category = amap.fallback_category(_line_category(doc))
    name = (card or comments or category).strip()[:120]
    extras = [p for p in [f"Doc #{doc_num}" if doc_num is not None else "", comments] if p and p != name]
    note = " · ".join(extras)

    return {
        "type": entry_type,
        "category": category,
        "name": name,
        "amount": amount,
        # Credit memos reduce their bucket; a negative total flips that again.
        "is_credit": credit_doc != negative,
        "month": month,
        "note": note[:500],
        "qb_txn_id": qb_txn_id,
        "recurring": False,
        "_sap_raw_type": source_entity,
        **money,
    }


def _since_filter(since: Optional[str]) -> str:
    if not since:
        return ""
    day = since[:10]
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        return ""
    # Incremental by last-modified (UpdateDate), not DocDate.
    return f" and UpdateDate ge '{day}'"


async def login(
    *,
    service_layer_url: str,
    company_db: str,
    username: str,
    password: str,
) -> dict:
    """Authenticate against Service Layer. Returns session fields to store."""
    base = normalize_service_layer_url(service_layer_url)
    company = (company_db or "").strip()
    user = (username or "").strip()
    if not company or not user or not password:
        raise ValueError("Company database, username, and password are required")

    login_url = urljoin(base.rstrip("/") + "/", "Login")
    try:
        async with httpx.AsyncClient(timeout=45.0, verify=True, follow_redirects=False) as hc:
            resp = await hc.post(
                login_url,
                json={"CompanyDB": company, "UserName": user, "Password": password},
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
    except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
        logger.warning("SAP B1 login network/timeout error: %s", exc)
        if _is_certificate_error(exc):
            # Many on-prem Service Layers use a self-signed certificate. Retrying never
            # fixes that, so say what to change instead of "temporarily unavailable".
            raise SapB1Error(SAP_CERT_MESSAGE) from exc
        raise SapB1TransientError("SAP connection temporarily unavailable") from exc
    if resp.status_code in (401, 403):
        logger.warning(
            "SAP B1 login rejected (%s) body=%s",
            resp.status_code, (resp.text or "")[:2000],
        )
        raise SapB1AuthError("SAP connection failed")
    if resp.status_code >= 500:
        logger.warning(
            "SAP B1 login temporarily unavailable (%s) body=%s",
            resp.status_code, (resp.text or "")[:2000],
        )
        raise SapB1TransientError("SAP connection temporarily unavailable")
    if resp.status_code >= 400:
        logger.warning(
            "SAP B1 login failed (%s) body=%s",
            resp.status_code, (resp.text or "")[:2000],
        )
        raise SapB1Error("SAP connection failed")

    body = resp.json() if resp.content else {}
    session_id = str((body or {}).get("SessionId") or "").strip()
    if not session_id:
        session_id = (resp.cookies.get("B1SESSION") or "").strip()
    if not session_id:
        raise SapB1AuthError("SAP login returned no session")

    route_id = (resp.cookies.get("ROUTEID") or "").strip() or None
    return {
        "service_layer_url": base,
        "company_db": company,
        "username": user,
        "password": password,
        "session_id": session_id,
        "route_id": route_id,
        "session_timeout": (body or {}).get("SessionTimeout"),
        "obtained_at": datetime.now(timezone.utc).isoformat(),
    }


def _revalidate_service_layer_url(creds: dict) -> str:
    """Re-check stored Service Layer URL on every outbound call (DNS rebinding TOCTOU).

    Connect-time allowlisting is not enough — hostname resolution can change between
    connect and later sync/logout requests.
    """
    return normalize_service_layer_url(creds.get("service_layer_url") or "")


async def logout(creds: dict) -> None:
    session_id = creds.get("session_id") or ""
    if not session_id or not (creds.get("service_layer_url") or ""):
        return
    try:
        base = _revalidate_service_layer_url(creds)
    except ValueError:
        logger.warning("SAP B1 logout skipped — stored service_layer_url failed revalidation")
        return
    url = urljoin(base.rstrip("/") + "/", "Logout")
    try:
        async with httpx.AsyncClient(timeout=15.0) as hc:
            await hc.post(
                url,
                headers=_session_headers(session_id, creds.get("route_id")),
            )
    except Exception:
        pass


async def ensure_session(creds: dict) -> dict:
    """Return credentials with a live session (re-login when needed)."""
    # Always re-validate before any outbound call — including session ping / re-login.
    base = _revalidate_service_layer_url(creds)
    creds = {**creds, "service_layer_url": base}
    if creds.get("session_id"):
        ping = urljoin(base.rstrip("/") + "/", "$metadata")
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as hc:
                resp = await hc.get(
                    ping,
                    headers=_session_headers(creds["session_id"], creds.get("route_id")),
                )
            if resp.status_code == 200:
                return creds
            if resp.status_code not in (401, 403):
                return creds
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            # Service Layer unreachable — do not re-login (and never drop creds) on a blip.
            logger.warning("SAP B1 session ping network/timeout error: %s", exc)
            raise SapB1TransientError("SAP connection temporarily unavailable") from exc
    return await login(
        service_layer_url=base,
        company_db=creds["company_db"],
        username=creds["username"],
        password=creds["password"],
    )


async def _fetch_collection_page(
    creds: dict,
    collection: str,
    *,
    select: str,
    filt: str,
    skip: int,
) -> httpx.Response:
    base = _revalidate_service_layer_url(creds).rstrip("/") + "/"
    url = urljoin(base, collection)
    params = {
        "$select": select,
        "$filter": filt,
        "$orderby": "DocDate asc",
        "$top": str(PAGE_SIZE),
        "$skip": str(skip),
    }
    last_exc: Optional[Exception] = None
    for attempt in range(SAP_MAX_RETRIES_429 + 1):
        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as hc:
                resp = await hc.get(
                    url,
                    params=params,
                    headers=_session_headers(creds["session_id"], creds.get("route_id")),
                )
        except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
            raise SapB1TransientError("SAP connection temporarily unavailable") from exc
        if resp.status_code != 429:
            return resp
        retry_after = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
        try:
            delay = float(retry_after) if retry_after else (2 ** attempt)
        except ValueError:
            delay = float(2 ** attempt)
        delay = min(max(delay, 1.0), 60.0)
        logger.warning("SAP B1 429 — sleeping %.1fs (attempt %s)", delay, attempt + 1)
        last_exc = SapB1TransientError("SAP rate limited")
        if attempt >= SAP_MAX_RETRIES_429:
            break
        await asyncio.sleep(delay)
    raise last_exc or SapB1TransientError("SAP rate limited")


async def _fetch_collection(
    creds: dict,
    collection: str,
    *,
    since: Optional[str] = None,
    _retried: bool = False,
) -> tuple[list[dict], bool, dict]:
    select = (
        "DocEntry,DocNum,DocDate,UpdateDate,UpdateTime,DocTotal,DocTotalFc,DocTotalSys,"
        "DocCurrency,DocRate,VatSum,VatSumFc,VatSumSys,CardName,Comments,Cancelled,DocumentLines"
    )
    # Include cancelled docs on incremental so we can delete matching entries.
    if since:
        filt = f"(Cancelled eq 'tNO' or Cancelled eq 'tYES'){_since_filter(since)}"
    else:
        filt = f"Cancelled eq 'tNO'{_since_filter(since)}"
    rows: list[dict] = []
    skip = 0
    for _ in range(MAX_PAGES):
        resp = await _fetch_collection_page(
            creds, collection, select=select, filt=filt, skip=skip,
        )
        if resp.status_code in (401, 403):
            if _retried:
                raise SapB1AuthError("SAP session expired")
            logger.info("SAP B1 401/403 on %s — re-login and retrying once", collection)
            # Clear session so ensure_session / login issues a fresh one.
            fresh = await login(
                service_layer_url=creds["service_layer_url"],
                company_db=creds["company_db"],
                username=creds["username"],
                password=creds["password"],
            )
            return await _fetch_collection(fresh, collection, since=since, _retried=True)
        if resp.status_code >= 500:
            raise SapB1TransientError("SAP connection temporarily unavailable")
        if resp.status_code >= 400:
            logger.warning(
                "SAP B1 %s fetch failed (%s) body=%s",
                collection, resp.status_code, (resp.text or "")[:2000],
            )
            raise SapB1Error("SAP connection failed")
        payload = resp.json() or {}
        page = payload.get("value") or []
        if not isinstance(page, list):
            return rows, True, creds
        rows.extend(d for d in page if isinstance(d, dict))
        if len(page) < PAGE_SIZE:
            return rows, True, creds
        skip += PAGE_SIZE
    return rows, False, creds


async def fetch_sap_transactions(creds: dict, since: Optional[str] = None) -> tuple[list[dict], bool, dict, list[str]]:
    """Pull A/R + A/P invoices and credit memos and map to financial_entries rows.

    Returns (mapped_rows, complete, creds, deleted_qb_txn_ids).
    Do not advance sap_b1_last_synced_at when complete is False.
    """
    live = await ensure_session(creds)
    out: list[dict] = []
    deleted: list[str] = []
    all_ok = True
    for collection, kind in SAP_COLLECTIONS:
        docs, ok, live = await _fetch_collection(live, collection, since=since)
        all_ok = all_ok and ok
        for doc in docs:
            if _is_cancelled(doc):
                de = doc.get("DocEntry")
                if de is not None:
                    deleted.append(f"sap_b1_{kind}_{de}")
                continue
            mapped = map_sap_document(doc, kind=kind)
            if mapped:
                out.append(mapped)
    return out, all_ok, live, deleted


def public_connection_info(creds: dict | None) -> dict:
    """Safe fields for the Integrations UI (never include password/session)."""
    if not creds:
        return {}
    return {
        "service_layer_url": creds.get("service_layer_url") or "",
        "company_db": creds.get("company_db") or "",
        "username": creds.get("username") or "",
    }
