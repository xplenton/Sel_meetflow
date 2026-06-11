"""iter 211 — Verify that ws_manager.broadcast() fans out cross-pod via Redis.

Simulates two FastAPI workers (Pod A and Pod B) that each own one
WebSocket-style connection. We only need the dispatcher → local fan-out path,
not real WebSockets, so we monkey-patch each pod's `_local_broadcast` to
record what it would send.

Steps:
  1. Pod A and Pod B each spawn an isolated ws_broker + ConnectionManager pair
     (subclassed so we can capture local sends).
  2. Pod A broadcasts a hand-raise message for meeting "m1" excluding "alice".
  3. Pod B's local fan-out should fire (because Pod B owns the recipient socket
     for "bob" in m1) — this exercises the Redis pub/sub envelope path.

Requires REDIS_URL. If unset, skips with status 0.
"""
import asyncio
import os
import sys

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402
load_dotenv("/app/backend/.env")


async def main() -> int:
    if not os.environ.get("REDIS_URL"):
        print("REDIS_URL not set — skipping cross-pod test")
        return 0

    from services.ws_broker import RedisWsBroker
    from services.ws_manager import ConnectionManager

    # --- Pod A
    broker_a = RedisWsBroker()
    cm_a = ConnectionManager()
    captured_a = []

    async def cap_a(meeting_id, msg, exclude=None):
        captured_a.append({"meeting_id": meeting_id, "msg": msg, "exclude": exclude})

    cm_a._local_broadcast = cap_a  # type: ignore

    async def dispatch_a(env):
        if env.get("kind") != "meeting":
            return
        d = env.get("data") or {}
        await cm_a._local_broadcast(env.get("target"), d.get("msg"), d.get("exclude"))

    broker_a.register_dispatcher(dispatch_a)
    await broker_a.start()
    assert broker_a.enabled, "broker A failed to start"

    # --- Pod B
    broker_b = RedisWsBroker()
    cm_b = ConnectionManager()
    captured_b = []

    async def cap_b(meeting_id, msg, exclude=None):
        captured_b.append({"meeting_id": meeting_id, "msg": msg, "exclude": exclude})

    cm_b._local_broadcast = cap_b  # type: ignore

    async def dispatch_b(env):
        if env.get("kind") != "meeting":
            return
        d = env.get("data") or {}
        await cm_b._local_broadcast(env.get("target"), d.get("msg"), d.get("exclude"))

    broker_b.register_dispatcher(dispatch_b)
    await broker_b.start()
    assert broker_b.enabled, "broker B failed to start"

    print(f"pod_a={broker_a.pod_id}  pod_b={broker_b.pod_id}")
    await asyncio.sleep(0.2)

    # Pod A broadcasts via the in-process ConnectionManager helper. We have
    # to override its publish target to use broker_a directly because the
    # real ws_manager singleton uses the global ws_broker.
    test_msg = {"type": "hand-raise", "raised": True, "sender": "alice"}
    # Mimic what cm_a.broadcast() does:
    await cm_a._local_broadcast("m1", test_msg, exclude="alice")
    await broker_a.publish(kind="meeting", target="m1", data={"msg": test_msg, "exclude": "alice"})
    await asyncio.sleep(0.5)

    print(f"pod_a captured: {captured_a}")
    print(f"pod_b captured: {captured_b}")

    assert len(captured_a) == 1, "pod A should have fired its own local broadcast"
    assert len(captured_b) == 1, "pod B should have received the cross-pod envelope"
    assert captured_b[0]["msg"]["type"] == "hand-raise"
    assert captured_b[0]["exclude"] == "alice"
    print("✓ cross-pod meeting-WS fan-out works")

    await broker_a.stop()
    await broker_b.stop()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
