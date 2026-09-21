"""Paddle webhook source IPs — fetched from https://api.paddle.com/ips, never hardcoded."""
from __future__ import annotations

import ipaddress
import logging
import time

import httpx

logger = logging.getLogger(__name__)

PADDLE_IPS_URL = "https://api.paddle.com/ips"
_CACHE_TTL_S = 3600
_cache: dict = {"fetched_at": 0.0, "networks": []}


def _parse_cidrs(payload: dict) -> list:
    cidrs = ((payload or {}).get("data") or {}).get("ipv4_cidrs") or []
    nets = []
    for raw in cidrs:
        try:
            nets.append(ipaddress.ip_network(str(raw).strip(), strict=False))
        except ValueError:
            logger.warning("Ignoring invalid Paddle CIDR %r", raw)
    return nets


async def refresh_paddle_ip_networks(*, force: bool = False) -> list:
    """Return cached IPv4 networks, refreshing from Paddle when stale."""
    now = time.time()
    if not force and _cache["networks"] and (now - _cache["fetched_at"]) < _CACHE_TTL_S:
        return _cache["networks"]
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(PADDLE_IPS_URL)
        resp.raise_for_status()
        nets = _parse_cidrs(resp.json())
    except Exception:
        logger.exception("Could not refresh Paddle webhook IP list")
        return list(_cache["networks"])
    if nets:
        _cache["networks"] = nets
        _cache["fetched_at"] = now
    return list(_cache["networks"])


def ip_allowed(ip: str, networks: list) -> bool:
    if not networks:
        return False
    try:
        addr = ipaddress.ip_address((ip or "").strip())
    except ValueError:
        return False
    return any(addr in net for net in networks)


def reset_cache_for_tests() -> None:
    _cache["fetched_at"] = 0.0
    _cache["networks"] = []
