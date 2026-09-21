"""Verify Clerk session JWTs and load user profile from Clerk API."""
from __future__ import annotations

import base64
import logging
import os
import time
from typing import Any
from urllib.parse import urlparse

import httpx
import jwt

from helm_config import TRENSTON_CANONICAL_ORIGIN, TRENSTON_PRIMARY_HOSTS, is_stale_deploy_url

logger = logging.getLogger(__name__)

TRENSTON_CLERK_JWKS_URL = "https://clerk.trenston.com/.well-known/jwks.json"
CLERK_BAPI = "https://api.clerk.com/v1"
CLERK_FAPI = os.environ.get("CLERK_FAPI_URL", "https://frontend-api.clerk.services").rstrip("/")


def _resolve_clerk_jwks_url() -> str:
    env = os.environ.get("CLERK_JWKS_URL", "").strip()
    if env:
        return env
    return TRENSTON_CLERK_JWKS_URL


CLERK_SECRET_KEY = os.environ.get("CLERK_SECRET_KEY", "")
CLERK_JWKS_URL = _resolve_clerk_jwks_url()

_raw_frontend = os.environ.get("FRONTEND_URL", "").strip().rstrip("/")
FRONTEND_URL = TRENSTON_CANONICAL_ORIGIN if is_stale_deploy_url(_raw_frontend) else _raw_frontend

_raw_app = os.environ.get("APP_URL", "").strip().rstrip("/")
APP_URL_CLERK = TRENSTON_CANONICAL_ORIGIN if is_stale_deploy_url(_raw_app) else (_raw_app or FRONTEND_URL)

# Extra origins from CORS_ORIGINS env (e.g. legacy apexcoach during migration).
_extra_cors = {
    o.strip().rstrip("/")
    for o in os.environ.get("CORS_ORIGINS", "").split(",")
    if o.strip()
}

TRENSTON_CLERK_ORIGINS = {
    "https://trenston.com",
    "https://www.trenston.com",
    # Legacy domains during DNS/301 cutover (remove once helmcontrol.online is retired).
    "https://helmcontrol.online",
    "https://www.helmcontrol.online",
    "https://apexcoach.tech",
    "https://www.apexcoach.tech",
    "http://localhost:3000",
    *_extra_cors,
}

_jwks_keys_cache: dict[str, Any] | None = None
_jwks_keys_cache_at: float = 0.0
_JWKS_TTL_SECONDS = 3600
_last_sync_status: dict[str, Any] | None = None


def clerk_configured() -> bool:
    return bool(CLERK_SECRET_KEY and CLERK_JWKS_URL)


def clerk_secret_mode() -> str | None:
    if CLERK_SECRET_KEY.startswith("sk_live_"):
        return "live"
    if CLERK_SECRET_KEY.startswith("sk_test_"):
        return "test"
    return None


def clerk_jwks_host() -> str | None:
    if not CLERK_JWKS_URL:
        return None
    return urlparse(CLERK_JWKS_URL).hostname


def clerk_jwt_issuer() -> str:
    """Clerk Frontend API URL — the `iss` claim on session tokens.

    Derived from CLERK_JWKS_URL (e.g. https://clerk.trenston.com/.well-known/jwks.json
    → https://clerk.trenston.com). Override with CLERK_JWT_ISSUER when needed.
    """
    explicit = os.environ.get("CLERK_JWT_ISSUER", "").strip().rstrip("/")
    if explicit:
        return explicit
    host = clerk_jwks_host()
    if not host:
        raise ValueError("CLERK_JWKS_URL is not configured")
    return f"https://{host}"


def clerk_jwt_audiences() -> list[str]:
    """Accepted `aud` values when a session/API token includes an audience claim.

    Default Clerk session tokens often omit `aud` (they use `azp` instead). When
    `aud` is present it is typically the Frontend API URL (same as issuer).
    Override with comma-separated CLERK_JWT_AUDIENCE.
    """
    explicit = os.environ.get("CLERK_JWT_AUDIENCE", "").strip()
    if explicit:
        return [a.strip() for a in explicit.split(",") if a.strip()]
    return [clerk_jwt_issuer()]


def clerk_authorized_parties() -> set[str]:
    """Origins allowed in the session token `azp` claim."""
    allowed = {o.rstrip("/") for o in helm_frontend_origins() if o}
    for extra in (
        clerk_primary_origin(),
        primary_frontend_origin(),
        FRONTEND_URL,
        APP_URL_CLERK,
        TRENSTON_CANONICAL_ORIGIN,
    ):
        if extra:
            allowed.add(extra.rstrip("/"))
    return {a for a in allowed if a}


def clerk_primary_origin() -> str | None:
    """Clerk instance primary app domain — redirect URLs must use this host."""
    explicit = os.environ.get("CLERK_PRIMARY_ORIGIN", "").strip().rstrip("/")
    if explicit:
        return explicit
    host = clerk_jwks_host()
    if host and host.startswith("clerk."):
        return f"https://{host[6:]}"
    return None


def _origin_registrable_host(origin: str) -> str:
    host = (urlparse(origin or "").hostname or "").lower()
    if host.startswith("www."):
        return host[4:]
    return host


def clerk_post_auth_url() -> str | None:
    """Public Trenston /app after Clerk auth.

    JWKS host clerk.example.com implies https://example.com, but the live site
    may be https://www.example.com. Use the public Trenston origin when they are
    the same registrable domain so forceRedirectUrl matches Clerk's allow list.
    """
    clerk_prim = clerk_primary_origin()
    helm = primary_frontend_origin() or TRENSTON_CANONICAL_ORIGIN
    if clerk_prim and helm:
        if _origin_registrable_host(clerk_prim) == _origin_registrable_host(helm):
            return f"{helm.rstrip('/')}/app"
        return f"{clerk_prim.rstrip('/')}/app"
    target = helm or clerk_prim
    return f"{target.rstrip('/')}/app" if target else None


def clerk_multi_domain_auth() -> bool:
    """True when Clerk's app domain is a different site than public Trenston (satellite)."""
    clerk_prim = (clerk_primary_origin() or "").rstrip("/")
    helm_prim = (primary_frontend_origin() or TRENSTON_CANONICAL_ORIGIN or "").rstrip("/")
    if not clerk_prim or not helm_prim:
        return False
    return _origin_registrable_host(clerk_prim) != _origin_registrable_host(helm_prim)


def derive_publishable_key_from_jwks(jwks_url: str, *, mode: str = "live") -> str | None:
    """Derive pk_* from JWKS host when CLERK_PUBLISHABLE_KEY is unset on Render."""
    host = urlparse(jwks_url).hostname
    if not host:
        return None
    prefix = "pk_test_" if mode == "test" else "pk_live_"
    encoded = base64.b64encode(f"{host}$".encode()).decode().rstrip("=")
    return f"{prefix}{encoded}"


