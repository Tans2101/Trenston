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
