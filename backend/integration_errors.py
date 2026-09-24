"""Shared OAuth/integration error classification helpers."""
from __future__ import annotations

import json
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class IntegrationRetryableError(Exception):
    """Transient provider/network failure — keep tokens; client should retry later."""


def is_revoked_refresh_response(status_code: int, body: str) -> bool:
    """True only for HTTP 400/401 whose JSON body has ``error == "invalid_grant"``.

    Intuit, Xero and Google all report a revoked/expired refresh grant this way.
    Anything else (5xx, 429, other 4xx, non-JSON bodies) is transient.
    """
    if status_code not in (400, 401):
        return False
    try:
        payload = json.loads(body or "")
    except (json.JSONDecodeError, TypeError, ValueError):
        return False
    if not isinstance(payload, dict):
        return False
    err = payload.get("error")
    return isinstance(err, str) and err.strip().lower() == "invalid_grant"


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
    # Wipe only on confirmed invalid_grant. 429, other 4xx and 5xx keep
    # tokens and surface as retryable so a misconfig blip does not force reconnect.
    logger.warning(
        "%s token refresh temporarily unavailable (%s): %s",
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
        try:
            payload = resp.json()
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("%s token refresh returned invalid JSON", provider)
            raise retryable_error_cls(f"{provider} token refresh temporarily unavailable") from exc
        if not isinstance(payload, dict):
            raise retryable_error_cls(f"{provider} token refresh temporarily unavailable")
        return resp
    raise classify_refresh_http_failure(
        provider=provider,
        status_code=resp.status_code,
        body=resp.text or "",
        auth_error_cls=auth_error_cls,
        retryable_error_cls=retryable_error_cls,
    )
