"""Sales & Accounting/Finance department migration + access filtering."""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_sales_finance_fold")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402
import department_migrate as migrate  # noqa: E402
import department_access as access  # noqa: E402
import departments_catalog as catalog  # noqa: E402

CEO = {
    "user_id": "u_ceo",
    "email": "ceo@acme.com",
    "name": "CEO",
    "workspace_id": "ws_fold",
    "role": "owner",
    "pack": "owner",
}

MEMBER = {
    "user_id": "u_member",
    "email": "alex@acme.com",
    "name": "Alex",
    "workspace_id": "ws_fold",
    "role": "member",
    "pack": "member",
}

OUTSIDER = {
    "user_id": "u_out",
    "email": "out@acme.com",
    "name": "Out",
    "workspace_id": "ws_fold",
    "role": "member",
    "pack": "member",
}


class UpdateResult:
    def __init__(self, modified_count):
        self.modified_count = modified_count


class FakeColl:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    async def find_one(self, query, projection=None):
        for r in self.rows:
            if self._match(r, query):
                return {k: v for k, v in r.items() if k != "_id"}
        return None

    def find(self, query, projection=None):
        matched = [dict(r) for r in self.rows if self._match(r, query)]
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=matched)
        cursor.sort = MagicMock(return_value=cursor)
        cursor.limit = MagicMock(return_value=cursor)
        return cursor

    async def insert_one(self, doc):
        self.rows.append(dict(doc))
        return MagicMock(inserted_id="x")

    async def insert_many(self, docs):
        for d in docs:
            self.rows.append(dict(d))

    async def update_one(self, query, update):
        for r in self.rows:
            if self._match(r, query):
                r.update(update.get("$set") or {})
                return UpdateResult(1)
        return UpdateResult(0)

    async def update_many(self, query, update):
        n = 0
        for r in self.rows:
            if self._match(r, query):
                r.update(update.get("$set") or {})
                n += 1
        return UpdateResult(n)

    async def delete_one(self, query):
        before = len(self.rows)
        self.rows = [r for r in self.rows if not self._match(r, query)]
        return MagicMock(deleted_count=before - len(self.rows))

    async def delete_many(self, query):
        before = len(self.rows)
        self.rows = [r for r in self.rows if not self._match(r, query)]
        return MagicMock(deleted_count=before - len(self.rows))

    async def count_documents(self, query):
        return sum(1 for r in self.rows if self._match(r, query))

    def aggregate(self, pipeline):
        # Minimal $match + $group for deal metrics
        match = pipeline[0].get("$match") or {}
        matched = [r for r in self.rows if self._match(r, match)]
        groups = {}
        for r in matched:
            key = r.get("stage")
            g = groups.setdefault(key, {"_id": key, "count": 0, "value": 0.0})
            g["count"] += 1
            g["value"] += float(r.get("value") or 0)
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=list(groups.values()))
        return cursor

    @staticmethod
    def _match(row, query):
        for k, v in query.items():
            if k == "$or":
                if not any(FakeColl._match(row, clause) for clause in v):
                    return False
                continue
            if isinstance(v, dict) and any(op.startswith("$") for op in v):
                if "$exists" in v:
                    exists = k in row and row.get(k) is not None if False else (k in row)
                    # Mongo $exists: true matches key present (including null); we treat None user_id specially via $ne
                    if bool(v["$exists"]) != (k in row):
                        return False
                if "$ne" in v:
                    if row.get(k) == v["$ne"]:
                        return False
                if "$in" in v:
                    if row.get(k) not in v["$in"]:
                        return False
                continue
            if row.get(k) != v:
                return False
        return True


