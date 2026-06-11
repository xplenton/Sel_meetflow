"""iter 204 — Verify the cross-pod cache-invalidation broker.

Spins up TWO CacheInvalidationBroker instances in the same process — these
play the role of "Pod A" and "Pod B". Each registers a fake handler. We then
publish from A and confirm B's handler fires (and vice-versa), and that
self-loop suppression works (publisher's own handler does NOT fire on its
own message).

Requires REDIS_URL to be set (loaded from /app/backend/.env). If Redis is not
reachable, the test exits early — same fallback behaviour as production.
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, "/app/backend")

# Ensure REDIS_URL is loaded the same way the app does.
from dotenv import load_dotenv  # noqa: E402
load_dotenv("/app/backend/.env")


async def main() -> int:
    if not os.environ.get("REDIS_URL"):
        print("REDIS_URL not set — single-pod mode, skipping cross-pod test.")
        return 0

    from services.cache_broker import CacheInvalidationBroker

    pod_a = CacheInvalidationBroker()
    pod_b = CacheInvalidationBroker()

    # Each pod records the (namespace, user_id) tuples its handler receives.
    received_a: list[tuple[str, str | None]] = []
    received_b: list[tuple[str, str | None]] = []

    async def handler_a_perm(uid):
        received_a.append(("permissions", uid))

    async def handler_b_perm(uid):
        received_b.append(("permissions", uid))

    async def handler_b_pending(uid):
        received_b.append(("pending_count", uid))

    pod_a.register("permissions", handler_a_perm)
    pod_b.register("permissions", handler_b_perm)
    pod_b.register("pending_count", handler_b_pending)

    await pod_a.start()
    await pod_b.start()
    if not (pod_a.enabled and pod_b.enabled):
        print(f"broker not enabled (a={pod_a.enabled} b={pod_b.enabled})")
        return 1

    print(f"pod_a.id={pod_a.pod_id}  pod_b.id={pod_b.pod_id}")

    # Give pubsub a moment to settle.
    await asyncio.sleep(0.2)

    # Pod A invalidates user_42's permissions → Pod B should receive it,
    # Pod A should NOT (self-loop suppression).
    await pod_a.publish("permissions", "user_42")
    await asyncio.sleep(0.4)
    assert received_b == [("permissions", "user_42")], f"expected B to see user_42, got {received_b}"
    assert received_a == [], f"expected A to skip self-publish, got {received_a}"
    print("✓ cross-pod broadcast OK (A → B), self-loop suppressed on A")

    # Pod B publishes pending_count invalidation for two users.
    await pod_b.publish("pending_count", "user_99")
    await pod_b.publish("pending_count", None)  # "everyone"
    await asyncio.sleep(0.4)
    # Pod A doesn't subscribe to pending_count → should still be empty
    assert received_a == [], f"A should ignore namespaces it didn't register: {received_a}"
    # Pod B suppressed its own publishes
    assert received_b == [("permissions", "user_42")], f"B self-publishes should not fire its handler: {received_b}"
    print("✓ self-loop suppression also OK on B; namespace filtering OK on A")

    # Latency probe: time from publish on A to handler fire on B.
    received_b.clear()
    t0 = time.perf_counter()
    await pod_a.publish("permissions", "latency_probe")
    while not received_b and (time.perf_counter() - t0) < 2.0:
        await asyncio.sleep(0.005)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert received_b == [("permissions", "latency_probe")], "did not receive latency probe"
    print(f"✓ A→B propagation latency: {elapsed_ms:.1f} ms")

    await pod_a.stop()
    await pod_b.stop()
    print("\nAll cross-pod cache-invalidation invariants OK ✓")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
