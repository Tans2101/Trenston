"""Deal owner_user_id: migration, filter=me, lead/CEO reassignment."""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DB_NAME", "test_deal_owner")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402


class DealStore:
    def __init__(self):
        self.docs = {}

    async def insert_one(self, doc):
        self.docs[doc["id"]] = dict(doc)
        return MagicMock()

    async def find_one(self, filt, proj=None):
        d = self.docs.get(filt.get("id"))
        if not d:
            return None
        if filt.get("workspace_id") and d.get("workspace_id") != filt.get("workspace_id"):
            return None
        return dict(d)

    async def update_one(self, filt, update):
        d = self.docs.get(filt.get("id"))
        if not d:
            return MagicMock(matched_count=0)
        if filt.get("workspace_id") and d.get("workspace_id") != filt.get("workspace_id"):
            return MagicMock(matched_count=0)
        if "$set" in update:
            d.update(update["$set"])
        return MagicMock(matched_count=1)

    def find(self, filt, proj=None):
        rows = []
        for d in self.docs.values():
            ok = True
            for k, v in filt.items():
                if k in ("updated_at",):
                    continue
                if isinstance(v, dict):
                    # ignore cursor operators for these tests
                    continue
                if d.get(k) != v:
                    ok = False
                    break
            if ok and (not filt.get("workspace_id") or d.get("workspace_id") == filt.get("workspace_id")):
                # apply simple owner_user_id equality if present
                if "owner_user_id" in filt and d.get("owner_user_id") != filt["owner_user_id"]:
                    continue
                rows.append(dict(d))
        rows.sort(key=lambda r: (r.get("updated_at") or "", r.get("id") or ""), reverse=True)

        class Cursor:
            def __init__(self, items):
                self._items = items

            def sort(self, *_a, **_k):
                return self

            def limit(self, n):
                self._items = self._items[:n]
                return self

            async def to_list(self, n):
                return self._items[:n]

        # Re-filter with owner when present (exact)
        if "owner_user_id" in filt:
            rows = [r for r in rows if r.get("owner_user_id") == filt["owner_user_id"]]
        return Cursor(rows)


def _users_find_factory(users_by_id):
    def find(query, projection=None):
        ids = []
        if isinstance(query.get("user_id"), dict) and "$in" in query["user_id"]:
            ids = query["user_id"]["$in"]
        elif query.get("user_id"):
            ids = [query["user_id"]]
        rows = [users_by_id[i] for i in ids if i in users_by_id]

        class C:
            async def to_list(self, n):
                return rows[:n]

        return C()

    return find


