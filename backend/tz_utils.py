"""Workspace-local calendar days.

User-facing "today" / "this week" follow the workspace's IANA timezone
(default Asia/Manila). Timestamps, cron dedupe keys and billing stay in UTC.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

DEFAULT_TZ = "Asia/Manila"


@lru_cache(maxsize=1)
def _valid_names() -> frozenset[str]:
    return frozenset(available_timezones())


def is_valid_timezone(name: Optional[str]) -> bool:
    return bool(name) and name in _valid_names()


@lru_cache(maxsize=512)
def _zone(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def workspace_tz(ws: Optional[dict]) -> ZoneInfo:
    """The workspace's ZoneInfo; missing or invalid -> DEFAULT_TZ."""
    name = ((ws or {}).get("timezone") or "").strip()
    if not is_valid_timezone(name):
        name = DEFAULT_TZ
    try:
        return _zone(name)
    except ZoneInfoNotFoundError:
        return _zone(DEFAULT_TZ)


def workspace_tz_name(ws: Optional[dict]) -> str:
    return workspace_tz(ws).key


def workspace_now(ws: Optional[dict]) -> datetime:
    """Aware 'now' in the workspace timezone."""
    return datetime.now(timezone.utc).astimezone(workspace_tz(ws))


def workspace_today(ws: Optional[dict]) -> date:
    return workspace_now(ws).date()


def workspace_today_iso(ws: Optional[dict]) -> str:
    """YYYY-MM-DD for the workspace's local today."""
    return workspace_today(ws).isoformat()


def _utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def day_bounds_utc(ws: Optional[dict], day: date) -> tuple[str, str]:
    """UTC ISO [start, end) of one local calendar day in the workspace timezone."""
    tz = workspace_tz(ws)
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    return _utc_iso(start), _utc_iso(end)


def week_bounds_utc(ws: Optional[dict], week_start: date) -> tuple[str, str]:
    """UTC ISO [start, end) of the 7 local days starting at week_start."""
    tz = workspace_tz(ws)
    start = datetime.combine(week_start, time.min, tzinfo=tz)
    end = datetime.combine(week_start + timedelta(days=7), time.min, tzinfo=tz)
    return _utc_iso(start), _utc_iso(end)
