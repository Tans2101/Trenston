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




def test_token_needs_refresh_tolerates_bad_expires_in():
    from datetime import timedelta
    fresh = {
        "obtained_at": datetime.now(timezone.utc).isoformat(),
        "expires_in": "nope",
    }
    assert gcal._token_needs_refresh(fresh) is False
    stale = {
        "obtained_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
        "expires_in": "bad",
    }
    assert gcal._token_needs_refresh(stale) is True


def test_create_spreadsheet_retries_once_on_401():
    tokens = {
        "access_token": "old",
        "refresh_token": "r1",
        "scope": "https://www.googleapis.com/auth/spreadsheets",
        "expires_in": 3600,
        "obtained_at": datetime.now(timezone.utc).isoformat(),
    }
    unauthorized = MagicMock(status_code=401, text="no")
    ok = MagicMock(status_code=200)
    ok.json.return_value = {"spreadsheetId": "sheet1", "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/sheet1"}
    refresh_resp = MagicMock(status_code=200)
    refresh_resp.json.return_value = {"access_token": "new", "expires_in": 3600}

    post_mock = AsyncMock(side_effect=[unauthorized, ok])
    mock_hc = AsyncMock()
    mock_hc.post = post_mock
    mock_hc.__aenter__ = AsyncMock(return_value=mock_hc)
    mock_hc.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("google_oauth.httpx.AsyncClient", return_value=mock_hc),
        patch("google_oauth.refresh_http_post", new=AsyncMock(return_value=refresh_resp)),
    ):
        sid, url, out = asyncio.run(gcal.create_spreadsheet(tokens, "cid", "sec", {"properties": {"title": "t"}}))

    assert sid == "sheet1" and "sheet1" in url
    assert post_mock.await_count == 2
    assert out.get("access_token") == "new"


def test_patch_calendar_event_url_encodes_event_id():
    tokens = {
        "access_token": "a",
        "refresh_token": "r",
        "scope": "https://www.googleapis.com/auth/calendar.events",
        "expires_in": 3600,
        "obtained_at": datetime.now(timezone.utc).isoformat(),
    }
    ok = MagicMock(status_code=200, text="")
    patch_mock = AsyncMock(return_value=ok)
    mock_hc = AsyncMock()
    mock_hc.patch = patch_mock
    mock_hc.__aenter__ = AsyncMock(return_value=mock_hc)
    mock_hc.__aexit__ = AsyncMock(return_value=None)

    with patch("google_oauth.httpx.AsyncClient", return_value=mock_hc):
        asyncio.run(gcal.patch_calendar_event(
            tokens, "cid", "sec", "abc/def?x=1",
            title="T", start_iso="2026-10-01T10:00:00+00:00", end_iso="2026-10-01T11:00:00+00:00",
        ))

    url = patch_mock.await_args.args[0]
    assert "/calendars/primary/events/abc%2Fdef%3Fx%3D1" in url


def test_download_drive_file_rejects_query_chars():
    tokens = {"scope": "https://www.googleapis.com/auth/drive.file", "access_token": "a", "refresh_token": "r"}
    try:
        asyncio.run(gcal.download_drive_file(tokens, "cid", "sec", "id?alt=media"))
        assert False, "expected GoogleAuthError"
    except gcal.GoogleAuthError:
        pass
