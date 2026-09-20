"""Department-sourced report drafts — deterministic, no LLM."""
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_dept_report_drafts")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import department_report_drafts as drafts  # noqa: E402
import departments_catalog as catalog  # noqa: E402
import server  # noqa: E402

NOW = datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc)  # Tuesday → week of Sep 7


def test_week_window_monday():
    start, end, period, key = drafts.week_window(NOW)
    assert key == "2026-09-07"
    assert start.day == 7
    assert (end - start).days == 7
    assert period == "Week of Sep 7, 2026"


def test_empty_activity_builds_nothing():
    spec = drafts.SPEC_BY_TYPE[catalog.TYPE_PRODUCTION]
    assert drafts.build_draft_doc(
        workspace_id="ws1", spec=spec, items=[], period="Week of Sep 7, 2026",
        week_start="2026-09-07", now_iso=NOW.isoformat(),
    ) is None


def test_production_draft_lists_completed_work_orders():
    spec = drafts.SPEC_BY_TYPE[catalog.TYPE_PRODUCTION]
    items = [
        {"id": "a", "reference": "Order #1", "status": "completed", "completed_at": "2026-09-07T12:00:00+00:00"},
        {"id": "b", "reference": "Order #2", "status": "completed", "completed_at": "2026-09-08T09:00:00+00:00"},
    ]
    start, end, period, key = drafts.week_window(NOW)
    kept = drafts.filter_completed(items, spec, start, end)
    doc = drafts.build_draft_doc(
        workspace_id="ws1", spec=spec, items=kept, period=period,
        week_start=key, now_iso=NOW.isoformat(),
    )
    assert doc["source"] == "department_draft"
    assert doc["status"] == "draft"
    assert doc["type"] == "Production"
    assert "2 work orders" in doc["summary"]
    assert "Order #1" in doc["summary"] and "Order #2" in doc["summary"]
    assert doc["metrics"] == [{"label": "Work orders finished", "value": "2"}]


def test_old_completions_are_not_in_this_week():
    spec = drafts.SPEC_BY_TYPE[catalog.TYPE_LEGAL]
    items = [
        {"id": "old", "title": "Lease", "status": "filed", "completed_at": "2026-08-01T00:00:00+00:00"},
        {"id": "new", "title": "NDA", "status": "filed", "completed_at": "2026-09-07T18:00:00+00:00"},
        {"id": "open", "title": "Open", "status": "draft", "updated_at": "2026-09-08T00:00:00+00:00"},
    ]
    start, end, period, key = drafts.week_window(NOW)
    kept = drafts.filter_completed(items, spec, start, end)
    assert [i["id"] for i in kept] == ["new"]
    doc = drafts.build_draft_doc(
        workspace_id="ws1", spec=spec, items=kept, period=period,
        week_start=key, now_iso=NOW.isoformat(),
    )
    assert "1 legal matter" in doc["summary"]
    assert "NDA" in doc["summary"]
    assert "Lease" not in doc["summary"]


def test_apply_status_completion_stamps_and_clears():
    upd = {"status": "delivered"}
    drafts.apply_status_completion({"status": "ordered"}, upd, done_status="delivered", now_iso="T")
    assert upd["completed_at"] == "T"
    upd2 = {"status": "ordered"}
    drafts.apply_status_completion({"status": "delivered", "completed_at": "T"}, upd2, done_status="delivered")
    assert upd2["completed_at"] is None


def test_module_does_not_call_an_llm():
    src = Path(drafts.__file__).read_text()
    assert "complete(" not in src
    assert "anthropic" not in src.lower()
    assert "helm_llm" not in src


class _Result:
    def __init__(self, n=1):
        self.modified_count = n
        self.matched_count = n


def _cursor(rows):
    cur = MagicMock()
    cur.to_list = AsyncMock(return_value=list(rows))
    cur.sort = MagicMock(return_value=cur)
    return cur


def _store(rows):
    col = MagicMock()

    async def find_one(query, projection=None):
        for d in rows:
            if all(d.get(k) == v for k, v in query.items()):
                return dict(d)
        return None

    async def insert_one(doc):
        rows.append(dict(doc))
        return MagicMock()

    async def update_one(query, update):
        rec = await find_one(query)
        if not rec:
            return _Result(0)
        for d in rows:
            if d.get("id") == rec.get("id") or all(d.get(k) == query.get(k) for k in query):
                d.update(update.get("$set") or {})
                return _Result(1)
        return _Result(0)

    async def delete_one(query):
        before = len(rows)
        keep = [d for d in rows if d.get("id") != query.get("id")]
        rows[:] = keep
        return _Result(before - len(rows))

    col.find_one = find_one
    col.insert_one = insert_one
    col.update_one = update_one
    col.delete_one = delete_one
    col.find = lambda *a, **k: _cursor(rows)
    return col


