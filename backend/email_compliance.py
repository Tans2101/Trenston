"""CAN-SPAM / marketing-email compliance helpers for Resend sends.

Classification of every Trenston Resend template (audit):

  Commercial (must include physical address + working unsubscribe):
    - weekly digest / weekly pack PDF  (_weekly_digest_email_html)
    - daily ops briefing       (_daily_briefing_email_html)
    - trial-ending retention reminder   (retention.trial_email_html)
    - inactivity catch-up nudge         (retention.inactivity_email_html)

  Transactional (exempt — no unsubscribe footer):
    - workspace invite                  (_invite_email_html)
    - task delegation notification      (_task_delegation_email_html)
    - high-severity decision alerts     (alert_notify.build_alert_email_html)

  Not sent by Trenston Resend (Clerk / Paddle):
    - password resets, magic links, billing receipts

Unsubscribe is honored immediately: the click writes an email_suppressions
document before the confirmation page is shown, and commercial send paths
skip suppressed addresses on the next (and every subsequent) send.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import quote

logger = logging.getLogger("helm.email_compliance")

# Matches frontend/src/lib/marketingCopy.js COMPANY_LOCATION and Privacy.jsx.
COMPANY_POSTAL_ADDRESS = "BGC, Taguig, Philippines"
COMPANY_LEGAL_NAME = "Trenston"

# One category covers all commercial Resend templates so a single click stops
# weekly pack + retention emails without affecting transactional alerts/invites.
CATEGORY_COMMERCIAL = "commercial"

CATEGORY_LABELS = {
    CATEGORY_COMMERCIAL: "Trenston product emails (weekly pack and catch-up reminders)",
}

TOKEN_TTL_SECONDS = 365 * 24 * 3600


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(token: str) -> bytes:
    pad = "=" * (-len(token) % 4)
    return base64.urlsafe_b64decode(token + pad)


def make_unsubscribe_token(
    email: str,
    category: str = CATEGORY_COMMERCIAL,
    *,
    secret: str,
    now: Optional[int] = None,
) -> str:
    """HMAC-signed token: no login required to unsubscribe."""
    addr = normalize_email(email)
    if not addr or "@" not in addr:
        raise ValueError("invalid email")
    cat = (category or CATEGORY_COMMERCIAL).strip() or CATEGORY_COMMERCIAL
    exp = int(now if now is not None else time.time()) + TOKEN_TTL_SECONDS
    payload = f"{addr}|{cat}|{exp}"
    sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return _b64encode(f"{payload}|{sig}".encode("utf-8"))


def parse_unsubscribe_token(token: str, *, secret: str, now: Optional[int] = None) -> dict:
    """Return {email, category} or raise ValueError if invalid/expired."""
    raw = (token or "").strip()
    if not raw:
        raise ValueError("missing token")
    try:
        decoded = _b64decode(raw).decode("utf-8")
    except Exception as exc:
        raise ValueError("invalid token") from exc
    parts = decoded.split("|")
    if len(parts) != 4:
        raise ValueError("invalid token")
    email, category, exp_s, sig = parts
    payload = f"{email}|{category}|{exp_s}"
    expected = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise ValueError("invalid token")
    try:
        exp = int(exp_s)
    except ValueError as exc:
        raise ValueError("invalid token") from exc
    if exp < int(now if now is not None else time.time()):
        raise ValueError("expired token")
    if "@" not in email:
        raise ValueError("invalid token")
    return {"email": normalize_email(email), "category": category}


def unsubscribe_url(app_base_url: str, email: str, *, secret: str, category: str = CATEGORY_COMMERCIAL) -> str:
    base = (app_base_url or "").rstrip("/")
    token = make_unsubscribe_token(email, category, secret=secret)
    # Frontend landing page; it calls the API so suppression is immediate.
    return f"{base}/unsubscribe?token={quote(token, safe='')}"


def api_unsubscribe_url(api_base_url: str, email: str, *, secret: str, category: str = CATEGORY_COMMERCIAL) -> str:
    """Direct API URL for List-Unsubscribe / one-click POST."""
    base = (api_base_url or "").rstrip("/")
    token = make_unsubscribe_token(email, category, secret=secret)
    return f"{base}/api/email/unsubscribe?token={quote(token, safe='')}"


def list_unsubscribe_headers(one_click_url: str) -> dict:
    """RFC 2369 + RFC 8058 headers for commercial mail."""
    url = (one_click_url or "").strip()
    if not url:
        return {}
    return {
        "List-Unsubscribe": f"<{url}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }


def marketing_footer_html(*, unsubscribe_url: str, postal_address: str = COMPANY_POSTAL_ADDRESS) -> str:
    unsub = html.escape(unsubscribe_url, quote=True)
    addr = html.escape(postal_address or COMPANY_POSTAL_ADDRESS)
    name = html.escape(COMPANY_LEGAL_NAME)
    return f"""\
