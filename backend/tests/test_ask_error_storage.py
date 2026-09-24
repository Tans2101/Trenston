"""T20: stream failures are stored as errors / interruptions, not real answers."""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_ask_error_storage")

import server  # noqa: E402
from tests.mongo_mocks import FakeCollection  # noqa: E402


def _run_ask(stream_fn):
    chat = FakeCollection()
    ws = {"name": "Acme", "workspace_id": "ws1", "plan": "starter", "people": {"people": []},
          "decisions": [], "telemetry_manual": {"risks": []}}
    mock_db = MagicMock()
    mock_db.chat_messages = chat
    period = {"key": "k", "start": datetime(2026, 9, 1, tzinfo=timezone.utc),
              "end": datetime(2026, 10, 1, tzinfo=timezone.utc)}

    async def _go():
        with patch.object(server, "get_ws", new=AsyncMock(return_value=ws)), \
                patch.object(server, "can_access_financials", new=AsyncMock(return_value=True)), \
                patch.object(server, "compute_financials", new=AsyncMock(return_value={})), \
                patch.object(server, "db", mock_db), \
                patch.object(server, "_product_event", new=AsyncMock()), \
                patch.object(server.helm_llm, "anthropic_configured", return_value=True), \
                patch.object(server.helm_llm, "stream_text", side_effect=stream_fn), \
                patch.object(server.plan_usage, "current_usage_period", return_value=period), \
                patch.object(server, "BILLING_ENFORCED", False), \
                patch.object(server.dept_access, "accessible_department_ids_by_type", new=AsyncMock(return_value={})), \
                patch.object(server.dept_migrate, "get_enabled_departments_by_type", new=AsyncMock(return_value={})), \
                patch.object(server, "_ask_helm_department_slice", new=AsyncMock(return_value=([], False, False))), \
                patch.object(server.helm_freshness, "resolve_workspace_data_as_of",
                             new=AsyncMock(return_value={"data_as_of": None, "sources": {}})):
            resp = await server.ask_helm(server.AskInput(message="Runway?"), {
                "user_id": "u1", "workspace_id": "ws1", "pack": "owner", "role": "owner",
            })
            return "".join([c async for c in resp.body_iterator])

    body = asyncio.run(_go())
    assistant = [d for d in chat.docs if d["role"] == "assistant"]
    assert len(assistant) == 1
    return body, assistant[0]


def test_error_before_any_text_is_flagged():
    async def boom(*_a, **_k):
        raise RuntimeError("anthropic down")
        yield  # pragma: no cover

    body, doc = _run_ask(boom)
    assert body == server.ASK_ERROR_REPLY
    assert doc["is_error"] is True
    assert "interrupted" not in doc
    assert doc["content"] == server.ASK_ERROR_REPLY


def test_error_after_partial_text_is_interrupted():
    async def partial(*_a, **_k):
        yield "Runway is about "
        raise RuntimeError("connection reset")

    body, doc = _run_ask(partial)
    assert body == "Runway is about " + "\n\n_(Response interrupted — please ask again.)_"
    assert doc["interrupted"] is True
    assert "is_error" not in doc
    assert doc["content"] == body


def test_success_has_no_flags():
    async def ok(*_a, **_k):
        yield "14 months."

    body, doc = _run_ask(ok)
    assert body == "14 months."
    assert "is_error" not in doc and "interrupted" not in doc
