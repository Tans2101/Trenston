"""Calendar timezone / hours exclusions and Gmail draft hardening."""
from __future__ import annotations

import asyncio
import base64
from datetime import datetime
from email import message_from_bytes
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import google_oauth as gcal
import pytest


def test_manila_day_boundary():
    # 2026-09-24 16:00 UTC = 2026-09-25 00:00 Asia/Manila
    with patch("google_oauth.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 9, 25, 0, 30, tzinfo=ZoneInfo("Asia/Manila"))
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
        # Call real fromisoformat etc via original
        from datetime import datetime as real_dt
        mock_dt.fromisoformat = real_dt.fromisoformat
        mock_dt.strptime = real_dt.strptime
        start, end = gcal._today_bounds("Asia/Manila")
    assert start.startswith("2026-09-25T00:00:00")
    assert "+08:00" in start or start.endswith("+08:00")


def test_all_day_and_declined_excluded_from_hours():
    meetings = [
        {"duration": 60, "all_day": True},
        {"duration": 60, "all_day": False, "self_response_status": "declined"},
        {"duration": 60, "all_day": False, "transparency": "transparent"},
        {"duration": 30, "all_day": False, "self_response_status": "accepted"},
    ]
    focus, meeting_h = gcal._compute_hours(meetings)
    assert meeting_h == 0.5
    assert focus == 7.5


def test_map_marks_all_day():
    mapped = gcal._map_google_event({
        "id": "1",
        "summary": "Holiday",
        "start": {"date": "2026-09-02"},
        "end": {"date": "2026-09-03"},
    })
    assert mapped["all_day"] is True
    assert mapped["time"] == ""


def test_non_ascii_subject_draft_encoded():
    tokens = {
        "access_token": "tok",
        "refresh_token": "r",
        "expires_in": 3600,
        "obtained_at": datetime.now().isoformat() + "+00:00",
        "scope": "https://www.googleapis.com/auth/gmail.compose",
    }
    captured = {}

    class _Resp:
        status_code = 200
        def json(self):
            return {"id": "d1", "message": {"id": "m1"}}

    class _Client:
        def __init__(self, *a, **k):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def post(self, *a, **k):
            captured["json"] = k.get("json")
            return _Resp()

    with patch.object(gcal, "refresh_google_token", AsyncMock(return_value=tokens)), \
         patch.object(gcal.httpx, "AsyncClient", _Client):
        draft_id, url, _ = asyncio.run(
            gcal.create_gmail_draft(
                tokens, "cid", "sec",
                to_email="buyer@acme.com",
                subject="Réunion — Q3",
                body="Hello",
                thread_id="",
            )
        )
    assert draft_id == "d1"
    raw_b64 = captured["json"]["message"]["raw"]
    # pad for decode
    pad = "=" * (-len(raw_b64) % 4)
    raw = base64.urlsafe_b64decode(raw_b64 + pad)
    msg = message_from_bytes(raw)
    # RFC 2047 encoded subject should not be raw non-ASCII in the header bytes,
    # or EmailMessage may keep unicode — either way Subject must round-trip.
    assert "Réunion" in (msg["Subject"] or "") or "=?utf-8?" in (msg["Subject"] or "").lower()
    assert "Re:" not in (msg["Subject"] or "")  # no thread → no Re:


def test_gmail_draft_requires_recipient():
    tokens = {
        "access_token": "tok",
        "refresh_token": "r",
        "expires_in": 3600,
        "obtained_at": datetime.now().isoformat() + "+00:00",
        "scope": "https://www.googleapis.com/auth/gmail.compose",
    }
    with patch.object(gcal, "refresh_google_token", AsyncMock(return_value=tokens)):
        with pytest.raises(gcal.GmailDraftError):
            asyncio.run(
                gcal.create_gmail_draft(
                    tokens, "cid", "sec",
                    to_email="me",
                    subject="Hi",
                    body="x",
                )
            )
