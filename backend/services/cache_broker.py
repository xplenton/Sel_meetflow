"""Cross-pod cache-invalidation broker (iter 204).

Why?
-----
We run several in-memory TTL caches in front of hot, idempotent reads
(`permissions_cache`, `user_cache`, `pending_count_cache`). On a single pod
this is perfect. As soon as we scale horizontally (multiple FastAPI workers
behind the K8s ingress) every pod has its own copy of those dicts and an
invalidate() call on pod A no longer affects pod B's cache → stale reads
until TTL expires.

Solution: Redis Pub/Sub. Whenever a pod invalidates a cache entry locally,
it also publishes a tiny envelope on a shared channel. Every pod subscribes
and drops the matching local entry, ignoring its own publishes (pod_id
filter) to avoid pointless dupes.

If REDIS_URL is unset or unreachable, the broker silently degrades to a
no-op — single-pod mode keeps working exactly as before.

Mirrors the lifecycle of `services/ws_broker.py` (start during lifespan,
graceful stop on shutdown) so we get free crash-resilience.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Any, Awaitable, Callable, Dict, Optional

logger = logging.getLogger(__name__)

_CHANNEL = "cache_invalidate"
# A handler is `async def(user_id: Optional[str]) -> None`. user_id=None means
# "invalidate everything in this namespace".
Handler = Callable[[Optional[str]], Awaitable[None]]


class CacheInvalidationBroker:
    def __init__(self) -> None:
        self.pod_id = uuid.uuid4().hex[:12]
        self._redis: Optional[Any] = None
        self._pubsub: Optional[Any] = None
        self._sub_task: Optional[asyncio.Task] = None
        self._handlers: Dict[str, Handler] = {}
        self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def register(self, namespace: str, handler: Handler) -> None:
        """Wire a cache module's local-drop function to incoming invalidations.

        Called at module import time — safe to call before start()."""
        self._handlers[namespace] = handler

    async def start(self) -> None:
        url = os.environ.get("REDIS_URL")
        if not url:
            logger.info("[cache_broker] REDIS_URL not set — running in single-pod mode")
            return
        try:
            import redis.asyncio as aioredis  # type: ignore
            self._redis = aioredis.from_url(url, decode_responses=True)
            await self._redis.ping()
            self._pubsub = self._redis.pubsub()
            await self._pubsub.subscribe(_CHANNEL)
            self._sub_task = asyncio.create_task(self._listen_loop())
            self._enabled = True
            logger.info(f"[cache_broker] ✓ connected to Redis, pod_id={self.pod_id}")
        except Exception as e:
            logger.warning(f"[cache_broker] init failed ({e!r}) — running in single-pod mode")
            self._redis = None
            self._pubsub = None
            self._enabled = False

    async def stop(self) -> None:
        if self._sub_task:
            self._sub_task.cancel()
            try:
                await self._sub_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._pubsub:
            try:
                await self._pubsub.unsubscribe(_CHANNEL)
                await self._pubsub.close()
            except Exception:
                pass
        if self._redis:
            try:
                await self._redis.close()
            except Exception:
                pass

    async def publish(self, namespace: str, user_id: Optional[str] = None) -> None:
        """Broadcast an invalidation. The local cache must already have been
        cleared by the caller — Redis is just the fan-out mechanism."""
        if not self._enabled or not self._redis:
            return
        try:
            await self._redis.publish(_CHANNEL, json.dumps({
                "pod": self.pod_id,
                "ns": namespace,
                "uid": user_id,  # None = invalidate-all in this namespace
            }))
        except Exception as e:
            # Network blip shouldn't break the calling write path. Worst case:
            # other pods serve stale entries until TTL expires.
            logger.warning(f"[cache_broker] publish failed ({e!r}) — falling back to TTL")

    async def _listen_loop(self) -> None:
        assert self._pubsub is not None
        try:
            async for msg in self._pubsub.listen():
                if msg.get("type") != "message":
                    continue
                try:
                    data = json.loads(msg.get("data") or "{}")
                except Exception:
                    continue
                # Skip messages we sent ourselves — local cache is already in sync.
                if data.get("pod") == self.pod_id:
                    continue
                ns = data.get("ns")
                handler = self._handlers.get(ns) if ns else None
                if not handler:
                    continue
                try:
                    await handler(data.get("uid"))
                except Exception as e:
                    logger.warning(f"[cache_broker] handler({ns}) failed: {e!r}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"[cache_broker] listen loop crashed: {e!r}")


cache_broker = CacheInvalidationBroker()
