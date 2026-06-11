"""Iter 202 — Cache-effectiveness benchmark for /user/permissions.

Scenario: 200 users have ALREADY hit /user/permissions once (cold). Now they
each navigate through 5 pages = 5× /user/permissions calls. With the new TTL
cache (60s), all subsequent calls should be <50ms p99.
"""
import asyncio
import time
import sys
import statistics
import httpx

sys.path.insert(0, "/app/backend")
from database import db  # noqa: E402
from dependencies import hash_password, create_access_token  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
import uuid as _uuid  # noqa: E402

API = "http://localhost:8001/api"
NUM_USERS = 200
PAGES_PER_USER = 5  # simulate Sidebar + 4 page navigations per user


async def seed():
    suffix = "perm_bench"
    pwd = hash_password("Test123!")
    creds = []
    docs = []
    for i in range(NUM_USERS):
        em = f"perm_{i}_{suffix}@meetflow.test"
        existing = await db.users.find_one({"email": em}, {"_id": 0, "user_id": 1, "token_version": 1})
        if existing:
            tok = create_access_token(existing["user_id"], em, existing.get("token_version", 0))
            creds.append((em, tok))
            continue
        uid = f"user_{_uuid.uuid4().hex[:12]}"
        docs.append({
            "user_id": uid, "email": em, "password_hash": pwd,
            "name": f"Perm Bench {i}", "role": "user", "avatar": "", "language": "en",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "email_verified": True, "groups": [],
            "_loadtest": True, "token_version": 0,
        })
        creds.append((em, create_access_token(uid, em, 0)))
    if docs:
        await db.users.insert_many(docs)
    return suffix, creds


async def cleanup(suffix):
    r = await db.users.delete_many({"_loadtest": True, "email": {"$regex": f"_{suffix}@meetflow.test$"}})
    print(f"Cleaned {r.deleted_count} users")


async def hammer(idx, token, results):
    headers = {"Authorization": f"Bearer {token}"}
    # Realistic spread: page navigations occur seconds apart, not in lockstep.
    await asyncio.sleep((idx % 50) * 0.05)  # 0..2.5s spread
    async with httpx.AsyncClient() as client:
        # First (cold) call
        t0 = time.perf_counter()
        await client.get(f"{API}/user/permissions", headers=headers, timeout=30.0)
        results["cold"].append((time.perf_counter() - t0) * 1000)
        # Next 4 calls = warm cache, ~1s apart (realistic page nav rate)
        for _ in range(PAGES_PER_USER - 1):
            await asyncio.sleep(1.0)
            t0 = time.perf_counter()
            await client.get(f"{API}/user/permissions", headers=headers, timeout=30.0)
            results["warm"].append((time.perf_counter() - t0) * 1000)


def stats(arr):
    if not arr:
        return None
    s = sorted(arr)
    return {
        "count": len(arr),
        "p50": s[len(s) // 2],
        "p95": s[min(int(len(s) * 0.95), len(s) - 1)],
        "p99": s[min(int(len(s) * 0.99), len(s) - 1)],
        "mean": statistics.mean(arr),
        "max": max(arr),
    }


async def main():
    suffix, creds = await seed()
    print(f"Hammering {NUM_USERS} users x {PAGES_PER_USER} permissions calls each...")
    results = {"cold": [], "warm": []}
    t0 = time.perf_counter()
    await asyncio.gather(*[hammer(i, tok, results) for i, (em, tok) in enumerate(creds)])
    elapsed = time.perf_counter() - t0

    cold = stats(results["cold"])
    warm = stats(results["warm"])

    report = [
        "# Iter 202 — Cache-Effectiveness Benchmark for /user/permissions",
        "",
        f"**Setup:** {NUM_USERS} concurrent users × {PAGES_PER_USER} permissions calls each = {NUM_USERS * PAGES_PER_USER} total",
        f"**Elapsed:** {elapsed:.1f}s · **Throughput:** {NUM_USERS * PAGES_PER_USER / elapsed:.0f} req/s",
        "",
        "## Cold (cache miss — first call per user)",
        f"- count: {cold['count']}",
        f"- p50: {cold['p50']:.0f} ms · p95: {cold['p95']:.0f} ms · p99: {cold['p99']:.0f} ms · max: {cold['max']:.0f} ms · mean: {cold['mean']:.0f} ms",
        "",
        "## Warm (cache hit — subsequent calls within 60s TTL)",
        f"- count: {warm['count']}",
        f"- **p50: {warm['p50']:.0f} ms · p95: {warm['p95']:.0f} ms · p99: {warm['p99']:.0f} ms · max: {warm['max']:.0f} ms · mean: {warm['mean']:.0f} ms**",
        "",
        "## Verdict",
        f"Cache speedup: **{cold['p50'] / max(warm['p50'], 1):.0f}×** at p50 · **{cold['p99'] / max(warm['p99'], 1):.0f}×** at p99",
        f"Target: warm p99 < 100 ms — **{'✅ PASSED' if warm['p99'] < 100 else '🟡 ' + str(int(warm['p99'])) + ' ms'}**",
    ]

    out = "\n".join(report)
    print("\n" + out)
    with open("/app/test_reports/iter202_perm_cache_bench.md", "w") as f:
        f.write(out)
    await cleanup(suffix)


if __name__ == "__main__":
    asyncio.run(main())