def publishable_key_instance_host(publishable_key: str) -> str | None:
    """Decode the Clerk frontend host embedded in a publishable key."""
    key = (publishable_key or "").strip()
    if not key.startswith("pk_"):
        return None
    parts = key.split("_", 2)
    if len(parts) < 3 or not parts[2]:
        return None
    payload = parts[2]
    pad = "=" * (-len(payload) % 4)
    try:
        decoded = base64.b64decode(payload + pad).decode()
    except Exception:
        return None
    return decoded.rstrip("$") or None


def clerk_keys_aligned(publishable_key: str, jwks_url: str) -> bool:
    """True when publishable key and JWKS URL refer to the same Clerk frontend."""
    pk_host = publishable_key_instance_host(publishable_key)
    jwks_host = urlparse(jwks_url).hostname
    if not pk_host or not jwks_host:
        return False
    return pk_host == jwks_host


def resolve_clerk_publishable_key() -> str:
    """Env override (must match JWKS), else derive from JWKS + secret mode."""
    explicit = os.environ.get("CLERK_PUBLISHABLE_KEY", "").strip()
    if explicit:
        if not clerk_keys_aligned(explicit, CLERK_JWKS_URL):
            logger.error(
                "CLERK_PUBLISHABLE_KEY does not match CLERK_JWKS_URL host — ignoring explicit key"
            )
        else:
            return explicit
    mode = clerk_secret_mode()
    if not mode or not CLERK_JWKS_URL:
        return ""
    derived = derive_publishable_key_from_jwks(CLERK_JWKS_URL, mode=mode)
    if derived and not clerk_keys_aligned(derived, CLERK_JWKS_URL):
        logger.warning("derived Clerk publishable key does not match JWKS host")
        return ""
    return derived or ""


def helm_frontend_origins() -> list[str]:
    """Origins Trenston must register with Clerk for browser auth."""
    origins = {o for o in (
        *TRENSTON_CLERK_ORIGINS,
        FRONTEND_URL,
        APP_URL_CLERK,
    ) if o}
    return sorted(origins)


def primary_frontend_origin() -> str | None:
    """Production frontend origin — trenston.com when configured."""
    for host in TRENSTON_PRIMARY_HOSTS:
        for origin in helm_frontend_origins():
            if not origin.startswith("https://") or host not in origin:
                continue
            if origin.startswith("https://www."):
                return origin
    for host in TRENSTON_PRIMARY_HOSTS:
        for origin in helm_frontend_origins():
            if origin.startswith("https://") and host in origin:
                return origin
    if TRENSTON_CANONICAL_ORIGIN and TRENSTON_CANONICAL_ORIGIN.startswith("https://"):
        return TRENSTON_CANONICAL_ORIGIN
    preferred = (FRONTEND_URL, APP_URL_CLERK)
    for origin in preferred:
        if origin and origin.startswith("https://") and "localhost" not in origin:
            return origin
    for origin in helm_frontend_origins():
        if origin.startswith("https://") and "localhost" not in origin and "vercel.app" not in origin:
            return origin
    for origin in helm_frontend_origins():
        if origin.startswith("https://") and "localhost" not in origin:
            return origin
    return helm_frontend_origins()[0] if helm_frontend_origins() else None


def clerk_sync_status() -> dict[str, Any]:
    return dict(_last_sync_status or {"synced": False, "reason": "not_run"})


def clerk_secret_publishable_mode_match(publishable_key: str) -> bool:
    """True when sk_live_/sk_test_ matches pk_live_/pk_test_."""
    mode = clerk_secret_mode()
    if not mode or not (publishable_key or "").strip():
        return False
    expected = "pk_test_" if mode == "test" else "pk_live_"
    return publishable_key.strip().startswith(expected)


def _fetch_public_jwks_sync() -> dict[str, Any]:
    """JWKS from Clerk custom-domain /.well-known/jwks.json (no secret required)."""
    if not CLERK_JWKS_URL:
        raise ValueError("CLERK_JWKS_URL is not configured")
    with httpx.Client(timeout=15) as client:
        r = client.get(CLERK_JWKS_URL)
        r.raise_for_status()
        return r.json()


def _fetch_bapi_jwks_sync() -> dict[str, Any]:
    """JWKS via Clerk Backend API — works when clerk.* custom-domain TLS is not ready."""
    import time

    global _jwks_keys_cache, _jwks_keys_cache_at
    now = time.time()
    if _jwks_keys_cache and now - _jwks_keys_cache_at < _JWKS_TTL_SECONDS:
        return _jwks_keys_cache
    with httpx.Client(timeout=15) as client:
        r = client.get(f"{CLERK_BAPI}/jwks", headers=_bapi_headers())
        if r.status_code in (401, 403):
            raise ValueError(
                "CLERK_SECRET_KEY rejected by Clerk API. Use the secret key from the same "
                "Clerk instance as your publishable key (Dashboard → API keys)"
            )
        r.raise_for_status()
        _jwks_keys_cache = r.json()
        _jwks_keys_cache_at = now
        return _jwks_keys_cache


def _fetch_jwks_sync() -> dict[str, Any]:
    """Prefer public JWKS (matches browser-issued session JWTs); BAPI as fallback."""
    try:
        return _fetch_public_jwks_sync()
    except httpx.HTTPError as exc:
        logger.warning("Clerk public JWKS fetch failed (%s) — trying BAPI JWKS", exc)
    try:
        return _fetch_bapi_jwks_sync()
    except ValueError:
        raise
    except httpx.HTTPError as exc:
        raise ValueError(
            "Could not load Clerk signing keys. Check CLERK_JWKS_URL and CLERK_SECRET_KEY on Render"
        ) from exc


def _signing_key_from_jwt(token: str):
    import json
    from jwt.algorithms import RSAAlgorithm

    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    jwks = _fetch_jwks_sync()
    for key_data in jwks.get("keys", []):
        if key_data.get("kid") == kid:
            return RSAAlgorithm.from_jwk(json.dumps(key_data))
    raise jwt.InvalidTokenError(
        "JWKS kid not found. CLERK_SECRET_KEY may be from a different Clerk instance than pk_live on Vercel"
    )


def _bapi_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {CLERK_SECRET_KEY}"}


_health_probe_cache: dict[str, tuple[float, bool]] = {}
_HEALTH_PROBE_TTL_OK_SECONDS = 120.0
_HEALTH_PROBE_TTL_FAIL_SECONDS = 15.0


def _cached_health(name: str) -> bool | None:
    row = _health_probe_cache.get(name)
    if not row:
        return None
    at, value = row
    ttl = _HEALTH_PROBE_TTL_OK_SECONDS if value else _HEALTH_PROBE_TTL_FAIL_SECONDS
    if time.time() - at > ttl:
        return None
    return value


def _store_health(name: str, value: bool) -> bool:
    _health_probe_cache[name] = (time.time(), value)
    return value


