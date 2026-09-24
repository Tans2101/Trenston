"""Google OAuth — token refresh, Calendar, and Gmail helpers.

Gmail access is read-only metadata + snippets for the daily briefing.
Do not persist full message bodies; callers should pass through API responses only.
"""
from __future__ import annotations

import base64
import email.utils
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote

import httpx

from integration_errors import (
    IntegrationRetryableError,
    force_token_refresh,
    refresh_http_post,
)

logger = logging.getLogger(__name__)

TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
GMAIL_PROFILE_URL = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
GMAIL_MESSAGES_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
GMAIL_DRAFTS_URL = "https://gmail.googleapis.com/gmail/v1/users/me/drafts"
SHEETS_URL = "https://sheets.googleapis.com/v4/spreadsheets"
DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"
CALENDAR_EVENTS_SCOPE = "https://www.googleapis.com/auth/calendar.events"
SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"

# Extra scopes beyond the original Calendar + Gmail read grant. Existing
# workspaces need one reconnect (prompt=consent) before write features work.
WRITE_SCOPE_FRAGMENTS = (
    "calendar.events",
    "gmail.compose",
    "spreadsheets",
    "drive.file",
)

# Prefer Gmail's own importance signal; fall back to recent primary inbox.
_IMPORTANT_QUERY = "(is:important OR is:starred) newer_than:14d -category:promotions -category:social -category:forums"
_INBOX_FALLBACK_QUERY = "in:inbox newer_than:5d -category:promotions -category:social -category:forums -in:chats"


class GoogleAuthError(Exception):
    """Refresh token invalid or revoked — user must reconnect."""


class GoogleRetryableError(IntegrationRetryableError):
    """Transient Google/network failure — keep tokens."""


def has_gmail_scope(tokens: Optional[dict]) -> bool:
    """True when the stored Google token grant includes gmail.readonly."""
    return has_scope(tokens, "gmail.readonly")


def has_scope(tokens: Optional[dict], fragment: str) -> bool:
    if not tokens or not fragment:
        return False
    return fragment in (tokens.get("scope") or "")


def missing_write_scopes(tokens: Optional[dict]) -> list[str]:
    if not tokens:
        return list(WRITE_SCOPE_FRAGMENTS)
    return [frag for frag in WRITE_SCOPE_FRAGMENTS if not has_scope(tokens, frag)]


def google_capabilities(tokens: Optional[dict]) -> dict:
    return {
        "connected": bool(tokens),
        "gmail": has_gmail_scope(tokens),
        "gmail_compose": has_scope(tokens, "gmail.compose"),
        "calendar_write": has_scope(tokens, "calendar.events"),
        "sheets": has_scope(tokens, "spreadsheets"),
        "drive_file": has_scope(tokens, "drive.file"),
        "needs_reconnect": bool(tokens) and bool(missing_write_scopes(tokens)),
    }


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


async def refresh_google_token(
    tokens: dict, client_id: str, client_secret: str, *, force: bool = False,
) -> dict:
    """Return valid tokens, refreshing via Google when the access token is near expiry."""
    if not force and not _token_needs_refresh(tokens):
        return tokens
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise GoogleAuthError("Missing refresh token. Reconnect Google Calendar")
    if not client_id or not client_secret:
        raise GoogleAuthError("Google OAuth is not configured")

    resp = await refresh_http_post(
        provider="Google",
        url=TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        headers={"Accept": "application/json"},
        auth_error_cls=GoogleAuthError,
        retryable_error_cls=GoogleRetryableError,
    )

    updated = {**tokens, **resp.json()}
    updated["obtained_at"] = datetime.now(timezone.utc).isoformat()
    if "refresh_token" not in updated and refresh_token:
        updated["refresh_token"] = refresh_token
    return updated


def _parse_event_dt(value: str) -> Optional[datetime]:
    if not value:
        return None
    if len(value) == 10:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _infer_meeting_type(title: str, attendee_count: int) -> str:
    lower = (title or "").lower()
    if attendee_count <= 2 or "1:1" in lower or "1-1" in lower:
        return "1:1"
    if any(k in lower for k in ("board", "investor", "advisor")):
        return "Board"
    if any(k in lower for k in ("demo", "sales", "customer", "prospect", "acme")):
        return "Sales"
    return "Internal"


