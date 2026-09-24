"""T17: Slack webhook encryption, masking, validation, escaping, broken handling."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_slack_webhook_storage")

import alert_notify as an  # noqa: E402
import credential_crypto as cred_crypto  # noqa: E402
import server  # noqa: E402
from scripts.migrate_encrypt_slack_webhooks import plan_for  # noqa: E402

URL = "https://hooks.slack.com/services/T0ABC/B0DEF/abcdEFGHwxyz"
OWNER = {"workspace_id": "ws1", "user_id": "u1", "pack": "owner", "role": "owner"}


@pytest.fixture(autouse=True)
def _fernet(monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", Fernet.generate_key().decode())


class _SlackClient:
    def __init__(self, status=200, body="ok"):
        self.status, self.body, self.posts = status, body, []

    def __call__(self, *a, **k):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None):
        self.posts.append((url, json))

        class R:
            status_code = self.status
            text = self.body

        return R()


def test_escaping_including_channel_mention():
    text = an.build_slack_text(
        "Acme & <Sons>", [{"title": "<!channel> Burn spike", "description": "a < b > c & d"}], "https://app",
    )
    assert "<!channel>" not in text
    assert "&lt;!channel&gt; Burn spike" in text
    assert "a &lt; b &gt; c &amp; d" in text
    assert text.startswith("*Trenston high-severity alert: Acme &amp; &lt;Sons&gt;*")
    assert "• " in text


@pytest.mark.parametrize("bad", [
    "https://hooks.slack.com.evil.com/x",
    "http://hooks.slack.com/x",
    "https://evil.com/hooks.slack.com/services/x",
    "https://user@evil.com/services/x",
])
def test_host_validation_rejects(bad):
    with pytest.raises(ValueError):
        server._validate_slack_webhook_url(bad)


def test_mask_format():
    assert server._mask_slack_webhook_url(URL) == "https://hooks.slack.com/services/T…/…wxyz"


def test_save_encrypts_into_new_field_and_unsets_legacy():
    fake_db = MagicMock()
    fake_db.workspaces.update_one = AsyncMock()
    with (
        patch.object(server, "db", fake_db),
        patch.object(server.httpx, "AsyncClient", _SlackClient()),
        patch.object(server, "log_activity", new=AsyncMock()),
    ):
        out = asyncio.run(server.update_slack_webhook(server.SlackWebhookInput(webhook_url=URL), principal=OWNER))
    update = fake_db.workspaces.update_one.await_args.args[1]
    assert update["$unset"] == {"slack_webhook_url": ""}
    enc = update["$set"]["slack_webhook_enc"]
    assert enc != URL and cred_crypto.decrypt_credential(enc) == URL
    assert out["slack_webhook_masked"].endswith("wxyz") and "slack_webhook_url" not in out


def test_failed_test_post_rejects_and_does_not_save():
    fake_db = MagicMock()
    fake_db.workspaces.update_one = AsyncMock()
    with patch.object(server, "db", fake_db), patch.object(server.httpx, "AsyncClient", _SlackClient(403, "invalid_token")):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(server.update_slack_webhook(server.SlackWebhookInput(webhook_url=URL), principal=OWNER))
    assert exc.value.status_code == 400
    assert exc.value.detail == "Slack didn't accept that webhook. Check the URL and try again."
    fake_db.workspaces.update_one.assert_not_called()


def test_reads_new_field_then_legacy_plaintext():
    enc = cred_crypto.encrypt_credential(URL)
    assert server._slack_webhook_plaintext({"slack_webhook_enc": enc}) == URL
    assert server._slack_webhook_plaintext({"slack_webhook_url": URL}) == URL
    assert server._slack_webhook_plaintext({"slack_webhook_url": enc}) == URL


@pytest.mark.parametrize("status,body", [(404, "no_service"), (410, ""), (200, "channel_is_archived"), (400, "invalid_token")])
def test_dead_webhook_marks_broken(status, body):
    fake_db = MagicMock()
    fake_db.workspaces.update_one = AsyncMock()
    with patch.object(server, "db", fake_db), patch.object(server.httpx, "AsyncClient", _SlackClient(status, body)):
        out = asyncio.run(server.post_slack_webhook(URL, "hi", workspace_id="ws1"))
    assert out == {"ok": False, "reason": "broken", "status": status}
    fake_db.workspaces.update_one.assert_awaited_once_with(
        {"workspace_id": "ws1"}, {"$set": {"slack_webhook_status": "broken"}},
    )


def test_broken_webhook_skipped_on_next_alert():
    ws = {"workspace_id": "ws1", "name": "Acme", "slack_webhook_enc": cred_crypto.encrypt_credential(URL),
          "slack_webhook_status": "broken"}
    suggestion = {"severity": "high", "title": "Runway", "signal": {"type": "runway", "severity": "high"}}
    fake_db = MagicMock()
    fake_db.workspaces.update_one = AsyncMock()
    with (
        patch.object(server, "db", fake_db),
        patch.object(server, "post_slack_webhook", new=AsyncMock()) as post,
        patch.object(server, "_alert_recipient_emails", new=AsyncMock(return_value=["ceo@acme.ph"])),
        patch.object(server, "send_resend_email", new=AsyncMock(return_value={"sent": True})),
    ):
        out = asyncio.run(server._notify_high_severity_alerts("ws1", [suggestion], ws))
    post.assert_not_called()
    assert out["slack"] is False and out["emailed"] is True


def test_migration_plan():
    enc = cred_crypto.encrypt_credential(URL)
    assert plan_for({"slack_webhook_url": URL})[0] == "encrypt"
    action, update = plan_for({"slack_webhook_url": URL})
    assert cred_crypto.decrypt_credential(update["$set"]["slack_webhook_enc"]) == URL
    assert update["$unset"] == {"slack_webhook_url": ""}
    assert plan_for({"slack_webhook_url": enc}) == ("move", {"$set": {"slack_webhook_enc": enc}, "$unset": {"slack_webhook_url": ""}})
    assert plan_for({"slack_webhook_url": URL, "slack_webhook_enc": enc})[0] == "drop_legacy"
    assert plan_for({"slack_webhook_url": "garbage"})[0] == "skip"
    assert plan_for({})[0] == "skip"
