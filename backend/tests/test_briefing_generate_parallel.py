"""POST /briefing/generate must load calendar + freshness in the same gather as fin/ops."""
from __future__ import annotations

import asyncio
import inspect
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_briefing_generate_parallel")

import server  # noqa: E402


def test_generate_briefing_source_gathers_calendar_and_freshness():
    src = inspect.getsource(server.generate_briefing)
    assert "_google_calendar_snapshot" in src
    assert "resolve_workspace_data_as_of" in src
    # Calendar must not be a sequential await after the gather of fin/acts/ops.
    gather_idx = src.index("await asyncio.gather(")
    cal_idx = src.index("_google_calendar_snapshot(")
    assert cal_idx > gather_idx
    # Compact JSON for the LLM payload (fewer tokens than indent=2).
    assert 'separators=(",", ":")' in src or "separators=(',', ':')" in src


@pytest.mark.asyncio
async def test_generate_briefing_awaits_calendar_concurrently_with_fin():
    """Slow calendar must not add full latency on top of slow financials."""
    ws = {
        "workspace_id": "ws_par",
        "name": "Acme",
        "plan": "pro",
        "briefing": {"headline": "Hi", "what_changed": [], "nrr": None},
        "decisions": [],
        "decision_suggestions": [],
    }
    principal = {
        "user_id": "u1",
        "workspace_id": "ws_par",
        "role": "owner",
        "pack": "owner",
    }
    order: list[str] = []

    async def slow_fin(_wid):
        order.append("fin_start")
        await asyncio.sleep(0.05)
        order.append("fin_done")
        return {
            "mrr": 1, "mrr_known": True, "mrr_value": 1, "mrr_delta": None,
            "burn": 1, "burn_known": True, "burn_value": 1, "burn_tone": "neutral",
            "runway_months": 1.0, "runway_no_burn": False, "cash_entered": True,
            "cash_value": 1, "currency": "usd",
        }

    async def slow_cal(*_a, **_k):
        order.append("cal_start")
        await asyncio.sleep(0.05)
        order.append("cal_done")
        return None

    empty_cursor = MagicMock()
    empty_cursor.sort.return_value = empty_cursor
    empty_cursor.to_list = AsyncMock(return_value=[])

    with patch.object(server, "get_ws", AsyncMock(return_value=ws)), \
         patch.object(server.helm_llm, "anthropic_configured", return_value=True), \
         patch.object(server.helm_llm, "complete", AsyncMock(return_value="Note.")), \
         patch.object(server, "can_access_financials", AsyncMock(return_value=True)), \
         patch.object(server, "compute_financials", side_effect=slow_fin), \
         patch.object(server, "_briefing_ops_metrics", AsyncMock(return_value=[])), \
         patch.object(server, "_google_calendar_snapshot", side_effect=slow_cal), \
         patch.object(server.helm_freshness, "resolve_workspace_data_as_of", AsyncMock(return_value={
             "data_as_of": "2026-09-23T09:00:00+00:00", "sources": {},
         })), \
         patch.object(server, "db") as mock_db:
        mock_db.activities.find.return_value = empty_cursor
        mock_db.workspaces.update_one = AsyncMock()
        t0 = asyncio.get_event_loop().time()
        result = await server.generate_briefing(principal)
        elapsed = asyncio.get_event_loop().time() - t0

    assert result["ai_summary"] == "Note."
    # Both started before either finished → overlapped.
    assert order.index("cal_start") < order.index("fin_done")
    assert order.index("fin_start") < order.index("cal_done")
    # Serial would be ~0.10s+; concurrent target under ~0.09s wall for the I/O phase
    # (plus LLM mock). Allow headroom for CI noise.
    assert elapsed < 0.20


@pytest.fixture(autouse=True)
def _no_ai_rate_limit(monkeypatch):
    # The endpoints rate-limit paid AI calls through Mongo; these tests mock db.
    from unittest.mock import AsyncMock as _AM
    monkeypatch.setattr(server.doc_rate_limit, "acquire_event_slot", _AM(return_value=True))
