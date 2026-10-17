"""Paid AI endpoints must stop when the hourly cap is used up."""
import asyncio
import os
from unittest.mock import AsyncMock, patch

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_ai_rate_limits")

import pytest
from fastapi import HTTPException

import server

P = {"user_id": "u1", "workspace_id": "ws1", "pack": "owner", "role": "owner"}


def run(c):
    return asyncio.new_event_loop().run_until_complete(c)


def test_weekly_pack_rate_limited():
    with patch.object(server.doc_rate_limit, "acquire_event_slot", AsyncMock(return_value=False)), \
         patch.object(server, "_generate_weekly_pack_content", AsyncMock()) as gen:
        with pytest.raises(HTTPException) as e:
            run(server.weekly_pack(principal=P))
    assert e.value.status_code == 429
    gen.assert_not_awaited()


def test_briefing_generate_rate_limited():
    with patch.object(server.doc_rate_limit, "acquire_event_slot", AsyncMock(return_value=False)), \
         patch.object(server, "get_ws", AsyncMock(return_value={"workspace_id": "ws1", "briefing": {}})), \
         patch.object(server.helm_llm, "anthropic_configured", lambda: True), \
         patch.object(server.helm_llm, "complete", AsyncMock()) as llm:
        with pytest.raises(HTTPException) as e:
            run(server.generate_briefing(principal=P))
    assert e.value.status_code == 429
    llm.assert_not_awaited()