async def clerk_api_ok() -> bool:
    """True when CLERK_SECRET_KEY can reach the Clerk API (matches publishable key instance)."""
    cached = _cached_health("api")
    if cached is not None:
        return cached
    if not CLERK_SECRET_KEY:
        return _store_health("api", False)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{CLERK_BAPI}/instance", headers=_bapi_headers())
            return _store_health("api", r.status_code == 200)
    except Exception:
        return _store_health("api", False)


async def clerk_jwks_ok() -> bool:
    """True when JWKS is reachable (public URL or Clerk Backend API)."""
    cached = _cached_health("jwks")
    if cached is not None:
        return cached
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(CLERK_JWKS_URL)
            if r.status_code == 200 and b"keys" in r.content:
                return _store_health("jwks", True)
    except Exception:
        pass
    if not CLERK_SECRET_KEY:
        return _store_health("jwks", False)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{CLERK_BAPI}/jwks", headers=_bapi_headers())
            return _store_health("jwks", r.status_code == 200 and b"keys" in r.content)
    except Exception:
        return _store_health("jwks", False)


async def _clerk_primary_domain_record() -> dict[str, Any] | None:
    """Fetch Clerk BAPI domain row for trenston.com (if configured)."""
    if not clerk_configured():
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{CLERK_BAPI}/domains", headers=_bapi_headers())
            if r.status_code >= 400:
                return None
            for d in (r.json().get("data") or []):
                if d.get("name") in {"trenston.com", "www.trenston.com"}:
                    return d
    except Exception:
        logger.debug("clerk domain list failed", exc_info=True)
    return None


def clerk_google_oauth_redirect_uris() -> list[str]:
    """Google Cloud authorized redirect URIs Clerk may send for this instance."""
    host = clerk_jwks_host()
    if not host or host.endswith(".clerk.accounts.dev"):
        return []
    uris = [f"https://{host}/v1/oauth_callback"]
    if host.startswith("clerk."):
        apex = host[len("clerk.") :]
        uris.append(f"https://accounts.{apex}/v1/oauth_callback")
    return uris


def clerk_google_oauth_redirect_uri() -> str | None:
    """Primary Clerk production Google OAuth callback — must match Google Cloud Console."""
    uris = clerk_google_oauth_redirect_uris()
    return uris[0] if uris else None


async def _clerk_google_client_id() -> str | None:
    """Google OAuth client ID configured in Clerk (from FAPI environment)."""
    host = clerk_jwks_host()
    if not host:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"https://{host}/v1/environment")
            if r.status_code >= 400:
                return None
            env = r.json() or {}
            display = env.get("display_config") or {}
            one_tap = (display.get("google_one_tap_client_id") or "").strip()
            if one_tap:
                return one_tap
            cr = await client.get(f"https://{host}/v1/client")
            if cr.status_code >= 400:
                return None
            cookies = dict(cr.cookies)
            sia_resp = await client.post(
                f"https://{host}/v1/client/sign_ins",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                content=b"",
                cookies=cookies,
            )
            sia = (sia_resp.json().get("response") or {}).get("id")
            if not sia:
                return None
            prep = await client.post(
                f"https://{host}/v1/client/sign_ins/{sia}/prepare_first_factor",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "strategy": "oauth_google",
                    "redirect_url": f"{TRENSTON_CANONICAL_ORIGIN}/app",
                    "action_complete_redirect_url": f"{TRENSTON_CANONICAL_ORIGIN}/app",
                },
                cookies=cookies,
            )
            url = (
                ((prep.json().get("response") or {}).get("first_factor_verification") or {})
                .get("external_verification_redirect_url")
                or ""
            )
            if "client_id=" not in url:
                return None
            from urllib.parse import parse_qs, urlparse

            qs = parse_qs(urlparse(url).query)
            return (qs.get("client_id") or [None])[0]
    except Exception:
        logger.debug("clerk google client id probe failed", exc_info=True)
    return None


async def clerk_google_oauth_status() -> dict[str, Any]:
    """Probe whether Google OAuth redirect URI is registered for Clerk sign-in."""
    redirect_uri = clerk_google_oauth_redirect_uri()
    redirect_uris = clerk_google_oauth_redirect_uris()
    client_id = await _clerk_google_client_id()
    result: dict[str, Any] = {
        "redirect_uri": redirect_uri,
        "redirect_uris": redirect_uris,
        "client_id": client_id,
        "redirect_uri_registered": None,
        "ok": False,
    }
    if not redirect_uri or not client_id:
        result["reason"] = "not_configured"
        return result
    project = client_id.split("-", 1)[0] if client_id else ""
    result["google_cloud_project_number"] = project or None
    result["google_cloud_console_url"] = (
        f"https://console.cloud.google.com/apis/credentials/oauthclient/{client_id}?project={project}"
        if project
        else "https://console.cloud.google.com/apis/credentials"
    )
    result["javascript_origins"] = [
        "https://trenston.com",
        "https://www.trenston.com",
        "https://clerk.trenston.com",
        "https://accounts.trenston.com",
    ]
    try:
        from urllib.parse import urlencode

        async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
            registered: dict[str, bool] = {}
            for uri in redirect_uris:
                params = urlencode(
                    {
                        "client_id": client_id,
                        "redirect_uri": uri,
                        "response_type": "code",
                        "scope": "openid email profile",
                    }
                )
                r = await client.get(f"https://accounts.google.com/o/oauth2/auth?{params}")
                loc = r.headers.get("location", "")
                registered[uri] = not ("oauth/error" in loc or "redirect_uri_mismatch" in loc)
            primary_ok = registered.get(redirect_uri, False)
            result["redirect_uri_checks"] = registered
            result["redirect_uri_registered"] = primary_ok
            result["ok"] = primary_ok
            missing = [u for u, ok in registered.items() if not ok]
            result["reason"] = "ok" if primary_ok else "redirect_uri_mismatch"
            if missing:
                result["missing_redirect_uris"] = missing
                if primary_ok:
                    result["reason"] = "ok_add_account_portal_uri"
    except Exception as exc:
        result["reason"] = "probe_failed"
        result["error"] = str(exc)[:200]
    return result


async def clerk_custom_domain_ssl_ok() -> bool:
    """True when clerk.* FAPI accepts TLS or Clerk BAPI reports certs issued."""
    cached = _cached_health("ssl")
    if cached is not None:
        return cached
    host = clerk_jwks_host()
    if not host or host.endswith(".clerk.accounts.dev"):
        return _store_health("ssl", True)
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(f"https://{host}/v1/client")
            if r.status_code < 500:
                return _store_health("ssl", True)
    except Exception:
        pass
    # Some hosts (Render) cannot TLS-probe Clerk even when certs are issued — trust BAPI.
    domain = await _clerk_primary_domain_record()
    if not domain:
        return _store_health("ssl", False)
    if not (domain.get("proxy_url") or "").strip():
        return _store_health("ssl", True)
    # Proxy still registered but Clerk Dashboard may show SSL issued — prefer DNS mode.
    return _store_health("ssl", True)


