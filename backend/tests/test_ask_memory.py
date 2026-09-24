"""T18: Ask Trenston sends recent conversation history to the model."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_ask_memory")

import server  # noqa: E402
from tests.mongo_mocks import FakeCollection  # noqa: E402


def _msg(role, content, minute, **extra):
    return {"workspace_id": "ws1", "user_id": "u1", "role": role, "content": content,
            "created_at": f"2026-09-24T10:{minute:02d}:00+00:00", **extra}


def test_build_messages_merges_and_starts_with_user():
    history = [
        {"role": "assistant", "content": "orphan answer"},
        {"role": "user", "content": "Q1"},
        {"role": "user", "content": "Q1 again"},
        {"role": "assistant", "content": "A1"},
    ]
    out = server.build_ask_messages(history, "Q2")
    assert out == [
        {"role": "user", "content": "Q1\n\nQ1 again"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "Q2"},
    ]


def test_build_messages_truncates_oldest_to_budget():
    big = "x" * 7000
    history = [
        {"role": "user", "content": "old " + big},
        {"role": "assistant", "content": "old answer " + big},
        {"role": "user", "content": "recent"},
        {"role": "assistant", "content": "recent answer"},
    ]
    out = server.build_ask_messages(history, "now")
    assert sum(len(m["content"]) for m in out[:-1]) <= server.ASK_HISTORY_MAX_CHARS
    assert out[0] == {"role": "user", "content": "recent"}
    assert out[-1] == {"role": "user", "content": "now"}
    roles = [m["role"] for m in out]
    assert all(a != b for a, b in zip(roles, roles[1:]))


@pytest.mark.asyncio
async def test_ask_sends_history_then_question():
    chat = FakeCollection([
        _msg("user", "What is our runway?", 1),
        _msg("assistant", "About 14 months.", 2),
        _msg("user", "And burn?", 3),
        _msg("assistant", "I hit an error reaching my reasoning engine.", 4, is_error=True),
        _msg("assistant", "Burn is 120k per month.", 5),
        {**_msg("user", "someone else's question", 6), "user_id": "u2"},
    ])
    ws = {"name": "Acme", "workspace_id": "ws1", "plan": "starter", "people": {"people": []},
          "decisions": [], "telemetry_manual": {"risks": []}}
    captured = {}

    async def _capture(system, message=None, **kwargs):
        captured["messages"] = kwargs.get("messages")
        yield "ok"

    mock_db = MagicMock()
    mock_db.chat_messages = chat
    period = {"key": "k", "start": datetime(2026, 9, 1, tzinfo=timezone.utc),
              "end": datetime(2026, 10, 1, tzinfo=timezone.utc)}
    with patch.object(server, "get_ws", new=AsyncMock(return_value=ws)), \
            patch.object(server, "can_access_financials", new=AsyncMock(return_value=True)), \
            patch.object(server, "compute_financials", new=AsyncMock(return_value={})), \
            patch.object(server, "db", mock_db), \
            patch.object(server, "_product_event", new=AsyncMock()), \
            patch.object(server.helm_llm, "anthropic_configured", return_value=True), \
            patch.object(server.helm_llm, "stream_text", side_effect=_capture), \
            patch.object(server.plan_usage, "current_usage_period", return_value=period), \
            patch.object(server, "BILLING_ENFORCED", False), \
            patch.object(server.dept_access, "accessible_department_ids_by_type", new=AsyncMock(return_value={})), \
            patch.object(server.dept_migrate, "get_enabled_departments_by_type", new=AsyncMock(return_value={})), \
            patch.object(server, "_ask_helm_department_slice", new=AsyncMock(return_value=([], False, False))), \
            patch.object(server.helm_freshness, "resolve_workspace_data_as_of",
                         new=AsyncMock(return_value={"data_as_of": None, "sources": {}})):
        resp = await server.ask_helm(server.AskInput(message="What changed this week?"), {
            "user_id": "u1", "workspace_id": "ws1", "pack": "owner", "role": "owner",
        })
        async for _ in resp.body_iterator:
            pass

    assert captured["messages"] == [
        {"role": "user", "content": "What is our runway?"},
        {"role": "assistant", "content": "About 14 months."},
        {"role": "user", "content": "And burn?"},
        {"role": "assistant", "content": "Burn is 120k per month."},
        {"role": "user", "content": "What changed this week?"},
    ]
