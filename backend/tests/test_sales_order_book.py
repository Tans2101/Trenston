"""Sales order book + monthly target API tests."""
import os
import re
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_sales_order_book")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import server  # noqa: E402
import departments_catalog as catalog  # noqa: E402

CEO = {
    "user_id": "u_ceo",
    "email": "ceo@acme.com",
    "name": "CEO",
    "workspace_id": "ws_test",
    "role": "owner",
    "pack": "owner",
}

LEAD = {
    "user_id": "u_lead",
    "email": "lead@acme.com",
    "name": "Lead",
    "workspace_id": "ws_test",
    "role": "member",
    "pack": "member",
}

MEMBER = {
    "user_id": "u_mem",
    "email": "mem@acme.com",
    "name": "Mem",
    "workspace_id": "ws_test",
    "role": "member",
    "pack": "member",
}

OUTSIDER = {
    "user_id": "u_out",
    "email": "out@acme.com",
    "name": "Out",
    "workspace_id": "ws_test",
    "role": "member",
    "pack": "member",
}

SALES_DEPT = {
    "department_id": "dept_sales",
    "workspace_id": "ws_test",
    "type": "sales",
    "name": "Sales",
    "enabled": True,
}


class DocStore:
    def __init__(self):
        self.rows = []

    async def find_one(self, query, projection=None):
        for r in self.rows:
            if _match_query(r, query):
                return {k: v for k, v in r.items() if k != "_id"}
        return None

    def find(self, query, projection=None):
        matched = [dict(r) for r in self.rows if _match_query(r, query or {})]
        state = {"sort": None}

        class C:
            def sort(self, field, direction=1):
                state["sort"] = (field, direction)
                return self

            async def to_list(self, n):
                items = list(matched)
                if state["sort"]:
                    field, direction = state["sort"]
                    items.sort(
                        key=lambda x: x.get(field) or "",
                        reverse=direction == -1,
                    )
                return items[:n]

        return C()

    async def insert_one(self, doc):
        self.rows.append(dict(doc))

    async def update_one(self, query, update):
        for r in self.rows:
            if _match_query(r, query):
                r.update(update.get("$set") or {})
                return MagicMock(matched_count=1)
        return MagicMock(matched_count=0)

    async def delete_one(self, query):
        before = len(self.rows)
        self.rows = [r for r in self.rows if not _match_query(r, query)]
        return MagicMock(deleted_count=before - len(self.rows))


def _match_query(doc: dict, query: dict) -> bool:
    if not query:
        return True
    for k, v in query.items():
        if k == "$or":
            if not any(_match_query(doc, clause) for clause in v):
                return False
            continue
        actual = doc.get(k)
        if isinstance(v, dict):
            if "$in" in v:
                if actual not in v["$in"]:
                    return False
            elif "$regex" in v:
                flags = re.IGNORECASE if "i" in str(v.get("$options") or "") else 0
                if not re.search(v["$regex"], str(actual or ""), flags):
                    return False
            else:
                return False
        elif actual != v:
            return False
    return True


@pytest.fixture
def sales_api():
    book = DocStore()
    targets = DocStore()
    depts = MagicMock()
    depts.find_one = AsyncMock(return_value=dict(SALES_DEPT))
    members = MagicMock()

    async def member_find_one(query, projection=None):
        uid = query.get("user_id")
        if uid == "u_mem":
            return {"department_id": "dept_sales", "user_id": "u_mem", "role": "member"}
        if uid == "u_lead":
            return {"department_id": "dept_sales", "user_id": "u_lead", "role": "lead"}
        if uid == "u_ceo":
            return None
        return None

    members.find_one = AsyncMock(side_effect=member_find_one)

    mock_db = MagicMock()
    mock_db.workspaces.find_one = AsyncMock(return_value={"timezone": "Asia/Manila"})
    mock_db.departments = depts
    mock_db.department_members = members
    mock_db.sales_order_book = book
    mock_db.sales_targets = targets

    async def as_ceo():
        return CEO

    async def as_member():
        return MEMBER

    async def as_lead():
        return LEAD

    async def as_outsider():
        return OUTSIDER

    server.app.dependency_overrides[server.get_principal] = as_member
    with patch.object(server, "db", mock_db), \
         patch.object(server, "BILLING_ENFORCED", False):
        client = TestClient(server.app)
        yield client, book, targets, as_ceo, as_member, as_lead, as_outsider, depts
    server.app.dependency_overrides.clear()


