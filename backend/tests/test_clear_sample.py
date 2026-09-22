"""Unit coverage for clearing Northwind sample data after opt-in."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import server
from seed_data import build_workspace


@pytest.mark.asyncio
async def test_clear_sample_rejects_non_sample_workspace():
    ws = build_workspace("ws1", "Acme", "u1", empty=True)
    assert ws["template"] == "empty"
    with patch.object(server, "get_ws", AsyncMock(return_value=ws)):
        with pytest.raises(HTTPException) as exc:
            await server._clear_sample_workspace("ws1", {"user_id": "u1", "workspace_id": "ws1"})
        assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_clear_sample_wipes_seed_keeps_profile_and_billing_fields():
    sample = build_workspace("ws1", "Northwind Robotics", "u1", empty=False)
    sample["plan"] = "growth"
    sample["industry"] = "Industrial Robotics"
    sample["mission"] = "Keep robots rolling."
    sample["company_setup_done"] = True
    sample["join_code"] = "KEEPME"

    ws_update = AsyncMock()
    fin_delete = AsyncMock()
    act_delete = AsyncMock()
    mock_db = MagicMock()
    mock_db.workspaces.update_one = ws_update
    mock_db.financial_entries.delete_many = fin_delete
    mock_db.activities.delete_many = act_delete

    with (
        patch.object(server, "get_ws", AsyncMock(return_value=sample)),
        patch.object(server, "db", mock_db),
        patch.object(server, "invalidate_financials_cache") as inv_fin,
        patch.object(server, "invalidate_workspace_list_cache") as inv_people,
    ):
        await server._clear_sample_workspace("ws1", {"user_id": "u1", "workspace_id": "ws1"})

    ws_update.assert_awaited_once()
    args, _kwargs = ws_update.await_args
    assert args[0] == {"workspace_id": "ws1"}
    update = args[1]["$set"]
    assert update["template"] == "empty"
    assert update["onboarding_done"] is True
    assert update["company_setup_done"] is True
    assert update["industry"] == "Industrial Robotics"
    assert update["mission"] == "Keep robots rolling."
    assert update["name"] == "Northwind Robotics"
    assert update["briefing"]["what_changed"] == []
    assert update["decisions"] == []
    assert update["people"]["people"] == []
    assert update["manual_reports"] == []
    assert "plan" not in update  # preserved via _PRESERVE_WS_FIELDS
    assert "join_code" not in update
    fin_delete.assert_awaited_once_with({"workspace_id": "ws1"})
    act_delete.assert_awaited_once_with({"workspace_id": "ws1"})
    inv_fin.assert_called_once_with("ws1")
    inv_people.assert_called_once_with("ws1", "people")