<tr><td style="padding:20px 36px 28px 36px;border-top:1px solid rgba(255,255,255,0.06);">
<p style="color:#52525b;font-size:12px;margin:0;line-height:1.6;">
{name}<br>{addr}<br><br>
You received this because you use Trenston. 
<a href="{unsub}" style="color:#a1a1aa;text-decoration:underline;">Unsubscribe</a>
 from these emails.
</p>
</td></tr>"""


def inject_marketing_footer(html_body: str, *, unsubscribe_url: str) -> str:
    """Insert CAN-SPAM footer into an existing email HTML shell.

    Prefers injecting a table row before the outer card closes; falls back to
    appending before </body>.
    """
    footer = marketing_footer_html(unsubscribe_url=unsubscribe_url)
    body = html_body or ""
    # Common Trenston shell: footer row belongs inside the inner card table.
    marker = "</table>\n</td></tr></table></body></html>"
    if marker in body and "Unsubscribe" not in body:
        # Insert before the final inner </table> that closes the card.
        # Weekly/invite shells end with: </td></tr></table></td></tr></table></body>
        needle = "</td></tr>\n</table>\n</td></tr></table></body></html>"
        if needle in body:
            return body.replace(needle, f"</td></tr>\n{footer}\n</table>\n</td></tr></table></body></html>", 1)
    if "</body>" in body.lower() and "Unsubscribe" not in body:
        # Wrap footer in a minimal table so it still renders.
        block = f'<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center"><table width="520" cellpadding="0" cellspacing="0">{footer}</table></td></tr></table>'
        idx = body.lower().rfind("</body>")
        return body[:idx] + block + body[idx:]
    if "Unsubscribe" in body:
        return body
    return body + footer


async def is_suppressed(db, email: str, category: str = CATEGORY_COMMERCIAL) -> bool:
    addr = normalize_email(email)
    if not addr:
        return True
    doc = await db.email_suppressions.find_one(
        {"email": addr, "category": category},
        {"_id": 0, "email": 1},
    )
    return bool(doc)


async def filter_unsuppressed(db, emails: list, category: str = CATEGORY_COMMERCIAL) -> list[str]:
    """Return unique normalized addresses that are not suppressed (one query)."""
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in emails or []:
        addr = normalize_email(raw)
        if not addr or addr in seen:
            continue
        seen.add(addr)
        ordered.append(addr)
    if not ordered:
        return []
    rows = await db.email_suppressions.find(
        {"email": {"$in": ordered}, "category": category},
        {"_id": 0, "email": 1},
    ).to_list(len(ordered) + 5)
    blocked = {normalize_email(r.get("email")) for r in rows if r.get("email")}
    return [addr for addr in ordered if addr not in blocked]


async def suppress_email(
    db,
    email: str,
    category: str = CATEGORY_COMMERCIAL,
    *,
    source: str = "one_click",
) -> dict:
    """Immediate suppression (honored on the next send — no batch delay)."""
    addr = normalize_email(email)
    cat = (category or CATEGORY_COMMERCIAL).strip() or CATEGORY_COMMERCIAL
    now = datetime.now(timezone.utc).isoformat()
    await db.email_suppressions.update_one(
        {"email": addr, "category": cat},
        {"$set": {
            "email": addr,
            "category": cat,
            "suppressed_at": now,
            "source": source,
            "label": CATEGORY_LABELS.get(cat, cat),
        }},
        upsert=True,
    )
    logger.info("email suppressed email=%s category=%s source=%s", addr, cat, source)
    return {"email": addr, "category": cat, "suppressed_at": now}


def category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category or CATEGORY_COMMERCIAL)