def clerk_proxy_url() -> str | None:
    """Public Clerk FAPI proxy — must be on Clerk primary apex (trenston.com), not www."""
    origin = clerk_primary_origin() or TRENSTON_CANONICAL_ORIGIN
    if not origin:
        return None
    host = urlparse(origin).hostname or ""
    if not host:
        return None
    apex = host[4:] if host.startswith("www.") else host
    return f"https://{apex}/__clerk"


async def proxy_clerk_fapi(path: str, request: Any) -> Any:
    """Proxy Clerk Frontend API when clerk.* custom-domain TLS is not ready."""
    import asyncio
    import subprocess
    from starlette.responses import JSONResponse, Response

    qs = request.url.query
    target = f"{CLERK_FAPI}/{path}".rstrip("/")
    if qs:
        target = f"{target}?{qs}"
    proxy_base = clerk_proxy_url() or f"{TRENSTON_CANONICAL_ORIGIN}/__clerk"

    forward: dict[str, str] = {}
    for key in (
        "authorization", "content-type", "accept", "accept-language",
        "user-agent", "cookie",
    ):
        val = request.headers.get(key)
        if val:
            forward[key] = val
    forward["Clerk-Proxy-Url"] = proxy_base
    if CLERK_SECRET_KEY:
        forward["Clerk-Secret-Key"] = CLERK_SECRET_KEY
    xff = request.headers.get("x-forwarded-for", "")
    client_ip = xff.split(",")[0].strip() if xff else (request.client.host if request.client else "127.0.0.1")
    forward["X-Forwarded-For"] = client_ip
    forward["Origin"] = TRENSTON_CANONICAL_ORIGIN or proxy_base.rsplit("/__clerk", 1)[0]

    body = await request.body()

    async def _httpx_upstream() -> httpx.Response:
        async with httpx.AsyncClient(timeout=30, http2=False) as client:
            return await client.request(
                request.method,
                target,
                headers=forward,
                content=body if body else None,
            )

    def _curl_upstream() -> tuple[int, bytes, dict[str, str]]:
        cmd = ["curl", "-sS", "-L", "--http1.1", "-w", "\n%{http_code}", "-X", request.method, target]
        for key, val in forward.items():
            cmd.extend(["-H", f"{key}: {val}"])
        if body and request.method not in ("GET", "HEAD"):
            cmd.extend(["--data-binary", "@-"])
        proc = subprocess.run(
            cmd,
            input=body if body else None,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.decode("utf-8", errors="replace")[:500] or f"curl exit {proc.returncode}")
        raw = proc.stdout
        if b"\n" not in raw:
            raise RuntimeError("curl response missing status line")
        payload, status_line = raw.rsplit(b"\n", 1)
        status = int(status_line.decode().strip())
        return status, payload, {"content-type": "application/json"}

    try:
        upstream = await _httpx_upstream()
    except Exception as httpx_err:
        logger.warning("clerk fapi httpx failed for %s: %s — trying curl", target, httpx_err)
        try:
            status, payload, hdrs = await asyncio.to_thread(_curl_upstream)
            return Response(content=payload, status_code=status, headers=hdrs)
        except Exception as curl_err:
            logger.exception("clerk fapi proxy failed for %s", target)
            return JSONResponse(
                {"error": "Clerk proxy failed", "httpx": str(httpx_err), "curl": str(curl_err)},
                status_code=502,
            )

    skip = {"transfer-encoding", "content-encoding", "content-length"}
    headers = {k: v for k, v in upstream.headers.items() if k.lower() not in skip}
    return Response(content=upstream.content, status_code=upstream.status_code, headers=headers)


async def fetch_clerk_instance() -> dict[str, Any] | None:
    if not clerk_configured():
        return None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{CLERK_BAPI}/instance", headers=_bapi_headers())
            if r.status_code >= 400:
                return None
            return r.json()
    except Exception:
        logger.exception("Clerk instance GET failed")
        return None


def _jwt_payload_unverified(token: str) -> dict[str, Any]:
    """Parse JWT payload without signature verification (for sid/sub only)."""
    import base64
    import json

    parts = (token or "").split(".")
    if len(parts) != 3:
        raise ValueError("Clerk returned a non-JWT token. Sign out and sign in again")
    pad = "=" * (-len(parts[1]) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(parts[1] + pad))
    except Exception as exc:
        raise ValueError("Invalid Clerk session token") from exc


_jwks_async_cache: dict[str, Any] | None = None
_jwks_async_cache_at: float = 0.0


async def prefetch_jwks() -> bool:
    """Warm JWKS cache at startup (async — works on Render)."""
    try:
        await _fetch_jwks_async()
        return True
    except Exception:
        logger.warning("Clerk JWKS prefetch failed", exc_info=True)
        return False


async def _fetch_jwks_async() -> dict[str, Any]:
    """JWKS from public Clerk URL using async httpx (Render-safe)."""
    import time

    global _jwks_async_cache, _jwks_async_cache_at
    now = time.time()
    if _jwks_async_cache and now - _jwks_async_cache_at < _JWKS_TTL_SECONDS:
        return _jwks_async_cache
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(CLERK_JWKS_URL)
        r.raise_for_status()
        _jwks_async_cache = r.json()
        _jwks_async_cache_at = now
        return _jwks_async_cache


async def _verify_clerk_session_via_bapi(token: str) -> dict[str, Any]:
    """Verify session by checking sid with Clerk Backend API (no local JWKS/crypto)."""
    import time

    payload = _jwt_payload_unverified(token)
    sid = payload.get("sid") or payload.get("session_id")
    sub = payload.get("sub")
    if not sid or not sub:
        raise ValueError("Clerk session token is missing session or user id")
    exp = payload.get("exp")
    if exp is not None and exp < time.time() - 60:
        raise ValueError("Clerk session expired. Sign out and sign in again")
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{CLERK_BAPI}/sessions/{sid}", headers=_bapi_headers())
    if r.status_code in (401, 403):
        raise ValueError(
            "CLERK_SECRET_KEY rejected by Clerk API. Use sk_live_ from clerk.trenston.com on Render"
        )
    if r.status_code == 404:
        raise ValueError(
            "Clerk session not found. CLERK_SECRET_KEY may be from a different Clerk instance than pk_live"
        )
    if r.status_code >= 400:
        raise ValueError(f"Clerk session check failed ({r.status_code})")
    session = r.json()
    if session.get("user_id") != sub:
        raise ValueError("Clerk session user mismatch")
    status = (session.get("status") or "").lower()
    if status not in ("active", "pending"):
        raise ValueError("Clerk session is not active. Sign in again")
    return payload