@pytest.mark.asyncio
async def test_migration_idempotent_creates_enrolls_backfills():
    depts = FakeColl()
    members = FakeColl()
    memberships = FakeColl([
        {"workspace_id": "ws_fold", "user_id": "u_ceo", "status": "active"},
        {"workspace_id": "ws_fold", "user_id": "u_member", "status": "active"},
        {"workspace_id": "ws_fold", "user_id": None, "email": "pending@acme.com", "status": "invited"},
    ])
    deals = FakeColl([
        {"id": "d1", "workspace_id": "ws_fold", "stage": "lead", "value": 100},
        {"id": "d2", "workspace_id": "ws_fold", "stage": "won", "value": 200, "department_id": None},
    ])
    fins = FakeColl([
        {"id": "f1", "workspace_id": "ws_fold", "type": "expense", "amount": 10, "month": "2026-01"},
        {"id": "f2", "workspace_id": "ws_fold", "type": "revenue", "amount": 20, "month": "2026-01"},
    ])
    workspaces = FakeColl([{"workspace_id": "ws_fold"}])
    mock_db = MagicMock()
    mock_db.departments = depts
    mock_db.department_members = members
    mock_db.memberships = memberships
    mock_db.deals = deals
    mock_db.financial_entries = fins
    mock_db.workspaces = workspaces

    before_deals = len(deals.rows)
    before_fins = len(fins.rows)

    s1 = await migrate.migrate_workspace_sales_finance(mock_db, "ws_fold")
    assert s1["sales_created"] is True
    assert s1["finance_created"] is True
    assert s1["members_enrolled_sales"] == 2
    assert s1["members_enrolled_finance"] == 2
    assert s1["deals_backfilled"] == 2
    assert s1["finance_entries_backfilled"] == 2
    assert len(deals.rows) == before_deals
    assert len(fins.rows) == before_fins
    assert all(d.get("department_id") for d in deals.rows)
    assert all(e.get("department_id") for e in fins.rows)

    sales_types = [d for d in depts.rows if d["type"] == "sales"]
    finance_types = [d for d in depts.rows if d["type"] == "accounting_finance"]
    assert len(sales_types) == 1
    assert len(finance_types) == 1
    sales_id = sales_types[0]["department_id"]
    finance_id = finance_types[0]["department_id"]
    assert all(d["department_id"] == sales_id for d in deals.rows)
    assert all(e["department_id"] == finance_id for e in fins.rows)

    s2 = await migrate.migrate_workspace_sales_finance(mock_db, "ws_fold")
    assert s2["sales_created"] is False
    assert s2["finance_created"] is False
    assert s2["members_enrolled_sales"] == 0
    assert s2["members_enrolled_finance"] == 0
    assert s2["deals_backfilled"] == 0
    assert s2["finance_entries_backfilled"] == 0
    assert len(depts.rows) == 2
    assert len(members.rows) == 4  # 2 users × 2 depts


def test_apply_department_filter():
    base = {"workspace_id": "ws"}
    assert access.apply_department_filter(base, None) == base
    assert access.apply_department_filter(base, [])["department_id"] == {"$in": []}
    assert access.apply_department_filter(base, ["d1"])["department_id"] == {"$in": ["d1"]}


