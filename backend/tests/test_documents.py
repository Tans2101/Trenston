"""Document upload + AI extraction for financial entries."""
import io
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_documents")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402

MOCK_PRINCIPAL = {
    "user_id": "test-user-docs",
    "email": "docs@example.com",
    "name": "Doc Tester",
    "workspace_id": "ws_doc_test",
    "role": "owner",
    "pack": "owner",
}

PDF_BYTES = b"%PDF-1.4 minimal test content"
OVERSIZED = b"x" * (15 * 1024 * 1024 + 1)


@pytest.fixture
def client():
    async def mock_principal():
        return MOCK_PRINCIPAL

    server.app.dependency_overrides[server.get_principal] = mock_principal
    mock_db = MagicMock()
    mock_db.documents = MagicMock()
    mock_db.documents.insert_one = AsyncMock(return_value=None)
    mock_db.documents.find_one = AsyncMock(return_value=None)
    mock_db.documents.update_one = AsyncMock(return_value=None)
    mock_db.documents.find_one_and_update = AsyncMock(return_value=None)
    mock_db.activities = MagicMock()
    mock_db.activities.insert_one = AsyncMock(return_value=None)
    mock_db.document_rate_events = MagicMock()
    mock_db.document_rate_events.count_documents = AsyncMock(return_value=0)
    mock_db.document_rate_events.insert_one = AsyncMock(return_value=None)
    mock_db.document_rate_buckets = MagicMock()
    mock_db.document_rate_buckets.find_one_and_update = AsyncMock(
        return_value={"_id": "ws_doc_test:upload", "count": 1},
    )
    mock_db.workspaces = MagicMock()
    # Default: room under the lifetime AI-extract cap (a test that wants the cap
    # already hit, e.g. test_free_lifetime_extract_quota_asks_to_upgrade, overrides
    # this to return None so acquire_lifetime_extract_slot() reports False).
    mock_db.workspaces.find_one_and_update = AsyncMock(return_value={
        "workspace_id": "ws_doc_test", "ai_extracts_lifetime_used": 1,
    })
    mock_db.workspaces.find_one = AsyncMock(return_value={
        "workspace_id": "ws_doc_test",
        "plan": "business",
        "subscription_status": "active",
        "financial_settings": {"currency": "usd"},
    })
    mock_db.memberships = MagicMock()
    mock_db.memberships.find_one = AsyncMock(return_value={
        "user_id": MOCK_PRINCIPAL["user_id"], "workspace_id": "ws_doc_test",
        "status": "active", "pack": "owner", "role": "owner", "section_grants": {},
    })

    with patch.object(server, "db", mock_db), patch.object(server.doc_storage, "r2_configured", return_value=True), patch.object(
        server.doc_storage, "upload_document", return_value="ws_doc_test/test-key.pdf"
    ), patch.object(server, "log_activity", new_callable=AsyncMock, return_value=None), patch.object(
        server, "can_section_write", new_callable=AsyncMock, return_value=True
    ), patch.object(
        server, "get_ws", new_callable=AsyncMock, return_value={
            "workspace_id": "ws_doc_test", "plan": "business", "subscription_status": "active",
            "billing_period_start": "2026-01-01T00:00:00+00:00",
        }
    ), patch.object(server, "BILLING_ENFORCED", False), patch.object(
        server.plan_usage, "increment_period_extract", new_callable=AsyncMock, return_value=None
    ), patch.object(
        server.plan_usage, "increment_lifetime_extract", new_callable=AsyncMock, return_value=None
    ):
        yield TestClient(server.app)
    server.app.dependency_overrides.clear()