async def _verify_clerk_jwt_jwks(token: str) -> dict[str, Any]:
    """Verify JWT signature against async-cached public JWKS.

    Defense-in-depth fallback when the BAPI session check is unreachable.
    Validates issuer (and audience when the token carries `aud`) — Clerk
    session tokens typically omit `aud` and use `azp` instead; we check both.
    """
    import json

    from jwt.algorithms import RSAAlgorithm

    jwks = await _fetch_jwks_async()
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    signing_key = None
    for key_data in jwks.get("keys", []):
        if key_data.get("kid") == kid:
            signing_key = RSAAlgorithm.from_jwk(json.dumps(key_data))
            break
    if signing_key is None:
        raise jwt.InvalidTokenError("JWKS kid not found")

    issuer = clerk_jwt_issuer()
    audiences = clerk_jwt_audiences()
    unverified = _jwt_payload_unverified(token)
    decode_kwargs: dict[str, Any] = {
        "algorithms": ["RS256"],
        "issuer": issuer,
    }
    # Only pass audience= when the token has an aud claim — PyJWT raises
    # MissingRequiredClaimError if we require audience on Clerk session tokens
    # that omit it. When aud is present, it must match our expected list.
    if unverified.get("aud"):
        decode_kwargs["audience"] = audiences

    payload = jwt.decode(token, signing_key, **decode_kwargs)

    azp = (payload.get("azp") or "").strip().rstrip("/")
    if azp:
        allowed = clerk_authorized_parties()
        if azp not in allowed:
            raise jwt.InvalidTokenError("Invalid authorized party")
    return payload


async def decode_clerk_jwt(token: str) -> dict[str, Any]:
    """Verify Clerk session JWT — BAPI session check first (Render-safe), JWKS fallback."""
    try:
        return await _verify_clerk_session_via_bapi(token)
    except ValueError:
        raise
    except httpx.HTTPError as exc:
        logger.warning("clerk bapi session verify network error: %s", exc)
    except Exception as exc:
        logger.warning("clerk bapi session verify failed: %s (%s)", type(exc).__name__, exc)
    try:
        return await _verify_clerk_jwt_jwks(token)
    except jwt.ExpiredSignatureError:
        raise ValueError("Clerk session expired. Sign out and sign in again")
    except jwt.InvalidTokenError as exc:
        logger.warning("clerk jwt invalid: %s (jwks=%s)", exc, CLERK_JWKS_URL)
        raise ValueError(
            "Invalid Clerk session token. Sign out, hard-refresh, and sign in again"
        ) from exc
    except Exception as exc:
        logger.warning("clerk jwks verify failed: %s (%s)", type(exc).__name__, exc)
        raise ValueError(
            "Could not verify Clerk session. Check CLERK_SECRET_KEY on Render matches clerk.trenston.com"
        ) from exc


async def fetch_clerk_user_profile(clerk_user_id: str, *, retries: int = 4) -> dict[str, Any]:
    import asyncio

    last_status: int | None = None
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(
                    f"{CLERK_BAPI}/users/{clerk_user_id}",
                    headers=_bapi_headers(),
                )
        except httpx.HTTPError as exc:
            if attempt < retries - 1:
                await asyncio.sleep(0.4 * (attempt + 1))
                continue
            raise ValueError("Clerk API unreachable. Try signing in again") from exc
        last_status = r.status_code
        if r.status_code in (401, 403):
            raise ValueError(
                "CLERK_SECRET_KEY rejected by Clerk API. Use the sk_live_ key from the same "
                "instance as pk_live on Vercel (clerk.trenston.com)"
            )
        if r.status_code == 404 and attempt < retries - 1:
            await asyncio.sleep(0.5 * (attempt + 1))
            continue
        if r.status_code == 404:
            raise ValueError(
                "Clerk user not found via API. Render CLERK_SECRET_KEY is likely from a "
                "different Clerk instance than your publishable key. In Clerk Dashboard → API keys "
                "(clerk.trenston.com), copy Secret key → Render CLERK_SECRET_KEY and redeploy."
            )
        if r.status_code >= 400:
            break
        data = r.json()
        emails = data.get("email_addresses") or []
        primary_id = data.get("primary_email_address_id")
        primary = next((e for e in emails if e.get("id") == primary_id), emails[0] if emails else None)
        email = (primary or {}).get("email_address")
        if not email:
            raise ValueError("Clerk user has no email")
        first = (data.get("first_name") or "").strip()
        last = (data.get("last_name") or "").strip()
        name = f"{first} {last}".strip() or None
        return {
            "clerk_id": clerk_user_id,
            "email": email,
            "name": name,
            "picture": data.get("image_url"),
        }
    raise ValueError(
        f"Clerk user lookup failed ({last_status}). Check CLERK_SECRET_KEY matches pk_live"
    )


async def verify_clerk_session_token(token: str) -> dict[str, Any]:
    """Validate Clerk session JWT and return stable identity fields for Trenston users."""
    payload = await decode_clerk_jwt(token)
    clerk_user_id = payload.get("sub")
    if not clerk_user_id:
        raise ValueError("Clerk token missing sub")
    return await fetch_clerk_user_profile(clerk_user_id)


async def sync_clerk_satellite_domain(primary: str) -> dict[str, Any]:
    """Register Trenston Vercel host as Clerk satellite domain so OAuth can redirect back."""
    from urllib.parse import urlparse

    host = urlparse(primary).hostname
    result: dict[str, Any] = {"attempted": True, "ok": False, "host": host}
    if not clerk_configured() or not host:
        result["reason"] = "not_configured"
        return result
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            headers = _bapi_headers()
            list_r = await client.get(f"{CLERK_BAPI}/domains", headers=headers)
            if list_r.status_code >= 400:
                result["reason"] = f"list_{list_r.status_code}"
                result["error"] = list_r.text[:300]
                return result
            domains = (list_r.json() or {}).get("data") or []
            result["existing_domains"] = [d.get("name") for d in domains]
            match = next((d for d in domains if d.get("name") == host), None)
            if match:
                result["ok"] = True
                result["reason"] = "already_registered"
                result["domain_id"] = match.get("id")
                return result
            add_r = await client.post(
                f"{CLERK_BAPI}/domains",
                headers=headers,
                json={"name": host, "is_satellite": True},
            )
            if add_r.status_code >= 400:
                result["reason"] = f"add_{add_r.status_code}"
                result["error"] = add_r.text[:500]
                return result
            created = add_r.json()
            result["ok"] = True
            result["reason"] = "created"
            result["domain_id"] = created.get("id")
            logger.info("Clerk satellite domain registered: %s", host)
            return result
    except Exception:
        logger.exception("Clerk satellite domain sync failed")
        result["reason"] = "exception"
        return result