def _all_day_exclusive_end(date_yyyy_mm_dd: str) -> str:
    """Google all-day end.date is exclusive — return the day after date_yyyy_mm_dd."""
    day = datetime.strptime(date_yyyy_mm_dd[:10], "%Y-%m-%d").date()
    return (day + timedelta(days=1)).isoformat()


def _map_google_event(event: dict) -> Optional[dict]:
    start_obj = event.get("start") or {}
    end_obj = event.get("end") or {}
    start_raw = start_obj.get("dateTime") or start_obj.get("date")
    end_raw = end_obj.get("dateTime") or end_obj.get("date")
    all_day = bool(start_obj.get("date") and not start_obj.get("dateTime"))
    start_dt = _parse_event_dt(start_raw or "")
    end_dt = _parse_event_dt(end_raw or "")
    if not start_dt:
        return None

    # Google Calendar all-day end.date is exclusive. Normalize to an inclusive
    # end day (matching department deadlines) so the UI does not paint a ghost
    # extra day.
    end_date_inclusive = None
    if all_day and end_dt:
        inclusive = (end_dt - timedelta(days=1)).replace(
            hour=23, minute=59, second=59, microsecond=0
        )
        if inclusive.date() < start_dt.date():
            inclusive = start_dt.replace(hour=23, minute=59, second=59, microsecond=0)
        end_dt = inclusive
        end_date_inclusive = inclusive.strftime("%Y-%m-%d")
    elif all_day:
        end_dt = start_dt.replace(hour=23, minute=59, second=59, microsecond=0)
        end_date_inclusive = start_dt.strftime("%Y-%m-%d")

    if end_dt:
        duration_m = max(int((end_dt - start_dt).total_seconds() // 60), 15)
    else:
        duration_m = 60

    attendees = event.get("attendees") or []
    attendee_count = len(attendees) if attendees else 1
    title = event.get("summary") or "Untitled meeting"

    mapped = {
        "id": event.get("id") or f"gcal_{hash(title) & 0xfffffff}",
        "title": title,
        "time": "" if all_day else start_dt.strftime("%H:%M"),
        "duration": duration_m,
        "attendees": attendee_count,
        "type": _infer_meeting_type(title, attendee_count),
        "prep": None,
        "importance": "medium",
        "source": "google_calendar",
        "date": start_dt.strftime("%Y-%m-%d"),
        "start_at": start_dt.isoformat(),
        "end_at": end_dt.isoformat() if end_dt else None,
        "all_day": all_day,
    }
    if end_date_inclusive:
        mapped["end_date"] = end_date_inclusive
    return mapped


def _today_bounds() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()


def week_bounds(week_start: datetime) -> tuple[str, str]:
    """Return ISO bounds for a 7-day window starting at week_start (UTC midnight)."""
    start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    return start.isoformat(), end.isoformat()


async def _fetch_calendar_events(
    tokens: dict,
    client_id: str,
    client_secret: str,
    time_min: str,
    time_max: str,
    *,
    max_results: int = 100,
) -> tuple[list[dict], dict]:
    tokens = await refresh_google_token(tokens, client_id, client_secret)
    access_token = tokens.get("access_token")
    if not access_token:
        raise GoogleAuthError("Missing access token")

    async def _once(access: str) -> httpx.Response:
        try:
            async with httpx.AsyncClient(timeout=45.0) as hc:
                return await hc.get(
                    CALENDAR_EVENTS_URL,
                    headers={"Authorization": f"Bearer {access}"},
                    params={
                        "timeMin": time_min,
                        "timeMax": time_max,
                        "maxResults": max_results,
                        "singleEvents": True,
                        "orderBy": "startTime",
                    },
                )
        except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
            raise GoogleRetryableError("Google Calendar temporarily unavailable") from exc

    resp = await _once(access_token)
    if resp.status_code == 401:
        logger.info("Google Calendar 401 — forcing token refresh and retrying once")
        tokens = await refresh_google_token(
            force_token_refresh(tokens), client_id, client_secret, force=True,
        )
        access_token = tokens.get("access_token") or ""
        resp = await _once(access_token)
        if resp.status_code == 401:
            raise GoogleAuthError("Google access token rejected. Reconnect Google Calendar")
    if resp.status_code >= 500:
        raise GoogleRetryableError(
            f"Google Calendar temporarily unavailable ({resp.status_code})"
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Google Calendar API failed ({resp.status_code}): {resp.text[:300]}")

    items = resp.json().get("items") or []
    events = [m for m in (_map_google_event(ev) for ev in items) if m]
    return events, tokens


def _compute_hours(meetings: list[dict]) -> tuple[float, float]:
    meeting_m = sum(m.get("duration", 0) for m in meetings)
    meeting_hours = round(meeting_m / 60, 2)
    focus_hours = round(max(8 - meeting_hours, 0), 2)
    return focus_hours, meeting_hours


async def fetch_today_calendar(
    tokens: dict,
    client_id: str,
    client_secret: str,
    *,
    max_results: int = 25,
) -> tuple[list[dict], float, float, dict]:
    """Fetch today's primary-calendar events. Returns (meetings, focus_hours, meeting_hours, tokens)."""
    time_min, time_max = _today_bounds()
    meetings, tokens = await _fetch_calendar_events(
        tokens, client_id, client_secret, time_min, time_max, max_results=max_results,
    )
    focus_hours, meeting_hours = _compute_hours(meetings)
    return meetings, focus_hours, meeting_hours, tokens


async def fetch_week_calendar(
    tokens: dict,
    client_id: str,
    client_secret: str,
    week_start: datetime,
    *,
    max_results: int = 100,
) -> tuple[list[dict], dict]:
    """Fetch one week of events from primary calendar."""
    time_min, time_max = week_bounds(week_start)
    return await _fetch_calendar_events(
        tokens, client_id, client_secret, time_min, time_max, max_results=max_results,
    )


def _header_map(payload: dict) -> dict[str, str]:
    headers = ((payload.get("payload") or {}).get("headers")) or []
    out: dict[str, str] = {}
    for h in headers:
        name = (h.get("name") or "").lower()
        if name and name not in out:
            out[name] = h.get("value") or ""
    return out


def _parse_from(raw: str) -> tuple[str, str]:
    """Return (display_name, email) from a From header value."""
    name, addr = email.utils.parseaddr(raw or "")
    addr = (addr or "").strip().lower()
    name = (name or "").strip() or (addr.split("@")[0] if addr else "Unknown")
    return name, addr


def _email_domain(addr: str) -> str:
    if "@" not in (addr or ""):
        return ""
    return addr.rsplit("@", 1)[-1].lower()


def _parse_message_date(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError):
        return None


def _thread_link(thread_id: str) -> str:
    tid = quote(thread_id or "", safe="")
    return f"https://mail.google.com/mail/u/0/#inbox/{tid}"


def _map_gmail_message(msg: dict, *, own_domain: str = "") -> Optional[dict]:
    headers = _header_map(msg)
    subject = (headers.get("subject") or "(no subject)").strip()
    sender_name, sender_email = _parse_from(headers.get("from") or "")
    if own_domain and sender_email and _email_domain(sender_email) == own_domain:
        # Skip self-sent / same-domain noise when filtering for external signal
        labels = set(msg.get("labelIds") or [])
        if "IMPORTANT" not in labels and "STARRED" not in labels:
            return None

    when = _parse_message_date(headers.get("date") or "")
    thread_id = msg.get("threadId") or msg.get("id") or ""
    if not thread_id:
        return None
    snippet = (msg.get("snippet") or "").strip()
    # Snippets only — never include body payload data
    return {
        "id": thread_id,
        "message_id": msg.get("id") or thread_id,
        "sender": sender_name,
        "sender_email": sender_email,
        "subject": subject,
        "snippet": snippet[:280],
        "thread_link": _thread_link(thread_id),
        "last_message_at": when.isoformat() if when else None,
    }


async def _gmail_list_ids(hc: httpx.AsyncClient, access_token: str, query: str, *, max_results: int) -> list[dict]:
    resp = await hc.get(
        GMAIL_MESSAGES_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        params={"q": query, "maxResults": max_results},
    )
    if resp.status_code == 401:
        raise GoogleAuthError("Google access token rejected. Reconnect Google")
    if resp.status_code == 403:
        raise GoogleAuthError("Gmail access not granted. Reconnect Google to enable Gmail")
    if resp.status_code != 200:
        raise RuntimeError(f"Gmail list failed ({resp.status_code}): {resp.text[:300]}")
    return list(resp.json().get("messages") or [])


async def _gmail_get_message(hc: httpx.AsyncClient, access_token: str, message_id: str) -> dict:
    resp = await hc.get(
        f"{GMAIL_MESSAGES_URL}/{message_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        params={
            "format": "metadata",
            "metadataHeaders": ["From", "Subject", "Date"],
            "fields": "id,threadId,snippet,labelIds,payload/headers",
        },
    )
    if resp.status_code == 401:
        raise GoogleAuthError("Google access token rejected. Reconnect Google")
    if resp.status_code == 403:
        raise GoogleAuthError("Gmail access not granted. Reconnect Google to enable Gmail")
    if resp.status_code != 200:
        raise RuntimeError(f"Gmail message failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json()


async def fetch_important_threads(
    tokens: dict,
    client_id: str,
    client_secret: str,
    *,
    since: Optional[datetime] = None,
    limit: int = 5,
) -> tuple[list[dict], dict]:
    """
    Pull a small set of relevant Gmail threads for the CEO briefing.

    Uses Gmail importance/star signals first, then recent primary inbox with a
    preference for external senders. Returns metadata + snippets only (no bodies).
    """
    if not has_gmail_scope(tokens):
        raise GoogleAuthError("Gmail access not granted. Reconnect Google to enable Gmail")

    tokens = await refresh_google_token(tokens, client_id, client_secret)
    access_token = tokens.get("access_token")
    if not access_token:
        raise GoogleAuthError("Missing access token")

    limit = max(1, min(int(limit or 5), 8))
    query = _IMPORTANT_QUERY
    if since is not None:
        # Gmail `after:` is epoch seconds (UTC)
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        query = f"{_IMPORTANT_QUERY} after:{int(since.timestamp())}"

    async with httpx.AsyncClient(timeout=45.0) as hc:
        profile = await hc.get(
            GMAIL_PROFILE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        own_email = ""
        if profile.status_code == 200:
            own_email = (profile.json().get("emailAddress") or "").strip().lower()
        own_domain = _email_domain(own_email)

        refs = await _gmail_list_ids(hc, access_token, query, max_results=max(limit * 3, 12))
        prefer_external = False
        if len(refs) < limit:
            prefer_external = True
            refs = await _gmail_list_ids(
                hc, access_token, _INBOX_FALLBACK_QUERY, max_results=max(limit * 4, 16),
            )

        threads: list[dict] = []
        seen_threads: set[str] = set()
        for ref in refs:
            mid = ref.get("id")
            if not mid:
                continue
            raw = await _gmail_get_message(hc, access_token, mid)
            mapped = _map_gmail_message(
                raw,
                own_domain=own_domain if prefer_external else "",
            )
            if not mapped:
                continue
            tid = mapped["id"]
            if tid in seen_threads:
                continue
            seen_threads.add(tid)
            threads.append(mapped)
            if len(threads) >= limit:
                break

    threads.sort(key=lambda t: t.get("last_message_at") or "", reverse=True)
    return threads[:limit], tokens


async def create_calendar_event(
    tokens: dict,
    client_id: str,
    client_secret: str,
    *,
    title: str,
    start_iso: str,
    end_iso: str,
    all_day: bool = False,
    date: Optional[str] = None,
) -> tuple[str, dict]:
    """Insert an event on the user's primary calendar. Returns (google_event_id, tokens)."""
    if not has_scope(tokens, "calendar.events"):
        raise GoogleAuthError("Calendar write access not granted. Reconnect Google")
    tokens = await refresh_google_token(tokens, client_id, client_secret)
    if all_day and date:
        body = {
            "summary": title,
            "start": {"date": date[:10]},
            # Google requires exclusive end.date > start.date for all-day events.
            "end": {"date": _all_day_exclusive_end(date)},
        }
    else:
        body = {
            "summary": title,
            "start": {"dateTime": start_iso, "timeZone": "UTC"},
            "end": {"dateTime": end_iso, "timeZone": "UTC"},
        }
    async with httpx.AsyncClient(timeout=30.0) as hc:
        resp = await hc.post(
            CALENDAR_EVENTS_URL,
            headers={"Authorization": f"Bearer {tokens.get('access_token')}", "Content-Type": "application/json"},
            json=body,
        )
    if resp.status_code in (401, 403):
        raise GoogleAuthError("Calendar write failed. Reconnect Google")
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Calendar insert failed ({resp.status_code}): {resp.text[:300]}")
    return (resp.json() or {}).get("id") or "", tokens


async def patch_calendar_event(
    tokens: dict,
    client_id: str,
    client_secret: str,
    google_event_id: str,
    *,
    title: str,
    start_iso: str,
    end_iso: str,
    all_day: bool = False,
    date: Optional[str] = None,
) -> dict:
    if not google_event_id:
        return tokens
    if not has_scope(tokens, "calendar.events"):
        return tokens
    tokens = await refresh_google_token(tokens, client_id, client_secret)
    if all_day and date:
        body = {
            "summary": title,
            "start": {"date": date[:10]},
            "end": {"date": _all_day_exclusive_end(date)},
        }
    else:
        body = {
            "summary": title,
            "start": {"dateTime": start_iso, "timeZone": "UTC"},
            "end": {"dateTime": end_iso, "timeZone": "UTC"},
        }
    async with httpx.AsyncClient(timeout=30.0) as hc:
        resp = await hc.patch(
            f"{CALENDAR_EVENTS_URL}/{google_event_id}",
            headers={"Authorization": f"Bearer {tokens.get('access_token')}", "Content-Type": "application/json"},
            json=body,
        )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Calendar patch failed ({resp.status_code}): {resp.text[:300]}")
    return tokens


async def delete_calendar_event(
    tokens: dict,
    client_id: str,
    client_secret: str,
    google_event_id: str,
) -> dict:
    if not google_event_id or not has_scope(tokens, "calendar.events"):
        return tokens
    tokens = await refresh_google_token(tokens, client_id, client_secret)
    async with httpx.AsyncClient(timeout=30.0) as hc:
        resp = await hc.delete(
            f"{CALENDAR_EVENTS_URL}/{google_event_id}",
            headers={"Authorization": f"Bearer {tokens.get('access_token')}"},
        )
    if resp.status_code not in (200, 204, 404, 410):
        raise RuntimeError(f"Calendar delete failed ({resp.status_code}): {resp.text[:300]}")
    return tokens


def build_ledger_spreadsheet_body(title: str, summary_rows: list[list], entry_rows: list[list]) -> dict:
    return {
        "properties": {"title": title},
        "sheets": [
            {
                "properties": {"title": "Summary", "gridProperties": {"frozenRowCount": 1}},
                "data": [{
                    "startRow": 0,
                    "startColumn": 0,
                    "rowData": [{"values": [{"userEnteredValue": {"stringValue": str(c)}} for c in row]} for row in summary_rows],
                }],
            },
            {
                "properties": {"title": "Ledger", "gridProperties": {"frozenRowCount": 1}},
                "data": [{
                    "startRow": 0,
                    "startColumn": 0,
                    "rowData": [{"values": [{"userEnteredValue": {"stringValue": str(c)}} for c in row]} for row in entry_rows],
                }],
            },
        ],
    }


async def create_spreadsheet(
    tokens: dict,
    client_id: str,
    client_secret: str,
    body: dict,
) -> tuple[str, str, dict]:
    """Create a Google Sheet the user owns. Returns (id, url, tokens)."""
    if not has_scope(tokens, "spreadsheets"):
        raise GoogleAuthError("Sheets access not granted. Reconnect Google")
    tokens = await refresh_google_token(tokens, client_id, client_secret)
    async with httpx.AsyncClient(timeout=45.0) as hc:
        resp = await hc.post(
            SHEETS_URL,
            headers={"Authorization": f"Bearer {tokens.get('access_token')}", "Content-Type": "application/json"},
            json=body,
        )
    if resp.status_code in (401, 403):
        raise GoogleAuthError("Sheets access not granted. Reconnect Google")
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Sheets create failed ({resp.status_code}): {resp.text[:300]}")
    data = resp.json() or {}
    sid = data.get("spreadsheetId") or ""
    url = data.get("spreadsheetUrl") or (f"https://docs.google.com/spreadsheets/d/{sid}" if sid else "")
    return sid, url, tokens


async def create_gmail_draft(
    tokens: dict,
    client_id: str,
    client_secret: str,
    *,
    to_email: str,
    subject: str,
    body: str,
    thread_id: str = "",
) -> tuple[str, str, dict]:
    """Create a Gmail draft (Trenston never sends). Returns (draft_id, open_url, tokens)."""
    if not has_scope(tokens, "gmail.compose"):
        raise GoogleAuthError("Gmail draft access not granted. Reconnect Google")
    tokens = await refresh_google_token(tokens, client_id, client_secret)
    subj = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    rfc = (
        f"To: {to_email}\r\n"
        f"Subject: {subj}\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        f"{body}"
    )
    raw = base64.urlsafe_b64encode(rfc.encode("utf-8")).decode("ascii").rstrip("=")
    payload: dict = {"message": {"raw": raw}}
    if thread_id:
        payload["message"]["threadId"] = thread_id
    async with httpx.AsyncClient(timeout=30.0) as hc:
        resp = await hc.post(
            GMAIL_DRAFTS_URL,
            headers={"Authorization": f"Bearer {tokens.get('access_token')}", "Content-Type": "application/json"},
            json=payload,
        )
    if resp.status_code in (401, 403):
        raise GoogleAuthError("Gmail draft access not granted. Reconnect Google")
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Gmail draft failed ({resp.status_code}): {resp.text[:300]}")
    data = resp.json() or {}
    draft_id = data.get("id") or ""
    msg_id = (data.get("message") or {}).get("id") or draft_id
    open_url = f"https://mail.google.com/mail/u/0/#drafts?compose={msg_id}"
    return draft_id, open_url, tokens


async def download_drive_file(
    tokens: dict,
    client_id: str,
    client_secret: str,
    file_id: str,
) -> tuple[bytes, str, str, dict]:
    """Download a Drive file the user picked. Returns (bytes, mime, name, tokens)."""
    if not has_scope(tokens, "drive.file"):
        raise GoogleAuthError("Drive access not granted. Reconnect Google")
    if not file_id or "/" in file_id or ".." in file_id:
        raise GoogleAuthError("Invalid Drive file")
    tokens = await refresh_google_token(tokens, client_id, client_secret)
    headers = {"Authorization": f"Bearer {tokens.get('access_token')}"}
    async with httpx.AsyncClient(timeout=60.0) as hc:
        meta = await hc.get(
            f"{DRIVE_FILES_URL}/{file_id}",
            headers=headers,
            params={"fields": "id,name,mimeType,size"},
        )
        if meta.status_code in (401, 403):
            raise GoogleAuthError("Drive access not granted. Reconnect Google")
        if meta.status_code != 200:
            raise RuntimeError(f"Drive metadata failed ({meta.status_code}): {meta.text[:300]}")
        info = meta.json() or {}
        mime = info.get("mimeType") or "application/octet-stream"
        name = info.get("name") or "document"
        media = await hc.get(
            f"{DRIVE_FILES_URL}/{file_id}",
            headers=headers,
            params={"alt": "media"},
        )
        if media.status_code != 200:
            raise RuntimeError(f"Drive download failed ({media.status_code}): {media.text[:300]}")
        return media.content, mime, name, tokens

