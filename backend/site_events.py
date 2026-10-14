"""Anonymous, first-party funnel events for the public site and sign-up.

No cookies, no user ids, no IP addresses stored. Each row is just
{name, path, a couple of short label fields, time}. The client IP is used only
transiently to rate-limit the endpoint. Product activation (first decision,
first task, ...) is not logged here: it is counted straight from the workspace's
own data by scripts/funnel_report.py.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import rate_limit

COLLECTION = "site_events"
BUCKETS = "site_event_buckets"
RETENTION_DAYS = 400
RATE_LIMIT = 60          # events per IP per window
RATE_WINDOW_SECONDS = 600

# name -> allowed prop keys. Anything else is dropped.
ALLOWED_EVENTS: dict[str, frozenset[str]] = {
    "cta_click": frozenset({"where"}),
    "plan_select": frozenset({"plan"}),
    "signup_view": frozenset(),
    "tour_started": frozenset({"guide"}),
    "tour_finished": frozenset({"guide"}),
    "intro_dismissed": frozenset({"guide"}),
    "upgrade_click": frozenset({"plan"}),
}
MAX_VALUE_LEN = 40
MAX_PATH_LEN = 80


def clean_event(name: Any, path: Any, props: Any) -> Optional[dict]:
    """Validate and trim an incoming event. None when it should be ignored."""
    if not isinstance(name, str) or name not in ALLOWED_EVENTS:
        return None
    allowed = ALLOWED_EVENTS[name]
    clean_props: dict[str, str] = {}
    if isinstance(props, dict):
        for key, value in props.items():
            if key in allowed and isinstance(value, (str, int, float)):
                clean_props[key] = str(value).strip()[:MAX_VALUE_LEN]
    p = path if isinstance(path, str) else ""
    p = p.split("?", 1)[0].split("#", 1)[0].strip()[:MAX_PATH_LEN]
    return {"name": name, "path": p, "props": clean_props}


async def record(db, name: Any, path: Any, props: Any, client_ip: str) -> bool:
    """Store one event. False when ignored or rate limited (callers stay silent either way)."""
    row = clean_event(name, path, props)
    if row is None:
        return False
    now = datetime.now(timezone.utc)
    # Hash the IP for the bucket key so no address is ever written to Mongo.
    ip_key = hashlib.sha256((client_ip or "unknown").encode()).hexdigest()[:20]
    ok = await rate_limit._acquire_window_bucket(
        db[BUCKETS],
        base_key=f"site_event:{ip_key}",
        limit=RATE_LIMIT,
        window_seconds=RATE_WINDOW_SECONDS,
        extra_fields={"action": "site_event"},
        now=now,
    )
    if not ok:
        return False
    row["created_at"] = now
    await db[COLLECTION].insert_one(row)
    return True


async def daily_counts(db, days: int = 30) -> dict[str, dict[str, int]]:
    """{event name: {YYYY-MM-DD: count}} for the last `days` days."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    out: dict[str, dict[str, int]] = {}
    cursor = db[COLLECTION].aggregate([
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {
            "_id": {"n": "$name", "d": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}}},
            "c": {"$sum": 1},
        }},
    ])
    async for doc in cursor:
        out.setdefault(doc["_id"]["n"], {})[doc["_id"]["d"]] = doc["c"]
    return out
