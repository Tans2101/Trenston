"""T8: USD default for new workspaces; currency on /company and page payloads."""
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
os.environ.setdefault("DB_NAME", "test_workspace_currency")

import money_fmt  # noqa: E402
import seed_data  # noqa: E402
import server  # noqa: E402

OWNER = {"workspace_id": "ws1", "user_id": "u1", "pack": "owner", "role": "owner"}


def test_new_workspace_defaults_to_usd():
    ws = seed_data.build_workspace("ws1", "Acme", "u1", empty=True)
    assert ws["financial_settings"]["currency"] == "usd"


def test_onboarding_currency_overrides_default():
    ws = seed_data.build_workspace("ws1", "Acme", "u1", empty=True, currency="PHP")
    assert ws["financial_settings"]["currency"] == "php"
    ws_sgd = seed_data.build_workspace("ws1", "Acme", "u1", empty=True, currency="SGD")
    assert ws_sgd["financial_settings"]["currency"] == "sgd"
    bogus = seed_data.build_workspace("ws1", "Acme", "u1", empty=True, currency="doge")
    assert bogus["financial_settings"]["currency"] == "usd"


def test_legacy_default_currency_unchanged():
    assert money_fmt.DEFAULT_CURRENCY == "usd"
    assert money_fmt.normalize_currency(None) == "usd"


def _company(ws):
    with patch.object(server, "get_ws", new=AsyncMock(return_value=ws)):
        return asyncio.run(server.company(principal={**OWNER, "name": "Ana"}))


def test_company_payload_includes_currency():
    ws = seed_data.build_workspace("ws1", "Acme", "u1", empty=True)
    out = _company(ws)
    assert out["currency"] == "usd"
    assert out["currency_symbol"] == "$"


def test_company_payload_legacy_workspace_is_usd():
    ws = seed_data.build_workspace("ws1", "Acme", "u1", empty=True)
    ws["financial_settings"].pop("currency")
    out = _company(ws)
    assert (out["currency"], out["currency_symbol"]) == ("usd", "$")


def test_company_patch_sets_currency():
    fake_db = MagicMock()
    fake_db.workspaces.update_one = AsyncMock()
    with patch.object(server, "db", fake_db), patch.object(server, "invalidate_financials_cache") as inv:
        asyncio.run(server.update_company(server.CompanySetupInput(currency="PHP"), principal=OWNER))
    sets = fake_db.workspaces.update_one.await_args.args[1]["$set"]
    assert sets["financial_settings.currency"] == "php"
    inv.assert_called_once_with("ws1")


def test_company_patch_rejects_unknown_currency():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.update_company(server.CompanySetupInput(currency="xyz"), principal=OWNER))
    assert exc.value.status_code == 400


def test_currency_fields_helper():
    fake_db = MagicMock()
    fake_db.workspaces.find_one = AsyncMock(return_value={"financial_settings": {"currency": "php"}})
    with patch.object(server, "db", fake_db):
        out = asyncio.run(server._workspace_currency_fields("ws1"))
    assert out == {"currency": "php", "currency_symbol": "₱"}
