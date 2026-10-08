"""T19: /ask/history returns the newest 200 messages in chronological order."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_ask_history_endpoint")

import server  # noqa: E402
from tests.mongo_mocks import FakeCollection  # noqa: E402


def test_history_returns_newest_200_in_order():
    docs = [
        {"workspace_id": "ws1", "user_id": "u1", "role": "user" if i % 2 else "assistant",
         "content": f"m{i}", "created_at": f"2026-09-24T10:00:{i:03d}"}
        for i in range(1, 251)
    ]
    docs.append({"workspace_id": "ws1", "user_id": "u2", "role": "user", "content": "other",
                 "created_at": "2026-09-24T11:00:000"})
    fake_db = MagicMock()
    fake_db.chat_messages = FakeCollection(docs)
    with patch.object(server, "db", fake_db):
        out = asyncio.run(server.ask_history(principal={"workspace_id": "ws1", "user_id": "u1"}))
    contents = [m["content"] for m in out["messages"]]
    assert contents == [f"m{i}" for i in range(51, 251)]


def test_new_chat_hides_old_thread_from_history_and_context():
    docs = [
        {"workspace_id": "ws1", "user_id": "u1", "role": "user", "content": "old q", "created_at": "2026-09-24T10:00:01"},
        {"workspace_id": "ws1", "user_id": "u1", "role": "assistant", "content": "old a", "created_at": "2026-09-24T10:00:02"},
        {"workspace_id": "ws1", "user_id": "u2", "role": "user", "content": "teammate", "created_at": "2026-09-24T10:00:03"},
    ]
    fake_db = MagicMock()
    fake_db.chat_messages = FakeCollection(docs)
    with patch.object(server, "db", fake_db):
        res = asyncio.run(server.ask_new_chat(principal={"workspace_id": "ws1", "user_id": "u1"}))
        mine = asyncio.run(server.ask_history(principal={"workspace_id": "ws1", "user_id": "u1"}))
        context = asyncio.run(server._ask_history("ws1", "u1"))
        theirs = asyncio.run(server.ask_history(principal={"workspace_id": "ws1", "user_id": "u2"}))
    assert res["archived"] == 2
    assert mine["messages"] == []
    assert context == []
    # Archived, not deleted, and another user's thread is untouched.
    assert len(fake_db.chat_messages.docs) == 3
    assert [m["content"] for m in theirs["messages"]] == ["teammate"]


def test_basis_labels_only_list_visible_data():
    labels = server.ask_basis_labels(
        financials=False,
        sections={"Pipeline": True, "Legal": False, "Production": True},
    )
    assert labels == ["Pipeline", "Production", "Decisions", "Risks", "People"]
    assert "Financials" in server.ask_basis_labels(financials=True, sections={})
