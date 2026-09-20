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

logger = logging.getLogger(__name__)

PAGE_SIZE = 100
MAX_PAGES = 20

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
    qb_txn_id = f"sap_b1_{kind}_{doc_entry}_{date_full}"

    card = (doc.get("CardName") or "").strip()
    doc_num = doc.get("DocNum")
    comments = (doc.get("Comments") or "").strip()
    category = amap.fallback_category(_line_category(doc))
    name = (card or comments or category).strip()[:120]
    extras = [p for p in [f"Doc #{doc_num}" if doc_num is not None else "", comments] if p and p != name]
    note = " · ".join(extras)

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
    }


def _since_filter(since: Optional[str]) -> str:
    if not since:
        return ""
    day = since[:10]
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        return ""
    return f" and DocDate ge '{day}'"


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
    async with httpx.AsyncClient(timeout=45.0, verify=True, follow_redirects=False) as hc:
        resp = await hc.post(
            login_url,
            json={"CompanyDB": company, "UserName": user, "Password": password},
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
    if resp.status_code in (401, 403):
        logger.warning(
            "SAP B1 login rejected (%s) body=%s",
            resp.status_code, (resp.text or "")[:2000],
        )
        raise SapB1AuthError("SAP connection failed")
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


async def logout(creds: dict) -> None:
    base = creds.get("service_layer_url") or ""
    session_id = creds.get("session_id") or ""
    if not base or not session_id:
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
    if creds.get("session_id") and creds.get("service_layer_url"):
        ping = urljoin(creds["service_layer_url"].rstrip("/") + "/", "$metadata")
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
        service_layer_url=creds["service_layer_url"],
        company_db=creds["company_db"],
        username=creds["username"],
        password=creds["password"],
    )


async def _fetch_collection(
    creds: dict,
    collection: str,
    *,
    since: Optional[str] = None,
) -> list[dict]:
    base = creds["service_layer_url"].rstrip("/") + "/"
    select = "DocEntry,DocNum,DocDate,DocTotal,CardName,Comments,Cancelled,DocumentLines"
    filt = f"Cancelled eq 'tNO'{_since_filter(since)}"
    rows: list[dict] = []
    skip = 0
    for _ in range(MAX_PAGES):
        url = (
            f"{urljoin(base, collection)}"
            f"?$select={select}&$filter={filt}"
            f"&$orderby=DocDate asc&$top={PAGE_SIZE}&$skip={skip}"
        )
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as hc:
            resp = await hc.get(
                url,
                headers=_session_headers(creds["session_id"], creds.get("route_id")),
            )
        if resp.status_code in (401, 403):
            raise SapB1AuthError("SAP session expired")
        if resp.status_code >= 400:
            logger.warning(
                "SAP B1 %s fetch failed (%s) body=%s",
                collection, resp.status_code, (resp.text or "")[:2000],
            )
            raise SapB1Error("SAP connection failed")
        payload = resp.json() or {}
        page = payload.get("value") or []
        if not isinstance(page, list):
            break
        rows.extend(d for d in page if isinstance(d, dict))
        if len(page) < PAGE_SIZE:
            break
        skip += PAGE_SIZE
    return rows


async def fetch_sap_transactions(creds: dict, since: Optional[str] = None) -> list[dict]:
    """Pull A/R Invoices + A/P PurchaseInvoices and map to financial_entries rows."""
    live = await ensure_session(creds)
    ar_docs = await _fetch_collection(live, "Invoices", since=since)
    ap_docs = await _fetch_collection(live, "PurchaseInvoices", since=since)
    out: list[dict] = []
    for doc in ar_docs:
        mapped = map_sap_document(doc, kind="ar")
        if mapped:
            out.append(mapped)
    for doc in ap_docs:
        mapped = map_sap_document(doc, kind="ap")
        if mapped:
            out.append(mapped)
    return out


def public_connection_info(creds: dict | None) -> dict:
    """Safe fields for the Integrations UI (never include password/session)."""
    if not creds:
        return {}
    return {
        "service_layer_url": creds.get("service_layer_url") or "",
        "company_db": creds.get("company_db") or "",
        "username": creds.get("username") or "",
    }