@pytest.mark.asyncio
async def test_run_upserts_activity_and_skips_empty():
    orders = [
        {
            "id": "s1", "workspace_id": "ws1", "reference": "Pack job", "status": "completed",
            "completed_at": "2026-09-07T10:00:00+00:00",
        },
    ]
    db = MagicMock()
    db.workspaces.find.return_value = _cursor([{"workspace_id": "ws1"}])
    db.departments.find.return_value = _cursor([
        {"type": "production"},
        {"type": "procurement"},
        {"type": "legal"},
        {"type": "engineering_maintenance"},
        {"type": "hr"},
    ])
    db.production_work_orders.find.return_value = _cursor(orders)
    db.procurement_requests.find.return_value = _cursor([])
    db.legal_matters.find.return_value = _cursor([])
    db.maintenance_tickets.find.return_value = _cursor([])
    db.hr_onboarding_instances.find.return_value = _cursor([])
    draft_rows = []
    db.department_report_drafts = _store(draft_rows)

    stats = await drafts.run_department_drafts(db, now=NOW)
    assert stats["drafts_upserted"] == 1
    assert stats["skipped_empty"] >= 1
    assert draft_rows[0]["type"] == "Production"
    assert draft_rows[0]["status"] == "draft"

    # Second run updates the same week instead of duplicating
    stats2 = await drafts.run_department_drafts(db, now=NOW)
    assert len(draft_rows) == 1
    assert stats2["drafts_upserted"] == 1


@pytest.mark.asyncio
async def test_run_does_not_regenerate_dismissed():
    draft_rows = [{
        "id": "drft_old",
        "workspace_id": "ws1",
        "department_type": "production",
        "week_start": "2026-09-07",
        "status": "dismissed",
    }]
    db = MagicMock()
    db.workspaces.find.return_value = _cursor([{"workspace_id": "ws1"}])
    db.departments.find.return_value = _cursor([{"type": "production"}])
    db.production_work_orders.find.return_value = _cursor([{
        "id": "s1", "workspace_id": "ws1", "reference": "Pack job", "status": "done",
        "completed_at": "2026-09-07T10:00:00+00:00",
    }])
    db.procurement_requests.find.return_value = _cursor([])
    db.legal_matters.find.return_value = _cursor([])
    db.maintenance_tickets.find.return_value = _cursor([])
    db.hr_onboarding_instances.find.return_value = _cursor([])
    db.department_report_drafts = _store(draft_rows)
    stats = await drafts.run_department_drafts(db, now=NOW)
    assert stats["skipped_closed"] == 1
    assert len(draft_rows) == 1
    assert draft_rows[0]["status"] == "dismissed"


OWNER = {
    "user_id": "u_owner",
    "email": "ceo@example.com",
    "name": "CEO",
    "workspace_id": "ws_1",
    "role": "owner",
    "pack": "owner",
}


def test_dismiss_and_publish_endpoints():
    rows = [{
        "id": "drft_1",
        "workspace_id": "ws_1",
        "status": "draft",
        "source": "department_draft",
        "title": "Production activity",
        "type": "Production",
        "period": "Week of Sep 7, 2026",
        "summary": "Finished 1 production stage: Pack.",
        "metrics": [{"label": "Stages finished", "value": "1"}],
    }]
    ws = {"workspace_id": "ws_1", "name": "Forge", "plan": "starter", "manual_reports": []}

    async def mock_principal():
        return OWNER

    mock_db = MagicMock()
    mock_db.department_report_drafts = _store(rows)

    async def fake_ws(_id):
        return ws

    async def ws_update(query, update):
        ws.update(update.get("$set") or {})
        return _Result(1)

    mock_db.workspaces.update_one = ws_update

    server.app.dependency_overrides[server.get_principal] = mock_principal
    try:
        with patch.object(server, "db", mock_db), patch.object(server, "get_ws", new=AsyncMock(side_effect=fake_ws)), \
             patch.object(server, "log_activity", new=AsyncMock()):
            client = TestClient(server.app)
            pub = client.post("/api/reports", json={
                "title": "Production activity",
                "type": "Production",
                "period": "Week of Sep 7, 2026",
                "summary": "Edited summary",
                "metrics": [{"label": "Stages finished", "value": "1"}],
                "from_draft_id": "drft_1",
            })
    finally:
        server.app.dependency_overrides.clear()
    assert pub.status_code == 200, pub.text
    assert pub.json()["report"]["source"] == "manual"
    assert pub.json()["report"]["summary"] == "Edited summary"
    assert rows[0]["status"] == "published"
    assert ws["manual_reports"][0]["source"] == "manual"


def test_dismiss_endpoint():
    rows = [{"id": "drft_2", "workspace_id": "ws_1", "status": "draft"}]

    async def mock_principal():
        return OWNER

    mock_db = MagicMock()
    mock_db.department_report_drafts = _store(rows)
    server.app.dependency_overrides[server.get_principal] = mock_principal
    try:
        with patch.object(server, "db", mock_db):
            client = TestClient(server.app)
            r = client.post("/api/reports/drafts/drft_2/dismiss")
    finally:
        server.app.dependency_overrides.clear()
    assert r.status_code == 200
    assert rows[0]["status"] == "dismissed"
    assert len(rows) == 1
