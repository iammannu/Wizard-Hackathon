"""
In-process TTL cache replacing Redis.
Good enough for a single-process dev server.
When you need shared cache across workers/deploys, swap this for Redis:
  - pip install redis[asyncio]
  - replace get/set with redis.get/redis.setex
"""
import time
from typing import Any

_store: dict[str, tuple[Any, float]] = {}


def cache_get(key: str) -> Any | None:
    entry = _store.get(key)
    if not entry:
        return None
    value, expires_at = entry
    if time.time() > expires_at:
        del _store[key]
        return None
    return value


def cache_set(key: str, value: Any, ttl: int = 60) -> None:
    _store[key] = (value, time.time() + ttl)
