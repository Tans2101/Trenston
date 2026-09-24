"""T10: Gmail draft MIME correctness."""
from __future__ import annotations

import asyncio
import base64
import os
import sys
from datetime import datetime, timezone
from email import message_from_bytes, policy
from email.header import decode_header, make_header
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_gmail_draft_headers")

import google_oauth as gcal  # noqa: E402
import server  # noqa: E402

TOKENS = {
    "access_token": "tok",
    "refresh_token": "r",
    "expires_in": 3600,
    "obtained_at": datetime.now(timezone.utc).isoformat(),
    "scope": "https://www.googleapis.com/auth/gmail.compose",
}


class _Resp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = ""

    def json(self):
        return self._payload


class _GmailClient:
    def __init__(self, thread_payload=None):
        self.thread_payload = thread_payload
        self.posted = None
        self.thread_params = None

    def __call__(self, *a, **k):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None, params=None):
        self.thread_params = params
        return _Resp(200, self.thread_payload or {})

    async def post(self, url, headers=None, json=None):
        self.posted = json
        return _Resp(200, {"id": "d1", "message": {"id": "m1"}})


def _draft(client, **kw):
    with patch.object(gcal.httpx, "AsyncClient", client):
        asyncio.run(gcal.create_gmail_draft(TOKENS, "cid", "csec", body="Hola", **kw))
    raw = client.posted["message"]["raw"]
    assert "=" not in raw  # unpadded base64url
    return message_from_bytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)), policy=policy.default)


def test_non_ascii_subject_round_trips():
    msg = _draft(_GmailClient(), to_email="compras@acme.ph", subject="Pedido Peña")
    raw_subject = msg.get("Subject", "")
    assert str(make_header(decode_header(raw_subject))) == "Pedido Peña"
    assert msg.get_content().strip() == "Hola"
    assert msg["To"] == "compras@acme.ph"


def test_crlf_stripped_from_subject_and_to():
    msg = _draft(
        _GmailClient(),
        to_email="a@b.com\r\nBcc: evil@x.com",
        subject="Hi\r\nBcc: evil@x.com",
    )
    assert msg["Bcc"] is None
    assert "\n" not in str(msg["Subject"]) and "\r" not in str(msg["Subject"])
    assert str(msg["Subject"]) == "HiBcc: evil@x.com"


def test_no_thread_keeps_subject_unchanged():
    msg = _draft(_GmailClient(), to_email="a@b.com", subject="Quarterly numbers")
    assert str(msg["Subject"]) == "Quarterly numbers"
    assert msg["In-Reply-To"] is None


def test_reply_sets_in_reply_to_and_references():
    thread = {"messages": [
        {"payload": {"headers": [{"name": "Message-ID", "value": "<first@mail>"}]}},
        {"payload": {"headers": [
            {"name": "Message-Id", "value": "<latest@mail>"},
            {"name": "References", "value": "<first@mail>"},
            {"name": "Subject", "value": "Order 42"},
        ]}},
    ]}
    client = _GmailClient(thread)
    msg = _draft(client, to_email="a@b.com", subject="Order 42", thread_id="t123")
    assert client.thread_params["format"] == "metadata"
    assert set(client.thread_params["metadataHeaders"]) == {"Message-ID", "References", "Subject"}
    assert msg["In-Reply-To"] == "<latest@mail>"
    assert msg["References"] == "<first@mail> <latest@mail>"
    assert str(msg["Subject"]) == "Re: Order 42"
    assert client.posted["message"]["threadId"] == "t123"


def test_reply_does_not_double_prefix_re():
    msg = _draft(_GmailClient({"messages": []}), to_email="a@b.com", subject="RE: Order 42", thread_id="t1")
    assert str(msg["Subject"]) == "RE: Order 42"


def test_route_rejects_missing_recipient():
    principal = {"workspace_id": "ws1", "user_id": "u1", "pack": "owner"}
    with (
        patch.object(server, "_require_user_google_tokens", new=AsyncMock(return_value=TOKENS)),
        patch.object(server.gcal, "create_gmail_draft", new_callable=AsyncMock) as create,
    ):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(server.google_gmail_draft(
                server.GmailDraftInput(thread_id="t1", to_email="   ", subject="Hi"),
                principal=principal,
            ))
    assert exc.value.status_code == 400
    assert exc.value.detail == "No recipient for this draft"
    create.assert_not_called()
