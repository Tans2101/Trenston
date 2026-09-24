"""SAP Business One Service Layer — login and A/R + A/P invoice sync.

Maps into the same financial_entries shape as QuickBooks/Xero (`qb_txn_id` key
included) so Decision Engine, Reports, and finance_recurrence treat all three
sources identically.

Credentials are per-workspace (Service Layer URL, CompanyDB, username, password)
— no platform OAuth app required.
"""
from __future__ import annotations

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
MAX_PAGES = 200  # 20k docs — if hit, return complete=False so last_synced_at is not advanced

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


class SapB1RetryableError(IntegrationRetryableError):
    """Transient Service Layer/network failure — keep credentials."""


class SapB1Error(Exception):
    """Non-auth Service Layer failure."""


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True when the address must not be contacted from the Trenston API."""
    # IPv4-mapped IPv6 (::ffff:x.x.x.x) → check the embedded IPv4.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
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
    raw = str(doc.get("DocDate") or doc.get("TaxDate") or "")[:10]
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        return raw
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _line_category(doc: dict) -> str:
    for line in doc.get("DocumentLines") or []:
        if not isinstance(line, dict):
            continue
        for key in ("AccountCode", "ItemDescription", "ItemCode"):
            val = line.get(key)
            if val:
                return str(val)[:80]
    return ""


def map_sap_document(doc: dict, *, kind: str) -> Optional[dict]:
    """Map an Invoices or PurchaseInvoices document to financial_entries fields.

    kind: \"ar\" (customer invoice → revenue) or \"ap\" (purchase invoice → expense).
    """
    import accounting_map as amap

    if kind not in ("ar", "ap"):
        return None
    if str(doc.get("Cancelled") or "tNO").upper() in ("TYES", "Y", "TRUE", "1"):
        return None

    date_full = _parse_doc_date(doc)
    month = date_full[:7]
    amount, is_credit = amap.normalize_mapped_amount(doc.get("DocTotal"))
    if amount <= 0:
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

    try:
        vat = float(doc.get("VatSum") or 0)
    except (TypeError, ValueError):
        vat = 0.0
    amount_net = round(max(amount - abs(vat), 0), 2)
    # DocTotalSys is local/system currency total when present; else DocRate conversion.
    if doc.get("DocTotalSys") is not None:
        amount_home, _ = amap.normalize_mapped_amount(doc.get("DocTotalSys"))
    else:
        amount_home = amap.apply_exchange_rate(amount, doc.get("DocRate"))
    currency = str(doc.get("DocCurrency") or "").upper() or None
    money = {"currency": currency, "amount_net": amount_net, "amount_home": amount_home}

    if kind == "ap":
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
            "_sap_raw_type": "purchase_invoice",
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
        "_sap_raw_type": "invoice",
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
        raise SapB1RetryableError("SAP connection temporarily unavailable") from exc
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
        raise SapB1RetryableError("SAP connection temporarily unavailable")
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
        except httpx.HTTPError:
            pass
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
    url = (
        f"{urljoin(base, collection)}"
        f"?$select={select}&$filter={filt}"
        f"&$orderby=DocDate asc&$top={PAGE_SIZE}&$skip={skip}"
    )
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as hc:
            return await hc.get(
                url,
                headers=_session_headers(creds["session_id"], creds.get("route_id")),
            )
    except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
        raise SapB1RetryableError("SAP connection temporarily unavailable") from exc


async def _fetch_collection(
    creds: dict,
    collection: str,
    *,
    since: Optional[str] = None,
    _retried: bool = False,
) -> tuple[list[dict], bool, dict]:
    select = "DocEntry,DocNum,DocDate,UpdateDate,DocTotal,DocTotalSys,DocCurrency,DocRate,VatSum,CardName,Comments,Cancelled,DocumentLines"
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
            raise SapB1RetryableError("SAP connection temporarily unavailable")
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
    """Pull A/R Invoices + A/P PurchaseInvoices and map to financial_entries rows.

    Returns (mapped_rows, complete, creds, deleted_qb_txn_ids).
    Do not advance sap_b1_last_synced_at when complete is False.
    """
    live = await ensure_session(creds)
    ar_docs, ar_ok, live = await _fetch_collection(live, "Invoices", since=since)
    ap_docs, ap_ok, live = await _fetch_collection(live, "PurchaseInvoices", since=since)
    out: list[dict] = []
    deleted: list[str] = []
    for doc in ar_docs:
        if str(doc.get("Cancelled") or "tNO").upper() in ("TYES", "Y", "TRUE", "1"):
            de = doc.get("DocEntry")
            if de is not None:
                deleted.append(f"sap_b1_ar_{de}")
            continue
        mapped = map_sap_document(doc, kind="ar")
        if mapped:
            out.append(mapped)
    for doc in ap_docs:
        if str(doc.get("Cancelled") or "tNO").upper() in ("TYES", "Y", "TRUE", "1"):
            de = doc.get("DocEntry")
            if de is not None:
                deleted.append(f"sap_b1_ap_{de}")
            continue
        mapped = map_sap_document(doc, kind="ap")
        if mapped:
            out.append(mapped)
    return out, ar_ok and ap_ok, live, deleted


def public_connection_info(creds: dict | None) -> dict:
    """Safe fields for the Integrations UI (never include password/session)."""
    if not creds:
        return {}
    return {
        "service_layer_url": creds.get("service_layer_url") or "",
        "company_db": creds.get("company_db") or "",
        "username": creds.get("username") or "",
    }
