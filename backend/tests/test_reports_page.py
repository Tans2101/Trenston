"""Reports page: report input is cleaned, money wording is plain, the CEO Pack is kept."""
import asyncio
import os

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_reports_page")

from mongomock_motor import AsyncMongoMockClient  # noqa: E402

import server  # noqa: E402


def test_metrics_are_cleaned_and_capped():
    raw = [
        {"label": " Deals ", "value": 4},
        {"label": "", "value": "x"},
        {"label": "Bad", "value": {"nested": 1}},
        "not a dict",
        {"label": "L" * 100, "value": "V" * 100},
    ] + [{"label": f"m{i}", "value": str(i)} for i in range(10)]
    out = server._sanitize_report_metrics(raw)
    assert out[0] == {"label": "Deals", "value": "4"}
    assert len(out) == 6
    assert len(out[1]["label"]) == 60 and len(out[1]["value"]) == 40
    assert all(isinstance(m["value"], str) for m in out)
    assert server._sanitize_report_metrics(None) == []


def test_negative_burn_reads_as_profit():
    fin = {"burn_known": True, "burn_value": -2180, "burn": "-$2.2K"}
    m = server._burn_metric(fin, "No comparison yet", "usd")
    assert m["label"] == "Profit this month" and m["value"].startswith("$") and "-" not in m["value"]
    fin = {"burn_known": True, "burn_value": 900, "burn": "$900"}
    assert server._burn_metric(fin, "x", "usd") == {"label": "Net burn this month", "value": "$900", "change": "x"}
    assert server._burn_metric({"burn_known": False}, "x", "usd")["value"] == "Add data"


def _ws():
    return {
        "workspace_id": "w1", "name": "Acme", "people": {"people": []},
        "tasks": {"items": []}, "manual_reports": [],
    }


def test_runway_without_burn_is_short_and_explained():
    fin = {"runway_months": None, "runway_no_burn": True, "currency": "usd",
           "mrr_known": True, "mrr": "$5.2K", "burn_known": True, "burn_value": -10, "burn": "-$10"}
    cards = server._computed_report_cards(_ws(), fin, [], [], 0, prior=None)
    money = cards[0]["metrics"]
    runway = next(m for m in money if m["label"] == "Cash runway")
    assert runway["value"] == "No burn" and runway["change"] == "Cash is growing"


def test_create_and_edit_report_clean_input(monkeypatch):
    db = AsyncMongoMockClient()["t"]
    monkeypatch.setattr(server, "db", db)

    async def run():
        await db.workspaces.insert_one(_ws())

        async def fake_log(*a, **k):
            return None
        monkeypatch.setattr(server, "log_activity", fake_log)
        principal = {"workspace_id": "w1", "user_id": "u1", "pack": "owner"}
        res = await server.create_report(server.ReportInput(
            title="  Sales  ", period="", metrics=[{"label": "Deals", "value": 3}, {"x": 1}],
        ), principal)
        rep = res["report"]
        assert rep["title"] == "Sales" and rep["period"] == "" and rep["metrics"] == [{"label": "Deals", "value": "3"}]
        res = await server.edit_report(rep["id"], server.ReportInput(
            title="Sales", period="Oct", metrics=[{"label": f"m{i}", "value": i} for i in range(9)],
        ), principal)
        assert len(res["report"]["metrics"]) == 6 and res["report"]["period"] == "Oct"

    asyncio.run(run())


def test_ceo_pack_is_saved_for_the_next_visit(monkeypatch):
    db = AsyncMongoMockClient()["t"]
    monkeypatch.setattr(server, "db", db)

    async def fake_generate(ws_id):
        return {"content": "# Acme: this week\nQuiet week.", "data_as_of": "2026-10-17"}
    monkeypatch.setattr(server, "_generate_weekly_pack_content", fake_generate)

    async def run():
        await db.workspaces.insert_one(_ws())
        out = await server.weekly_pack({"workspace_id": "w1", "user_id": "u1", "pack": "owner"})
        assert out["content"].startswith("# Acme") and out["created_at"]
        saved = (await db.workspaces.find_one({"workspace_id": "w1"}))["last_weekly_pack"]
        assert saved["content"] == out["content"] and saved["created_by"] == "u1"

    asyncio.run(run())
