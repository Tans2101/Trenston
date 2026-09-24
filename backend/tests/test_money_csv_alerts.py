"""Unit tests for money formatting, CSV import, alerts debounce, Slack failure isolation."""
import os
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

os.environ.setdefault("DB_NAME", "test_database")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

import money_fmt
import finance_csv
import alert_notify as an


def test_fmt_money_uses_currency_symbol():
    assert money_fmt.fmt_money(1500, "usd").startswith("$")
    assert "₱" in money_fmt.fmt_money(1500, "php")
    assert "€" in money_fmt.fmt_money(1500, "eur")
    assert money_fmt.fmt_money(500, "usd") == "$500"
    # Unknown codes fall back to USD
    assert money_fmt.fmt_money(100, "zzz") == "$100"


def test_csv_preview_valid_and_skipped_rows():
    text = """Date,Type,Category,Amount,Note
2026-03,revenue,Subscriptions,5000,MRR
2026-03-15,expense,Payroll,12000,
bad-date,expense,Cloud,100,
2026-04,income,Services,2500.50,consulting
2026-04,expense,Other,not-a-number,
"""
    parsed = finance_csv.parse_financial_csv(text)
    assert parsed["valid_count"] == 3
    assert parsed["skipped_count"] == 2
    assert parsed["valid"][0]["month"] == "2026-03"
    assert parsed["valid"][0]["type"] == "revenue"
    assert parsed["valid"][0]["name"] == "Subscriptions"
    assert parsed["valid"][2]["type"] == "revenue"  # income alias
    assert parsed["valid"][2]["amount"] == 2500.50
    reasons = " ".join(s["reason"] for s in parsed["skipped"])
    assert "Invalid date" in reasons or "bad-date" in reasons
    assert "Invalid amount" in reasons


def test_csv_rejects_missing_headers():
    with pytest.raises(ValueError, match="Missing required"):
        finance_csv.parse_financial_csv("foo,bar\n1,2\n")


def test_csv_name_column_and_category_fallback():
    text = """Month,Type,Category,Name,Amount
2026-09,expense,Cloud/Infra,MongoDB Database Subscription,57
2026-09,expense,Software,,99
"""
    parsed = finance_csv.parse_financial_csv(text)
    assert parsed["valid_count"] == 2
    assert parsed["valid"][0]["name"] == "MongoDB Database Subscription"
    assert parsed["valid"][0]["category"] == "Cloud/Infra"
    assert parsed["valid"][1]["name"] == "Software"
    assert parsed["valid"][1]["category"] == "Software"


def test_alert_debounce_skips_already_notified():
    sug = {
        "id": "sug_1",
        "title": "Runway risk",
        "severity": "high",
        "signal": {"type": "runway_risk", "severity": "high", "summary": "Cash runway", "related_id": None},
    }
    key = an.signal_notify_key(sug["signal"])
    fresh = an.new_high_alerts([sug], {key})
    assert fresh == []
    fresh2 = an.new_high_alerts([sug], set())
    assert len(fresh2) == 1


@pytest.mark.asyncio
async def test_notify_debounce_and_slack_failure_non_blocking():
    import server

    ws_id = "ws_notify_test"
    suggestions = [{
        "id": "sug_hi",
        "title": "Burn spike",
        "description": "Burn up 50%",
        "severity": "high",
        "signal": {
            "type": "burn_increase",
            "severity": "high",
            "summary": "Cash runway / burn pressure",
            "detail": "burn rose",
            "related_id": None,
        },
    }]
    c = {
        "name": "Notify Co",
        "notified_signal_ids": [],
        "slack_webhook_url": "https://hooks.slack.com/services/T/B/XXX",
    }

    email_calls = []
    slack_calls = []

    async def fake_email(**kwargs):
        email_calls.append(kwargs)
        return {"sent": True, "id": "em_1", "to": kwargs.get("to")}

    async def fake_slack(url, text, **kwargs):
        slack_calls.append((url, text))
        return {"ok": False, "reason": "http_error", "status": 500}

    async def fake_recipients(_ws):
        return ["ceo@example.com"]

    mock_update = AsyncMock()
    with patch.object(server, "send_resend_email", fake_email), \
         patch.object(server, "post_slack_webhook", fake_slack), \
         patch.object(server, "_alert_recipient_emails", fake_recipients), \
         patch.object(server, "db") as mock_db:
        mock_db.workspaces.update_one = mock_update
        r1 = await server._notify_high_severity_alerts(ws_id, suggestions, c)
        assert r1["new_alerts"] == 1
        assert r1["emailed"] is True
        assert r1["slack"] is False  # failed but did not raise
        assert r1["debounced"] is True  # email succeeded → debounce
        assert len(email_calls) == 1
        assert len(slack_calls) == 1

        # Second run with same open signal — debounced
        c2 = {
            "name": "Notify Co",
            "notified_signal_ids": [an.signal_notify_key(suggestions[0]["signal"])],
            "slack_webhook_url": "https://hooks.slack.com/services/T/B/XXX",
        }
        r2 = await server._notify_high_severity_alerts(ws_id, suggestions, c2)
        assert r2["new_alerts"] == 0
        assert len(email_calls) == 1  # no second email


@pytest.mark.asyncio
async def test_notify_does_not_debounce_when_both_channels_fail():
    import server

    suggestions = [{
        "id": "sug_hi",
        "title": "Burn spike",
        "severity": "high",
        "signal": {
            "type": "burn_increase",
            "severity": "high",
            "summary": "Cash runway / burn pressure",
            "related_id": None,
        },
    }]
    c = {
        "name": "Notify Co",
        "notified_signal_ids": [],
        "slack_webhook_url": "https://hooks.slack.com/services/T/B/XXX",
    }
    updates = []

    async def fake_email(**kwargs):
        return {"sent": False, "reason": "no_key"}

    async def fake_slack(url, text, **kwargs):
        return {"ok": False, "reason": "http_error"}

    async def fake_recipients(_ws):
        return ["ceo@example.com"]

    async def capture_update(*a, **k):
        updates.append(k)
        return None

    with patch.object(server, "send_resend_email", fake_email), \
         patch.object(server, "post_slack_webhook", fake_slack), \
         patch.object(server, "_alert_recipient_emails", fake_recipients), \
         patch.object(server, "db") as mock_db:
        mock_db.workspaces.update_one = capture_update
        r = await server._notify_high_severity_alerts("ws_x", suggestions, c)
        assert r["debounced"] is False
        assert updates == []  # must not write notified_signal_ids
