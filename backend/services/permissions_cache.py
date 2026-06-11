"""TTL cache for /api/user/permissions (iter 202).

Backed by a simple in-memory dict + timestamps. The /user/permissions endpoint
is hit on every page-load — caching shaves p99 from ~4.6s to <100ms under load
(see /app/test_reports/iter201_load_200users.md).

Invalidation:
- TTL: 60 seconds per user. Stale-tolerant — admin role changes propagate within
  one minute which is acceptable for a clinic comms platform.
- Explicit invalidate(user_id): call from admin role/grant/group endpoints.
- Bulk invalidate(): when admin changes group capabilities (affects many users).

Iter 204 — invalidations are also broadcast over Redis Pub/Sub so other pods
running the same service drop their local L1 entries; falls back to local-only
when REDIS_URL is unset (see services/cache_broker.py).
"""
import asyncio
import time
from typing import Any, Dict, Optional

from services.cache_broker import cache_broker

_NS = "permissions"
_TTL_SECONDS = 60
_lock = asyncio.Lock()
_cache: Dict[str, tuple[float, Any]] = {}


async def get(user_id: str) -> Optional[Any]:
    """Return cached payload for user_id, or None if missing/expired."""
    async with _lock:
        entry = _cache.get(user_id)
        if not entry:
            return None
        ts, payload = entry
        if time.time() - ts > _TTL_SECONDS:
            _cache.pop(user_id, None)
            return None
        return payload


async def set(user_id: str, payload: Any) -> None:
    async with _lock:
        _cache[user_id] = (time.time(), payload)


async def _drop_local(user_id: Optional[str]) -> None:
    async with _lock:
        if user_id is None:
            _cache.clear()
        else:
            _cache.pop(user_id, None)


async def invalidate(user_id: str) -> None:
    """Drop the cache entry for one user (this pod + broadcast to peers)."""
    await _drop_local(user_id)
    await cache_broker.publish(_NS, user_id)


async def invalidate_all() -> None:
    """Drop all cache entries (e.g. when capabilities catalog changes)."""
    await _drop_local(None)
    await cache_broker.publish(_NS, None)


def stats() -> Dict[str, int]:
    return {"entries": len(_cache), "ttl_seconds": _TTL_SECONDS}


# Subscribe to invalidation broadcasts from other pods.
cache_broker.register(_NS, _drop_local)
