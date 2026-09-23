"""Unit tests for Manage Access section helpers and can_section_write grants."""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DB_NAME", "test_database")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

import access_sections as sec_access


def test_normalize_section_grants_filters_and_dedupes():
    assert sec_access.normalize_section_grants(["tasks", "bogus", "Tasks", "decisions", ""]) == [
        "tasks",
        "decisions",
    ]
    assert sec_access.normalize_section_grants(None) == []
    assert sec_access.normalize_section_grants({"tasks": True}) == []


def test_sections_for_perms_maps_pack_perms():
    assert sec_access.sections_for_perms({"finance:write", "read"}) == ["financials"]
    assert "tasks" in sec_access.sections_for_perms({"tasks:assign", "decisions:act"})
    assert "decisions" in sec_access.sections_for_perms({"tasks:assign", "decisions:act"})
    assert sec_access.sections_for_perms({"read", "tasks:move"}) == []


def test_normalize_section_access_keeps_known_sections():
    raw = {
        "tasks": ["Engineering", "engineering", ""],
        "unknown": ["Sales"],
        "sales": "not-a-list",
    }
    out = sec_access.normalize_section_access(raw)
    assert out == {"tasks": ["Engineering"]}


@pytest.mark.asyncio
async def test_can_section_write_honors_member_grants():
    import server

    principal = {
        "user_id": "u_member",
        "workspace_id": "ws_1",
        "pack": "member",
    }
    membership = {
        "user_id": "u_member",
        "workspace_id": "ws_1",
        "status": "active",
        "department": "Engineering",
        "section_grants": ["decisions"],
    }

    with patch.object(server, "_membership_for", new=AsyncMock(return_value=membership)) as mem_mock:
        with patch.object(server, "get_ws", new=AsyncMock(return_value={"section_access": {}})) as ws_mock:
            assert await server.can_section_write(principal, "decisions", "decisions:act") is True
            assert await server.can_section_write(principal, "tasks", "tasks:assign") is False
            # Preloaded objects skip both fetchers entirely.
            assert await server.can_section_write(
                principal, "decisions", "decisions:act",
                membership=membership, workspace={"section_access": {}},
            ) is True
            assert mem_mock.await_count == 2  # only the two calls without preload
            assert ws_mock.await_count == 1  # only the tasks miss that needs legacy dept check


@pytest.mark.asyncio
async def test_auth_me_section_loop_fetches_ws_once_not_per_section():
    """granted_sections must not scale Mongo round-trips with MANAGEABLE_SECTIONS."""
    import server
    import access_sections as sec_access

    user = {
        "user_id": "u1",
        "email": "a@b.co",
        "name": "Ada",
        "age_confirmed": True,
        "active_workspace_id": "ws_1",
    }
    membership = {
        "user_id": "u1",
        "workspace_id": "ws_1",
        "role": "member",
        "pack": "member",
        "status": "active",
        "department": "Engineering",
        "section_grants": ["tasks"],
    }
    ws = {"workspace_id": "ws_1", "section_access": {}}

    mock_db = MagicMock()
    mock_db.memberships.find_one = AsyncMock(return_value=membership)

    with patch.object(server, "db", mock_db), \
         patch.object(server, "get_ws", new=AsyncMock(return_value=ws)) as ws_mock, \
         patch.object(server, "_membership_for", new=AsyncMock(return_value=membership)) as mem_mock, \
         patch.object(server.dept_access, "department_names_by_user_id", new=AsyncMock(return_value={})), \
         patch.object(server.dept_access, "attach_real_departments", new=lambda payload, _names: payload):
        out = await server._user_session_payload(user)
        assert "tasks" in out["granted_sections"]
        assert ws_mock.await_count == 1
        # Preloaded membership/workspace — loop must not call _membership_for per section.
        assert mem_mock.await_count == 0
        assert len(sec_access.MANAGEABLE_SECTIONS) >= 2
        assert ws_mock.await_count < len(sec_access.MANAGEABLE_SECTIONS)


@pytest.mark.asyncio
async def test_can_section_write_honors_legacy_department_grants():
    import server

    principal = {
        "user_id": "u_member",
        "workspace_id": "ws_1",
        "pack": "member",
    }
    membership = {
        "user_id": "u_member",
        "workspace_id": "ws_1",
        "status": "active",
        "department": "Engineering",
        "section_grants": [],
    }
    ws = {"section_access": {"tasks": ["Engineering"]}}

    with patch.object(server, "_membership_for", new=AsyncMock(return_value=membership)):
        with patch.object(server, "get_ws", new=AsyncMock(return_value=ws)):
            assert await server.can_section_write(principal, "tasks", "tasks:assign") is True
            assert await server.can_section_write(principal, "decisions", "decisions:act") is False


@pytest.mark.asyncio
async def test_can_section_write_casefold_grants_and_departments():
    import server

    principal = {
        "user_id": "u_member",
        "workspace_id": "ws_1",
        "pack": "member",
    }
    membership = {
        "user_id": "u_member",
        "workspace_id": "ws_1",
        "status": "active",
        "department": "engineering",
        "section_grants": ["Decisions"],
    }
    ws = {"section_access": {"Tasks": ["ENGINEERING"]}}

    with patch.object(server, "_membership_for", new=AsyncMock(return_value=membership)):
        with patch.object(server, "get_ws", new=AsyncMock(return_value=ws)):
            assert await server.can_section_write(principal, "decisions", "decisions:act") is True
            assert await server.can_section_write(principal, "tasks", "tasks:assign") is True
            assert await server.can_section_write(principal, "TASKS", "tasks:assign") is True


@pytest.mark.asyncio
async def test_can_section_write_pack_perm_short_circuits():
    import server

    principal = {
        "user_id": "u_exec",
        "workspace_id": "ws_1",
        "pack": "exec",
    }
    with patch.object(server, "_membership_for", new=AsyncMock(return_value={})) as mem:
        assert await server.can_section_write(principal, "decisions", "decisions:act") is True
        mem.assert_not_called()
