#!/usr/bin/env python3
"""Idempotent: encrypt plaintext slack_webhook_url values at rest.

Do NOT run against production from this agent. Invoke manually after backup:

  cd backend && python -m scripts.migrate_slack_webhook_encrypt --mongo-url "$MONGO_URL" --db "$DB_NAME" --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from motor.motor_asyncio import AsyncIOMotorClient

import credential_crypto as cred_crypto  # noqa: E402


async def migrate(mongo_url: str, db_name: str, *, dry_run: bool) -> dict:
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    sealed = 0
    skipped = 0
    cursor = db.workspaces.find(
        {"slack_webhook_url": {"$exists": True, "$nin": [None, ""]}},
        {"_id": 1, "workspace_id": 1, "slack_webhook_url": 1},
    )
    async for doc in cursor:
        raw = doc.get("slack_webhook_url")
        if isinstance(raw, dict) and cred_crypto.is_sealed_credentials(raw):
            skipped += 1
            continue
        if not isinstance(raw, str):
            skipped += 1
            continue
        # Already a Fernet token?
        try:
            cred_crypto.decrypt_credential(raw)
            skipped += 1
            continue
        except Exception:
            pass
        if not raw.startswith("https://hooks.slack.com/"):
            skipped += 1
            continue
        sealed += 1
        if not dry_run:
            await db.workspaces.update_one(
                {"_id": doc["_id"]},
                {"$set": {"slack_webhook_url": cred_crypto.encrypt_credential(raw)}},
            )
    client.close()
    return {"sealed": sealed, "skipped": skipped, "dry_run": dry_run}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mongo-url", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(asyncio.run(migrate(args.mongo_url, args.db, dry_run=args.dry_run)))


if __name__ == "__main__":
    main()
