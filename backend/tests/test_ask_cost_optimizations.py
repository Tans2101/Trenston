"""Ask Trenston cost optimizations: compact JSON, prompt cache blocks, max_tokens."""
from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_ask_cost")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")

import server


def _period():
    from datetime import datetime, timezone
    return {
        "key": "2026-09-01",
        "start": datetime(2026, 9, 1, tzinfo=timezone.utc),
        "end": datetime(2026, 10, 1, tzinfo=timezone.utc),
    }


@pytest.mark.asyncio
async def test_ask_helm_uses_compact_json_cached_system_and_capped_tokens():
    ws = {
        "name": "Acme Co",
        "workspace_id": "ws_cost",
        "plan": "starter",
        "stage": "Seed",
        "employees": 2,
        "people": {"people": []},
        "decisions": [],
        "telemetry_manual": {"risks": []},
    }
    principal = {
        "user_id": "u1",
        "workspace_id": "ws_cost",
        "pack": "owner",
        "role": "owner",
    }
    captured = {}

    async def _capture(system, message, **kwargs):
        captured["system"] = system
        captured["message"] = message
        captured["max_tokens"] = kwargs.get("max_tokens")
        yield "answer"

    mock_db = MagicMock()
    mock_db.chat_messages = MagicMock()
    mock_db.chat_messages.insert_one = AsyncMock()

    with patch.object(server, "get_ws", new=AsyncMock(return_value=ws)), \
            patch.object(server, "can_access_financials", new=AsyncMock(return_value=True)), \
            patch.object(server, "compute_financials", new=AsyncMock(return_value={})), \
            patch.object(server, "db", mock_db), \
            patch.object(server, "_product_event", new=AsyncMock()), \
            patch.object(server.helm_llm, "anthropic_configured", return_value=True), \
            patch.object(server.helm_llm, "stream_text", side_effect=_capture), \
            patch.object(server.plan_usage, "acquire_period_ask_slot", new=AsyncMock(return_value=True)), \
            patch.object(server.plan_usage, "current_usage_period", return_value=_period()), \
            patch.object(server, "BILLING_ENFORCED", False), \
            patch.object(
                server.dept_access, "accessible_department_ids_by_type",
                new=AsyncMock(return_value={}),
            ), \
            patch.object(
                server.dept_migrate, "get_enabled_departments_by_type",
                new=AsyncMock(return_value={}),
            ), \
            patch.object(
                server, "_ask_helm_department_slice",
                new=AsyncMock(return_value=([], False, False)),
            ), \
            patch.object(
                server.helm_freshness, "resolve_workspace_data_as_of",
                new=AsyncMock(return_value={"data_as_of": None, "sources": {}}),
            ):
        resp = await server.ask_helm(server.AskInput(message="What is our runway?"), principal)
        async for _ in resp.body_iterator:
            pass

    assert captured["max_tokens"] == server.ASK_TRENSTON_MAX_TOKENS == 1000
    system = captured["system"]
    assert isinstance(system, list) and len(system) == 2
    assert system[0]["type"] == "text"
    assert system[0]["text"] == server.STATIC_ASK_TRENSTON_INSTRUCTIONS
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert "Never treat missing figures as zero" in system[0]["text"]
    assert system[1]["type"] == "text"
    assert "cache_control" not in system[1]
    assert "You are advising Acme Co." in system[1]["text"]
    assert "Current company snapshot:\n" in system[1]["text"]
    snapshot = system[1]["text"].split("Current company snapshot:\n", 1)[1]
    # Compact JSON: no indentation whitespace after separators
    assert "\n  " not in snapshot
    parsed = json.loads(snapshot)
    assert parsed["company_profile"]["name"] == "Acme Co"
    assert "instructions_for_missing_data" in json.dumps(parsed)


def test_static_ask_instructions_cover_missing_vs_zero_discipline():
    text = server.STATIC_ASK_TRENSTON_INSTRUCTIONS
    assert "instructions_for_missing_data" in text
    assert "unknown_fields" in text
    assert "restricted" in text
    assert "possibly_stale_count" in text
    assert "literally" in text