@pytest.fixture
def fold_api():
    depts = FakeColl([
        {
            "department_id": "dept_sales",
            "workspace_id": "ws_fold",
            "type": "sales",
            "name": "Sales",
            "enabled": True,
        },
        {
            "department_id": "dept_fin",
            "workspace_id": "ws_fold",
            "type": "accounting_finance",
            "name": "Accounting & Finance",
            "enabled": True,
        },
    ])
    dept_members = FakeColl([
        {"department_id": "dept_sales", "user_id": "u_member", "role": "member"},
        {"department_id": "dept_fin", "user_id": "u_member", "role": "member"},
    ])
    deals = FakeColl([
        {
            "id": "deal_a", "workspace_id": "ws_fold", "department_id": "dept_sales",
            "name": "Alpha", "company": "", "value": 50, "stage": "lead",
            "owner_name": "A", "created_by_user_id": "u_ceo", "created_by_name": "CEO",
            "close_date": "", "created_at": "2026-01-02T00:00:00+00:00",
            "updated_at": "2026-01-02T00:00:00+00:00",
        },
        {
            "id": "deal_b", "workspace_id": "ws_fold", "department_id": "dept_other",
            "name": "Beta", "company": "", "value": 80, "stage": "lead",
            "owner_name": "B", "created_by_user_id": "u_ceo", "created_by_name": "CEO",
            "close_date": "", "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        },
    ])
    fins = FakeColl([
        {
            "id": "fe_1", "workspace_id": "ws_fold", "department_id": "dept_fin",
            "type": "expense", "category": "Payroll", "amount": 100, "month": "2026-08",
            "recurring": True, "note": "", "source": "manual",
        },
        {
            "id": "fe_2", "workspace_id": "ws_fold", "department_id": "dept_other",
            "type": "expense", "category": "Other", "amount": 999, "month": "2026-08",
            "recurring": False, "note": "", "source": "manual",
        },
    ])
    mock_db = MagicMock()
    mock_db.departments = depts
    mock_db.department_members = dept_members
    mock_db.deals = deals
    mock_db.financial_entries = fins
    mock_db.users = FakeColl([])
    mock_db.product_events = FakeColl([])
    mock_db.workspaces.find_one = AsyncMock(return_value={
        "workspace_id": "ws_fold",
        "financial_settings": {"cash": 10000, "currency": "usd"},
    })

    async def as_ceo():
        return CEO

    async def as_member():
        return MEMBER

    async def as_outsider():
        return OUTSIDER

    server.app.dependency_overrides[server.get_principal] = as_ceo
    with patch.object(server, "db", mock_db), \
         patch.object(server, "BILLING_ENFORCED", False), \
         patch.object(server, "can_section_write", AsyncMock(return_value=True)):
        client = TestClient(server.app)
        yield client, mock_db, as_ceo, as_member, as_outsider
    server.app.dependency_overrides.clear()


def test_ceo_sees_all_deals_and_finance(fold_api):
    client, mock_db, as_ceo, as_member, as_outsider = fold_api
    r = client.get("/api/deals")
    assert r.status_code == 200
    ids = {d["id"] for d in r.json()["deals"]}
    assert ids == {"deal_a", "deal_b"}

    r2 = client.get("/api/financials")
    assert r2.status_code == 200
    eids = {e["id"] for e in r2.json()["entries"]}
    assert eids == {"fe_1", "fe_2"}


def test_member_sees_only_enrolled_department_records(fold_api):
    client, mock_db, as_ceo, as_member, as_outsider = fold_api
    server.app.dependency_overrides[server.get_principal] = as_member
    r = client.get("/api/deals")
    assert r.status_code == 200
    ids = {d["id"] for d in r.json()["deals"]}
    assert ids == {"deal_a"}

    r2 = client.get("/api/financials")
    assert r2.status_code == 200
    eids = {e["id"] for e in r2.json()["entries"]}
    assert eids == {"fe_1"}


def test_member_without_dept_membership_sees_nothing(fold_api):
    client, mock_db, as_ceo, as_member, as_outsider = fold_api
    server.app.dependency_overrides[server.get_principal] = as_outsider
    r = client.get("/api/deals")
    assert r.status_code == 200
    assert r.json()["deals"] == []
    assert r.json()["metrics"]["open_count"] == 0

    r2 = client.get("/api/financials")
    assert r2.status_code == 200
    assert r2.json()["entries"] == []
    assert r2.json()["has_data"] is False


def test_create_deal_sets_sales_department_id(fold_api):
    client, mock_db, as_ceo, as_member, as_outsider = fold_api
    r = client.get("/api/deals")
    assert r.status_code == 200
    assert any(d.get("department_id") == "dept_sales" for d in r.json()["deals"])


@pytest.mark.asyncio
async def test_create_deal_auto_department_id_unit():
    """Unit-level: sales_department_id helper returns Sales dept id."""
    depts = FakeColl([{
        "department_id": "dept_sales",
        "workspace_id": "ws_fold",
        "type": "sales",
        "enabled": True,
        "name": "Sales",
    }])
    mock_db = MagicMock()
    mock_db.departments = depts
    assert await migrate.sales_department_id(mock_db, "ws_fold") == "dept_sales"


@pytest.mark.asyncio
async def test_ensure_enabled_department_handles_insert_race():
    """Concurrent first-enable must not 500 on unique (workspace_id, type)."""
    from pymongo.errors import DuplicateKeyError

    calls = {"insert": 0}
    existing_after_race = {
        "department_id": "dept_fin_raced",
        "workspace_id": "ws_race",
        "type": catalog.TYPE_ACCOUNTING_FINANCE,
        "name": "Accounting & Finance",
        "enabled": True,
    }

    class RaceColl:
        async def find_one(self, query, projection=None):
            # First call: nothing; after failed insert: the raced row.
            if calls["insert"] == 0:
                return None
            return dict(existing_after_race)

        async def insert_one(self, doc):
            calls["insert"] += 1
            raise DuplicateKeyError("E11000 duplicate key")

        async def update_one(self, query, update):
            return MagicMock(modified_count=1)

    mock_db = MagicMock()
    mock_db.departments = RaceColl()
    dept, created = await migrate.ensure_enabled_department(
        mock_db, "ws_race", catalog.TYPE_ACCOUNTING_FINANCE,
    )
    assert created is False
    assert dept["department_id"] == "dept_fin_raced"
    assert await migrate.finance_department_id(mock_db, "ws_race") == "dept_fin_raced"


def test_placeholder_types_exclude_sales_finance():
    assert catalog.TYPE_SALES not in catalog.PLACEHOLDER_SHELL_TYPES
    assert catalog.TYPE_ACCOUNTING_FINANCE not in catalog.PLACEHOLDER_SHELL_TYPES
