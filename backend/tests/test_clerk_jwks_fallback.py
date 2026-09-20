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


@pytest.mark.asyncio
async def test_decode_clerk_jwt_primary_bapi_still_preferred():
    """BAPI path is unchanged — JWKS is only the fallback."""
    with patch.object(
        clerk_auth,
        "_verify_clerk_session_via_bapi",
        AsyncMock(return_value={"sub": "user_from_bapi", "sid": "sess"}),
    ), patch.object(
        clerk_auth, "_verify_clerk_jwt_jwks", AsyncMock(side_effect=AssertionError("jwks should not run")),
    ):
        payload = await clerk_auth.decode_clerk_jwt("dummy.jwt.token")
    assert payload["sub"] == "user_from_bapi"


@pytest.mark.asyncio
async def test_decode_clerk_jwt_falls_back_to_jwks_on_network_error():
    private_pem, public_jwk = _rsa_pair()
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "user_fallback",
            "sid": "sess_fb",
            "iss": "https://clerk.trenston.com",
            "azp": "https://www.trenston.com",
            "iat": now,
            "exp": now + 600,
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": "test_kid"},
    )
    import httpx

    with patch.object(
        clerk_auth,
        "_verify_clerk_session_via_bapi",
        AsyncMock(side_effect=httpx.ConnectError("down")),
    ), patch.object(
        clerk_auth, "_fetch_jwks_async", AsyncMock(return_value={"keys": [public_jwk]}),
    ):
        payload = await clerk_auth.decode_clerk_jwt(token)
    assert payload["sub"] == "user_fallback"
