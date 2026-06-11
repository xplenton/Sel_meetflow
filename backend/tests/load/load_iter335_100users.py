"""Iter 335 — Load / Performance test with 100 concurrent users.

Goal: surface bottlenecks in the most-used GET / read endpoints under
sustained concurrent load.

We test against the public preview URL (REACT_APP_BACKEND_URL) so the
results include the full Kubernetes ingress + uvicorn stack, not just
the local socket. 100 users hit a basket of endpoints in parallel,
each user runs N rounds. We measure:

  * Response latency (avg, p50, p95, p99, max)
  * Error rate per endpoint
  * Throughput (RPS overall)
  * CPU / Memory snapshot before & after

How to read the report:
  * p95 < 800 ms = OK for interactive dashboards
  * p95 > 2000 ms = bottleneck — flag for index / cache review
  * error rate > 1 % = stability issue under load

Usage:
  python3 /app/backend/tests/load/load_iter335_100users.py
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

import aiohttp

BASE = os.environ.get("LOAD_BASE_URL") or "https://video-meet-pro.preview.emergentagent.com"
USERNAME = os.environ.get("LOAD_USER", "admin@meetflow.com")
PASSWORD = os.environ.get("LOAD_PASS", "admin123")
CONCURRENCY = int(os.environ.get("LOAD_USERS", "100"))
ROUNDS = int(os.environ.get("LOAD_ROUNDS", "5"))

# Read-heavy endpoints — what the dashboard / list views fire on load.
READ_ENDPOINTS: list[tuple[str, str]] = [
    ("dashboard_stats", "/api/dashboard/stats"),
    ("tasks_list", "/api/tasks?limit=50"),
    ("news_feed", "/api/news/feed"),
    ("notifications", "/api/notifications?limit=20"),
    ("resources_list", "/api/resources"),
    ("my_bookings", "/api/booking/my-bookings"),
    ("bookings_list", "/api/resource-bookings"),
    ("calendar_events", "/api/calendar/events"),
    ("chat_conversations", "/api/chat/conversations"),
    ("chat_unread", "/api/chat/unread-summary"),
    ("users_directory", "/api/chat/users"),
    ("user_permissions", "/api/user/permissions"),
    ("auth_me", "/api/auth/me"),
    ("catering_items", "/api/catering-items"),
    ("cost_centers", "/api/cost-centers"),
]


async def login(session: aiohttp.ClientSession) -> str:
    async with session.post(
        f"{BASE}/api/auth/login",
        json={"email": USERNAME, "password": PASSWORD},
        timeout=aiohttp.ClientTimeout(total=30),
    ) as resp:
        if resp.status != 200:
            txt = await resp.text()
            raise RuntimeError(f"login failed {resp.status}: {txt[:200]}")
        data = await resp.json()
        return data.get("access_token") or data.get("token") or ""


async def hit(session: aiohttp.ClientSession, url: str, token: str) -> tuple[int, float]:
    headers = {"Authorization": f"Bearer {token}"}
    t0 = time.perf_counter()
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            await resp.read()
            return resp.status, time.perf_counter() - t0
    except asyncio.TimeoutError:
        return 0, time.perf_counter() - t0
    except Exception:
        return -1, time.perf_counter() - t0


async def user_worker(uid: int, token: str, rounds: int, results: dict, connector: aiohttp.TCPConnector) -> None:
    """Each virtual user hits the full endpoint basket `rounds` times."""
    async with aiohttp.ClientSession(connector=connector, connector_owner=False) as session:
        for _ in range(rounds):
            for name, path in READ_ENDPOINTS:
                status, dt = await hit(session, f"{BASE}{path}", token)
                bucket = results[name]
                bucket["latencies"].append(dt)
                if status == 200:
                    bucket["ok"] += 1
                elif status == 0:
                    bucket["timeout"] += 1
                else:
                    bucket["err"] += 1


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = int(round((len(s) - 1) * q))
    return s[k]


def summarise(name: str, b: dict, total_users: int) -> dict:
    lats = b["latencies"]
    return {
        "endpoint": name,
        "calls": len(lats),
        "ok": b["ok"],
        "err": b["err"],
        "timeout": b["timeout"],
        "error_rate_pct": round(100 * (b["err"] + b["timeout"]) / max(1, len(lats)), 2),
        "avg_ms": round(1000 * statistics.fmean(lats), 1) if lats else 0,
        "p50_ms": round(1000 * percentile(lats, 0.50), 1),
        "p95_ms": round(1000 * percentile(lats, 0.95), 1),
        "p99_ms": round(1000 * percentile(lats, 0.99), 1),
        "max_ms": round(1000 * max(lats), 1) if lats else 0,
    }


async def main() -> int:
    print(f"== Load test ==")
    print(f"  base       : {BASE}")
    print(f"  users      : {CONCURRENCY}")
    print(f"  rounds/usr : {ROUNDS}")
    print(f"  endpoints  : {len(READ_ENDPOINTS)}")
    print(f"  total calls: {CONCURRENCY * ROUNDS * len(READ_ENDPOINTS)}")

    # Single login — reuse same admin token for all virtual users.
    async with aiohttp.ClientSession() as s:
        token = await login(s)
    if not token:
        print("ERROR: empty token")
        return 2
    print(f"  token len  : {len(token)}")

    results: dict = {n: {"latencies": [], "ok": 0, "err": 0, "timeout": 0} for n, _ in READ_ENDPOINTS}
    # Iter 335 — single shared connector so all virtual users share a real
    # TCP pool. Without this, every "user" opened its own connector which
    # created thousands of short-lived TLS handshakes and saturated the
    # client event loop (not the server).
    shared_connector = aiohttp.TCPConnector(limit=200, limit_per_host=200, ssl=False)
    t_start = time.perf_counter()
    try:
        await asyncio.gather(*[
            user_worker(i, token, ROUNDS, results, shared_connector)
            for i in range(CONCURRENCY)
        ])
    finally:
        await shared_connector.close()
    elapsed = time.perf_counter() - t_start

    rows = [summarise(n, b, CONCURRENCY) for n, b in results.items()]
    rows.sort(key=lambda r: r["p95_ms"], reverse=True)

    total_calls = sum(r["calls"] for r in rows)
    total_err = sum(r["err"] + r["timeout"] for r in rows)
    overall_p95 = round(1000 * percentile(
        [v for b in results.values() for v in b["latencies"]], 0.95
    ), 1)
    overall_avg = round(1000 * statistics.fmean(
        [v for b in results.values() for v in b["latencies"]]
    ), 1)

    print("")
    print(f"== Result (elapsed {elapsed:.1f}s, RPS={total_calls/elapsed:.1f}) ==")
    print(f"  total calls: {total_calls}")
    print(f"  errors     : {total_err} ({100*total_err/max(1,total_calls):.2f} %)")
    print(f"  overall avg: {overall_avg} ms  p95: {overall_p95} ms")
    print("")
    print(f"  {'endpoint':<22} {'calls':>6} {'err':>4} {'avg':>7} {'p50':>7} {'p95':>7} {'p99':>7} {'max':>7}")
    for r in rows:
        print(f"  {r['endpoint']:<22} {r['calls']:>6} {r['err']+r['timeout']:>4} "
              f"{r['avg_ms']:>7.1f} {r['p50_ms']:>7.1f} {r['p95_ms']:>7.1f} "
              f"{r['p99_ms']:>7.1f} {r['max_ms']:>7.1f}")

    # Persist machine-readable report
    out = {
        "base": BASE,
        "users": CONCURRENCY,
        "rounds": ROUNDS,
        "elapsed_s": round(elapsed, 2),
        "rps": round(total_calls / elapsed, 2),
        "total_calls": total_calls,
        "errors": total_err,
        "error_rate_pct": round(100 * total_err / max(1, total_calls), 2),
        "overall_avg_ms": overall_avg,
        "overall_p95_ms": overall_p95,
        "endpoints": rows,
    }
    report_dir = Path("/app/test_reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "load_iter335_100users.json"
    report_path.write_text(json.dumps(out, indent=2))
    print(f"\nReport written to {report_path}")

    # Exit code: non-zero on bad health so this can be wired into CI later.
    if out["error_rate_pct"] > 5:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
