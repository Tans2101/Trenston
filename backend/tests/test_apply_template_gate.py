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