def test_sales_type_exists():
    assert catalog.TYPE_SALES == "sales"


def test_outsider_gets_403(sales_api):
    client, book, targets, as_ceo, as_member, as_lead, as_outsider, depts = sales_api
    server.app.dependency_overrides[server.get_principal] = as_outsider
    assert client.get("/api/sales/order-book").status_code == 403
    assert client.post("/api/sales/order-book", json={
        "buyer_name": "Acme", "country": "US", "product": "Widget",
        "price": 10, "quantity": 2,
    }).status_code == 403


def test_sales_disabled_404(sales_api):
    client, book, targets, as_ceo, as_member, as_lead, as_outsider, depts = sales_api
    depts.find_one = AsyncMock(return_value=None)
    r = client.get("/api/sales/order-book")
    assert r.status_code == 404
    assert "not enabled" in r.json()["detail"].lower()


def test_member_creates_and_lists_entry(sales_api):
    client, book, targets, as_ceo, as_member, as_lead, as_outsider, depts = sales_api
    r = client.post("/api/sales/order-book", json={
        "buyer_name": "Buyer Co",
        "country": "Germany",
        "product": "Widget",
        "price": 100,
        "quantity": 3,
        "status": "expected",
        "expected_close_month": "2026-09",
        "notes": "pipe",
    })
    assert r.status_code == 200, r.text
    entry = r.json()["entry"]
    assert entry["buyer_name"] == "Buyer Co"
    assert entry["country"] == "Germany"
    assert entry["product"] == "Widget"
    assert entry["price"] == 100.0
    assert entry["quantity"] == 3.0
    assert entry["total_value"] == 300.0
    assert entry["status"] == "expected"
    assert entry["expected_close_month"] == "2026-09"
    assert entry["created_by_user_id"] == "u_mem"
    assert entry["workspace_id"] == "ws_test"
    assert entry["department_id"] == "dept_sales"
    assert entry["id"].startswith("sob_")
    assert len(book.rows) == 1

    listed = client.get("/api/sales/order-book")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["my_user_id"] == "u_mem"
    assert body["is_lead"] is False
    assert body["is_ceo"] is False
    assert len(body["entries"]) == 1
    assert body["entries"][0]["id"] == entry["id"]
    assert body["summary"]["line_count"] == 1
    assert "target_vs_actual" in body
    assert body["target_vs_actual"]["target_entered"] is False
    assert set(body["statuses"]) == {"confirmed", "expected", "in_negotiation"}


def test_list_filters_status_and_country(sales_api):
    client, book, targets, as_ceo, as_member, as_lead, as_outsider, depts = sales_api
    client.post("/api/sales/order-book", json={
        "buyer_name": "A", "country": "US", "product": "P1",
        "price": 10, "quantity": 1, "status": "confirmed",
    })
    client.post("/api/sales/order-book", json={
        "buyer_name": "B", "country": "DE", "product": "P2",
        "price": 20, "quantity": 1, "status": "expected",
    })
    r = client.get("/api/sales/order-book", params={"status": "confirmed"})
    assert r.status_code == 200
    assert len(r.json()["entries"]) == 1
    assert r.json()["entries"][0]["buyer_name"] == "A"

    r2 = client.get("/api/sales/order-book", params={"country": "de"})
    assert r2.status_code == 200
    assert len(r2.json()["entries"]) == 1
    assert r2.json()["entries"][0]["buyer_name"] == "B"


def test_create_validation(sales_api):
    client, book, targets, as_ceo, as_member, as_lead, as_outsider, depts = sales_api
    assert client.post("/api/sales/order-book", json={
        "buyer_name": " ", "country": "US", "product": "P", "price": 1, "quantity": 1,
    }).status_code == 400
    assert client.post("/api/sales/order-book", json={
        "buyer_name": "A", "country": "US", "product": "P", "price": -1, "quantity": 1,
    }).status_code == 400
    assert client.post("/api/sales/order-book", json={
        "buyer_name": "A", "country": "US", "product": "P", "price": 1, "quantity": 0,
    }).status_code == 400
    assert client.post("/api/sales/order-book", json={
        "buyer_name": "A", "country": "US", "product": "P",
        "price": 1, "quantity": 1, "status": "won",
    }).status_code == 400