def test_upload_valid_pdf(client):
    r = client.post(
        "/api/documents/upload",
        files={"file": ("invoice.pdf", io.BytesIO(PDF_BYTES), "application/pdf")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "uploaded"
    assert body["document_id"].startswith("doc_")


def test_upload_oversized_rejected(client):
    r = client.post(
        "/api/documents/upload",
        files={"file": ("huge.pdf", io.BytesIO(OVERSIZED), "application/pdf")},
    )
    assert r.status_code == 400
    assert "15MB" in r.json()["detail"]


def test_upload_wrong_content_type_rejected(client):
    r = client.post(
        "/api/documents/upload",
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert r.status_code == 400
    assert "not allowed" in r.json()["detail"].lower()


def test_extract_not_financial_returns_error_json(client):
    doc_id = "doc_test123"
    server.db.documents.find_one = AsyncMock(return_value={
        "id": doc_id,
        "workspace_id": MOCK_PRINCIPAL["workspace_id"],
        "storage_key": "ws_doc_test/key.pdf",
        "filename": "resume.pdf",
        "content_type": "application/pdf",
        "status": "uploaded",
    })

    with patch.object(server.doc_storage, "get_document_bytes", return_value=PDF_BYTES), patch.object(
        server.helm_llm, "anthropic_configured", return_value=True
    ), patch.object(
        server.helm_llm, "extract_financial_document", new_callable=AsyncMock, return_value={"error": "not_financial"}
    ):
        r = client.post(f"/api/documents/{doc_id}/extract")

    assert r.status_code == 200
    assert r.json() == {"error": "not_financial"}


def test_validate_currency_formatted_amount():
    import llm

    result = llm._validate_extracted_financial({
        "type": "expense",
        "amount": "$1,240.00",
        "month": "2024-06",
        "category": "G&A",
        "vendor": "Acme Corp",
        "confidence": "high",
    })
    assert result["amount"] == 1240.0
    assert result["type"] == "expense"
    assert result["confidence"] == "high"
    assert result["name"] == "Acme Corp"
    assert result["vendor"] == "Acme Corp"


def test_validate_invalid_type_coerces_to_expense_with_low_confidence():
    import llm

    result = llm._validate_extracted_financial({
        "type": "invoice",
        "amount": 100,
        "month": "2024-06",
        "category": "Subscriptions",
        "vendor": "Vendor",
        "confidence": "high",
    })
    assert result["type"] == "expense"
    assert result["confidence"] == "low"


def test_validate_prefers_extracted_name_over_vendor():
    import llm

    result = llm._validate_extracted_financial({
        "type": "expense",
        "amount": 79,
        "month": "2026-09",
        "category": "Cloud/Infra",
        "name": "MongoDB Database Subscription",
        "vendor": "MongoDB Inc",
        "confidence": "high",
    })
    assert result["name"] == "MongoDB Database Subscription"
    assert result["category"] == "Cloud/Infra"
    assert result["vendor"] == "MongoDB Inc"


def test_validate_garbage_amount_returns_unparseable_error():
    import llm

    result = llm._validate_extracted_financial({
        "type": "expense",
        "amount": "unknown",
        "month": "2024-06",
        "category": "G&A",
        "vendor": "Acme",
    })
    assert result == {"error": "unparseable_amount"}


def test_extract_unparseable_amount_returns_error_json(client):
    doc_id = "doc_test456"
    server.db.documents.find_one = AsyncMock(return_value={
        "id": doc_id,
        "workspace_id": MOCK_PRINCIPAL["workspace_id"],
        "storage_key": "ws_doc_test/key.pdf",
        "filename": "blurry.pdf",
        "content_type": "application/pdf",
        "status": "uploaded",
    })

    with patch.object(server.doc_storage, "get_document_bytes", return_value=PDF_BYTES), patch.object(
        server.helm_llm, "anthropic_configured", return_value=True
    ), patch.object(
        server.helm_llm, "extract_financial_document", new_callable=AsyncMock,
        return_value={"error": "unparseable_amount"},
    ):
        r = client.post(f"/api/documents/{doc_id}/extract")

    assert r.status_code == 200
    assert r.json() == {"error": "unparseable_amount"}


def test_extract_returns_cached_result_without_second_claude_call(client):
    doc_id = "doc_cached"
    doc = {
        "id": doc_id,
        "workspace_id": MOCK_PRINCIPAL["workspace_id"],
        "storage_key": "ws_doc_test/key.pdf",
        "filename": "invoice.pdf",
        "content_type": "application/pdf",
        "status": "uploaded",
        "extracted_data": None,
    }
    extracted_payload = {
        "type": "expense",
        "amount": 42.0,
        "month": "2024-06",
        "category": "G&A",
        "vendor": "Acme",
        "confidence": "high",
    }

    async def update_one(_filter, update):
        doc.update(update.get("$set", {}))

    server.db.documents.find_one = AsyncMock(return_value=doc)
    server.db.documents.update_one = AsyncMock(side_effect=update_one)

    with patch.object(server.doc_storage, "get_document_bytes", return_value=PDF_BYTES), patch.object(
        server.helm_llm, "anthropic_configured", return_value=True
    ), patch.object(
        server.helm_llm, "extract_financial_document", new_callable=AsyncMock, return_value=extracted_payload
    ) as extract_mock, patch.object(
        server.doc_rate_limit, "acquire_event_slot", new_callable=AsyncMock, return_value=True
    ):
        r1 = client.post(f"/api/documents/{doc_id}/extract")
        r2 = client.post(f"/api/documents/{doc_id}/extract")
        r3 = client.post(f"/api/documents/{doc_id}/extract?force=true")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 200
    assert r1.json() == extracted_payload
    assert r2.json() == extracted_payload
    assert extract_mock.await_count == 2  # initial extract + force re-extract only


def test_upload_rate_limit_returns_429(client):
    with patch.object(server.doc_rate_limit, "acquire_event_slot", new_callable=AsyncMock, return_value=False), patch.object(
        server, "log_activity", new_callable=AsyncMock
    ) as log_mock:
        r = client.post(
            "/api/documents/upload",
            files={"file": ("invoice.pdf", io.BytesIO(PDF_BYTES), "application/pdf")},
        )

    assert r.status_code == 429
    assert r.json()["detail"] == "Upload limit reached. Try again in a bit"
    log_mock.assert_awaited()
    assert log_mock.await_args.args[2] == "document.rate_limit"


def test_rate_limit_scoped_per_workspace():
    import asyncio
    import rate_limit

    events = []
    mock_coll = MagicMock()

    async def count_documents(query):
        return sum(
            1 for e in events
            if e["workspace_id"] == query["workspace_id"] and e["action"] == query["action"]
        )

    async def insert_one(doc):
        events.append(doc)

    mock_coll.count_documents = AsyncMock(side_effect=count_documents)
    mock_coll.insert_one = AsyncMock(side_effect=insert_one)
    mock_db = MagicMock()
    mock_db.document_rate_events = mock_coll

    limit = 2

    async def run():
        await rate_limit.record_event(mock_db, "ws_a", "upload")
        await rate_limit.record_event(mock_db, "ws_a", "upload")
        assert await rate_limit.is_over_limit(mock_db, "ws_a", "upload", limit)
        assert not await rate_limit.is_over_limit(mock_db, "ws_b", "upload", limit)

    asyncio.run(run())


def test_cleanup_deletes_old_uncommitted_documents():
    import asyncio
    from datetime import datetime, timezone, timedelta

    import document_cleanup

    old_uploaded = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    orphan = {
        "id": "doc_orphan_old",
        "workspace_id": "ws_doc_test",
        "storage_key": "ws_doc_test/orphan.pdf",
        "status": "uploaded",
        "linked_entry_id": None,
        "uploaded_at": old_uploaded,
    }
    stored = [orphan]

    mock_coll = MagicMock()

    async def find_to_list(*_args, **_kwargs):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=document_cleanup.DOC_ORPHAN_RETENTION_DAYS)).isoformat()
        return [
            d for d in stored
            if d["status"] in document_cleanup.ORPHAN_STATUSES
            and not d.get("linked_entry_id")
            and d["uploaded_at"] < cutoff
        ]

    async def delete_one(query):
        nonlocal stored
        before = len(stored)
        stored = [d for d in stored if d["id"] != query.get("id")]
        deleted = MagicMock()
        deleted.deleted_count = 1 if len(stored) < before else 0
        return deleted

    mock_coll.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(side_effect=find_to_list)))
    mock_coll.delete_one = AsyncMock(side_effect=delete_one)
    mock_db = MagicMock()
    mock_db.documents = mock_coll

    with patch.object(document_cleanup.doc_storage, "r2_configured", return_value=True), patch.object(
        document_cleanup.doc_storage, "delete_document", return_value=None
    ) as delete_mock:
        result = asyncio.run(document_cleanup.cleanup_orphaned_documents(mock_db))

    assert result["deleted_count"] == 1
    assert result["deleted_ids"] == ["doc_orphan_old"]
    assert stored == []
    delete_mock.assert_called_once_with("ws_doc_test/orphan.pdf")