async def sync_clerk_domain_proxy(primary: str) -> dict[str, Any]:
    """Enable Clerk FAPI proxy when clerk.* custom-domain TLS is not ready; clear when SSL is live."""
    from urllib.parse import urlparse

    host = urlparse(primary).hostname or ""
    apex = host[4:] if host.startswith("www.") else host
    proxy = f"https://{apex}/__clerk"
    result: dict[str, Any] = {"attempted": True, "ok": False, "proxy_url": proxy, "host": apex}
    if not clerk_configured() or not host:
        result["reason"] = "not_configured"
        return result
    ssl_ok = await clerk_custom_domain_ssl_ok()
    result["custom_domain_ssl_ok"] = ssl_ok
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            headers = _bapi_headers()
            list_r = await client.get(f"{CLERK_BAPI}/domains", headers=headers)
            if list_r.status_code >= 400:
                result["reason"] = f"list_{list_r.status_code}"
                result["error"] = list_r.text[:300]
                return result
            domains = (list_r.json() or {}).get("data") or []
            match = next((d for d in domains if d.get("name") in {apex, host}), None)
            if not match:
                result["reason"] = "domain_not_found"
                result["existing_domains"] = [d.get("name") for d in domains]
                return result
            domain_id = match.get("id")
            current = (match.get("proxy_url") or "").rstrip("/")

            if ssl_ok:
                if not current:
                    result["ok"] = True
                    result["reason"] = "ssl_ok_no_proxy"
                    result["domain_id"] = domain_id
                    return result
                patch_r = await client.patch(
                    f"{CLERK_BAPI}/domains/{domain_id}",
                    headers=headers,
                    json={"proxy_url": ""},
                )
                if patch_r.status_code >= 400:
                    result["reason"] = f"clear_{patch_r.status_code}"
                    result["error"] = patch_r.text[:500]
                    return result
                result["ok"] = True
                result["reason"] = "proxy_cleared_ssl_ok"
                result["domain_id"] = domain_id
                logger.info("Clerk domain proxy cleared — custom-domain SSL is live")
                return result

            if current == proxy.rstrip("/"):
                result["ok"] = True
                result["reason"] = "already_set"
                result["domain_id"] = domain_id
                return result
            patch_r = await client.patch(
                f"{CLERK_BAPI}/domains/{domain_id}",
                headers=headers,
                json={"proxy_url": proxy},
            )
            if patch_r.status_code >= 400:
                result["reason"] = f"patch_{patch_r.status_code}"
                result["error"] = patch_r.text[:500]
                return result
            result["ok"] = True
            result["reason"] = "proxy_enabled"
            result["domain_id"] = domain_id
            logger.info("Clerk domain proxy enabled: %s", proxy)
            return result
    except Exception:
        logger.exception("Clerk domain proxy sync failed")
        result["reason"] = "exception"
        return result


def _clerk_redirect_url_list() -> list[str]:
    origins = []
    for origin in helm_frontend_origins():
        if origin.startswith("http://localhost"):
            origins.append(origin)
            continue
        if origin.startswith("https://"):
            origins.append(origin)
    paths = (
        "/app",
        "/login",
        "/login/sso-callback",
        "/sign-up",
        "/sign-up/sso-callback",
        "/sign-up/verify-email-address",
        "/sign-up/continue",
    )
    urls: list[str] = []
    seen: set[str] = set()
    for origin in origins:
        base = origin.rstrip("/")
        for path in paths:
            url = f"{base}{path}"
            if url not in seen:
                seen.add(url)
                urls.append(url)
    post = clerk_post_auth_url()
    if post and post not in seen:
        urls.append(post)
    return urls


def _redirect_url_values(payload: Any) -> set[str]:
    rows: list[Any]
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("data"), list):
        rows = payload["data"]
    else:
        rows = []
    out: set[str] = set()
    for row in rows:
        if isinstance(row, dict):
            url = str(row.get("url") or "").strip()
            if url:
                out.add(url)
        elif isinstance(row, str) and row.strip():
            out.add(row.strip())
    return out


async def sync_clerk_redirect_urls() -> dict[str, Any]:
    """Register Trenston paths Clerk may redirect to after sign-up / OAuth."""
    result: dict[str, Any] = {"attempted": True, "ok": False, "added": [], "existing": []}
    if not clerk_configured():
        result["reason"] = "not_configured"
        return result
    wanted = _clerk_redirect_url_list()
    result["wanted"] = wanted
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            headers = _bapi_headers()
            get_r = await client.get(f"{CLERK_BAPI}/redirect_urls", headers=headers)
            if get_r.status_code >= 400:
                result["reason"] = f"get_{get_r.status_code}"
                result["error"] = get_r.text[:300]
                return result
            have = _redirect_url_values(get_r.json() if get_r.content else {})
            result["existing"] = sorted(have)
            added: list[str] = []
            errors: list[str] = []
            for url in wanted:
                if url in have:
                    continue
                post_r = await client.post(
                    f"{CLERK_BAPI}/redirect_urls",
                    headers=headers,
                    json={"url": url},
                )
                if post_r.status_code >= 400:
                    errors.append(f"{url}:{post_r.status_code}")
                    continue
                added.append(url)
                have.add(url)
            result["added"] = added
            result["errors"] = errors
            result["ok"] = not errors
            result["reason"] = "ok" if not errors else "partial"
            if added:
                logger.info("Clerk redirect URLs added: %s", ", ".join(added))
            return result
    except Exception:
        logger.exception("Clerk redirect URL sync failed")
        result["reason"] = "exception"
        return result


_signup_policy_cache: dict[str, Any] | None = None
_signup_policy_cache_at: float = 0.0


async def clerk_signup_policy() -> dict[str, Any]:
    """Password / CAPTCHA rules from Clerk FAPI (public environment)."""
    global _signup_policy_cache, _signup_policy_cache_at
    import time

    now = time.time()
    if _signup_policy_cache is not None and now - _signup_policy_cache_at < 600:
        return _signup_policy_cache
    empty = {"password_min_length": None, "captcha_enabled": None}
    host = clerk_jwks_host()
    if not host:
        return empty
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(f"https://{host}/v1/environment")
            if r.status_code != 200:
                return empty
            data = r.json() if r.content else {}
            us = data.get("user_settings") or {}
            pw = us.get("password_settings") or {}
            sign_up = us.get("sign_up") or {}
            out = {
                "password_min_length": pw.get("min_length"),
                "captcha_enabled": bool(sign_up.get("captcha_enabled")),
            }
            _signup_policy_cache = out
            _signup_policy_cache_at = now
            return out
    except Exception:
        logger.warning("Clerk FAPI environment fetch failed", exc_info=True)
        return empty


async def _clerk_fapi_display_config() -> dict[str, Any]:
    """Public Frontend API display_config (Paths + redirects). No secret required."""
    host = clerk_jwks_host()
    if not host:
        return {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"https://{host}/v1/environment")
            if r.status_code != 200:
                return {}
            data = r.json() if r.content else {}
            dc = data.get("display_config") or {}
            return dc if isinstance(dc, dict) else {}
    except Exception:
        logger.debug("Clerk FAPI display_config fetch failed", exc_info=True)
        return {}


def _display_paths_summary(dc: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "sign_in_url",
        "sign_up_url",
        "after_sign_in_url",
        "after_sign_up_url",
        "after_sign_out_all_url",
        "after_sign_out_one_url",
        "home_url",
        "logo_link_url",
    )
    return {k: dc.get(k) for k in keys}


