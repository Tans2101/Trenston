"""Weekly CEO Pack writing-style contract and scenario samples."""
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import os
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_weekly_pack_tone")

import server  # noqa: E402


# Rigid templates the old prompt (and common AI packs) forced every week.
_BANNED_FIXED_HEADERS = (
    "Headline",
    "Growth",
    "Financial Health",
    "Risks",
    "This Week's Focus",
)


def pack_style_flags(text: str) -> dict:
    """Heuristic flags for AI-slop pack formatting (used in tests, not runtime)."""
    body = text or ""
    bold_label_lines = len(re.findall(r"(?m)^\s*[-*]?\s*\*\*[^*]+:\*\*", body))
    bold_label_inline = len(re.findall(r"\*\*[^*]{1,40}:\*\*", body))
    em_dashes = body.count("—") + body.count(" – ")
    fixed_headers = [
        h for h in _BANNED_FIXED_HEADERS
        if re.search(rf"(?im)^##\s*{re.escape(h)}\s*$", body)
    ]
    always_on = sum(
        1 for h in ("What happened", "What needs attention", "Next week")
        if re.search(rf"(?im)^##\s*{re.escape(h)}\s*$", body)
    )
    return {
        "bold_label_lines": bold_label_lines,
        "bold_label_hits": bold_label_inline,
        "em_dashes": em_dashes,
        "fixed_headers": fixed_headers,
        "always_on_sections": always_on,
    }


def assert_natural_pack_style(text: str):
    flags = pack_style_flags(text)
    assert flags["bold_label_hits"] <= 2, flags
    assert flags["em_dashes"] <= 1, flags
    assert not flags["fixed_headers"], flags
    assert flags["always_on_sections"] < 3, flags


QUIET_WEEK = """# Northwind — this week

A quiet week. Monthly recurring revenue (MRR) held at $12K and cash runway stayed at 14 months.
Two team updates came in with no blockers. Nothing here needs a call before Monday.
"""

ALARMING_WEEK = """# Northwind — this week

Burn jumped hard. Monthly burn is **$36K**, up from $8K last check-in, almost entirely cloud and infra.
Cash was never entered, so we cannot compute runway. Add a cash balance on Financials before treating
any runway number as real.

Sales logged one small qualified deal ($15). The only decision that matters right now is whether to
freeze non-essential infrastructure spend this week.
"""

MIXED_WEEK = """# Northwind — this week

Revenue is fine; the friction is capacity. Monthly recurring revenue (MRR) rose to $28K, and we closed
the Agri Exim testing deal. Engineering still has two overdue handoffs and one blocked hire.

## Monday
Approve or cut the $40K infra reservation. It is the only open call that changes next month's burn.
"""

SLOP_PACK = """# Weekly update — Northwind

## Headline
**Revenue:** flat — **Burn:** rising — **Runway:** unclear.

## Growth
**New deals:** one small deal — **Pipeline:** quiet.

## Financial Health
**Cash on hand:** missing — **Burn:** $36K — **MRR:** $0.

## Risks
**Infrastructure spend:** quadrupled — **Hiring:** stalled.

## This Week's Focus
**Decision:** freeze cloud — **Owner:** CEO — **Deadline:** today.
"""


def test_natural_samples_pass_style_contract():
    for sample in (QUIET_WEEK, ALARMING_WEEK, MIXED_WEEK):
        assert_natural_pack_style(sample)


def test_slop_sample_fails_style_contract():
    flags = pack_style_flags(SLOP_PACK)
    assert flags["bold_label_hits"] > 2
    assert flags["em_dashes"] > 1
    assert flags["fixed_headers"]


def test_scenario_samples_differ_in_shape():
    """Quiet / alarming / mixed notes should not share one rigid section skeleton."""
    quiet_h = set(re.findall(r"(?m)^##\s+(.+)$", QUIET_WEEK))
    alarm_h = set(re.findall(r"(?m)^##\s+(.+)$", ALARMING_WEEK))
    mixed_h = set(re.findall(r"(?m)^##\s+(.+)$", MIXED_WEEK))
    assert quiet_h == set()
    assert alarm_h == set()
    assert mixed_h == {"Monday"}
    assert QUIET_WEEK != ALARMING_WEEK != MIXED_WEEK


@pytest.mark.asyncio
async def test_weekly_pack_system_prompt_requires_natural_tone():
    captured = {}

    async def fake_complete(system, user, **kwargs):
        captured["system"] = system
        captured["user"] = user
        return QUIET_WEEK

    ws = {
        "workspace_id": "ws_1",
        "name": "Northwind",
        "telemetry": {"kpis": []},
        "tasks": {"items": []},
        "people": {"people": []},
        "employees": 2,
        "manual_reports": [],
        "report_snapshot": None,
    }
    updates = MagicMock()
    updates.to_list = AsyncMock(return_value=[])
    mock_db = MagicMock()
    mock_db.updates.find.return_value = updates
    mock_db.workspaces.update_one = AsyncMock()
    mock_db.financial_entries.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
    principal = {"workspace_id": "ws_1", "user_id": "u1", "pack": "owner"}

    with patch.object(server, "get_ws", new=AsyncMock(return_value=ws)), \
         patch.object(server, "compute_financials", new=AsyncMock(return_value={
             "mrr": "$12K", "runway_months": 14, "burn": "$4K",
             "mrr_value": 12000, "burn_value": 4000,
         })), \
         patch.object(server, "db", mock_db), \
         patch.object(server.helm_llm, "anthropic_configured", return_value=True), \
         patch.object(server.helm_llm, "complete", new=AsyncMock(side_effect=fake_complete)):
        result = await server.weekly_pack(principal=principal)

    system = captured["system"].lower()
    assert result["content"] == QUIET_WEEK
    assert "board" not in system
    assert "plain english" in system
    assert "bold-label-plus-colon" in system or "**label:**" in system
    assert "em dash" in system or "em dashes" in system
    assert "structure follows" in system
    assert "what happened" in system  # banned as always-on, still named so model avoids it
    assert "instructions_for_missing_data" in captured["user"]
    assert "350 words" in system
    assert "monetization signal" in system
    assert_natural_pack_style(result["content"])


@pytest.fixture(autouse=True)
def _no_ai_rate_limit(monkeypatch):
    # The endpoint rate-limits paid AI calls through Mongo; this test mocks db.
    monkeypatch.setattr(server.doc_rate_limit, "acquire_event_slot", AsyncMock(return_value=True))
