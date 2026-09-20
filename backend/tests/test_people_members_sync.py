"""People ↔ Team & Access sync."""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_people_members_sync")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import server  # noqa: E402
from mongo_mocks import attach_users_in_find  # noqa: E402

MOCK_PRINCIPAL = {
    "user_id": "u_owner",
    "email": "ceo@acme.com",
    "name": "CEO",
    "workspace_id": "ws_test",
    "role": "owner",
    "pack": "owner",
}


def _ws(people=None):
    return {
        "workspace_id": "ws_test",
        "name": "Acme",
        "plan": "pro",
        "people": people or {"people": []},
        "employees": 0,
        "section_access": {},
    }


def _empty_cursor():
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[])
    return cursor


@pytest.mark.asyncio
async def test_ensure_person_creates_and_links_by_email():
    ws = _ws()

    async def reload(_wid):
        return ws

    async def persist(_q, update):
        ws["people"] = update["$set"]["people"]
        ws["employees"] = update["$set"]["employees"]

    membership = {
        "membership_id": "mem_alex",
        "workspace_id": "ws_test",
        "email": "alex@acme.com",
        "user_id": None,
        "department": "Engineering",
        "pack": "member",
        "status": "invited",
    }
    mock_db = MagicMock()
    mock_db.workspaces.update_one = AsyncMock(side_effect=persist)
    mock_db.users.find_one = AsyncMock(return_value=None)

    with patch.object(server, "get_ws", new=AsyncMock(side_effect=reload)), \
         patch.object(server, "db", mock_db):
        person = await server.ensure_person_for_membership("ws_test", membership, name="Alex Rivera")
        assert person["name"] == "Alex Rivera"
        assert person["email"] == "alex@acme.com"
        assert person["membership_id"] == "mem_alex"
        assert len(ws["people"]["people"]) == 1
        assert "trust_score" not in person

        again = await server.ensure_person_for_membership("ws_test", membership, name="Alex Rivera")
        assert again["id"] == person["id"]
        assert len(ws["people"]["people"]) == 1


@pytest.mark.asyncio
async def test_ensure_person_links_existing_roster_by_email():
    ws = _ws({
        "people": [{
            "id": "p_existing",
            "name": "Alex",
            "role": "Engineer",
            "department": "Eng",
            "email": "alex@acme.com",
            "tenure": "New",
        }],
    })

    async def persist(_q, update):
        ws["people"] = update["$set"]["people"]

    membership = {
        "membership_id": "mem_alex",
        "workspace_id": "ws_test",
        "email": "alex@acme.com",
        "user_id": "u_alex",
        "department": "Engineering",
        "pack": "member",
        "status": "active",
    }
    mock_db = MagicMock()
    mock_db.workspaces.update_one = AsyncMock(side_effect=persist)
    mock_db.users.find_one = AsyncMock(return_value={"name": "Alex Rivera"})

    with patch.object(server, "get_ws", new=AsyncMock(return_value=ws)), \
         patch.object(server, "db", mock_db):
        person = await server.ensure_person_for_membership("ws_test", membership)
        assert person["id"] == "p_existing"
        assert person["membership_id"] == "mem_alex"
        assert person["user_id"] == "u_alex"
        assert len(ws["people"]["people"]) == 1


