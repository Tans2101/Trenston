"""Weekly CEO Pack PDF export — no LLM, no rewards."""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_weekly_pack_export")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import weekly_pack_export as pack_pdf  # noqa: E402
import server  # noqa: E402

SAMPLE = """# Headline
Cash is tight but orders are holding.

## Growth
Closed **two** shop-floor contracts.

### Risks
- Overtime on the night shift
- Late steel delivery

Paragraph with <special> & characters.
"""


def test_pdf_filename_includes_workspace_and_date():
    name = pack_pdf.pdf_filename("Acme Manufacturing", datetime(2026, 9, 8, tzinfo=timezone.utc))
    assert name == "Trenston-Weekly-Pack-Acme-Manufacturing-2026-09-08.pdf"


def test_pdf_filename_strips_unsafe_chars():
    name = pack_pdf.pdf_filename('North/West "Co"')
    assert "/" not in name
    assert '"' not in name
    assert name.startswith("Trenston-Weekly-Pack-")
    assert name.endswith(".pdf")


def test_render_weekly_pack_pdf_is_legible_pdf():
    pdf = pack_pdf.render_weekly_pack_pdf(
        SAMPLE,
        workspace_name="Northwind Manufacturing",
        generated_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
    )
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 800
    assert pdf.rstrip().endswith(b"%%EOF") or b"%%EOF" in pdf[-64:]


def test_render_rejects_empty():
    with pytest.raises(ValueError):
        pack_pdf.render_weekly_pack_pdf("   ", workspace_name="Acme")


def test_no_board_ready_in_export_module():
    src = Path(pack_pdf.__file__).read_text()
    assert "board-ready" not in src.lower()


def test_export_pdf_endpoint_returns_attachment():
    async def mock_principal():
        return {
            "user_id": "u_owner",
            "email": "ceo@example.com",
            "name": "CEO",
            "workspace_id": "ws_1",
            "role": "owner",
            "pack": "owner",
        }

    async def fake_ws(_wid):
        return {"workspace_id": "ws_1", "name": "Forge Co", "plan": "starter"}

    server.app.dependency_overrides[server.get_principal] = mock_principal
    try:
        with patch.object(server, "get_ws", new=AsyncMock(side_effect=fake_ws)), \
             patch.object(server, "BILLING_ENFORCED", False):
            client = TestClient(server.app)
            r = client.post("/api/reports/weekly-pack/export-pdf", json={"content": SAMPLE})
    finally:
        server.app.dependency_overrides.clear()
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert "Trenston-Weekly-Pack-Forge-Co" in r.headers.get("content-disposition", "")
    assert r.content.startswith(b"%PDF")


def test_export_pdf_rejects_empty_body():
    async def mock_principal():
        return {
            "user_id": "u_owner",
            "email": "ceo@example.com",
            "workspace_id": "ws_1",
            "role": "owner",
            "pack": "owner",
        }

    server.app.dependency_overrides[server.get_principal] = mock_principal
    try:
        with patch.object(server, "BILLING_ENFORCED", False):
            client = TestClient(server.app)
            r = client.post("/api/reports/weekly-pack/export-pdf", json={"content": "  "})
    finally:
        server.app.dependency_overrides.clear()
    assert r.status_code == 400


def test_export_pdf_forbidden_without_pack_perm():
    async def mock_principal():
        return {
            "user_id": "u_mem",
            "email": "member@example.com",
            "workspace_id": "ws_1",
            "role": "member",
            "pack": "member",
        }

    server.app.dependency_overrides[server.get_principal] = mock_principal
    try:
        client = TestClient(server.app)
        r = client.post("/api/reports/weekly-pack/export-pdf", json={"content": SAMPLE})
    finally:
        server.app.dependency_overrides.clear()
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_weekly_pack_system_prompt_has_no_board():
    captured = {}

    async def fake_complete(system, user, **kwargs):
        captured["system"] = system
        return "ok"

    ws = {
        "workspace_id": "ws_1",
        "name": "Acme",
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
             "mrr": "$0", "runway_months": 12, "burn": "$0",
         })), \
         patch.object(server, "db", mock_db), \
         patch.object(server.helm_llm, "anthropic_configured", return_value=True), \
         patch.object(server.helm_llm, "complete", new=AsyncMock(side_effect=fake_complete)):
        result = await server.weekly_pack(principal=principal)
    assert result["content"] == "ok"
    assert "board" not in captured["system"].lower()
    assert "plain english" in captured["system"].lower()
    assert "thoughtful" in captured["system"].lower()
    assert "350 words" in captured["system"].lower()
    assert "structure follows" in captured["system"].lower() or "structure follow" in captured["system"].lower()
    assert "em dash" in captured["system"].lower() or "em dashes" in captured["system"].lower()
    assert "exact markdown structure" not in captured["system"].lower()


@pytest.fixture(autouse=True)
def _no_ai_rate_limit(monkeypatch):
    # The endpoints rate-limit paid AI calls through Mongo; these tests mock db.
    from unittest.mock import AsyncMock as _AM
    monkeypatch.setattr(server.doc_rate_limit, "acquire_event_slot", _AM(return_value=True))
