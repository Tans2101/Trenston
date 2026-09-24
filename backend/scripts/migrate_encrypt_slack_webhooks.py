#!/usr/bin/env python3
"""Move Slack webhooks into the encrypted ``slack_webhook_enc`` field.

For each workspace with a legacy ``slack_webhook_url``:
  - plaintext https://hooks.slack.com/... -> encrypt into slack_webhook_enc
  - already a Fernet token (older hardening)  -> move as-is into slack_webhook_enc
  - then unset slack_webhook_url
Workspaces that already have slack_webhook_enc just lose the stale legacy field.
Values that are neither a Slack URL nor decryptable are reported and left alone.

Idempotent. Dry-run is the default; pass --apply to write. Requires the same
INTEGRATION_ENCRYPTION_KEY as the running app.

  cd backend && python -m scripts.migrate_encrypt_slack_webhooks --mongo-url "$MONGO_URL" --db "$DB_NAME"
  cd backend && python -m scripts.migrate_encrypt_slack_webhooks --mongo-url "$MONGO_URL" --db "$DB_NAME" --apply
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import credential_crypto as cred_crypto  # noqa: E402


def plan_for(doc: dict[str, Any]) -> tuple[str, Optional[dict]]:
    """(action, update) for one workspace doc. action: encrypt|move|drop_legacy|skip."""
    raw = doc.get("slack_webhook_url")
    if not raw:
        return "skip", None
    if doc.get("slack_webhook_enc"):
        return "drop_legacy", {"$unset": {"slack_webhook_url": ""}}
    if isinstance(raw, str):
        try:
            cred_crypto.decrypt_credential(raw)
            return "move", {"$set": {"slack_webhook_enc": raw}, "$unset": {"slack_webhook_url": ""}}
        except Exception:
            pass
        if raw.strip().startswith("https://hooks.slack.com/"):
            return "encrypt", {
                "$set": {"slack_webhook_enc": cred_crypto.encrypt_credential(raw.strip())},
                "$unset": {"slack_webhook_url": ""},
            }
    return "skip", None


async def migrate(mongo_url: str, db_name: str, *, apply: bool) -> dict[str, Any]:
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    counts = {"scanned": 0, "encrypt": 0, "move": 0, "drop_legacy": 0, "skip": 0}
    try:
        cursor = db.workspaces.find(
            {"slack_webhook_url": {"$exists": True, "$nin": [None, ""]}},
            {"_id": 1, "slack_webhook_url": 1, "slack_webhook_enc": 1},
        )
        async for doc in cursor:
            counts["scanned"] += 1
            action, update = plan_for(doc)
            counts[action] += 1
            if apply and update:
                await db.workspaces.update_one({"_id": doc["_id"]}, update)
    finally:
        client.close()
    return {**counts, "applied": apply}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mongo-url", required=True)
    parser.add_argument("--db", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True, help="Report only (default)")
    mode.add_argument("--apply", action="store_true", help="Write changes")
    args = parser.parse_args()
    stats = asyncio.run(migrate(args.mongo_url, args.db, apply=bool(args.apply)))
    label = "APPLIED" if stats.pop("applied") else "DRY RUN (no writes)"
    print(f"[{label}] " + " ".join(f"{k}={v}" for k, v in stats.items()))


if __name__ == "__main__":
    main()