@pytest.fixture
def api_client():
    ws = _ws()
    inserted_mems = []
    server.simple_cache.clear()

    async def mock_principal():
        return MOCK_PRINCIPAL

    async def insert_mem(doc):
        inserted_mems.append(doc)

    async def update_ws(query, update):
        if "people" in (update.get("$set") or {}):
            ws["people"] = update["$set"]["people"]
            if "employees" in update["$set"]:
                ws["employees"] = update["$set"]["employees"]

    class MemFind:
        def __init__(self):
            self.items = []

        def __call__(self, *args, **kwargs):
            cursor = MagicMock()
            cursor.to_list = AsyncMock(return_value=list(self.items))
            return cursor

    mem_find_cursor = MemFind()
    empty_cursor = _empty_cursor()
    mock_db = MagicMock()
    mock_db.memberships.find_one = AsyncMock(return_value=None)
    mock_db.memberships.insert_one = AsyncMock(side_effect=insert_mem)
    mock_db.memberships.find = mem_find_cursor
    mock_db.memberships.delete_one = AsyncMock()
    mock_db.memberships.update_one = AsyncMock()
    mock_db.users.find_one = AsyncMock(return_value=None)
    attach_users_in_find(mock_db.users)
    mock_db.workspaces.update_one = AsyncMock(side_effect=update_ws)
    mock_db.workspaces.find_one = AsyncMock(return_value=ws)
    mock_db.departments.find = MagicMock(return_value=empty_cursor)
    mock_db.departments.find_one = AsyncMock(return_value=None)
    mock_db.department_members.find = MagicMock(return_value=empty_cursor)
    for coll in (
        "production_work_orders", "legal_matters", "maintenance_tickets",
        "hr_onboarding_instances", "hr_offboarding_instances", "deals",
        "hr_employees", "procurement_requests",
    ):
        getattr(mock_db, coll).find = MagicMock(return_value=_empty_cursor())

    server.app.dependency_overrides[server.get_principal] = mock_principal

    with patch.object(server, "db", mock_db), \
         patch.object(server, "get_ws", new=AsyncMock(side_effect=lambda wid: ws)), \
         patch.object(server, "can_section_write", new=AsyncMock(return_value=True)), \
         patch.object(server, "log_activity", new=AsyncMock()), \
         patch.object(server, "_enforce_seat_available", new=AsyncMock()), \
         patch.object(server, "send_invite_email", new=AsyncMock(return_value={"sent": True})), \
         patch.object(server, "BILLING_ENFORCED", False):
        client = TestClient(server.app)
        yield client, ws, inserted_mems, mock_db

    server.app.dependency_overrides.clear()
    server.simple_cache.clear()


def test_invite_member_creates_people_row(api_client):
    client, ws, inserted_mems, mock_db = api_client
    r = client.post("/api/members/invite", json={
        "email": "alex@acme.com",
        "pack": "member",
        "department": "Engineering",
        "name": "Alex",
    })
    assert r.status_code == 200, r.text
    assert inserted_mems and inserted_mems[0]["email"] == "alex@acme.com"
    assert any(p.get("email") == "alex@acme.com" for p in ws["people"]["people"])
    alex = next(p for p in ws["people"]["people"] if p.get("email") == "alex@acme.com")
    assert alex["name"] == "Alex"
    assert alex["membership_id"] == inserted_mems[0]["membership_id"]
    assert "trust_score" not in alex


