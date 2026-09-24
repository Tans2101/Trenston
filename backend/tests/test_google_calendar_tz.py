"""T7: Google Calendar in the workspace timezone."""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_google_calendar_tz")

import google_oauth as gcal  # noqa: E402
import tz_utils  # noqa: E402

FROZEN = datetime(2026, 9, 24, 23, 30, tzinfo=timezone.utc)  # 07:30 on Sep 25 in Manila


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return FROZEN if tz is None or tz is timezone.utc else FROZEN.astimezone(tz)


class _Resp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = ""

    def json(self):
        return self._payload


class _CalendarClient:
    def __init__(self, pages):
        self.pages = list(pages)
        self.params_seen: list[dict] = []

    def __call__(self, *a, **k):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None, params=None):
        self.params_seen.append(dict(params or {}))
        return _Resp(200, self.pages.pop(0))


def _fresh_tokens():
    return {"access_token": "a", "refresh_token": "r", "expires_in": 3600,
            "obtained_at": datetime.now(timezone.utc).isoformat()}


def _timed(eid, start, end, **extra):
    return {"id": eid, "summary": eid, "start": {"dateTime": start}, "end": {"dateTime": end}, **extra}


def test_manila_morning_event_is_in_today():
    """07:00 Manila on Sep 25 is 23:00 UTC on Sep 24 — still 'today' in Manila."""
    client = _CalendarClient([{"items": [
        _timed("early", "2026-09-24T23:00:00Z", "2026-09-24T23:30:00Z"),
    ]}])
    with patch.object(tz_utils, "datetime", _FrozenDatetime), patch.object(gcal.httpx, "AsyncClient", client):
        meetings, _focus, hours, _tok = asyncio.run(gcal.fetch_today_calendar(
            _fresh_tokens(), "cid", "csec", timezone_name="Asia/Manila",
        ))
    params = client.params_seen[0]
    assert params["timeMin"] == "2026-09-24T16:00:00+00:00"
    assert params["timeMax"] == "2026-09-25T16:00:00+00:00"
    assert params["timeZone"] == "Asia/Manila"
    assert meetings[0]["date"] == "2026-09-25"
    assert meetings[0]["time"] == "07:00"
    assert hours == 0.5


def test_all_day_event_contributes_no_hours():
    ev = gcal._map_google_event({"id": "hol", "start": {"date": "2026-09-25"}, "end": {"date": "2026-09-26"}})
    assert ev["all_day"] is True
    assert gcal._compute_hours([ev]) == (8, 0)


def test_declined_and_free_events_contribute_no_hours():
    declined = gcal._map_google_event(_timed(
        "d", "2026-09-25T01:00:00Z", "2026-09-25T03:00:00Z",
        attendees=[{"email": "me@x.com", "self": True, "responseStatus": "declined"}, {"email": "b@x.com"}],
    ))
    free = gcal._map_google_event(_timed(
        "f", "2026-09-25T04:00:00Z", "2026-09-25T05:00:00Z", transparency="transparent",
    ))
    busy = gcal._map_google_event(_timed("b", "2026-09-25T06:00:00Z", "2026-09-25T07:00:00Z"))
    assert declined["declined"] is True and declined["free"] is False
    assert free["free"] is True and free["declined"] is False
    focus, hours = gcal._compute_hours([declined, free, busy])
    assert hours == 1.0
    assert focus == 7.0


def test_week_fetch_follows_next_page_token():
    client = _CalendarClient([
        {"items": [_timed("e1", "2026-09-21T01:00:00Z", "2026-09-21T02:00:00Z")], "nextPageToken": "p2"},
        {"items": [_timed("e2", "2026-09-22T01:00:00Z", "2026-09-22T02:00:00Z")], "nextPageToken": "p3"},
        {"items": [_timed("e3", "2026-09-23T01:00:00Z", "2026-09-23T02:00:00Z")]},
    ])
    with patch.object(gcal.httpx, "AsyncClient", client):
        events, _ = asyncio.run(gcal.fetch_week_calendar(
            _fresh_tokens(), "cid", "csec", datetime(2026, 9, 20, tzinfo=timezone.utc),
            timezone_name="Asia/Manila",
        ))
    assert [e["id"] for e in events] == ["e1", "e2", "e3"]
    assert [p.get("pageToken") for p in client.params_seen] == [None, "p2", "p3"]
    assert client.params_seen[0]["timeMin"] == "2026-09-19T16:00:00+00:00"


def test_pagination_stops_at_250_events():
    page = {"items": [_timed(f"e{i}", "2026-09-21T01:00:00Z", "2026-09-21T02:00:00Z") for i in range(100)],
            "nextPageToken": "more"}
    client = _CalendarClient([page, page, page, page])
    with patch.object(gcal.httpx, "AsyncClient", client):
        events, _ = asyncio.run(gcal.fetch_week_calendar(
            _fresh_tokens(), "cid", "csec", date(2026, 9, 20), timezone_name="Asia/Manila",
        ))
    assert len(events) == 250
    assert len(client.params_seen) == 3


def test_week_bounds_negative_offset_keeps_local_sunday():
    start, end = gcal.week_bounds(datetime(2026, 9, 20, tzinfo=timezone.utc), "America/Los_Angeles")
    assert start == "2026-09-20T07:00:00+00:00"
    assert end == "2026-09-27T07:00:00+00:00"


def test_create_event_uses_workspace_timezone():
    captured = {}

    class _Client:
        def __call__(self, *a, **k):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            captured["body"] = json
            return _Resp(200, {"id": "g1"})

    tokens = {**_fresh_tokens(), "scope": "https://www.googleapis.com/auth/calendar.events"}
    with patch.object(gcal.httpx, "AsyncClient", _Client()):
        asyncio.run(gcal.create_calendar_event(
            tokens, "cid", "csec", title="Standup",
            start_iso="2026-09-25T09:00:00+08:00", end_iso="2026-09-25T09:15:00+08:00",
            timezone_name="Asia/Manila",
        ))
    assert captured["body"]["start"] == {"dateTime": "2026-09-25T09:00:00+08:00", "timeZone": "Asia/Manila"}
    assert captured["body"]["end"]["timeZone"] == "Asia/Manila"
