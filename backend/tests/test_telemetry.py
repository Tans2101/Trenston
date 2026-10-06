"""Telemetry API: heatmap today window, suggested-risk dedupe, risk cap."""
import os
import sys
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_telemetry")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402
from server import _activity_heatmap_for_workspace  # noqa: E402

OWNER = {
    "user_id": "u_owner",
    "email": "owner@acme.com",
    "name": "Owner",
    "workspace_id": "ws_tel",
    "role": "owner",
    "pack": "owner",
}


@pytest.mark.asyncio
async def test_heatmap_manila_today_window_vs_utc_bucketing():
    """Window uses workspace today; cells stay UTC date of created_at (FIX 1).

    2026-09-24T17:00:00Z = Sep 25 01:00 Asia/Manila, but UTC-date bucket is Sep 24.
    """
    crossing = "2026-09-24T17:00:00+00:00"
    docs = [{"created_at": crossing}]

    async def _aiter(self):
        for d in docs:
            yield d

    cursor = MagicMock()
    cursor.__aiter__ = _aiter

    with patch("server.db") as mock_db:
        mock_db.activities.find.return_value = cursor
        manila = await _activity_heatmap_for_workspace(
            "ws_tel", today=date(2026, 9, 25), weeks=2,
        )
        utc_ws = await _activity_heatmap_for_workspace(
            "ws_tel", today=date(2026, 9, 24), weeks=2,
        )

    manila_by = {b["date"]: b["count"] for col in manila["columns"] for b in col["bins"]}
    utc_by = {b["date"]: b["count"] for col in utc_ws["columns"] for b in col["bins"]}
    assert manila_by.get("2026-09-24") == 1
    assert utc_by.get("2026-09-24") == 1
    assert "2026-09-25" in manila_by
    assert utc_by.get("2026-09-25", 0) == 0


def test_patch_preserves_source_signal_and_caps_at_20():
    stored = {}

    async def fake_get_ws(ws_id):
        return {
            "workspace_id": ws_id,
            "telemetry_manual": stored.get("manual") or {"risks": [], "notes": "", "targets": {}},
        }

    async def fake_update_one(query, update):
        stored["manual"] = update["$set"]["telemetry_manual"]

    mock_db = MagicMock()
    mock_db.workspaces.update_one = AsyncMock(side_effect=fake_update_one)

    async def as_owner():
        return OWNER

    risks_25 = [
        {
            "name": f"Risk {i}",
            "likelihood": 2,
            "impact": 3,
            "category": "Ops",
            **({"source_signal": "overdue_task"} if i == 0 else {}),
        }
        for i in range(25)
    ]

    server.app.dependency_overrides[server.get_principal] = as_owner
    try:
        with patch.object(server, "get_ws", fake_get_ws), \
             patch.object(server, "db", mock_db), \
             patch.object(server, "can_section_write", AsyncMock(return_value=True)), \
             patch.object(server, "log_activity", AsyncMock()):
            client = TestClient(server.app)
            r = client.patch("/api/telemetry", json={"risks": risks_25, "notes": ""})
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["risks"]) == 20
        assert body["risks"][0].get("source_signal") == "overdue_task"
        assert stored["manual"]["risks"][0].get("source_signal") == "overdue_task"
        assert len(stored["manual"]["risks"]) == 20
    finally:
        server.app.dependency_overrides.clear()


def test_suggested_risk_overdue_task_hidden_after_resolved():
    """GET /telemetry drops suggestions whose source_signal is already on a saved risk."""
    ws = {
        "workspace_id": "ws_tel",
        "template": "empty",
        "tasks": {"items": []},
        "people": {"people": []},
        "employees": 0,
        "telemetry": {"funnel": [], "risks": []},
        "telemetry_manual": {
            "risks": [{
                "id": "r1",
                "name": "Overdue tasks",
                "likelihood": 3,
                "impact": 3,
                "category": "Ops",
                "source_signal": "overdue_task",
            }],
            "notes": "",
            "targets": {"enabled": False, "monthly_growth_pct": 0},
        },
        "financial_settings": {"currency": "usd"},
    }

    async def fake_get_ws(_ws_id):
        return ws

    async def as_owner():
        return OWNER

    suggestions = [
        {"name": "Overdue tasks", "category": "Ops", "source_signal": "overdue_task"},
        {"name": "Runway thin", "category": "Financial", "source_signal": "runway_risk"},
    ]

    fin = {
        "currency": "usd",
        "expense_breakdown": [],
        "revenue_series": [],
        "mrr_delta": 0,
        "mrr_known": False,
        "mrr_state": "missing",
        "arr": "$0",
        "spark": [],
        "runway_months": None,
        "runway_no_burn": False,
        "runway_state": "missing",
        "burn_known": False,
        "burn_tone": "neutral",
        "burn_series": [],
        "burn_state": "missing",
        "has_data": False,
        "cash_entered": False,
    }

    server.app.dependency_overrides[server.get_principal] = as_owner
    try:
        with patch.object(server, "get_ws", fake_get_ws), \
             patch.object(server, "compute_financials", AsyncMock(return_value=fin)), \
             patch.object(server, "db") as mock_db, \
             patch.object(server, "can_section_write", AsyncMock(return_value=True)), \
             patch.object(server, "can_access_financials", AsyncMock(return_value=True)), \
             patch.object(server, "_workspace_live_signals", AsyncMock(return_value=[])), \
             patch.object(server, "_telemetry_risk_suggestions_from_signals", return_value=suggestions), \
             patch.object(server, "_activity_heatmap_for_workspace", AsyncMock(return_value={"columns": [], "total": 0})), \
             patch.object(server, "_workspace_tz_doc", AsyncMock(return_value={"timezone": "Asia/Manila"})), \
             patch.object(server, "_user_google_tokens_present", AsyncMock(return_value=False)), \
             patch.object(server.helm_freshness, "resolve_workspace_data_as_of", AsyncMock(return_value={"data_as_of": None, "sources": {}})):
            mock_db.deals.find.return_value = MagicMock(to_list=AsyncMock(return_value=[]))
            client = TestClient(server.app)
            r = client.get("/api/telemetry")
        assert r.status_code == 200, r.text
        suggested = r.json()["suggested_risks"]
        types = [s.get("source_signal") for s in suggested]
        assert "overdue_task" not in types
        assert "runway_risk" in types
    finally:
        server.app.dependency_overrides.clear()
