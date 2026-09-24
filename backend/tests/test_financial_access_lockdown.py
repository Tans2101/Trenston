"""Financial access: report cards, Ask Trenston context, restricted markers."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_financial_access_lockdown")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server
from tests.mongo_mocks import FakeCollection  # noqa: E402
from server import (  # noqa: E402
    FINANCIALS_ACCESS_DENIED_MESSAGE,
    ask_context_for_synthesis,
    message_requests_financials,
    _computed_report_cards,
)


def _sample_fin():
    return {
        "mrr": "$10K",
        "arr": "$120K",
        "runway_months": 12,
        "burn": "$5K",
        "mrr_value": 10000,
        "burn_value": 5000,
        "cash_entered": True,
        "cash_value": 50000.0,
        "mrr_known": True,
        "burn_known": True,
        "currency": "usd",
        "months": ["2026-01", "2026-02"],
        "latest_month": "2026-02",
    }


def test_computed_report_cards_omit_money_when_no_fin_access():
    fin = _sample_fin()
    with_fin = _computed_report_cards({}, fin, [], [], 3, prior=None, include_financials=True)
    without = _computed_report_cards({}, fin, [], [], 3, prior=None, include_financials=False)
    assert [c["id"] for c in with_fin] == ["auto_fin", "auto_team", "auto_exec"]
    assert [c["id"] for c in without] == ["auto_team", "auto_exec"]
    assert all(c["id"] != "auto_fin" for c in without)
    assert "Money check-in" not in [c["title"] for c in without]


def test_ask_context_restricts_financials_when_not_visible():
    fin = _sample_fin()
    c = {
        "name": "Acme",
        "stage": "Seed",
        "employees": 2,
        "people": {"people": [{"id": "p1"}]},
        "decisions": [{"title": "Hire", "status": "pending"}],
        "telemetry_manual": {"risks": []},
    }
    open_ctx = ask_context_for_synthesis(
        c, fin, deals=[], sales_tracked=True, onboarding_instances=[], hr_tracked=True,
        financials_visible=True,
    )
    assert open_ctx["financials"].get("access") != "restricted"
    assert open_ctx["financials"].get("mrr") == 10000

    locked = ask_context_for_synthesis(
        c, fin, deals=[], sales_tracked=True, onboarding_instances=[], hr_tracked=True,
        financials_visible=False,
    )
    assert locked["financials"] == {
        "access": "restricted",
        "note": "Financial figures are not shared with this user's role.",
    }
    blob = str(locked["financials"])
    assert "10000" not in blob
    assert "$10K" not in blob
    assert "50000" not in blob
    assert locked["open_decisions"] == ["Hire"]
    assert locked["people_count"] == 1
    assert locked["pipeline"]["deal_count"] == 0


@pytest.mark.parametrize(
    "message,expected",
    [
        ("How many months of runway do we really have?", True),
        ("What is our MRR?", True),
        ("What's our burn rate?", True),
        ("Show cash balance", True),
        ("Which decision should I make first?", False),
        ("Where is my team over capacity?", False),
        ("", False),
    ],
)
def test_message_requests_financials(message, expected):
    assert message_requests_financials(message) is expected


@pytest.mark.asyncio
async def test_can_access_financials_matches_section_write():
    owner = {"pack": "owner", "workspace_id": "ws1", "user_id": "u1"}
    member = {"pack": "member", "workspace_id": "ws1", "user_id": "u2"}
    assert await server.can_access_financials(owner) is True
    with patch.object(server, "_membership_for", new=AsyncMock(return_value={
        "section_grants": [], "department": "Engineering",
    })), patch.object(server, "get_ws", new=AsyncMock(return_value={"section_access": {}})):
        assert await server.can_access_financials(member) is False
    with patch.object(server, "_membership_for", new=AsyncMock(return_value={
        "section_grants": ["financials"], "department": "Engineering",
    })), patch.object(server, "get_ws", new=AsyncMock(return_value={"section_access": {}})):
        assert await server.can_access_financials(member) is True


@pytest.mark.asyncio
async def test_ask_helm_finance_deny_streams_without_model():
    principal = {
        "user_id": "u_member",
        "workspace_id": "ws_lock",
        "pack": "member",
        "role": "member",
        "email": "member@example.com",
        "name": "Member",
    }
    ws = {
        "workspace_id": "ws_lock",
        "name": "Lock Co",
        "plan": "starter",
        "people": {"people": []},
        "decisions": [],
        "telemetry_manual": {"risks": []},
    }
    mock_db = MagicMock()
    mock_db.chat_messages.insert_one = AsyncMock(return_value=None)
    mock_db.chat_messages.find = FakeCollection().find

    async def _never_stream(*_a, **_k):
        raise AssertionError("model must not be called")
        yield ""  # pragma: no cover

    with patch.object(server, "get_ws", new=AsyncMock(return_value=ws)), \
            patch.object(server, "can_access_financials", new=AsyncMock(return_value=False)), \
            patch.object(server, "compute_financials", new=AsyncMock(side_effect=AssertionError("no compute"))), \
            patch.object(server, "db", mock_db), \
            patch.object(server, "_product_event", new=AsyncMock()), \
            patch.object(server.helm_llm, "anthropic_configured", return_value=True), \
            patch.object(server.helm_llm, "stream_text", side_effect=_never_stream), \
            patch.object(server.plan_usage, "acquire_period_ask_slot", new=AsyncMock(return_value=True)), \
            patch.object(server.plan_usage, "current_usage_period", return_value={
                "key": "2026-09-01",
                "start": __import__("datetime").datetime(2026, 9, 1, tzinfo=__import__("datetime").timezone.utc),
                "end": __import__("datetime").datetime(2026, 10, 1, tzinfo=__import__("datetime").timezone.utc),
            }), \
            patch.object(server, "BILLING_ENFORCED", False):
        resp = await server.ask_helm(
            server.AskInput(message="How much runway do we have?"),
            principal,
        )
        assert resp.media_type == "text/event-stream"
        chunks = []
        async for chunk in resp.body_iterator:
            chunks.append(chunk if isinstance(chunk, str) else chunk.decode())

    text = "".join(chunks)
    assert text == FINANCIALS_ACCESS_DENIED_MESSAGE
    assert "10000" not in text
    assert mock_db.chat_messages.insert_one.await_count >= 2
