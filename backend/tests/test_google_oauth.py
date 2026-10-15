"""Unit tests for Google OAuth calendar helpers."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import google_oauth as gcal


def test_map_google_event_all_day():
    ev = {
        "id": "evt1",
        "summary": "Board prep",
        "start": {"date": "2026-09-02"},
        "end": {"date": "2026-09-03"},  # Google exclusive end → one calendar day
        "attendees": [{"email": "a@x.com"}, {"email": "b@x.com"}, {"email": "c@x.com"}],
    }
    mapped = gcal._map_google_event(ev)
    assert mapped is not None
    assert mapped["title"] == "Board prep"
    assert mapped["type"] == "Board"
    assert mapped["attendees"] == 3
    assert mapped["all_day"] is True
    assert mapped["date"] == "2026-09-02"
    assert mapped["end_date"] == "2026-09-02"
    assert mapped["time"] == ""
    # Inclusive end — must not spill onto 2026-09-03
    assert mapped["end_at"].startswith("2026-09-02T23:59:59")


def test_map_google_event_all_day_multi_day():
    ev = {
        "id": "evt2",
        "summary": "Offsite",
        "start": {"date": "2026-09-02"},
        "end": {"date": "2026-09-05"},  # exclusive → covers Sep 2–4
    }
    mapped = gcal._map_google_event(ev)
    assert mapped is not None
    assert mapped["date"] == "2026-09-02"
    assert mapped["end_date"] == "2026-09-04"
    assert mapped["end_at"].startswith("2026-09-04T23:59:59")


def test_all_day_exclusive_end():
    assert gcal._all_day_exclusive_end("2026-09-02") == "2026-09-03"
    assert gcal._all_day_exclusive_end("2026-12-31") == "2027-01-01"


def test_create_calendar_event_all_day_uses_exclusive_end():
    tokens = {
        "access_token": "tok",
        "refresh_token": "ref",
        "expires_in": 3600,
        "obtained_at": datetime.now(timezone.utc).isoformat(),
        "scope": "https://www.googleapis.com/auth/calendar.events",
    }
    api_resp = MagicMock()
    api_resp.status_code = 200
    api_resp.json.return_value = {"id": "g1"}

    mock_hc = AsyncMock()
    mock_hc.post = AsyncMock(return_value=api_resp)
    mock_hc.__aenter__ = AsyncMock(return_value=mock_hc)
    mock_hc.__aexit__ = AsyncMock(return_value=None)

    with patch("google_oauth.httpx.AsyncClient", return_value=mock_hc):
        gid, _ = asyncio.run(
            gcal.create_calendar_event(
                tokens,
                "cid",
                "sec",
                title="Holiday",
                start_iso="2026-09-02T00:00:00+00:00",
                end_iso="2026-09-02T23:59:59+00:00",
                all_day=True,
                date="2026-09-02",
            )
        )

    assert gid == "g1"
    body = mock_hc.post.call_args.kwargs["json"]
    assert body["start"] == {"date": "2026-09-02"}
    assert body["end"] == {"date": "2026-09-03"}


def test_infer_meeting_type_1_1():
    assert gcal._infer_meeting_type("Weekly 1:1 with Maya", 2) == "1:1"


def test_refresh_skips_when_fresh():
    tokens = {
        "access_token": "abc",
        "refresh_token": "r1",
        "expires_in": 3600,
        "obtained_at": datetime.now(timezone.utc).isoformat(),
    }
    out = asyncio.run(gcal.refresh_google_token(tokens, "cid", "sec"))
    assert out["access_token"] == "abc"


def test_fetch_today_calendar_maps_events():
    tokens = {
        "access_token": "tok",
        "refresh_token": "ref",
        "expires_in": 3600,
        "obtained_at": datetime.now(timezone.utc).isoformat(),
    }
    api_resp = MagicMock()
    api_resp.status_code = 200
    api_resp.json.return_value = {
        "items": [
            {
                "id": "1",
                "summary": "Sales demo",
                "start": {"dateTime": "2026-09-02T10:00:00Z"},
                "end": {"dateTime": "2026-09-02T10:30:00Z"},
                "attendees": [{"email": "x@y.com"}],
            }
        ]
    }
    mock_hc = AsyncMock()
    mock_hc.get = AsyncMock(return_value=api_resp)
    mock_hc.__aenter__ = AsyncMock(return_value=mock_hc)
    mock_hc.__aexit__ = AsyncMock(return_value=None)

    with patch("google_oauth.httpx.AsyncClient", return_value=mock_hc):
        meetings, focus, meeting_h, _ = asyncio.run(gcal.fetch_today_calendar(tokens, "cid", "sec"))

    assert len(meetings) == 1
    assert meetings[0]["title"] == "Sales demo"
    assert meeting_h > 0
    assert focus >= 0


