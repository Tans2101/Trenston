"""Workspace deletion removes Mongo records and private R2 objects."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_workspace_deletion")

import server  # noqa: E402


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _limit):
        return self.rows


class Collection:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.find = lambda *_args, **_kwargs: Cursor(self.rows)
        self.delete_many = AsyncMock()
        self.delete_one = AsyncMock()


class FakeDB:
    def __init__(self):
        self.collections = {name: Collection() for name in server._WORKSPACE_COLLECTIONS}
        self.documents = Collection([{"storage_key": "ws_1/invoice.pdf"}])
        self.report_documents = Collection()
        self.legal_matters = Collection([
            {"document_ref": {"storage_key": "ws_1/contract.pdf"}},
        ])
        self.departments = Collection([{"department_id": "dept_1"}])
        self.department_members = Collection()
        self.memberships = Collection()
        self.referrals = Collection()
        self.workspaces = Collection()
        self.collections.update({
            "documents": self.documents,
            "report_documents": self.report_documents,
            "legal_matters": self.legal_matters,
        })

    def __getitem__(self, name):
        return self.collections[name]


def test_delete_workspace_purges_r2_and_workspace_collections():
    fake_db = FakeDB()
    deleted = []
    with (
        patch.object(server, "db", fake_db),
        patch.object(server.doc_storage, "r2_configured", return_value=True),
        patch.object(server.doc_storage, "delete_document", side_effect=deleted.append),
    ):
        asyncio.run(server._delete_workspace_data("ws_1"))

    assert set(deleted) == {"ws_1/invoice.pdf", "ws_1/contract.pdf"}
    for name in server._WORKSPACE_COLLECTIONS:
        fake_db[name].delete_many.assert_awaited_once_with({"workspace_id": "ws_1"})
    fake_db.department_members.delete_many.assert_awaited_once_with(
        {"department_id": {"$in": ["dept_1"]}},
    )
    fake_db.departments.delete_many.assert_awaited_once_with({"workspace_id": "ws_1"})
    fake_db.memberships.delete_many.assert_awaited_once_with({"workspace_id": "ws_1"})
    fake_db.referrals.delete_many.assert_awaited_once_with({"referred_workspace_id": "ws_1"})
    fake_db.workspaces.delete_one.assert_awaited_once_with({"workspace_id": "ws_1"})
