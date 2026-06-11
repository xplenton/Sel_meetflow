"""Regression test for iter 176 — Redis Pub/Sub cross-pod fan-out.

Simulates two pods:
  * Pod A has a fake WebSocket connection for user "alice"
  * Pod B calls `send_to_user("alice", {...})`

Expected: via Redis pub/sub, Pod A's local dispatcher fires and the fake
WS on Pod A receives the payload.

Run:  python3 /app/backend/tests/test_ws_broker_fanout.py
"""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Ensure env is loaded (REDIS_URL etc.)
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v.strip().strip('"').strip("'"))


class FakeWS:
    def __init__(self):
        self.received = []

    async def send_json(self, msg):
        self.received.append(msg)


async def main():
    from services.ws_broker import RedisWsBroker

    # --- Pod A ---
    pod_a_delivered = []

    broker_a = RedisWsBroker()
    async def dispatch_a(envelope):
        # Mimic how chat_ws dispatches locally
        pod_a_delivered.append(envelope)
    broker_a.set_dispatcher(dispatch_a)
    await broker_a.start()
    assert broker_a.enabled, "Pod A broker failed to connect to Redis"

    # --- Pod B ---
    broker_b = RedisWsBroker()
    # Pod B is the publisher only in this test
    broker_b.set_dispatcher(lambda e: None)
    await broker_b.start()
    assert broker_b.enabled, "Pod B broker failed to connect to Redis"
    assert broker_a.pod_id != broker_b.pod_id

    # --- Fire an envelope from Pod B ---
    await broker_b.publish("user", {"type": "test", "payload": "hello"}, target="alice")
    # Give the subscriber loop a moment to dispatch
    await asyncio.sleep(0.2)

    # --- Verify Pod A received it ---
    assert len(pod_a_delivered) == 1, f"Pod A expected 1 delivery, got {len(pod_a_delivered)}: {pod_a_delivered}"
    e = pod_a_delivered[0]
    assert e["kind"] == "user"
    assert e["target"] == "alice"
    assert e["data"] == {"type": "test", "payload": "hello"}
    assert e["pod"] == broker_b.pod_id

    # --- Pod B should NOT receive its own message ---
    pod_b_delivered = []
    broker_b.set_dispatcher(lambda env: pod_b_delivered.append(env))
    await broker_b.publish("user", {"type": "test2"}, target="alice")
    await asyncio.sleep(0.2)
    # Broker skips own pod — pod_b_delivered must still be empty
    assert len(pod_b_delivered) == 0, f"Pod B should skip own messages, got {pod_b_delivered}"
    # But Pod A should have received it
    assert len(pod_a_delivered) == 2

    print("✓ cross-pod delivery works")
    print("✓ same-pod loopback is suppressed")

    await broker_a.stop()
    await broker_b.stop()


if __name__ == "__main__":
    asyncio.run(main())
    print("ALL OK")