def test_cleanup_skips_committed_documents():
    import asyncio
    from datetime import datetime, timezone, timedelta

    import document_cleanup

    old_uploaded = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    committed = {
        "id": "doc_committed_old",
        "workspace_id": "ws_doc_test",
        "storage_key": "ws_doc_test/committed.pdf",
        "status": "committed",
        "linked_entry_id": "fe_abc123",
        "uploaded_at": old_uploaded,
    }
    stored = [committed]

    mock_coll = MagicMock()
    mock_coll.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=list(stored))))
    mock_coll.delete_one = AsyncMock()
    mock_db = MagicMock()
    mock_db.documents = mock_coll

    with patch.object(document_cleanup.doc_storage, "delete_document") as delete_mock:
        result = asyncio.run(document_cleanup.cleanup_orphaned_documents(mock_db))

    assert result["deleted_count"] == 0
    assert stored == [committed]
    delete_mock.assert_not_called()
    mock_coll.delete_one.assert_not_awaited()


def test_financial_entry_commits_its_source_document():
    import asyncio

    mock_db = MagicMock()
    mock_db.documents.find_one_and_update = AsyncMock(return_value={
        "id": "doc_1",
        "workspace_id": MOCK_PRINCIPAL["workspace_id"],
        "status": "committing",
    })
    mock_db.documents.update_one = AsyncMock()
    mock_db.financial_entries.insert_one = AsyncMock()
    payload = server.FinEntryInput(
        type="expense",
        category="Travel",
        name="Client offsite flights",
        amount=125,
        month="2026-09",
        source_document_id="doc_1",
    )

    with patch.object(server, "db", mock_db), patch.object(
        server.dept_migrate, "finance_department_id", new=AsyncMock(return_value="dept_fin"),
    ), patch.object(
        server.dept_migrate, "ensure_department_member", new=AsyncMock(return_value=True),
    ), patch.object(
        server, "_workspace_currency", new=AsyncMock(return_value="USD"),
    ), patch.object(server, "log_activity", new=AsyncMock()):
        result = asyncio.run(server.add_fin_entry(payload, MOCK_PRINCIPAL))

    assert result["entry"]["source"] == "ai_upload"
    assert result["entry"]["name"] == "Client offsite flights"
    assert result["entry"]["source_document_id"] == "doc_1"
    mock_db.documents.find_one_and_update.assert_awaited_once()
    mock_db.documents.update_one.assert_awaited_once_with(
        {"id": "doc_1", "workspace_id": MOCK_PRINCIPAL["workspace_id"]},
        {"$set": {"status": "committed", "linked_entry_id": result["entry"]["id"]}},
    )