@pytest.fixture
def owner_api():
    # Every test in this file reuses the same workspace_id/user_id/department,
    # so GET /api/deals's simple_cache entry from one test would otherwise leak
    # into the next (each gets its own fresh DealStore, but the cache key is
    # identical) — clear it so each test starts from a fresh fetch.
    server.simple_cache.clear()
    deals = DealStore()
    members = [
        {"department_id": "dept_sales", "user_id": "u_lead", "role": "lead"},
        {"department_id": "dept_sales", "user_id": "u_rep", "role": "member"},
        {"department_id": "dept_sales", "user_id": "u_rep2", "role": "member"},
    ]
    users_by_id = {
        "u_lead": {"user_id": "u_lead", "name": "Sam Lead", "email": "lead@ex.com"},
        "u_rep": {"user_id": "u_rep", "name": "Riley Rep", "email": "rep@ex.com"},
        "u_rep2": {"user_id": "u_rep2", "name": "Riley Rep", "email": "rep2@ex.com"},
        "u_ceo": {"user_id": "u_ceo", "name": "Casey CEO", "email": "ceo@ex.com"},
    }

    mock_db = MagicMock()
    mock_db.deals = deals
    mock_db.activities = MagicMock()
    mock_db.activities.insert_one = AsyncMock(return_value=None)
    mock_db.workspaces = MagicMock()
    mock_db.workspaces.find_one = AsyncMock(return_value={
        "workspace_id": "ws1",
        "financial_settings": {"currency": "usd"},
    })
    mock_db.memberships = MagicMock()
    mock_db.memberships.find_one = AsyncMock(return_value={
        "user_id": "u_lead", "workspace_id": "ws1", "status": "active",
        "pack": "owner", "role": "owner", "section_grants": {},
    })
    mock_db.departments = MagicMock()
    mock_db.departments.find_one = AsyncMock(return_value={
        "department_id": "dept_sales",
        "workspace_id": "ws1",
        "type": "sales",
        "name": "Sales",
        "enabled": True,
    })
    mock_db.department_members = MagicMock()

    async def member_find_one(query, projection=None):
        for m in members:
            if all(m.get(k) == v for k, v in query.items()):
                return dict(m)
        return None

    mock_db.department_members.find_one = AsyncMock(side_effect=member_find_one)
    mock_db.department_members.find = MagicMock(return_value=MagicMock(
        to_list=AsyncMock(return_value=list(members)),
    ))
    mock_db.users = MagicMock()
    mock_db.users.find = MagicMock(side_effect=_users_find_factory(users_by_id))
    mock_db.users.find_one = AsyncMock(side_effect=lambda q, p=None: users_by_id.get(q.get("user_id")))
    mock_db.financial_entries = MagicMock()
    mock_db.financial_entries.find_one = AsyncMock(return_value=None)
    mock_db.financial_entries.insert_one = AsyncMock(return_value=None)

    principal = {
        "user_id": "u_lead",
        "name": "Sam Lead",
        "email": "lead@ex.com",
        "workspace_id": "ws1",
        "pack": "owner",
        "role": "owner",
    }

    async def as_principal():
        return principal

    server.app.dependency_overrides[server.get_principal] = as_principal
    with patch.object(server, "db", mock_db), \
         patch.object(server, "log_activity", new_callable=AsyncMock, return_value=None), \
         patch.object(server, "can_section_write", new_callable=AsyncMock, return_value=True), \
         patch.object(server, "_deal_metrics_for_workspace", new_callable=AsyncMock, return_value={
             "open_value": 0, "won_value": 0, "open_count": 0, "by_stage": [],
         }), \
         patch.object(server, "_product_event", new_callable=AsyncMock, return_value=None), \
         patch.object(server, "BILLING_ENFORCED", False):
        client = TestClient(server.app)
        yield client, deals, principal, members, users_by_id, mock_db
    server.app.dependency_overrides.clear()


def test_migrate_confident_name_match(owner_api):
    client, deals, *_ = owner_api
    deals.docs["deal_legacy"] = {
        "id": "deal_legacy",
        "workspace_id": "ws1",
        "department_id": "dept_sales",
        "name": "Legacy",
        "company": "Co",
        "value": 1000,
        "stage": "lead",
        "owner_name": "Sam Lead",
        "owner_user_id": None,
        "updated_at": "2026-09-01T00:00:00+00:00",
        "created_at": "2026-09-01T00:00:00+00:00",
    }
    r = client.get("/api/deals")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["can_reassign_owner"] is True
    assert any(o["user_id"] == "u_rep" for o in body["sales_owners"])
    migrated = next(d for d in body["deals"] if d["id"] == "deal_legacy")
    assert migrated["owner_user_id"] == "u_lead"
    assert deals.docs["deal_legacy"]["owner_user_id"] == "u_lead"


