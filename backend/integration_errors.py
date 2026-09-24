"""Shared OAuth/integration error classification helpers."""
from __future__ import annotations

import json
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Provider refresh responses that mean the grant is gone — wipe stored tokens.
_REVOKED_ERROR_CODES = frozenset({
    "invalid_grant",
    "invalid_token",
    "expired_token",
    "revoked",
    "unauthorized_client",
})


class IntegrationRetryableError(Exception):
    """Transient provider/network failure — keep tokens; client should retry later."""


def _error_code_from_body(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        lower = raw.lower()
        for code in _REVOKED_ERROR_CODES:
            if code in lower:
                return code
        return ""
    if not isinstance(payload, dict):
        return ""
    for key in ("error", "errorCode", "ErrorCode", "code"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip().lower()
    # Intuit nested fault shape
    fault = payload.get("fault") or payload.get("Fault") or {}
    if isinstance(fault, dict):
        err = fault.get("error") or fault.get("Error") or []
        if isinstance(err, list) and err:
            first = err[0] if isinstance(err[0], dict) else {}
            code = first.get("code") or first.get("error") or ""
            if isinstance(code, str):
                return code.strip().lower()
        elif isinstance(err, dict):
            code = err.get("code") or err.get("error") or ""
            if isinstance(code, str):
                return code.strip().lower()
    return ""


def is_revoked_refresh_response(status_code: int, body: str) -> bool:
    """True only when the provider confirms the refresh grant is invalid/revoked."""
    if status_code not in (400, 401):
        return False
    code = _error_code_from_body(body)
    if code in _REVOKED_ERROR_CODES:
        return True
    # Some providers return 400/401 with only a message containing invalid_grant.
    lower = (body or "").lower()
    return "invalid_grant" in lower


def classify_refresh_http_failure(
    *,
    provider: str,
    status_code: int,
    body: str,
    auth_error_cls: type[Exception],
    retryable_error_cls: type[Exception] = IntegrationRetryableError,
) -> Exception:
    """Map a non-200 token-refresh HTTP response to auth vs retryable."""
    snippet = (body or "")[:300]
    if is_revoked_refresh_response(status_code, body):
        return auth_error_cls(snippet or f"{provider} token refresh revoked")
    if status_code >= 500 or status_code in (408, 429):
        logger.warning(
            "%s token refresh temporarily unavailable (%s): %s",
            provider, status_code, snippet,
        )
        return retryable_error_cls(
            f"{provider} token refresh temporarily unavailable ({status_code})"
        )
    # Other 4xx without invalid_grant — treat as auth (misconfig / bad request).
    if 400 <= status_code < 500:
        return auth_error_cls(snippet or f"{provider} token refresh failed")
    logger.warning(
        "%s token refresh unexpected status (%s): %s",
        provider, status_code, snippet,
    )
    return retryable_error_cls(
        f"{provider} token refresh temporarily unavailable ({status_code})"
    )


def classify_refresh_transport_error(
    *,
    provider: str,
    exc: BaseException,
    retryable_error_cls: type[Exception] = IntegrationRetryableError,
) -> Exception:
    logger.warning("%s token refresh network/timeout error: %s", provider, exc)
    return retryable_error_cls(f"{provider} token refresh temporarily unavailable")


def force_token_refresh(tokens: dict) -> dict:
    """Return a copy that will always refresh on the next refresh_*_token call."""
    out = dict(tokens)
    out["obtained_at"] = "1970-01-01T00:00:00+00:00"
    return out


async def refresh_http_post(
    *,
    provider: str,
    url: str,
    data: dict,
    auth: Optional[tuple[str, str]] = None,
    headers: Optional[dict] = None,
    auth_error_cls: type[Exception],
    retryable_error_cls: type[Exception] = IntegrationRetryableError,
    timeout: float = 30.0,
) -> httpx.Response:
    """POST to a token endpoint; raise auth/retryable on non-200."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as hc:
            resp = await hc.post(url, data=data, auth=auth, headers=headers or {"Accept": "application/json"})
    except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
        raise classify_refresh_transport_error(
            provider=provider, exc=exc, retryable_error_cls=retryable_error_cls,
        ) from exc
    if resp.status_code == 200:
        return resp
    raise classify_refresh_http_failure(
        provider=provider,
        status_code=resp.status_code,
        body=resp.text or "",
        auth_error_cls=auth_error_cls,
        retryable_error_cls=retryable_error_cls,
    )
