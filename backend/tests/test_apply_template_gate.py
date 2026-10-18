"""Unit tests for sample apply-template destructive gate."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import server
from seed_data import build_workspace


@pytest.mark.asyncio
async def test_sample_apply_allowed_during_onboarding():
    ws = build_workspace("ws1", "Acme", "u1", empty=True)
    assert ws["onboarding_done"] is False
    ws_update = AsyncMock()
    fin_delete = AsyncMock()
    fin_insert = AsyncMock()
    mock_db = MagicMock()
    mock_db.workspaces.update_one = ws_update
    mock_db.financial_entries.delete_many = fin_delete
    mock_db.financial_entries.insert_many = fin_insert
    mock_db.financial_entries.count_documents = AsyncMock(return_value=0)
    mock_db.financial_entries.find_one = AsyncMock(return_value=None)

    with (
        patch.object(server, "get_ws", AsyncMock(return_value=ws)),
        patch.object(server, "db", mock_db),
        patch.object(server.dept_migrate, "migrate_workspace_sales_finance", AsyncMock()),
        patch.object(server.dept_migrate, "finance_department_id", AsyncMock(return_value=None)),
        patch.object(server, "invalidate_financials_cache"),
    ):
        out = await server.apply_template(
            server.TemplateInput(template="sample"),
            {"user_id": "u1", "workspace_id": "ws1", "pack": "owner"},
        )
    assert out == {"ok": True}
    fin_delete.assert_awaited_once()
    fin_insert.assert_awaited_once()


@pytest.mark.asyncio
async def test_sample_apply_blocked_on_live_workspace_without_confirm():
    ws = build_workspace("ws1", "Live Co", "u1", empty=False)
    ws["onboarding_done"] = True
    ws["template"] = "sample"
    mock_db = MagicMock()
    mock_db.financial_entries.count_documents = AsyncMock(return_value=5)
    mock_db.financial_entries.find_one = AsyncMock(return_value=None)
    mock_db.financial_entries.delete_many = AsyncMock()

    with (
        patch.object(server, "get_ws", AsyncMock(return_value=ws)),
        patch.object(server, "db", mock_db),
    ):
        with pytest.raises(HTTPException) as exc:
            await server.apply_template(
                server.TemplateInput(template="sample", confirm_destructive=False),
                {"user_id": "u1", "workspace_id": "ws1", "pack": "owner"},
            )
    assert exc.value.status_code == 400
    assert "confirm_destructive" in str(exc.value.detail)
    mock_db.financial_entries.delete_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_sample_apply_confirm_destructive_allows_wipe():
    ws = build_workspace("ws1", "Live Co", "u1", empty=False)
    ws["onboarding_done"] = True
    ws["template"] = "sample"
    ws_update = AsyncMock()
    fin_delete = AsyncMock()
    fin_insert = AsyncMock()
    mock_db = MagicMock()
    mock_db.workspaces.update_one = ws_update
    mock_db.financial_entries.delete_many = fin_delete
    mock_db.financial_entries.insert_many = fin_insert
    mock_db.financial_entries.count_documents = AsyncMock(return_value=5)
    mock_db.financial_entries.find_one = AsyncMock(return_value=None)

    with (
        patch.object(server, "get_ws", AsyncMock(return_value=ws)),
        patch.object(server, "db", mock_db),
        patch.object(server.dept_migrate, "migrate_workspace_sales_finance", AsyncMock()),
        patch.object(server.dept_migrate, "finance_department_id", AsyncMock(return_value=None)),
        patch.object(server, "invalidate_financials_cache"),
    ):
        out = await server.apply_template(
            server.TemplateInput(template="sample", confirm_destructive=True),
            {"user_id": "u1", "workspace_id": "ws1", "pack": "owner"},
        )
    assert out == {"ok": True}
    fin_delete.assert_awaited_once()


# --- Pre-setup demo -----------------------------------------------------------


def _demo_db(fin_count=0):
    mock_db = MagicMock()
    mock_db.workspaces.update_one = AsyncMock()
    mock_db.financial_entries.delete_many = AsyncMock()
    mock_db.financial_entries.insert_many = AsyncMock()
    mock_db.financial_entries.count_documents = AsyncMock(return_value=fin_count)
    mock_db.financial_entries.find_one = AsyncMock(return_value=None)
    mock_db.activities.delete_many = AsyncMock()
    return mock_db


@pytest.mark.asyncio
async def test_demo_apply_keeps_company_setup_pending():
    ws = build_workspace("ws1", "Acme", "u1", empty=True)
    mock_db = _demo_db()
    with (
        patch.object(server, "get_ws", AsyncMock(return_value=ws)),
        patch.object(server, "db", mock_db),
        patch.object(server.dept_migrate, "migrate_workspace_sales_finance", AsyncMock()),
        patch.object(server.dept_migrate, "finance_department_id", AsyncMock(return_value=None)),
        patch.object(server, "invalidate_financials_cache"),
    ):
        out = await server.apply_template(
            server.TemplateInput(template="demo"),
            {"user_id": "u1", "workspace_id": "ws1", "pack": "owner"},
        )
    assert out == {"ok": True}
    update = mock_db.workspaces.update_one.await_args.args[1]["$set"]
    assert update["demo_mode"] is True
    assert update["demo_seen"] is True
    assert update["company_setup_done"] is False
    assert update["onboarding_done"] is True
    assert update["template"] == "sample"
    mock_db.financial_entries.insert_many.assert_awaited_once()


@pytest.mark.asyncio
async def test_demo_apply_rejected_after_company_setup():
    ws = build_workspace("ws1", "Live Co", "u1", empty=True)
    ws["company_setup_done"] = True
    mock_db = _demo_db()
    with (
        patch.object(server, "get_ws", AsyncMock(return_value=ws)),
        patch.object(server, "db", mock_db),
    ):
        with pytest.raises(HTTPException) as exc:
            await server.apply_template(
                server.TemplateInput(template="demo"),
                {"user_id": "u1", "workspace_id": "ws1", "pack": "owner"},
            )
    assert exc.value.status_code == 400
    mock_db.workspaces.update_one.assert_not_awaited()
    mock_db.financial_entries.insert_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_regular_sample_apply_is_not_demo_mode():
    ws = build_workspace("ws1", "Acme", "u1", empty=True)
    mock_db = _demo_db()
    with (
        patch.object(server, "get_ws", AsyncMock(return_value=ws)),
        patch.object(server, "db", mock_db),
        patch.object(server.dept_migrate, "migrate_workspace_sales_finance", AsyncMock()),
        patch.object(server.dept_migrate, "finance_department_id", AsyncMock(return_value=None)),
        patch.object(server, "invalidate_financials_cache"),
    ):
        await server.apply_template(
            server.TemplateInput(template="sample"),
            {"user_id": "u1", "workspace_id": "ws1", "pack": "owner"},
        )
    update = mock_db.workspaces.update_one.await_args.args[1]["$set"]
    assert update["demo_mode"] is False
    assert update["company_setup_done"] is True


@pytest.mark.asyncio
async def test_clean_template_marks_empty_and_finishes_onboarding():
    ws = build_workspace("ws1", "Acme", "u1", empty=True)
    mock_db = _demo_db()
    with (
        patch.object(server, "get_ws", AsyncMock(return_value=ws)),
        patch.object(server, "db", mock_db),
    ):
        out = await server.apply_template(
            server.TemplateInput(template="clean"),
            {"user_id": "u1", "workspace_id": "ws1", "pack": "owner"},
        )
    assert out == {"ok": True}
    update = mock_db.workspaces.update_one.await_args.args[1]["$set"]
    assert update["onboarding_done"] is True
    assert update["template"] == "empty"
    assert update["demo_mode"] is False


@pytest.mark.asyncio
async def test_leaving_demo_returns_to_company_setup_with_clean_profile():
    ws = build_workspace("ws1", "Acme", "u1", empty=False)
    ws["demo_mode"] = True
    ws["demo_seen"] = True
    ws["company_setup_done"] = False
    mock_db = _demo_db()
    with (
        patch.object(server, "get_ws", AsyncMock(return_value=ws)),
        patch.object(server, "db", mock_db),
        patch.object(server, "invalidate_financials_cache"),
        patch.object(server, "invalidate_workspace_list_cache"),
    ):
        await server.clear_sample_data({"user_id": "u1", "workspace_id": "ws1", "pack": "owner"})
    update = mock_db.workspaces.update_one.await_args.args[1]["$set"]
    assert update["demo_mode"] is False
    assert update["company_setup_done"] is False
    assert update["onboarding_done"] is False
    assert update["template"] == "empty"
    # Northwind's profile must not leak into the real company setup form.
    assert update["industry"] == ""
    assert update["stage"] == ""
    assert update["employees"] == 0
    assert update["has_team"] is None
    # Demo-era manual rows go too, and activity is wiped completely.
    delete_filter = mock_db.financial_entries.delete_many.await_args.args[0]
    assert {"source": "manual"} in delete_filter["$or"]
    assert mock_db.activities.delete_many.await_args.args[0] == {"workspace_id": "ws1"}


@pytest.mark.asyncio
async def test_clear_sample_after_setup_still_skips_company_setup():
    ws = build_workspace("ws1", "Acme", "u1", empty=False)
    ws["demo_mode"] = False
    mock_db = _demo_db()
    mock_db.user_google_tokens.find = MagicMock()
    mock_db.user_google_tokens.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(return_value=[])
    mock_db.financial_entries.find = MagicMock()
    mock_db.financial_entries.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(return_value=[])
    with (
        patch.object(server, "get_ws", AsyncMock(return_value=ws)),
        patch.object(server, "db", mock_db),
        patch.object(server, "invalidate_financials_cache"),
        patch.object(server, "invalidate_workspace_list_cache"),
    ):
        await server.clear_sample_data({"user_id": "u1", "workspace_id": "ws1", "pack": "owner"})
    update = mock_db.workspaces.update_one.await_args.args[1]["$set"]
    assert update["company_setup_done"] is True
    assert update["onboarding_done"] is True
    assert update["industry"] == ws["industry"]
    assert mock_db.financial_entries.delete_many.await_args.args[0] == {
        "workspace_id": "ws1", "created_by": "seed",
    }


@pytest.mark.asyncio
async def test_patch_company_inside_demo_does_not_finish_setup():
    ws = build_workspace("ws1", "Acme", "u1", empty=False)
    ws["demo_mode"] = True
    ws["company_setup_done"] = False
    mock_db = _demo_db()
    principal = {"user_id": "u1", "workspace_id": "ws1", "pack": "owner"}
    with (
        patch.object(server, "get_ws", AsyncMock(return_value=ws)),
        patch.object(server, "db", mock_db),
        patch.object(server.dept_access, "is_workspace_ceo", return_value=True),
    ):
        await server.update_company(
            server.CompanySetupInput(timezone="Asia/Manila", company_setup_done=True),
            principal,
        )
    update = mock_db.workspaces.update_one.await_args.args[1]["$set"]
    assert "company_setup_done" not in update
