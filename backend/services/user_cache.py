"""Per-request user-document cache (iter 202).

Mirrors permissions_cache.py but with a much shorter TTL (5s) since user
documents are mutated more frequently (status, last_seen etc.) and we don't
want stale data to linger.

Use case: under heavy concurrent traffic, get_current_user() is called once
per HTTP request. With many requests per second from a single user (page
loads + polling), this saves dozens of db.users.find_one() calls.

Invalidation:
- TTL: 5 seconds.
- Explicit invalidate(user_id): call from admin endpoints that mutate the user.

Iter 204 — invalidations are broadcast cross-pod via Redis Pub/Sub
(services/cache_broker.py); falls back to local-only when REDIS_URL is unset.
"""
import asyncio
import time
from typing import Any, Dict, Optional

from services.cache_broker import cache_broker

_NS = "user"
_TTL_SECONDS = 5
_lock = asyncio.Lock()
_cache: Dict[str, tuple[float, Any]] = {}


async def get(user_id: str) -> Optional[Any]:
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
    await _drop_local(user_id)
    await cache_broker.publish(_NS, user_id)


async def invalidate_all() -> None:
    await _drop_local(None)
    await cache_broker.publish(_NS, None)


def stats() -> Dict[str, int]:
    return {"entries": len(_cache), "ttl_seconds": _TTL_SECONDS}


cache_broker.register(_NS, _drop_local)