def test_free_lifetime_extract_quota_asks_to_upgrade(client):
    doc_id = "doc_free_quota"
    server.db.documents.find_one = AsyncMock(return_value={
        "id": doc_id,
        "workspace_id": MOCK_PRINCIPAL["workspace_id"],
        "storage_key": "ws_doc_test/key.pdf",
        "filename": "invoice.pdf",
        "content_type": "application/pdf",
        "status": "uploaded",
    })
    free_ws = {
        "workspace_id": MOCK_PRINCIPAL["workspace_id"],
        "plan": "free",
        "ai_extracts_lifetime_used": 5,
    }
    # At the free-plan lifetime cap: the atomic $lt guard matches nothing, so
    # find_one_and_update returns None and acquire_lifetime_extract_slot() is False.
    server.db.workspaces.find_one_and_update = AsyncMock(return_value=None)
    with patch.object(server, "BILLING_ENFORCED", True), patch.object(
        server, "get_ws", new_callable=AsyncMock, return_value=free_ws
    ), patch.object(server.helm_llm, "anthropic_configured", return_value=True):
        r = client.post(f"/api/documents/{doc_id}/extract")
    assert r.status_code == 403
    detail = r.json()["detail"].lower()
    assert "upgrade to continue" in detail
    assert "5 free" in detail


def test_extract_skips_document_ai_when_daily_cap_hit(client):
    doc_id = "doc_dai_cap"
    server.db.documents.find_one = AsyncMock(return_value={
        "id": doc_id,
        "workspace_id": MOCK_PRINCIPAL["workspace_id"],
        "storage_key": "ws_doc_test/key.pdf",
        "filename": "invoice.pdf",
        "content_type": "application/pdf",
        "status": "uploaded",
    })
    extracted_payload = {
        "type": "expense",
        "amount": 9.0,
        "month": "2026-09",
        "category": "G&A",
        "vendor": "Acme",
        "confidence": "high",
        "engine": "anthropic",
    }
    with patch.object(server.doc_storage, "get_document_bytes", return_value=PDF_BYTES), patch.object(
        server.helm_llm, "extraction_configured", return_value=True
    ), patch.object(
        server.helm_llm, "extract_financial_document", new_callable=AsyncMock, return_value=extracted_payload
    ) as extract_mock, patch.object(
        server.doc_rate_limit, "acquire_event_slot", new_callable=AsyncMock, return_value=True
    ), patch.object(
        server.gcp_docai, "document_ai_configured", return_value=True
    ), patch.object(
        server.doc_rate_limit, "document_ai_allowed", new_callable=AsyncMock, return_value=False
    ), patch.object(server.doc_rate_limit, "record_document_ai", new_callable=AsyncMock) as record_dai:
        r = client.post(f"/api/documents/{doc_id}/extract")

    assert r.status_code == 200
    assert extract_mock.await_args.kwargs.get("use_document_ai") is False
    record_dai.assert_not_awaited()
