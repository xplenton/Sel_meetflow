"""Iter 188 — quick performance smoke for the read_db migration.
Hits 4 read endpoints in parallel (200 concurrent, 5 rounds each = 1000 reqs)
and reports p50/p95/p99 + error rate. Lightweight comparison aid for the
chat-package + read_db refactor.

Run:  python /app/backend/tests/perf/load_iter188.py
"""
from __future__ import annotations
import asyncio
import os
import statistics
import time

import aiohttp


API = os.environ.get("API_URL", "")
if not API:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                API = line.split("=", 1)[1].strip().rstrip("/")
                break

ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PWD = "admin123"
CONCURRENCY = 200
ROUNDS = 5

PATHS = [
    "/api/news/feed?limit=20",
    "/api/surveys",
    "/api/meetings?limit=20",
    "/api/admin/stats",
]


async def _login(session: aiohttp.ClientSession) -> str:
    async with session.post(f"{API}/api/auth/login",
                            json={"email": ADMIN_EMAIL, "password": ADMIN_PWD}) as r:
        body = await r.json()
        return body.get("access_token") or body.get("token")


async def _fire(session, token, path, results, errors):
    h = {"Authorization": f"Bearer {token}"}
    t0 = time.perf_counter()
    try:
        async with session.get(f"{API}{path}", headers=h, timeout=aiohttp.ClientTimeout(total=15)) as r:
            await r.read()
            results.append((path, time.perf_counter() - t0, r.status))
    except Exception as e:
        errors.append((path, str(e)))


async def main():
    print(f"[load] target={API} concurrency={CONCURRENCY} rounds={ROUNDS}")
    async with aiohttp.ClientSession() as session:
        token = await _login(session)
        print(f"[load] logged in (token len={len(token)})")
        results, errors = [], []
        for r in range(ROUNDS):
            tasks = [
                _fire(session, token, PATHS[i % len(PATHS)], results, errors)
                for i in range(CONCURRENCY)
            ]
            t0 = time.perf_counter()
            await asyncio.gather(*tasks)
            print(f"[round {r+1}/{ROUNDS}] {CONCURRENCY} reqs in {time.perf_counter()-t0:.2f}s "
                  f"(rps≈{CONCURRENCY/(time.perf_counter()-t0):.0f})")

        # Per-path stats
        print("\n--- Latency (ms) ---")
        print(f"{'path':<40} {'count':>5} {'p50':>7} {'p95':>7} {'p99':>7} {'errors':>7}")
        for p in PATHS:
            durs = [d * 1000 for (pp, d, st) in results if pp == p and st < 500]
            errs = sum(1 for (pp, d, st) in results if pp == p and st >= 500)
            errs += sum(1 for (pp, _) in errors if pp == p)
            if durs:
                p50 = statistics.median(durs)
                p95 = statistics.quantiles(durs, n=20)[18] if len(durs) >= 20 else max(durs)
                p99 = statistics.quantiles(durs, n=100)[98] if len(durs) >= 100 else max(durs)
                print(f"{p:<40} {len(durs):>5} {p50:>7.1f} {p95:>7.1f} {p99:>7.1f} {errs:>7}")
            else:
                print(f"{p:<40} {0:>5} {'-':>7} {'-':>7} {'-':>7} {errs:>7}")
        total = len(results) + len(errors)
        ok = sum(1 for r in results if 200 <= r[2] < 400)
        print(f"\n[summary] total={total} ok={ok} ({ok*100/max(1,total):.1f}%) errors={len(errors)}")


if __name__ == "__main__":
    asyncio.run(main())
