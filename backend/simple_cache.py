"""Minimal in-process TTL cache for single-instance Render deploys.

No Redis / external deps — a plain dict keyed by string with monotonic expiry.
Hit/miss counters make production verification possible via /api/health.

Generation/epoch guards prevent a slow loader that started before invalidate()
from writing stale values back after a newer generation was published.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

logger = logging.getLogger("helm.cache")

_store: dict[str, tuple[Any, float, int]] = {}
_generations: dict[str, int] = {}
_hits = 0
_misses = 0


def _bump_generation(key: str) -> int:
    nxt = _generations.get(key, 0) + 1
    _generations[key] = nxt
    return nxt


def _current_generation(key: str) -> int:
    return _generations.get(key, 0)


async def get_or_set(
    key: str,
    ttl_seconds: float,
    loader: Callable[[], Awaitable[Any]],
) -> Any:
    """Return cached value if fresh; otherwise await loader(), store, return.

    If invalidate(key) runs while loader is in flight, the loader result is
    discarded so a stale generation cannot overwrite a fresher miss.
    """
    global _hits, _misses
    now = time.monotonic()
    row = _store.get(key)
    if row is not None and row[1] > now:
        _hits += 1
        logger.debug("cache hit key=%s", key)
        return row[0]
    _misses += 1
    logger.debug("cache miss key=%s", key)
    gen = _current_generation(key)
    value = await loader()
    if _current_generation(key) != gen:
        # Invalidated while loading — do not put stale value.
        logger.debug("cache discard stale load key=%s", key)
        return value
    _store[key] = (value, time.monotonic() + float(ttl_seconds), gen)
    return value


def peek(key: str) -> Any | None:
    """Return cached value if present and unexpired; else None (no loader)."""
    global _hits, _misses
    now = time.monotonic()
    row = _store.get(key)
    if row is not None and row[1] > now:
        _hits += 1
        return row[0]
    _misses += 1
    return None


def put(key: str, value: Any, ttl_seconds: float) -> None:
    """Store a value with TTL without going through a loader."""
    gen = _current_generation(key)
    _store[key] = (value, time.monotonic() + float(ttl_seconds), gen)


def invalidate(key: str) -> bool:
    """Drop one key and bump its generation. Returns True if it was present."""
    _bump_generation(key)
    return _store.pop(key, None) is not None


def invalidate_prefix(prefix: str) -> int:
    """Drop every key that starts with prefix. Returns count removed."""
    if not prefix:
        return 0
    dead = [k for k in _store if k.startswith(prefix)]
    touched = set(dead)
    for k in list(_generations):
        if k.startswith(prefix):
            touched.add(k)
    for k in touched:
        _bump_generation(k)
        _store.pop(k, None)
    return len(dead)


def stats() -> dict[str, Any]:
    """Hit/miss/size snapshot for health checks."""
    now = time.monotonic()
    live = sum(1 for _v, exp, _g in _store.values() if exp > now)
    return {
        "hits": _hits,
        "misses": _misses,
        "entries": len(_store),
        "live_entries": live,
        "hit_rate": round(_hits / (_hits + _misses), 4) if (_hits + _misses) else None,
    }


def clear() -> None:
    """Wipe store + counters (tests / process recycle)."""
    global _hits, _misses
    _store.clear()
    _generations.clear()
    _hits = 0
    _misses = 0
