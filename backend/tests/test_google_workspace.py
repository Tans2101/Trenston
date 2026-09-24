"""Google Workspace + Document AI helpers."""
from __future__ import annotations

from google_document_ai import map_invoice_document
import google_oauth as gcal
import integrations_catalog as cat


def test_map_invoice_total_amount():
    doc = {
        "entities": [
            {"type": "total_amount", "normalizedValue": {"moneyValue": {"units": "49", "nanos": 0}}},
            {"type": "supplier_name", "mentionText": "Render"},
            {"type": "invoice_date", "normalizedValue": {"datetimeValue": {"year": 2026, "month": 9}}},
            {"type": "invoice_id", "mentionText": "INV-9"},
        ]
    }
    out = map_invoice_document(doc)
    assert out.get("error") is None
    assert out["amount"] == 49
    assert out["month"] == "2026-09"
    assert out["vendor"] == "Render"
    assert out["engine"] == "document_ai"
    assert out["type"] == "expense"


def test_map_invoice_missing_amount():
    out = map_invoice_document({"entities": [{"type": "supplier_name", "mentionText": "X"}]})
    assert out["error"] == "unparseable_amount"


def test_capabilities_and_missing_write_scopes():
    tokens = {"scope": "https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/gmail.readonly"}
    caps = gcal.google_capabilities(tokens)
    assert caps["gmail"] is True
    assert caps["sheets"] is False
    assert caps["drive_file"] is False
    assert caps["calendar_write"] is False
    assert caps["needs_reconnect"] is True
    assert "spreadsheets" in gcal.missing_write_scopes(tokens)
    assert "drive.file" in gcal.missing_write_scopes(tokens)


def test_catalog_reconnect_when_write_scopes_missing():
    ws = {"workspace_id": "ws1"}
    user_google = {
        "access_token": "x",
        "scope": "https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/gmail.readonly",
    }
    ints = cat.merge_integrations(
        ws, google_configured=True, qb_configured=False, user_google_tokens=user_google,
    )
    google = next(i for i in ints if i["id"] == "google")
    assert google["connected"] is True
    assert google.get("needs_reconsent") is True
    assert google["capabilities"]["gmail"] is True


def test_spreadsheet_body_has_two_sheets():
    body = gcal.build_ledger_spreadsheet_body("T", [["Metric", "Value"]], [["Month", "Type"]])
    assert body["properties"]["title"] == "T"
    assert len(body["sheets"]) == 2
    assert body["sheets"][0]["properties"]["title"] == "Summary"
    assert body["sheets"][1]["properties"]["title"] == "Ledger"