def test_member_deletes_own_entry(sales_api):
    client, book, targets, as_ceo, as_member, as_lead, as_outsider, depts = sales_api
    r = client.post("/api/sales/order-book", json={
        "buyer_name": "A", "country": "US", "product": "P", "price": 5, "quantity": 2,
    })
    eid = r.json()["entry"]["id"]
    deleted = client.delete(f"/api/sales/order-book/{eid}")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["ok"] is True
    assert book.rows == []


def test_member_cannot_delete_others_entry(sales_api):
    client, book, targets, as_ceo, as_member, as_lead, as_outsider, depts = sales_api
    book.rows.append({
        "id": "sob_other",
        "workspace_id": "ws_test",
        "department_id": "dept_sales",
        "created_by_user_id": "u_lead",
        "buyer_name": "X",
        "country": "US",
        "product": "P",
        "price": 1,
        "quantity": 1,
        "total_value": 1,
        "status": "expected",
        "expected_close_month": "",
        "notes": "",
        "created_at": "2026-09-01T00:00:00+00:00",
        "updated_at": "2026-09-01T00:00:00+00:00",
    })
    r = client.delete("/api/sales/order-book/sob_other")
    assert r.status_code == 403
    assert len(book.rows) == 1


def test_lead_can_delete_any_and_set_target(sales_api):
    client, book, targets, as_ceo, as_member, as_lead, as_outsider, depts = sales_api
    client.post("/api/sales/order-book", json={
        "buyer_name": "A", "country": "US", "product": "P",
        "price": 50, "quantity": 2, "status": "confirmed",
        "expected_close_month": "2026-09",
    })
    eid = book.rows[0]["id"]
    server.app.dependency_overrides[server.get_principal] = as_lead

    deleted = client.delete(f"/api/sales/order-book/{eid}")
    assert deleted.status_code == 200
    assert book.rows == []

    # recreate for target actual check
    client.post("/api/sales/order-book", json={
        "buyer_name": "A", "country": "US", "product": "P",
        "price": 50, "quantity": 2, "status": "confirmed",
        "expected_close_month": "2026-09",
    })
    put = client.put("/api/sales/targets", json={"month": "2026-09", "target": 500})
    assert put.status_code == 200, put.text
    assert put.json()["ok"] is True
    assert put.json()["target"]["month"] == "2026-09"
    assert put.json()["target"]["target"] == 500.0
    assert len(targets.rows) == 1

    # upsert same month
    put2 = client.put("/api/sales/targets", json={"month": "2026-09", "target": 750})
    assert put2.status_code == 200
    assert len(targets.rows) == 1
    assert targets.rows[0]["target"] == 750.0


def test_member_cannot_set_target(sales_api):
    client, book, targets, as_ceo, as_member, as_lead, as_outsider, depts = sales_api
    r = client.put("/api/sales/targets", json={"month": "2026-09", "target": 100})
    assert r.status_code == 403


def test_ceo_sets_target_and_list_shows_tvs(sales_api):
    client, book, targets, as_ceo, as_member, as_lead, as_outsider, depts = sales_api
    server.app.dependency_overrides[server.get_principal] = as_ceo
    # Force current-month attribution via expected_close_month matching helper month
    import sales_order_book as sob
    month = sob.current_month()
    client.post("/api/sales/order-book", json={
        "buyer_name": "A", "country": "US", "product": "P",
        "price": 100, "quantity": 1, "status": "confirmed",
        "expected_close_month": month,
    })
    put = client.put("/api/sales/targets", json={"month": month, "target": 400})
    assert put.status_code == 200, put.text

    listed = client.get("/api/sales/order-book")
    assert listed.status_code == 200
    body = listed.json()
    assert body["is_ceo"] is True
    assert body["is_lead"] is True
    tvs = body["target_vs_actual"]
    assert tvs["target_entered"] is True
    assert tvs["target"] == 400.0
    assert tvs["actual"] == 100.0
    assert tvs["gap"] == -300.0
    assert tvs["pct_of_target"] == 25.0


def test_delete_missing_404(sales_api):
    client, book, targets, as_ceo, as_member, as_lead, as_outsider, depts = sales_api
    r = client.delete("/api/sales/order-book/sob_missing")
    assert r.status_code == 404


def test_routes_registered_on_app():
    paths = {
        getattr(r, "path", None)
        for r in server.app.routes
        if getattr(r, "path", None)
    }
    assert "/api/sales/order-book" in paths
    assert "/api/sales/targets" in paths