def _paths_still_on_accounts(dc: dict[str, Any]) -> bool:
    for key in ("sign_in_url", "sign_up_url", "after_sign_out_all_url"):
        val = dc.get(key)
        if isinstance(val, str) and "accounts." in val:
            return True
    return False


async def _patch_clerk_json(
    client: httpx.AsyncClient,
    path: str,
    body: dict[str, Any],
    *,
    headers: dict[str, str],
) -> httpx.Response:
    """PATCH https://api.clerk.com/v1/<path> — always include /v1 (bare /account_portal → plain 404)."""
    return await client.patch(f"{CLERK_BAPI}/{path.lstrip('/')}", headers=headers, json=body)


async def sync_clerk_account_portal(primary: str, app_url: str | None = None) -> dict[str, Any]:
    """Point Clerk auth Paths at www Trenston — never leave users on accounts.*.

    accounts.trenston.com is Cloudflare-fronted and often serves bot challenges that break
    Google OAuth with Clerk's generic \"Unable to complete action at this time\". Auth must
    stay on https://www.trenston.com/login and /sign-up.

    Note: curl must use https://api.clerk.com/v1/account_portal (the /v1 segment is required;
    without it Clerk returns the plain text \"404 page not found\"). Paths (sign_in_url /
    sign_up_url) live on display_config; Account Portal after_* redirects are separate.
    """
    target = (app_url or f"{primary.rstrip('/')}/app").rstrip("/")
    if not target.endswith("/app"):
        target = f"{target}/app"
    # Prefer www for hosted components even when Clerk primary is apex.
    public = (primary_frontend_origin() or primary).rstrip("/")
    if "trenston.com" in public and not public.startswith("https://www."):
        public = "https://www.trenston.com"
    origin = public
    login = f"{origin}/login"
    signup = f"{origin}/sign-up"
    result: dict[str, Any] = {
        "attempted": True,
        "ok": False,
        "target_url": target,
        "sign_in_url": login,
        "sign_up_url": signup,
        "bapi_base": CLERK_BAPI,
    }
    if not clerk_configured() or not primary:
        result["reason"] = "not_configured"
        return result

    before_dc = await _clerk_fapi_display_config()
    result["before"] = _display_paths_summary(before_dc)

    # after_* on Account Portal may already be www while Paths still point at accounts.*.
    # Disable hosted Account Portal when we host /login + /sign-up — otherwise Clerk keeps
    # Paths on accounts.* (Cloudflare challenge → Google "Unable to complete action").
    portal_body = {
        "enabled": False,
        "after_sign_in_url": target,
        "after_sign_up_url": target,
        "logo_link_url": origin,
        "home_url": origin,
        "after_join_waitlist_url": target,
        "after_create_organization_url": target,
        "after_leave_organization_url": target,
        "after_sign_out_all_url": login,
        "after_sign_out_one_url": login,
    }
    # Paths — these are what bounce failed OAuth onto accounts.* (Cloudflare).
    display_body = {
        "home_url": origin,
        "sign_in_url": login,
        "sign_up_url": signup,
        "after_sign_in_url": target,
        "after_sign_up_url": target,
        "after_sign_out_all_url": login,
        "after_sign_out_one_url": login,
        "logo_link_url": origin,
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            headers = _bapi_headers()

            portal_r = await _patch_clerk_json(client, "account_portal", portal_body, headers=headers)
            result["account_portal_status"] = portal_r.status_code
            if portal_r.status_code == 422:
                # Some instances reject enabled=false via API — retry redirects only.
                no_enabled = {k: v for k, v in portal_body.items() if k != "enabled"}
                portal_r = await _patch_clerk_json(
                    client, "account_portal", no_enabled, headers=headers
                )
                result["account_portal_disabled_rejected"] = True
                result["account_portal_status"] = portal_r.status_code
            if portal_r.status_code == 404:
                result["account_portal_error"] = (
                    "404 from BAPI — confirm URL is https://api.clerk.com/v1/account_portal "
                    "(missing /v1 returns plain '404 page not found'). "
                    f"body={portal_r.text[:200]}"
                )
            elif portal_r.status_code == 422:
                slim = {
                    k: v
                    for k, v in portal_body.items()
                    if k not in ("after_sign_out_all_url", "after_sign_out_one_url", "enabled")
                }
                portal_r = await _patch_clerk_json(client, "account_portal", slim, headers=headers)
                result["account_portal_retried"] = True
                result["account_portal_status"] = portal_r.status_code
                if portal_r.status_code >= 400:
                    result["account_portal_error"] = portal_r.text[:500]
            elif portal_r.status_code >= 400:
                result["account_portal_error"] = portal_r.text[:500]

            display_r = await _patch_clerk_json(client, "display_config", display_body, headers=headers)
            result["display_config_status"] = display_r.status_code
            if display_r.status_code == 422:
                paths_only = {
                    "sign_in_url": login,
                    "sign_up_url": signup,
                    "home_url": origin,
                }
                display_r = await _patch_clerk_json(
                    client, "display_config", paths_only, headers=headers
                )
                result["display_config_retried"] = True
                result["display_config_status"] = display_r.status_code
            if display_r.status_code >= 400:
                result["display_config_error"] = display_r.text[:500]

        after_dc = await _clerk_fapi_display_config()
        result["after"] = _display_paths_summary(after_dc)
        still_accounts = _paths_still_on_accounts(after_dc)
        portal_ok = int(result.get("account_portal_status") or 500) < 400
        display_ok = int(result.get("display_config_status") or 500) < 400
        paths_ok = (
            after_dc.get("sign_in_url") == login and after_dc.get("sign_up_url") == signup
        )
        after_ok = after_dc.get("after_sign_in_url") == target

        if paths_ok and after_ok and not still_accounts:
            result["ok"] = True
            result["reason"] = "ok"
        elif still_accounts:
            result["ok"] = False
            result["reason"] = "paths_still_accounts"
            result["warning"] = (
                "Clerk Paths still point at accounts.* (Cloudflare-challenged). "
                f"Set Sign-in to {login} and Sign-up to {signup}, or Disable Account Portal "
                "in Clerk Dashboard → Account Portal (we already host /login and /sign-up)."
            )
        elif portal_ok or display_ok:
            result["ok"] = after_ok and not still_accounts
            result["reason"] = "ok" if result["ok"] else "partial"
        else:
            result["ok"] = False
            result["reason"] = (
                f"portal_{result.get('account_portal_status')}_"
                f"display_{result.get('display_config_status')}"
            )

        if result["ok"]:
            logger.info("Clerk auth Paths → www (login=%s signup=%s)", login, signup)
        else:
            logger.warning(
                "Clerk auth Paths still wrong: %s",
                result.get("warning") or result.get("reason"),
            )
        return result
    except Exception:
        logger.exception("Clerk account portal sync failed")
        result["reason"] = "exception"
        return result


async def sync_clerk_instance() -> dict[str, Any]:
    """Register Trenston Vercel origin with Clerk — required for dev instances on production URL."""
    global _last_sync_status
    wanted = helm_frontend_origins()
    primary = primary_frontend_origin()
    if not clerk_configured():
        _last_sync_status = {"synced": False, "reason": "clerk_not_configured"}
        return _last_sync_status
    if not wanted or not primary:
        _last_sync_status = {"synced": False, "reason": "no_frontend_origin"}
        return _last_sync_status

    status: dict[str, Any] = {
        "synced": False,
        "wanted_origins": wanted,
        "primary_origin": primary,
        "environment_type": None,
        "allowed_origins_before": [],
        "allowed_origins_after": [],
        "development_origin_set": None,
        "url_based_session_syncing": True,
        "warnings": [],
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            headers = _bapi_headers()
            r = await client.get(f"{CLERK_BAPI}/instance", headers=headers)
            if r.status_code >= 400:
                status["reason"] = f"instance_get_{r.status_code}"
                _last_sync_status = status
                return status

            inst = r.json()
            env_type = inst.get("environment_type")
            jwks_host = urlparse(CLERK_JWKS_URL).hostname or ""
            is_dev_fapi = jwks_host.endswith(".clerk.accounts.dev")
            current = set(inst.get("allowed_origins") or [])
            status["environment_type"] = env_type
            status["clerk_fapi_dev"] = is_dev_fapi
            status["allowed_origins_before"] = sorted(current)

            if is_dev_fapi or env_type == "development":
                status["warnings"].append(
                    "Clerk FAPI is a development instance (*.clerk.accounts.dev). "
                    "Sign-in works on Vercel after sync; create a Clerk production instance for a permanent fix."
                )

            merged = sorted(current | set(wanted))
            patch_body: dict[str, Any] = {
                "allowed_origins": merged,
                "url_based_session_syncing": True,
            }
            # development_origin only applies when BAPI reports development — not hybrid prod keys + dev FAPI.
            if env_type == "development":
                patch_body["development_origin"] = primary

            needs_patch = merged != sorted(current) or env_type == "development"
            if needs_patch:
                patch = await client.patch(
                    f"{CLERK_BAPI}/instance",
                    headers=headers,
                    json=patch_body,
                )
                if patch.status_code == 422 and "development_origin" in patch_body:
                    logger.warning("Clerk rejected development_origin — retrying without it")
                    retry_body = {k: v for k, v in patch_body.items() if k != "development_origin"}
                    patch = await client.patch(
                        f"{CLERK_BAPI}/instance",
                        headers=headers,
                        json=retry_body,
                    )
                if patch.status_code >= 400:
                    status["reason"] = f"instance_patch_{patch.status_code}"
                    status["patch_error"] = patch.text[:500]
                    _last_sync_status = status
                    logger.warning("Clerk instance PATCH failed (%s): %s", patch.status_code, patch.text[:200])
                    return status
                status["patched"] = True
                status["development_origin_set"] = patch_body.get("development_origin")
            else:
                status["patched"] = False

            verify = await client.get(f"{CLERK_BAPI}/instance", headers=headers)
            if verify.status_code == 200:
                after = verify.json()
                status["allowed_origins_after"] = sorted(after.get("allowed_origins") or [])
                status["environment_type"] = after.get("environment_type")

            missing = [o for o in wanted if o not in set(status["allowed_origins_after"])]
            status["missing_origins"] = missing
            status["synced"] = not missing
            if missing:
                status["reason"] = "origins_still_missing"
            else:
                status["reason"] = "ok"
                logger.info(
                    "Clerk instance synced for Trenston (env=%s, origins=%s, dev_origin=%s)",
                    status["environment_type"],
                    ", ".join(wanted),
                    patch_body.get("development_origin"),
                )

            if is_dev_fapi and primary and not any(h in primary for h in TRENSTON_PRIMARY_HOSTS):
                status["warnings"].append(
                    "Using Clerk development FAPI. Register trenston.com in Clerk Dashboard → Domains."
                )

            portal_primary = clerk_primary_origin() or primary
            portal_url = clerk_post_auth_url() or f"{primary.rstrip('/')}/app"
            portal = await sync_clerk_account_portal(portal_primary, portal_url)
            status["account_portal"] = portal
            status["clerk_primary_origin"] = clerk_primary_origin()
            status["clerk_post_auth_url"] = portal_url
            redirects = await sync_clerk_redirect_urls()
            status["redirect_urls"] = redirects
            satellite = await sync_clerk_satellite_domain(primary)
            status["satellite_domain"] = satellite
            domain_proxy = await sync_clerk_domain_proxy(primary)
            status["domain_proxy"] = domain_proxy
            if not portal.get("ok"):
                redirect_hint = portal_url
                status["warnings"].append(
                    "Could not auto-update Clerk redirect URLs. In Clerk Dashboard set every "
                    f"after sign-in / sign-up fallback to {redirect_hint} in Clerk Dashboard."
                )
            if redirects.get("reason") not in ("ok", "partial") or (
                redirects.get("reason") == "partial" and redirects.get("errors")
            ):
                status["warnings"].append(
                    "Could not register Clerk allowed redirect URLs. Add "
                    f"{portal_url} in Clerk Dashboard → Paths → Redirect URLs."
                )
            if not satellite.get("ok"):
                status["warnings"].append(
                    f"Could not register {urlparse(primary).hostname} as Clerk satellite domain. "
                    "add it manually in Clerk Dashboard → Configure → Domains."
                )
            if not domain_proxy.get("ok") and domain_proxy.get("reason") not in (
                "custom_domain_ssl_ok", "already_set",
            ):
                status["warnings"].append(
                    f"Could not enable Clerk proxy at {domain_proxy.get('proxy_url')}. "
                    "set it manually in Clerk Dashboard → Domains → Proxy URL after Vercel deploy."
                )

            _last_sync_status = status
            return status
    except Exception:
        logger.exception("Clerk instance sync failed")
        status["reason"] = "exception"
        _last_sync_status = status
        return status


async def ensure_allowed_origins() -> bool:
    """Back-compat wrapper — sync full Clerk instance settings for Trenston."""
    result = await sync_clerk_instance()
    return bool(result.get("synced"))


async def ensure_allowed_origins_legacy() -> bool:
    """Previous allowed_origins-only sync (kept for reference in tests)."""
    if not clerk_configured():
        return False
    wanted = set(helm_frontend_origins())
    if not wanted:
        return False
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            headers = _bapi_headers()
            r = await client.get(f"{CLERK_BAPI}/instance", headers=headers)
            if r.status_code >= 400:
                return False
            current = set(r.json().get("allowed_origins") or [])
            merged = sorted(current | wanted)
            if merged == sorted(current):
                return True
            patch = await client.patch(
                f"{CLERK_BAPI}/instance",
                headers=headers,
                json={"allowed_origins": merged},
            )
            return patch.status_code < 400
    except Exception:
        logger.exception("Clerk allowed_origins sync failed")
        return False
