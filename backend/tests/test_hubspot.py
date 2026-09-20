"""Unit tests for HubSpot deal mapping and token refresh."""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("HUBSPOT_CLIENT_ID", "test-client")
os.environ.setdefault("HUBSPOT_CLIENT_SECRET", "test-secret")

import hubspot as hs  # noqa: E402

# Module constants are read at import; pin them for workers that imported hubspot earlier.
hs.HUBSPOT_CLIENT_ID = os.environ["HUBSPOT_CLIENT_ID"]
hs.HUBSPOT_CLIENT_SECRET = os.environ["HUBSPOT_CLIENT_SECRET"]


def test_map_stage_closed_won_lost():
    assert hs.map_hubspot_stage("Closed Won", "closedwon") == "won"
    assert hs.map_hubspot_stage("Closed Lost", "closedlost") == "lost"
    assert hs.map_hubspot_stage("Contract Sent", "contractsent") == "negotiation"
    assert hs.map_hubspot_stage("Presentation Scheduled", "presentationscheduled") == "proposal"
    assert hs.map_hubspot_stage("Qualified To Buy", "qualifiedtobuy") == "qualified"
    assert hs.map_hubspot_stage("Appointment Scheduled", "appointmentscheduled") == "lead"


def test_map_hubspot_deal_shape():
    deal = {
        "id": "501",
        "properties": {
            "dealname": "Acme expansion",
            "amount": "12500.5",
            "dealstage": "closedwon",
            "closedate": "2026-08-15T00:00:00.000Z",
        },
        "associations": {"companies": {"results": [{"id": "99"}]}},
    }
    mapped = hs.map_hubspot_deal(deal, {"closedwon": "Closed Won"}, {"99": "Acme Corp"})
    assert mapped["hubspot_deal_id"] == "501"
    assert mapped["name"] == "Acme expansion"
    assert mapped["company"] == "Acme Corp"
    assert mapped["value"] == 12500.5
    assert mapped["stage"] == "won"
    assert mapped["close_date"] == "2026-08-15"
    assert mapped["source"] == "hubspot_sync"


def test_refresh_skips_when_fresh():
    tokens = {
        "access_token": "abc",
        "refresh_token": "r1",
        "expires_in": 21600,
        "obtained_at": datetime.now(timezone.utc).isoformat(),
    }
    with patch("hubspot.httpx.AsyncClient") as mock_client:
        out = asyncio.run(hs.refresh_hubspot_token(tokens))
    assert out == tokens
    mock_client.assert_not_called()


def test_refresh_updates_access_token():
    tokens = {
        "access_token": "old",
        "refresh_token": "r1",
        "expires_in": 21600,
        "obtained_at": (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat(),
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": "new",
        "refresh_token": "r2",
        "expires_in": 21600,
    }
    mock_hc = AsyncMock()
    mock_hc.post = AsyncMock(return_value=mock_resp)
    mock_hc.__aenter__ = AsyncMock(return_value=mock_hc)
    mock_hc.__aexit__ = AsyncMock(return_value=None)
    with patch("hubspot.httpx.AsyncClient", return_value=mock_hc):
        out = asyncio.run(hs.refresh_hubspot_token(tokens))
    assert out["access_token"] == "new"
    assert out["refresh_token"] == "r2"


def test_refresh_raises_on_failure():
    tokens = {
        "access_token": "old",
        "refresh_token": "r1",
        "expires_in": 21600,
        "obtained_at": (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat(),
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "invalid"
    mock_hc = AsyncMock()
    mock_hc.post = AsyncMock(return_value=mock_resp)
    mock_hc.__aenter__ = AsyncMock(return_value=mock_hc)
    mock_hc.__aexit__ = AsyncMock(return_value=None)
    with patch("hubspot.httpx.AsyncClient", return_value=mock_hc):
        with pytest.raises(hs.HubSpotAuthError):
            asyncio.run(hs.refresh_hubspot_token(tokens))
