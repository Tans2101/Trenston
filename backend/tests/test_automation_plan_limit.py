"""After a downgrade, only the plan's number of automation rules keep running."""
import asyncio
import os
from unittest.mock import AsyncMock, patch

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_automation_plan_limit")

from mongomock_motor import AsyncMongoMockClient

import server


def test_rules_capped_to_plan_limit_oldest_first():
    db = AsyncMongoMockClient()["auto"]
    loop = asyncio.new_event_loop()
    for i in range(5):
        loop.run_until_complete(db.automation_rules.insert_one({
            "workspace_id": "ws1", "enabled": True, "id": f"r{i}", "created_at": f"2026-10-0{i + 1}",
        }))
    seen = {}

    async def fake_run_rules(_db, _ws, *, rules, **kw):
        seen["ids"] = [r["id"] for r in rules]
        return {}

    with patch.object(server, "db", db), \
         patch.object(server, "_automation_rule_limit", AsyncMock(return_value=2)), \
         patch.object(server, "_automation_inputs", AsyncMock(return_value=({"name": "A"}, {}, [], []))), \
         patch.object(server.helm_automations, "run_rules", fake_run_rules):
        loop.run_until_complete(server.run_workspace_automations("ws1", anomalies=False))
    assert seen["ids"] == ["r0", "r1"]
