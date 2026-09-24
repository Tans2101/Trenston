"""Slack webhook escaping, broken status, and save-time validation."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_slack_hardening")

import alert_notify as an  # noqa: E402
import server  # noqa: E402


def test_slack_mrkdwn_escaping():
    text = an.build_slack_text(
        "Acme <Corp> & Co",
        [{"title": "Burn <high>", "description": "Cash & burn @channel"}],
        "https://app.example",
    )
    assert "&amp;" in text
    assert "&lt;" in text
    assert "&gt;" in text
    assert "<Corp>" not in text
    assert "@channel" in text  # literal text is fine once <>& escaped


def test_validate_slack_webhook_url():
    assert server._validate_slack_webhook_url(
        "https://hooks.slack.com/services/T/B/XXX"
    ).startswith("https://hooks.slack.com/")
    with pytest.raises(ValueError):
        server._validate_slack_webhook_url("http://hooks.slack.com/services/T/B/XXX")
    with pytest.raises(ValueError):
        server._validate_slack_webhook_url("https://evil.example/hooks.slack.com/x")


@pytest.mark.asyncio
async def test_broken_webhook_sets_status():
    fake_db = MagicMock()
    fake_db.workspaces.update_one = AsyncMock()

    class _Resp:
        status_code = 404
        text = "no_service"

    class _Client:
        def __init__(self, *a, **k):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def post(self, *a, **k):
            return _Resp()

    with patch.object(server, "db", fake_db), patch.object(server.httpx, "AsyncClient", _Client):
        result = await server.post_slack_webhook(
            "https://hooks.slack.com/services/T/B/XXX",
            "hi",
            workspace_id="ws1",
        )
    assert result["reason"] == "broken"
    fake_db.workspaces.update_one.assert_awaited()
    assert fake_db.workspaces.update_one.await_args.args[1]["$set"]["slack_webhook_status"] == "broken"


@pytest.mark.asyncio
async def test_save_rejects_failed_test_message():
    principal = {"workspace_id": "ws1", "user_id": "u1", "pack": "owner", "role": "owner"}

    with patch.object(
        server, "post_slack_webhook", AsyncMock(return_value={"ok": False, "reason": "http_error"})
    ), patch.object(server, "log_activity", AsyncMock()), patch.object(
        server, "require_integration_provider", lambda *_a, **_k: (lambda: principal)
    ):
        # Call the endpoint function directly.
        with pytest.raises(server.HTTPException) as exc:
            await server.update_slack_webhook(
                server.SlackWebhookInput(webhook_url="https://hooks.slack.com/services/T/B/XXX"),
                principal,
            )
    assert exc.value.status_code == 400