def test_migrate_ambiguous_name_left_alone(owner_api):
    client, deals, *_ = owner_api
    deals.docs["deal_amb"] = {
        "id": "deal_amb",
        "workspace_id": "ws1",
        "department_id": "dept_sales",
        "name": "Ambiguous",
        "company": "Co",
        "value": 500,
        "stage": "lead",
        "owner_name": "Riley Rep",  # two members share this name
        "owner_user_id": None,
        "updated_at": "2026-09-01T00:00:00+00:00",
        "created_at": "2026-09-01T00:00:00+00:00",
    }
    r = client.get("/api/deals")
    assert r.status_code == 200
    row = next(d for d in r.json()["deals"] if d["id"] == "deal_amb")
    assert row.get("owner_user_id") in (None, "")
    assert deals.docs["deal_amb"].get("owner_user_id") in (None, "")


def test_filter_owner_user_id_me(owner_api):
    client, deals, principal, *_ = owner_api
    deals.docs["mine"] = {
        "id": "mine", "workspace_id": "ws1", "department_id": "dept_sales",
        "name": "Mine", "company": "A", "value": 1, "stage": "lead",
        "owner_user_id": "u_lead", "owner_name": "Sam Lead",
        "updated_at": "2026-09-10T00:00:00+00:00", "created_at": "2026-09-01T00:00:00+00:00",
    }
    deals.docs["theirs"] = {
        "id": "theirs", "workspace_id": "ws1", "department_id": "dept_sales",
        "name": "Theirs", "company": "B", "value": 2, "stage": "lead",
        "owner_user_id": "u_rep", "owner_name": "Riley Rep",
        "updated_at": "2026-09-10T00:00:00+00:00", "created_at": "2026-09-01T00:00:00+00:00",
    }
    r = client.get("/api/deals", params={"owner_user_id": "me"})
    assert r.status_code == 200, r.text
    ids = {d["id"] for d in r.json()["deals"]}
    assert ids == {"mine"}


def test_non_lead_cannot_reassign(owner_api):
    client, deals, principal, members, users_by_id, mock_db = owner_api
    principal["user_id"] = "u_rep"
    principal["name"] = "Riley Rep"
    principal["email"] = "rep@ex.com"
    principal["pack"] = "sales"
    principal["role"] = "member"
    mock_db.memberships.find_one = AsyncMock(return_value={
        "user_id": "u_rep", "workspace_id": "ws1", "status": "active",
        "pack": "sales", "role": "member", "section_grants": {"sales": True},
    })
    deals.docs["d1"] = {
        "id": "d1", "workspace_id": "ws1", "department_id": "dept_sales",
        "name": "Owned", "company": "A", "value": 10, "stage": "lead",
        "owner_user_id": "u_rep", "owner_name": "Riley Rep",
        "close_date": "", "next_step": "", "next_step_date": "",
        "updated_at": "2026-09-01T00:00:00+00:00", "created_at": "2026-09-01T00:00:00+00:00",
    }
    r = client.patch("/api/deals/d1", json={
        "name": "Owned", "company": "A", "value": 10, "stage": "lead",
        "owner_name": "Sam Lead", "owner_user_id": "u_lead", "close_date": "",
    })
    assert r.status_code == 403, r.text
    assert deals.docs["d1"]["owner_user_id"] == "u_rep"


def test_lead_can_reassign(owner_api):
    client, deals, *_ = owner_api
    deals.docs["d1"] = {
        "id": "d1", "workspace_id": "ws1", "department_id": "dept_sales",
        "name": "Owned", "company": "A", "value": 10, "stage": "lead",
        "owner_user_id": "u_rep", "owner_name": "Riley Rep",
        "close_date": "", "next_step": "", "next_step_date": "",
        "updated_at": "2026-09-01T00:00:00+00:00", "created_at": "2026-09-01T00:00:00+00:00",
    }
    r = client.patch("/api/deals/d1", json={
        "name": "Owned", "company": "A", "value": 10, "stage": "qualified",
        "owner_name": "Sam Lead", "owner_user_id": "u_lead", "close_date": "",
    })
    assert r.status_code == 200, r.text
    assert r.json()["deal"]["owner_user_id"] == "u_lead"
    assert deals.docs["d1"]["owner_user_id"] == "u_lead"
