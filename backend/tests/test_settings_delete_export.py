import asyncio
import os

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_db")
import pytest
from fastapi import HTTPException

import server


class _Resp:
    def __init__(self, code, body=None):
        self.status_code = code
        self._body = body or {}
        self.text = str(body)

    def json(self):
        return self._body


def _client(post, get=None):
    class C:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return post

        async def get(self, *a, **k):
            return get or _Resp(500)
    return C


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_cancel_ok(monkeypatch):
    monkeypatch.setattr(server, "PADDLE_API_KEY", "k")
    monkeypatch.setattr(server.httpx, "AsyncClient", _client(_Resp(200)))
    run(server._cancel_paddle_subscription("sub_1"))


def test_cancel_already_canceled(monkeypatch):
    monkeypatch.setattr(server, "PADDLE_API_KEY", "k")
    monkeypatch.setattr(server.httpx, "AsyncClient", _client(
        _Resp(400), _Resp(200, {"data": {"status": "canceled"}})))
    run(server._cancel_paddle_subscription("sub_1"))


def test_cancel_failure_blocks_delete(monkeypatch):
    monkeypatch.setattr(server, "PADDLE_API_KEY", "k")
    monkeypatch.setattr(server.httpx, "AsyncClient", _client(_Resp(500), _Resp(500)))
    with pytest.raises(HTTPException) as e:
        run(server._cancel_paddle_subscription("sub_1"))
    assert e.value.status_code == 503


def test_no_subscription_is_noop():
    run(server._cancel_paddle_subscription(""))


def test_fin_settings_only_touches_sent_fields():
    p = server.FinSettingsInput(cash=5)
    assert "gross_margin" not in p.model_fields_set
    p2 = server.FinSettingsInput(gross_margin=None)
    assert "gross_margin" in p2.model_fields_set
