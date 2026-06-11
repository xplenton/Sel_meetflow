"""TTL cache for /api/tasks/pending-count (iter 203).

The Sidebar polls this endpoint every ~60s per active client. With 200+
concurrent clinic users, that's a steady stream of count queries. Two indexed
count_documents calls per request are cheap individually, but in aggregate they
add measurable load and lock pressure on the read-replica.

Strategy:
- Per-user dict cache with a 30-second TTL — short enough that newly assigned
  tasks show up in the badge within half a polling cycle, long enough to cut
  read traffic by ~95% under steady-state polling.
- Invalidate explicitly when a task is created, updated (status/assignee/
  archived change), or deleted. The route layer is the single source of
  invalidation calls so the service layer stays cache-agnostic.

Iter 204 — invalidations are broadcast cross-pod via Redis Pub/Sub
(services/cache_broker.py); falls back to local-only when REDIS_URL is unset.
"""
import asyncio
import time
from typing import Any, Dict, Iterable, Optional

from services.cache_broker import cache_broker

_NS = "pending_count"
_TTL_SECONDS = 30
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


async def invalidate_many(user_ids: Iterable[str]) -> None:
    """Drop entries for a batch of users (e.g. all assignees of a task).

    Publishes one Redis message per user-id so peers stay in sync. Cheap —
    typical assignee-set size is 1-5 users."""
    ids = [u for u in (user_ids or []) if u]
    if not ids:
        return
    async with _lock:
        for uid in ids:
            _cache.pop(uid, None)
    for uid in ids:
        await cache_broker.publish(_NS, uid)


async def invalidate_all() -> None:
    await _drop_local(None)
    await cache_broker.publish(_NS, None)


def stats() -> Dict[str, int]:
    return {"entries": len(_cache), "ttl_seconds": _TTL_SECONDS}


cache_broker.register(_NS, _drop_local)
