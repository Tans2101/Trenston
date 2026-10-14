"""Funnel report: where do visitors and new workspaces drop off?

Usage (from backend/, with MONGO_URL and DB_NAME set):
    python scripts/funnel_report.py [days]

Part 1 counts the anonymous site events (button clicks, sign-up views, tours).
Part 2 counts activation for workspaces created in the window straight from
the workspace data, so it works without any event tracking.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

import site_events  # noqa: E402

def _iso(dt: datetime) -> str:
    return dt.isoformat()


async def activation(db, ws_ids: list[str]) -> list[tuple[str, int]]:
    """How many of these workspaces reached each step. Sample/seed data is excluded where we can tell."""
    if not ws_ids:
        return []
    in_cohort = {"workspace_id": {"$in": ws_ids}}
    numbers = await db.financial_entries.distinct(
        "workspace_id", {**in_cohort, "created_by": {"$ne": "seed"}},
    )
    decisions = await db.workspaces.count_documents({**in_cohort, "decisions.0": {"$exists": True}})
    tasks = await db.workspaces.count_documents({**in_cohort, "tasks.items.0": {"$exists": True}})
    invited = await db.memberships.distinct(
        "workspace_id", {**in_cohort, "invite_token": {"$exists": True}},
    )
    return [
        ("added real numbers", len(numbers)),
        ("logged a decision", decisions),
        ("created a task", tasks),
        ("invited a teammate", len(invited)),
    ]


async def main(days: int) -> None:
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    since = datetime.now(timezone.utc) - timedelta(days=days)

    print(f"== Site events, last {days} days ==")
    counts = await site_events.daily_counts(db, days)
    if not counts:
        print("  (none yet)")
    for name in sorted(counts):
        print(f"  {name:<16} {sum(counts[name].values()):>6}")
    clicks = sum(counts.get("cta_click", {}).values())
    views = sum(counts.get("signup_view", {}).values())
    if clicks:
        print(f"  sign-up page views per CTA click: {views / clicks:.0%}")

    print(f"\n== Workspaces created in the last {days} days ==")
    rows = await db.workspaces.find(
        {"$or": [{"created_at": {"$gte": _iso(since)}}, {"created_at": {"$gte": since}}]},
        {"_id": 0, "workspace_id": 1},
    ).to_list(100000)
    ws_ids = [r["workspace_id"] for r in rows if r.get("workspace_id")]
    print(f"  created: {len(ws_ids)}")
    for label, n in await activation(db, ws_ids):
        print(f"  {label:<24} {n:>5} ({n / len(ws_ids):.0%})")
    print("\nSample-data decisions and tasks may be counted; 'real numbers' excludes seeded rows.")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 30))