def test_add_person_with_invite_to_access(api_client):
    client, ws, inserted_mems, _ = api_client
    r = client.post("/api/people", json={
        "name": "Alex",
        "role": "Engineer",
        "department": "Engineering",
        "invite_to_access": True,
        "email": "alex@acme.com",
        "pack": "member",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["person"]["name"] == "Alex"
    assert body["person"]["membership_id"]
    assert body["person"]["has_access"] is True
    assert body["email_sent"] is True
    assert inserted_mems[0]["email"] == "alex@acme.com"


def test_delete_person_blocked_when_has_access(api_client):
    client, ws, _, mock_db = api_client
    ws["people"] = {
        "people": [{
            "id": "p_alex",
            "name": "Alex",
            "role": "",
            "department": "General",
            "membership_id": "mem_alex",
            "tenure": "New",
        }],
    }
    mock_db.memberships.find_one = AsyncMock(return_value={"membership_id": "mem_alex", "status": "active"})
    r = client.delete("/api/people/p_alex")
    assert r.status_code == 400
    assert "Team & Access" in r.json()["detail"]


def test_delete_person_allowed_after_access_revoked_stale_link(api_client):
    """Membership gone but People row still has membership_id — delete must succeed."""
    client, ws, _, mock_db = api_client
    ws["people"] = {
        "people": [{
            "id": "p_alex",
            "name": "Alex",
            "role": "",
            "department": "General",
            "membership_id": "mem_alex",
            "tenure": "New",
        }],
    }
    mock_db.memberships.find_one = AsyncMock(return_value=None)
    r = client.delete("/api/people/p_alex")
    assert r.status_code == 200, r.text
    assert ws["people"]["people"] == []


@pytest.mark.asyncio
async def test_remove_member_unlinks_and_invalidates_people_cache():
    ws = _ws({
        "people": [{
            "id": "p_alex",
            "name": "Alex",
            "membership_id": "mem_alex",
            "email": "alex@acme.com",
            "tenure": "New",
        }],
    })
    membership = {
        "membership_id": "mem_alex",
        "workspace_id": "ws_test",
        "user_id": "u_alex",
        "email": "alex@acme.com",
        "status": "active",
        "pack": "member",
    }
    mock_db = MagicMock()
    mock_db.memberships.find_one = AsyncMock(return_value=membership)
    mock_db.memberships.delete_one = AsyncMock()
    mock_db.workspaces.update_one = AsyncMock()

    async def persist(_q, update):
        if "people" in (update.get("$set") or {}):
            ws["people"] = update["$set"]["people"]

    mock_db.workspaces.update_one = AsyncMock(side_effect=persist)

    with patch.object(server, "db", mock_db), \
         patch.object(server, "get_ws", new=AsyncMock(return_value=ws)), \
         patch.object(server, "_release_seat_reservation", new=AsyncMock()), \
         patch.object(server, "invalidate_workspace_list_cache") as inv:
        out = await server.remove_member("mem_alex", MOCK_PRINCIPAL)
    assert out == {"ok": True}
    assert "membership_id" not in ws["people"]["people"][0]
    inv.assert_called_with("ws_test", "people")


def test_people_get_clears_stale_membership_id(api_client):
    client, ws, _, mock_db = api_client
    ws["people"] = {
        "people": [{
            "id": "p_alex",
            "name": "Alex",
            "membership_id": "mem_gone",
            "email": "alex@acme.com",
            "tenure": "New",
            "user_id": "u_alex",
        }],
    }
    # No active memberships
    mock_db.memberships.find = MagicMock(return_value=_empty_cursor())
    r = client.get("/api/people")
    assert r.status_code == 200, r.text
    body = r.json()
    person = body["people"][0]
    assert person["has_access"] is False
    assert "membership_id" not in person or not person.get("membership_id")
    # Persisted cleanup
    assert "membership_id" not in ws["people"]["people"][0]


@pytest.mark.asyncio
async def test_department_names_by_user_id_maps_memberships():
    import department_access as da

    depts_cursor = MagicMock()
    depts_cursor.to_list = AsyncMock(return_value=[
        {"department_id": "d1", "name": "Sales", "type": "sales"},
        {"department_id": "d2", "name": "Production", "type": "production"},
    ])
    mem_cursor = MagicMock()
    mem_cursor.to_list = AsyncMock(return_value=[
        {"department_id": "d1", "user_id": "u_alex"},
        {"department_id": "d2", "user_id": "u_alex"},
        {"department_id": "d1", "user_id": "u_sam"},
    ])
    mock_db = MagicMock()
    mock_db.departments.find = MagicMock(return_value=depts_cursor)
    mock_db.department_members.find = MagicMock(return_value=mem_cursor)
    out = await da.department_names_by_user_id(mock_db, "ws_test")
    assert out["u_alex"] == ["Production", "Sales"]
    assert out["u_sam"] == ["Sales"]


def test_invite_ignores_legacy_department_payload(api_client):
    client, _, inserted_mems, _ = api_client
    r = client.post("/api/members/invite", json={
        "email": "alex@acme.com",
        "pack": "member",
        "department": "Engineering",
        "name": "Alex",
    })
    assert r.status_code == 200, r.text
    assert "department" not in inserted_mems[0]


def test_people_get_overlays_real_departments_not_stale_label(api_client):
    client, ws, _, mock_db = api_client
    ws["people"] = {
        "people": [
            {
                "id": "p_alex",
                "name": "Alex",
                "role": "AE",
                "department": "General",
                "user_id": "u_alex",
                "tenure": "New",
            },
            {
                "id": "p_pat",
                "name": "Pat",
                "role": "Ops",
                "department": "Operations",
                "tenure": "New",
            },
        ],
    }
    depts_cursor = MagicMock()
    depts_cursor.to_list = AsyncMock(return_value=[
        {"department_id": "d_sales", "name": "Sales", "type": "sales", "enabled": True},
    ])
    mem_cursor = MagicMock()
    mem_cursor.to_list = AsyncMock(return_value=[
        {"department_id": "d_sales", "user_id": "u_alex"},
    ])
    mock_db.departments.find = MagicMock(return_value=depts_cursor)
    mock_db.department_members.find = MagicMock(return_value=mem_cursor)

    r = client.get("/api/people")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "departments" not in body
    assert body["unassigned_count"] == 1
    alex = next(p for p in body["people"] if p["id"] == "p_alex")
    pat = next(p for p in body["people"] if p["id"] == "p_pat")
    assert alex["departments"] == ["Sales"]
    assert alex["department"] == "Sales"
    assert alex["open_item_count"] == 0
    assert pat["departments"] == []
    assert pat["department"] == "Unassigned"
    assert "open_item_count" not in pat  # no user_id → no workload fields


def test_edit_person_does_not_write_legacy_department(api_client):
    client, ws, _, mock_db = api_client
    ws["people"] = {
        "people": [{
            "id": "p_alex",
            "name": "Alex",
            "role": "Engineer",
            "department": "Engineering",
            "membership_id": "mem_alex",
            "tenure": "New",
        }],
    }
    r = client.patch("/api/people/p_alex", json={
        "name": "Alex",
        "role": "Senior Engineer",
        "department": "Sales",
    })
    assert r.status_code == 200, r.text
    stored = next(p for p in ws["people"]["people"] if p["id"] == "p_alex")
    assert stored["role"] == "Senior Engineer"
    assert stored.get("department") == "Engineering"
    assert mock_db.memberships.update_one.await_count == 0


@pytest.mark.asyncio
async def test_users_by_ids_one_query_omits_missing():
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[{"user_id": "u1", "name": "A"}])
    mock_db = MagicMock()
    mock_db.users.find = MagicMock(return_value=cursor)
    with patch.object(server, "db", mock_db):
        out = await server._users_by_ids(["u1", "u_missing"], {"_id": 0, "user_id": 1, "name": 1})
    assert out == {"u1": {"user_id": "u1", "name": "A"}}
    mock_db.users.find.assert_called_once()
    query = mock_db.users.find.call_args[0][0]
    assert query["user_id"]["$in"] == ["u1", "u_missing"]


def test_list_members_batches_user_lookups_and_missing_user(api_client):
    client, ws, _, mock_db = api_client
    mock_db.memberships.find.items = [
        {
            "membership_id": "m1", "email": "a@x.com", "role": "member", "pack": "member",
            "status": "active", "user_id": "u1", "section_grants": [],
        },
        {
            "membership_id": "m2", "email": "b@x.com", "role": "member", "pack": "member",
            "status": "active", "user_id": "u2", "section_grants": [],
        },
        {
            "membership_id": "m3", "email": "invited@x.com", "role": "member", "pack": "member",
            "status": "invited", "user_id": None, "section_grants": [],
        },
        {
            "membership_id": "m4", "email": "ghost@x.com", "role": "member", "pack": "member",
            "status": "active", "user_id": "u_ghost", "section_grants": [],
        },
    ]

    async def user_one(query, projection=None):
        uid = query.get("user_id")
        if uid == "u1":
            return {"name": "Ada", "picture": None}
        if uid == "u2":
            return {"name": "Bob", "picture": "pic.png"}
        return None

    mock_db.users.find_one = AsyncMock(side_effect=user_one)
    find_calls = {"n": 0}
    inner = attach_users_in_find(mock_db.users).find

    def counting_find(query, projection=None):
        find_calls["n"] += 1
        return inner(query, projection)

    mock_db.users.find = counting_find

    r = client.get("/api/members")
    assert r.status_code == 200, r.text
    assert find_calls["n"] == 1
    by_id = {m["membership_id"]: m for m in r.json()["members"]}
    assert by_id["m1"]["name"] == "Ada"
    assert by_id["m2"]["name"] == "Bob"
    assert by_id["m2"]["picture"] == "pic.png"
    assert by_id["m3"]["name"] is None
    assert by_id["m4"]["name"] is None
