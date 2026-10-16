"""Purge abandoned document uploads that were never committed to financial entries."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

import storage as doc_storage

logger = logging.getLogger("helm")

DOC_ORPHAN_RETENTION_DAYS = int(os.environ.get("DOC_ORPHAN_RETENTION_DAYS", "7"))
ORPHAN_STATUSES = frozenset({"uploaded", "extracted", "failed"})


def _orphan_query(cutoff_iso: str) -> dict:
    return {
        "status": {"$in": sorted(ORPHAN_STATUSES)},
        "$or": [{"linked_entry_id": None}, {"linked_entry_id": {"$exists": False}}],
        "uploaded_at": {"$lt": cutoff_iso},
    }


async def cleanup_orphaned_documents(db, *, now: datetime | None = None) -> dict:
    """Delete stale uncommitted documents from R2 and Mongo."""
    now = now or datetime.now(timezone.utc)
    cutoff_iso = (now - timedelta(days=DOC_ORPHAN_RETENTION_DAYS)).isoformat()
    docs = await db.documents.find(_orphan_query(cutoff_iso), {"_id": 0}).to_list(1000)
    deleted_ids: list[str] = []

    for doc in docs:
        if doc.get("linked_entry_id"):
            continue
        storage_key = doc.get("storage_key")
        if storage_key and doc_storage.r2_configured():
            try:
                await asyncio.to_thread(doc_storage.delete_document, storage_key)
            except Exception:
                logger.exception("orphan cleanup: failed to delete R2 object %s", storage_key)
                continue
        delete_filt: dict = {"id": doc["id"]}
        # Prefer tenant-scoped delete when the orphan doc carries workspace_id.
        wid = doc.get("workspace_id")
        if wid:
            delete_filt["workspace_id"] = wid
        result = await db.documents.delete_one(delete_filt)
        if result.deleted_count:
            deleted_ids.append(doc["id"])

    logger.info(
        "orphaned document cleanup complete: deleted %d document(s) older than %d days",
        len(deleted_ids),
        DOC_ORPHAN_RETENTION_DAYS,
    )
    return {"deleted_count": len(deleted_ids), "deleted_ids": deleted_ids}
