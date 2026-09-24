"""Unit coverage for clearing Northwind sample data after opt-in."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import server
from seed_data import build_workspace, sample_financial_entries
from tests.mongo_mocks import FakeCollection


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
    mock_db.financial_entries = FakeCollection()
    mock_db.financial_entries.delete_many = fin_delete
    mock_db.user_google_tokens = FakeCollection()
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
    fin_delete.assert_awaited_once_with({"workspace_id": "ws1", "created_by": "seed"})
    # No real data ever arrived, so all sample-era activity is cleared.
    act_delete.assert_awaited_once_with({"workspace_id": "ws1"})
    inv_fin.assert_called_once_with("ws1")
    inv_people.assert_called_once_with("ws1", "people")


def _sample_ws():
    ws = build_workspace("ws1", "Northwind Robotics", "u1", empty=False)
    ws["onboarding_done"] = True
    return ws


def _qb_entry(**extra):
    return {
        "id": "fe_qb1", "workspace_id": "ws1", "type": "revenue", "amount": 500, "month": "2026-09",
        "source": "quickbooks_sync", "qb_txn_id": "qb_invoice_1", "created_by": "u1",
        "created_at": "2026-09-10T00:00:00+00:00", **extra,
    }


def _fake_db(entries, activities=()):
    mock_db = MagicMock()
    mock_db.workspaces.update_one = AsyncMock()
    mock_db.financial_entries = FakeCollection(entries)
    mock_db.activities = FakeCollection(activities)
    mock_db.user_google_tokens = FakeCollection()
    return mock_db


@pytest.mark.asyncio
async def test_clear_sample_deletes_only_seed_entries_and_pre_real_activity():
    seed = sample_financial_entries("ws1")
    manual = {
        "id": "fe_m1", "workspace_id": "ws1", "type": "expense", "amount": 10, "month": "2026-09",
        "source": "manual", "created_by": "u1", "created_at": "2026-09-12T00:00:00+00:00",
    }
    acts = [
        {"activity_id": "a_old", "workspace_id": "ws1", "created_at": "2026-09-01T00:00:00+00:00"},
        {"activity_id": "a_new", "workspace_id": "ws1", "created_at": "2026-09-11T00:00:00+00:00"},
    ]
    mock_db = _fake_db(seed + [_qb_entry(), manual], acts)
    with (
        patch.object(server, "get_ws", AsyncMock(return_value=_sample_ws())),
        patch.object(server, "db", mock_db),
        patch.object(server, "invalidate_financials_cache"),
        patch.object(server, "invalidate_workspace_list_cache"),
    ):
        await server._clear_sample_workspace("ws1", {"user_id": "u1", "workspace_id": "ws1"})

    remaining = {e["id"] for e in mock_db.financial_entries.docs}
    assert remaining == {"fe_qb1", "fe_m1"}
    # First real entry (the QuickBooks row) arrived 2026-09-10: older activity goes, newer stays.
    assert [a["activity_id"] for a in mock_db.activities.docs] == ["a_new"]


@pytest.mark.asyncio
async def test_apply_sample_rejected_when_synced_entries_exist():
    mock_db = _fake_db(sample_financial_entries("ws1") + [_qb_entry()])
    with (
        patch.object(server, "get_ws", AsyncMock(return_value=_sample_ws())),
        patch.object(server, "db", mock_db),
    ):
        for confirm in (False, True):
            with pytest.raises(HTTPException) as exc:
                await server.apply_template(
                    server.TemplateInput(template="sample", confirm_destructive=confirm),
                    {"user_id": "u1", "workspace_id": "ws1", "pack": "owner"},
                )
            assert exc.value.status_code == 400
            assert exc.value.detail == "Disconnect accounting integrations before loading sample data"
    assert any(e["id"] == "fe_qb1" for e in mock_db.financial_entries.docs)


@pytest.mark.asyncio
async def test_apply_sample_replaces_seed_and_manual_keeps_other_sources():
    old_seed = sample_financial_entries("ws1")[:2]
    manual = {"id": "fe_m1", "workspace_id": "ws1", "source": "manual", "created_by": "u1"}
    csv_row = {"id": "fe_csv", "workspace_id": "ws1", "source": "csv_import", "created_by": "u1"}
    mock_db = _fake_db(old_seed + [manual, csv_row])
    with (
        patch.object(server, "get_ws", AsyncMock(return_value=_sample_ws())),
        patch.object(server, "db", mock_db),
        patch.object(server.dept_migrate, "migrate_workspace_sales_finance", AsyncMock()),
        patch.object(server.dept_migrate, "finance_department_id", AsyncMock(return_value=None)),
        patch.object(server, "invalidate_financials_cache"),
    ):
        await server.apply_template(
            server.TemplateInput(template="sample", confirm_destructive=True),
            {"user_id": "u1", "workspace_id": "ws1", "pack": "owner"},
        )
    ids = {e["id"] for e in mock_db.financial_entries.docs}
    assert "fe_m1" not in ids
    assert "fe_csv" in ids
    assert not ({e["id"] for e in old_seed} & ids)
    assert sum(1 for e in mock_db.financial_entries.docs if e.get("created_by") == "seed") == 36
