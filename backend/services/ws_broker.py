"""
Redis Pub/Sub broker for cross-pod WebSocket fan-out.

Problem solved (Phase B of iter 174 load test):
  When MeetFlow runs across ≥ 2 FastAPI pods behind a load balancer, each
  pod owns a different subset of WebSocket connections. A chat message
  created on Pod A cannot reach a user connected on Pod B because the two
  in-memory connection dicts don't know about each other.

Solution:
  Every pod publishes its WS envelopes to a shared Redis pub/sub channel.
  Every pod also subscribes to that channel and, on each incoming message,
  dispatches to any LOCAL connections that match the envelope's target.

Envelope shape (JSON):
  {
    "kind":   "user" | "conversation" | "status",
    "target": "<user_id | conversation_id>",    # optional for "status"
    "pod":    "<uuid>",                         # sender pod id
    "data":   {...}                             # payload forwarded as-is
  }

If REDIS_URL is not set or Redis is unreachable at startup, the broker
silently degrades to single-pod mode (publish() + the subscriber become
no-ops and the existing in-memory fan-out in ChatWSManager still works).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Any, Callable, Optional

logger = logging.getLogger("ws_broker")

_REDIS_CHANNEL = "meetflow:ws"


class RedisWsBroker:
    """Singleton broker: publishes WS envelopes to Redis and subscribes for
    envelopes produced by other pods.

    `local_dispatch(envelope)` is the callback that performs the actual
    delivery to in-memory WebSocket connections on THIS pod. It is registered
    by the caller (ChatWSManager) after instantiation.
    """

    def __init__(self) -> None:
        self.pod_id = uuid.uuid4().hex[:12]
        self._redis: Any = None
        self._pubsub: Any = None
        self._sub_task: Optional[asyncio.Task] = None
        # iter 211 — support multiple dispatchers (chat + meetings + future
        # subsystems can each register independently). `_local_dispatch` is
        # kept as the legacy single-shot setter for backwards compat.
        self._local_dispatch: Optional[Callable[[dict], Any]] = None
        self._dispatchers: list = []
        self._enabled = False

    def set_dispatcher(self, fn: Callable[[dict], Any]) -> None:
        # Legacy API — still works, registers as one of several handlers.
        self._local_dispatch = fn

    def register_dispatcher(self, fn: Callable[[dict], Any]) -> None:
        """Register an additional async dispatcher. Every incoming envelope
        is delivered to ALL registered dispatchers AND to the legacy
        `_local_dispatch` (if set). Each handler is responsible for filtering
        envelopes it cares about (typically by `kind`)."""
        if fn not in self._dispatchers:
            self._dispatchers.append(fn)

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def start(self) -> None:
        """Connect to Redis, start the subscriber task. Safe to call once."""
        url = os.environ.get("REDIS_URL")
        if not url:
            logger.info("[ws_broker] REDIS_URL not set — running in single-pod mode")
            return
        try:
            import redis.asyncio as aioredis  # type: ignore
            self._redis = aioredis.from_url(url, decode_responses=True)
            # Verify connectivity before committing to enabled state
            await self._redis.ping()
            self._pubsub = self._redis.pubsub()
            await self._pubsub.subscribe(_REDIS_CHANNEL)
            self._sub_task = asyncio.create_task(self._listen_loop())
            self._enabled = True
            logger.info(f"[ws_broker] ✓ connected to Redis, pod_id={self.pod_id}")
        except Exception as e:
            logger.warning(f"[ws_broker] init failed ({e!r}) — running in single-pod mode")
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
                await self._pubsub.unsubscribe(_REDIS_CHANNEL)
                await self._pubsub.close()
            except Exception:
                pass
        if self._redis:
            try:
                await self._redis.close()
            except Exception:
                pass

    async def publish(self, kind: str, data: dict, target: str = "") -> None:
        """Publish a WS envelope to the shared Redis channel.

        If Redis is disabled, this is a no-op — the caller is expected to
        also do its local fan-out directly.
        """
        if not self._enabled or not self._redis:
            return
        envelope = {
            "kind": kind,
            "target": target,
            "pod": self.pod_id,
            "data": data,
        }
        try:
            await self._redis.publish(_REDIS_CHANNEL, json.dumps(envelope))
        except Exception as e:
            logger.warning(f"[ws_broker] publish failed: {e!r}")

    # ---- Presence (cross-pod online set) ---------------------------------
    # Iter 176.2 — track "who is online" in a Redis sorted-set keyed by
    # user_id with `last_heartbeat` as the score. 60 s TTL → a pod crash
    # lets stale entries expire automatically without manual cleanup.
    _PRESENCE_KEY = "meetflow:presence"
    _PRESENCE_TTL = 60  # seconds

    async def mark_online(self, user_id: str) -> None:
        if not self._enabled or not self._redis or not user_id:
            return
        try:
            import time as _t
            await self._redis.zadd(self._PRESENCE_KEY, {user_id: _t.time()})
        except Exception as e:
            logger.warning(f"[ws_broker] mark_online failed: {e!r}")

    async def mark_offline(self, user_id: str) -> None:
        if not self._enabled or not self._redis or not user_id:
            return
        try:
            await self._redis.zrem(self._PRESENCE_KEY, user_id)
        except Exception as e:
            logger.warning(f"[ws_broker] mark_offline failed: {e!r}")

    async def is_online(self, user_id: str) -> bool:
        """True iff user heartbeated within the last _PRESENCE_TTL seconds."""
        if not self._enabled or not self._redis or not user_id:
            return False
        try:
            import time as _t
            cutoff = _t.time() - self._PRESENCE_TTL
            score = await self._redis.zscore(self._PRESENCE_KEY, user_id)
            return bool(score and score >= cutoff)
        except Exception:
            return False

    async def online_users(self) -> list:
        """Return the list of currently-online user_ids across all pods."""
        if not self._enabled or not self._redis:
            return []
        try:
            import time as _t
            cutoff = _t.time() - self._PRESENCE_TTL
            # ZRANGEBYSCORE keeps only live heartbeats
            ids = await self._redis.zrangebyscore(self._PRESENCE_KEY, cutoff, "+inf")
            return list(ids or [])
        except Exception:
            return []

    async def sweep_presence(self) -> int:
        """Drop stale entries (older than TTL). Returns count removed."""
        if not self._enabled or not self._redis:
            return 0
        try:
            import time as _t
            cutoff = _t.time() - self._PRESENCE_TTL
            return int(await self._redis.zremrangebyscore(self._PRESENCE_KEY, 0, cutoff))
        except Exception:
            return 0

    async def _listen_loop(self) -> None:
        """Read envelopes from Redis and dispatch to local connections."""
        assert self._pubsub is not None
        try:
            async for msg in self._pubsub.listen():
                if msg.get("type") != "message":
                    continue
                raw = msg.get("data")
                if not raw:
                    continue
                try:
                    envelope = json.loads(raw)
                except Exception:
                    continue
                # Skip our own messages — they were already delivered
                # locally by the caller (ChatWSManager uses LOCAL fan-out
                # directly and relies on pub/sub only for CROSS-POD delivery).
                if envelope.get("pod") == self.pod_id:
                    continue
                # iter 211 — fan out to legacy single dispatcher AND every
                # registered additive dispatcher. Each is responsible for
                # filtering envelopes by `kind`.
                handlers = []
                if self._local_dispatch is not None:
                    handlers.append(self._local_dispatch)
                handlers.extend(self._dispatchers)
                for handler in handlers:
                    try:
                        res = handler(envelope)
                        if asyncio.iscoroutine(res):
                            await res
                    except Exception as e:
                        logger.warning(f"[ws_broker] dispatch failed: {e!r}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"[ws_broker] listen loop died: {e!r}")
            self._enabled = False


# Singleton
ws_broker = RedisWsBroker()
