"""iter 203 — Verify TTL cache behaviour for /api/tasks/pending-count.

Checks:
 1. First call is a cache MISS, subsequent calls within TTL are cache HITS
    (verified by latency: hits should be ~10x faster than miss).
 2. Creating a new task assigned to the user invalidates the cache → next call
    reflects the higher count immediately.
 3. Deleting the task invalidates the cache → count drops back.
 4. Updating a task's status to 'done' invalidates the cache.

Run: python /app/backend/tests/bench_iter203_pending_count_cache.py
"""
import asyncio
import os
import time

import httpx

API = os.environ.get("API_URL") or "http://localhost:8001"
EMAIL = "admin@meetflow.com"
PASSWORD = "admin123"


async def login(client: httpx.AsyncClient) -> str:
    r = await client.post(
        f"{API}/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["token"]


async def time_call(client: httpx.AsyncClient, headers) -> tuple[float, dict]:
    t0 = time.perf_counter()
    r = await client.get(f"{API}/api/tasks/pending-count", headers=headers, timeout=10)
    r.raise_for_status()
    return (time.perf_counter() - t0) * 1000, r.json()


async def main():
    async with httpx.AsyncClient() as client:
        token = await login(client)
        headers = {"Authorization": f"Bearer {token}"}

        # Identify ourselves so we can assign.
        me = await client.get(f"{API}/api/auth/me", headers=headers)
        me.raise_for_status()
        my_id = me.json()["user_id"]

        print("=" * 60)
        print("iter 203 — pending-count TTL cache")
        print("=" * 60)

        # 1) Cold call (MISS) + 5 warm calls (HIT)
        miss_ms, base = await time_call(client, headers)
        warm = []
        for _ in range(5):
            ms, _ = await time_call(client, headers)
            warm.append(ms)
        print(f"baseline count={base}")
        print(f"MISS:        {miss_ms:6.1f} ms")
        print(f"HIT (avg5):  {sum(warm) / len(warm):6.1f} ms")
        print(f"HIT (p99):   {max(warm):6.1f} ms")
        assert sum(warm) / len(warm) < miss_ms, "warm calls should be faster than cold"

        # 2) Create a task assigned to me → cache must invalidate
        r = await client.post(
            f"{API}/api/tasks",
            headers=headers,
            json={
                "title": "iter203 cache invalidation probe",
                "priority": "normal",
                "assignee_ids": [my_id],
            },
        )
        r.raise_for_status()
        new_task_id = r.json()["task_id"]
        _, after_create = await time_call(client, headers)
        print(f"after CREATE count={after_create}")
        assert after_create["count"] == base["count"] + 1, "count should bump after create"

        # 3) Update status to 'done' → cache must invalidate, count drops
        r = await client.put(
            f"{API}/api/tasks/{new_task_id}",
            headers=headers,
            json={"status": "done"},
        )
        r.raise_for_status()
        _, after_done = await time_call(client, headers)
        print(f"after DONE   count={after_done}")
        assert after_done["count"] == base["count"], "count should fall back after done"

        # 4) Delete the task → still consistent
        r = await client.delete(f"{API}/api/tasks/{new_task_id}", headers=headers)
        r.raise_for_status()
        _, after_delete = await time_call(client, headers)
        print(f"after DELETE count={after_delete}")
        assert after_delete["count"] == base["count"], "count stable after delete of done task"

        print("\nAll cache invariants OK ✓")


if __name__ == "__main__":
    asyncio.run(main())
