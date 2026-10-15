"""Calendar timezone and meeting-hours exclusions."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import google_oauth as gcal


def test_manila_day_boundary():
    # 2026-09-24 16:30 UTC = 2026-09-25 00:30 Asia/Manila -> local day starts 16:00 UTC.
    import tz_utils

    frozen = datetime(2026, 9, 24, 16, 30, tzinfo=ZoneInfo("UTC"))

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen if tz is None else frozen.astimezone(tz)

    with patch.object(tz_utils, "datetime", _Frozen):
        start, end = gcal._today_bounds("Asia/Manila")
    assert start == "2026-09-24T16:00:00+00:00"
    assert end == "2026-09-25T16:00:00+00:00"


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


