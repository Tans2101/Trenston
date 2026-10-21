"""Clerk JWKS fallback verifies issuer + audience (defense in depth)."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_clerk_jwks")
os.environ["CLERK_SECRET_KEY"] = "sk_live_test"
os.environ["CLERK_JWKS_URL"] = "https://clerk.trenston.com/.well-known/jwks.json"
os.environ["FRONTEND_URL"] = "https://www.trenston.com"
os.environ["APP_URL"] = "https://www.trenston.com"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import clerk_auth  # noqa: E402


def _rsa_pair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    public_jwk["kid"] = "test_kid"
    public_jwk["alg"] = "RS256"
    public_jwk["use"] = "sig"
    return private_pem, public_jwk


def test_clerk_jwt_issuer_from_jwks():
    assert clerk_auth.clerk_jwt_issuer() == "https://clerk.trenston.com"
    assert clerk_auth.clerk_jwt_audiences() == ["https://clerk.trenston.com"]


@pytest.mark.asyncio
async def test_jwks_fallback_accepts_valid_session_token():
    private_pem, public_jwk = _rsa_pair()
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "user_abc",
            "sid": "sess_abc",
            "iss": "https://clerk.trenston.com",
            "azp": "https://www.trenston.com",
            "iat": now,
            "exp": now + 600,
            "nbf": now - 5,
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": "test_kid"},
    )
    with patch.object(clerk_auth, "_fetch_jwks_async", AsyncMock(return_value={"keys": [public_jwk]})):
        payload = await clerk_auth._verify_clerk_jwt_jwks(token)
    assert payload["sub"] == "user_abc"
    assert payload["sid"] == "sess_abc"


@pytest.mark.asyncio
async def test_jwks_fallback_rejects_wrong_issuer():
    private_pem, public_jwk = _rsa_pair()
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "user_abc",
            "sid": "sess_abc",
            "iss": "https://evil.example.com",
            "azp": "https://www.trenston.com",
            "iat": now,
            "exp": now + 600,
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": "test_kid"},
    )
    with patch.object(clerk_auth, "_fetch_jwks_async", AsyncMock(return_value={"keys": [public_jwk]})):
        with pytest.raises(jwt.InvalidTokenError):
            await clerk_auth._verify_clerk_jwt_jwks(token)


@pytest.mark.asyncio
async def test_jwks_fallback_rejects_wrong_audience():
    private_pem, public_jwk = _rsa_pair()
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "user_abc",
            "sid": "sess_abc",
            "iss": "https://clerk.trenston.com",
            "aud": "https://attacker.example",
            "azp": "https://www.trenston.com",
            "iat": now,
            "exp": now + 600,
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": "test_kid"},
    )
    with patch.object(clerk_auth, "_fetch_jwks_async", AsyncMock(return_value={"keys": [public_jwk]})):
        with pytest.raises(jwt.InvalidTokenError):
            await clerk_auth._verify_clerk_jwt_jwks(token)


@pytest.mark.asyncio
async def test_jwks_fallback_accepts_matching_audience():
    private_pem, public_jwk = _rsa_pair()
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "user_abc",
            "sid": "sess_abc",
            "iss": "https://clerk.trenston.com",
            "aud": "https://clerk.trenston.com",
            "azp": "https://www.trenston.com",
            "iat": now,
            "exp": now + 600,
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": "test_kid"},
    )
    with patch.object(clerk_auth, "_fetch_jwks_async", AsyncMock(return_value={"keys": [public_jwk]})):
        payload = await clerk_auth._verify_clerk_jwt_jwks(token)
    assert payload["aud"] == "https://clerk.trenston.com"


@pytest.mark.asyncio
async def test_jwks_fallback_rejects_bad_azp():
    private_pem, public_jwk = _rsa_pair()
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "user_abc",
            "sid": "sess_abc",
            "iss": "https://clerk.trenston.com",
            "azp": "https://evil.example",
            "iat": now,
            "exp": now + 600,
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": "test_kid"},
    )
    with patch.object(clerk_auth, "_fetch_jwks_async", AsyncMock(return_value={"keys": [public_jwk]})):
        with pytest.raises(jwt.InvalidTokenError, match="authorized party"):
            await clerk_auth._verify_clerk_jwt_jwks(token)


def _signed_token(private_pem, **overrides):
    now = int(time.time())
    claims = {
        "sub": "user_local",
        "sid": "sess_local",
        "iss": "https://clerk.trenston.com",
        "azp": "https://www.trenston.com",
        "iat": now,
        "exp": now + 600,
    }
    claims.update(overrides)
    return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": "test_kid"})


@pytest.mark.asyncio
async def test_decode_clerk_jwt_verifies_locally_without_calling_clerk():
    """Fast path: a valid token is checked against cached JWKS, no Clerk API call."""
    private_pem, public_jwk = _rsa_pair()
    token = _signed_token(private_pem)
    with patch.object(
        clerk_auth,
        "_verify_clerk_session_via_bapi",
        AsyncMock(side_effect=AssertionError("bapi should not run")),
    ), patch.object(
        clerk_auth, "_fetch_jwks_async", AsyncMock(return_value={"keys": [public_jwk]}),
    ):
        payload = await clerk_auth.decode_clerk_jwt(token)
    assert payload["sub"] == "user_local"


@pytest.mark.asyncio
async def test_decode_clerk_jwt_bad_signature_is_final_no_bapi_fallback():
    private_pem, _ = _rsa_pair()
    _, other_jwk = _rsa_pair()  # different key under the same kid
    token = _signed_token(private_pem)
    with patch.object(
        clerk_auth,
        "_verify_clerk_session_via_bapi",
        AsyncMock(side_effect=AssertionError("bapi must not rescue a forged token")),
    ), patch.object(
        clerk_auth, "_fetch_jwks_async", AsyncMock(return_value={"keys": [other_jwk]}),
    ):
        with pytest.raises(ValueError, match="Invalid Clerk session token"):
            await clerk_auth.decode_clerk_jwt(token)


@pytest.mark.asyncio
async def test_decode_clerk_jwt_expired_is_final():
    private_pem, public_jwk = _rsa_pair()
    now = int(time.time())
    token = _signed_token(private_pem, iat=now - 900, exp=now - 600)
    with patch.object(
        clerk_auth,
        "_verify_clerk_session_via_bapi",
        AsyncMock(side_effect=AssertionError("bapi should not run")),
    ), patch.object(
        clerk_auth, "_fetch_jwks_async", AsyncMock(return_value={"keys": [public_jwk]}),
    ):
        with pytest.raises(ValueError, match="expired"):
            await clerk_auth.decode_clerk_jwt(token)


@pytest.mark.asyncio
async def test_decode_clerk_jwt_refreshes_jwks_once_when_kid_unknown():
    private_pem, public_jwk = _rsa_pair()
    token = _signed_token(private_pem)
    calls = []

    async def fake_fetch(force=False):
        calls.append(force)
        return {"keys": [public_jwk]} if force else {"keys": []}

    with patch.object(clerk_auth, "_fetch_jwks_async", fake_fetch):
        payload = await clerk_auth.decode_clerk_jwt(token)
    assert payload["sub"] == "user_local"
    assert calls == [False, True]


@pytest.mark.asyncio
async def test_decode_clerk_jwt_uses_bapi_jwks_when_public_jwks_down():
    """When public JWKS is unreachable, still verify RS256 via BAPI /jwks — never unsigned sid."""
    private_pem, public_jwk = _rsa_pair()
    token = _signed_token(private_pem)
    import httpx
    from unittest.mock import MagicMock

    clerk_auth._jwks_async_cache = None
    clerk_auth._jwks_async_cache_at = 0.0

    class _Resp:
        def __init__(self, status, data):
            self.status_code = status
            self._data = data

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("err", request=MagicMock(), response=MagicMock())

        def json(self):
            return self._data

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None):
            if "well-known/jwks" in url:
                raise httpx.ConnectError("public jwks down")
            if url.endswith("/jwks"):
                return _Resp(200, {"keys": [public_jwk]})
            raise AssertionError(f"unexpected url {url}")

    with patch.object(clerk_auth.httpx, "AsyncClient", _Client), patch.object(
        clerk_auth,
        "_verify_clerk_session_via_bapi",
        AsyncMock(side_effect=AssertionError("unsigned bapi auth must not run")),
    ):
        payload = await clerk_auth.decode_clerk_jwt(token)
    assert payload["sub"] == "user_local"


@pytest.mark.asyncio
async def test_decode_clerk_jwt_rejects_unknown_kid_without_unsigned_bapi():
    private_pem, _ = _rsa_pair()
    token = _signed_token(private_pem)
    empty = {"keys": []}
    with patch.object(
        clerk_auth, "_fetch_jwks_async", AsyncMock(return_value=empty),
    ), patch.object(
        clerk_auth,
        "_verify_clerk_session_via_bapi",
        AsyncMock(side_effect=AssertionError("bapi must not rescue unknown kid")),
    ):
        with pytest.raises(ValueError, match="Invalid Clerk session token"):
            await clerk_auth.decode_clerk_jwt(token)


@pytest.mark.asyncio
async def test_decode_clerk_jwt_rejects_forged_unsigned_when_jwks_down():
    """alg=none / fake kid must never authenticate via session-id lookup."""
    import base64
    import json as _json

    header = base64.urlsafe_b64encode(
        _json.dumps({"alg": "none", "kid": "attacker"}).encode()
    ).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        _json.dumps({
            "sub": "user_victim",
            "sid": "sess_victim",
            "iss": "https://clerk.trenston.com",
            "azp": "https://www.trenston.com",
            "exp": int(time.time()) + 600,
        }).encode()
    ).rstrip(b"=").decode()
    forged = f"{header}.{payload}."

    import httpx

    with patch.object(
        clerk_auth, "_fetch_jwks_async", AsyncMock(side_effect=httpx.ConnectError("down")),
    ), patch.object(
        clerk_auth,
        "_verify_clerk_session_via_bapi",
        AsyncMock(return_value={"sub": "user_victim", "sid": "sess_victim"}),
    ):
        with pytest.raises(ValueError):
            await clerk_auth.decode_clerk_jwt(forged)


@pytest.mark.asyncio
async def test_jwks_rejects_missing_azp_and_exp():
    private_pem, public_jwk = _rsa_pair()
    now = int(time.time())
    no_azp = jwt.encode(
        {
            "sub": "user_abc",
            "sid": "sess_abc",
            "iss": "https://clerk.trenston.com",
            "iat": now,
            "exp": now + 600,
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": "test_kid"},
    )
    no_exp = jwt.encode(
        {
            "sub": "user_abc",
            "sid": "sess_abc",
            "iss": "https://clerk.trenston.com",
            "azp": "https://www.trenston.com",
            "iat": now,
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": "test_kid"},
    )
    with patch.object(clerk_auth, "_fetch_jwks_async", AsyncMock(return_value={"keys": [public_jwk]})):
        with pytest.raises(jwt.InvalidTokenError, match="authorized party"):
            await clerk_auth._verify_clerk_jwt_jwks(no_azp)
        with pytest.raises(jwt.MissingRequiredClaimError):
            await clerk_auth._verify_clerk_jwt_jwks(no_exp)


def test_authorized_parties_exclude_localhost_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    parties = clerk_auth.clerk_authorized_parties()
    assert all("localhost" not in p for p in parties)
    assert all(p.startswith("https://") for p in parties)
