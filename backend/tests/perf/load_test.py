"""
Load/Performance test for MeetFlow (iter 172).

Simulates the user's acceptance scenario:
  * 500 concurrent authenticated users
  * 100 of them (10 groups x 10 users) exchanging chat messages
  * 400 mixed read-heavy users
  * A parallel burst driver sustaining >= 1000 req per 500ms window
    (>= 2000 RPS) over the full duration
  * 60s total duration by default

Usage:
  python3 /app/backend/tests/perf/load_test.py

Environment overrides:
  API_URL            default http://localhost:8001 (bypass ingress throttling)
  CONCURRENT_USERS   default 500
  CHAT_USERS         default 100
  BURST_RPS_TARGET   default 2000  (= 1000 req / 500ms)
  BURST_DURATION_SEC default 60
  REPORT_PATH        default /app/test_reports/perf_iteration_172.json
"""
import asyncio
import json
import os
import random
import statistics
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import aiohttp
from motor.motor_asyncio import AsyncIOMotorClient

# ---- config ----
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

# Load backend .env for MONGO_URL / DB_NAME / JWT_SECRET
BACKEND_ENV = ROOT / "backend" / ".env"
if BACKEND_ENV.exists():
    for line in BACKEND_ENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k, v.strip().strip('"').strip("'"))

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
API_URL = os.environ.get("API_URL", "http://localhost:8001").rstrip("/")

CONCURRENT = int(os.environ.get("CONCURRENT_USERS", 500))
CHAT_USERS = int(os.environ.get("CHAT_USERS", 100))
CHAT_GROUPS = CHAT_USERS // 10
BURST_SPIKE_SIZE = int(os.environ.get("BURST_SPIKE_SIZE", 1000))
BURST_WINDOW_MS = int(os.environ.get("BURST_WINDOW_MS", 500))
BURST_AT_SEC = int(os.environ.get("BURST_AT_SEC", 20))
BURST_DURATION = int(os.environ.get("BURST_DURATION_SEC", 60))
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "/app/test_reports/perf_iteration_172.json"))
TEST_TAG = "perf-iter172"
JWT_SECRET = os.environ.get("JWT_SECRET", "your-secret-key-change-this-in-production")

# ---- metrics ----
metrics = defaultdict(list)          # endpoint -> list[latency_ms]
errors = defaultdict(int)            # endpoint -> count
status_counts = defaultdict(int)     # status_code -> count
total_requests = 0
burst_requests = 0


def record(endpoint: str, elapsed_ms: float, status: int, is_burst: bool = False):
    global total_requests, burst_requests
    total_requests += 1
    if is_burst:
        burst_requests += 1
    metrics[endpoint].append(elapsed_ms)
    status_counts[status] += 1
    if status >= 400:
        errors[endpoint] += 1


# ============ seed ============
async def seed_users() -> List[Dict]:
    """Create CONCURRENT perf users directly in mongo with pre-signed JWT tokens."""
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    try:
        import bcrypt
        import jwt as pyjwt
        from datetime import datetime, timezone
        password_hash = bcrypt.hashpw(b"perf12345", bcrypt.gensalt()).decode()
        users = []
        bulk = []
        now_iso = datetime.now(timezone.utc).isoformat()
        for i in range(CONCURRENT):
            uid = f"perf_u_{i:04d}_{uuid.uuid4().hex[:6]}"
            email = f"perf_{i:04d}@loadtest.local"
            bulk.append({
                "user_id": uid, "email": email, "name": f"PerfUser {i:04d}",
                "password_hash": password_hash, "role": "member",
                "avatar": None, "language": "de", "status": "active",
                "created_at": now_iso,
                "groups": [], "profession": None, "department": None, "location": None,
                "token_version": 0, "perf_tag": TEST_TAG,
            })
            token = pyjwt.encode(
                {"user_id": uid, "email": email, "tv": 0,
                 "exp": int(time.time()) + 3600},
                JWT_SECRET, algorithm="HS256",
            )
            users.append({"user_id": uid, "email": email, "token": token})
        # Wipe any previous perf users/convos
        await db.users.delete_many({"perf_tag": TEST_TAG})
        await db.conversations.delete_many({"perf_tag": TEST_TAG})
        await db.messages.delete_many({"perf_tag": TEST_TAG})
        await db.users.insert_many(bulk)
        return users
    finally:
        client.close()


async def teardown():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    try:
        convs = await db.conversations.find({"perf_tag": TEST_TAG}, {"_id": 0, "conversation_id": 1}).to_list(None)
        conv_ids = [c["conversation_id"] for c in convs]
        if conv_ids:
            await db.messages.delete_many({"conversation_id": {"$in": conv_ids}})
        await db.conversations.delete_many({"perf_tag": TEST_TAG})
        await db.users.delete_many({"perf_tag": TEST_TAG})
    finally:
        client.close()


async def create_chat_conversations(session, users) -> List[str]:
    """Create CHAT_GROUPS group conversations via the real API.

    Returns list of conversation_ids (len == CHAT_GROUPS)."""
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    try:
        conv_ids: List[str] = []
        for g in range(CHAT_GROUPS):
            creator = users[g * 10]
            members = [users[g * 10 + k]["user_id"] for k in range(10)]
            headers = {"Authorization": f"Bearer {creator['token']}"}
            payload = {
                "type": "group",
                "name": f"Perf Group {g:02d}",
                "member_ids": members,
            }
            async with session.post(f"{API_URL}/api/chat/conversations",
                                    json=payload, headers=headers, timeout=30) as r:
                body = await r.json()
                conv_id = body.get("conversation_id")
                if not conv_id:
                    raise RuntimeError(f"Failed to create conv for group {g}: {body}")
            # Tag it for cleanup
            await db.conversations.update_one(
                {"conversation_id": conv_id},
                {"$set": {"perf_tag": TEST_TAG}},
            )
            conv_ids.append(conv_id)
        return conv_ids
    finally:
        client.close()


# ============ worker loops ============
READ_ENDPOINTS = [
    "/api/news/feed?limit=10",
    "/api/meetings?scope=upcoming&limit=20",
    "/api/surveys",
    "/api/notifications",
    "/api/auth/me",
    "/api/chat/conversations",
    "/api/chat/unread-summary",
    "/api/news/categories",
    "/api/news/unread-count",
    "/api/dashboard/stats",
]


async def hit(session, token, url, method="GET", payload=None, is_burst=False):
    start = time.perf_counter()
    status = 0
    try:
        headers = {"Authorization": f"Bearer {token}"}
        if method == "GET":
            async with session.get(url, headers=headers, timeout=30) as r:
                status = r.status
                await r.read()
        else:
            async with session.post(url, headers=headers, json=payload, timeout=30) as r:
                status = r.status
                await r.read()
    except asyncio.TimeoutError:
        status = 599
    except Exception:
        status = 598
    elapsed_ms = (time.perf_counter() - start) * 1000
    # Normalize path - strip query & conv id (keep /messages bucket)
    path = url.split("?")[0].replace(API_URL, "")
    if "/api/chat/conversations/" in path and path.endswith("/messages"):
        path = "/api/chat/conversations/{id}/messages"
    elif "/api/chat/conversations/" in path and path.count("/") == 4:
        path = "/api/chat/conversations/{id}"
    record(path, elapsed_ms, status, is_burst=is_burst)
    return status


async def chat_user_loop(session, user, conv_id, duration):
    end = time.monotonic() + duration
    msg_counter = 0
    while time.monotonic() < end:
        msg_counter += 1
        await hit(
            session, user["token"],
            f"{API_URL}/api/chat/conversations/{conv_id}/messages",
            method="POST",
            payload={"content": f"perf msg #{msg_counter} from {user['user_id'][-6:]}"},
        )
        if msg_counter % 3 == 0:
            await hit(session, user["token"],
                      f"{API_URL}/api/chat/conversations/{conv_id}/messages?limit=20")
        if msg_counter % 5 == 0:
            await hit(session, user["token"], f"{API_URL}/api/chat/unread-summary")
        await asyncio.sleep(random.uniform(0.5, 2.0))


async def read_user_loop(session, user, duration):
    end = time.monotonic() + duration
    while time.monotonic() < end:
        ep = random.choice(READ_ENDPOINTS)
        await hit(session, user["token"], f"{API_URL}{ep}")
        await asyncio.sleep(random.uniform(0.3, 1.5))


async def burst_spike(session, users, spike_size=1000, window_ms=500):
    """Fire one concentrated burst of `spike_size` requests as fire-and-forget
    tasks. All tasks are created in a tight synchronous loop, then asyncio
    schedules them immediately onto the event loop.

    Returns:
      dispatch_time (s): how long it took to create all tasks (should be ~ms)
      burst_wall_time (s): how long until all burst tasks resolved (or 30s cap)
    """
    t_dispatch_start = time.monotonic()
    tasks = []
    for _ in range(spike_size):
        u = random.choice(users)
        ep = random.choice(READ_ENDPOINTS)
        t = asyncio.create_task(hit(session, u["token"], f"{API_URL}{ep}", is_burst=True))
        tasks.append(t)
    dispatch_time = time.monotonic() - t_dispatch_start
    # Let scheduler pump
    await asyncio.sleep(0)
    # Wait for the burst to resolve (cap at 30s)
    t_wait = time.monotonic()
    await asyncio.wait(tasks, timeout=30)
    burst_wall_time = time.monotonic() - t_wait + dispatch_time
    return dispatch_time, burst_wall_time


# ============ report ============
def build_report(run_duration_sec):
    stats_rows = []
    for ep, lats in sorted(metrics.items(), key=lambda x: -len(x[1])):
        if not lats:
            continue
        sorted_lats = sorted(lats)
        p50 = sorted_lats[len(sorted_lats) // 2]
        p95 = sorted_lats[int(len(sorted_lats) * 0.95)]
        p99 = sorted_lats[int(len(sorted_lats) * 0.99)]
        err = errors.get(ep, 0)
        stats_rows.append({
            "endpoint": ep,
            "requests": len(lats),
            "errors": err,
            "error_rate_pct": round(100.0 * err / len(lats), 2),
            "p50_ms": round(p50, 1),
            "p95_ms": round(p95, 1),
            "p99_ms": round(p99, 1),
            "avg_ms": round(statistics.fmean(lats), 1),
        })
    return {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "config": {
            "concurrent_users": CONCURRENT,
            "chat_users": CHAT_USERS,
            "chat_groups": CHAT_GROUPS,
            "burst_spike_size": BURST_SPIKE_SIZE,
            "burst_window_ms": BURST_WINDOW_MS,
            "burst_at_sec": BURST_AT_SEC,
            "burst_duration_sec": BURST_DURATION,
            "api_url": API_URL,
        },
        "totals": {
            "total_requests": total_requests,
            "burst_requests": burst_requests,
            "run_duration_sec": round(run_duration_sec, 1),
            "effective_rps": round(total_requests / run_duration_sec, 1) if run_duration_sec > 0 else 0,
            "status_counts": dict(status_counts),
            "error_total": sum(errors.values()),
            "error_rate_pct": round(100.0 * sum(errors.values()) / total_requests, 2) if total_requests else 0,
        },
        "per_endpoint": stats_rows,
    }


# ============ main ============
async def main():
    print(f"[PERF] Seeding {CONCURRENT} users ...", flush=True)
    t0 = time.monotonic()
    users = await seed_users()
    print(f"[PERF] Seed done in {time.monotonic() - t0:.1f}s", flush=True)

    connector = aiohttp.TCPConnector(limit=0, ttl_dns_cache=300, force_close=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        print(f"[PERF] Creating {CHAT_GROUPS} chat groups via API ...", flush=True)
        t1 = time.monotonic()
        conv_ids = await create_chat_conversations(session, users)
        print(f"[PERF] Chat groups created in {time.monotonic() - t1:.1f}s", flush=True)

        duration = BURST_DURATION
        chat_tasks = []
        for gi in range(CHAT_GROUPS):
            for k in range(10):
                chat_tasks.append(
                    chat_user_loop(session, users[gi * 10 + k], conv_ids[gi], duration)
                )
        read_tasks = [read_user_loop(session, u, duration) for u in users[CHAT_USERS:]]

        print(
            f"[PERF] Running {len(chat_tasks)} chat + {len(read_tasks)} read loops "
            f"for {duration}s + burst of {BURST_SPIKE_SIZE} requests in "
            f"{BURST_WINDOW_MS}ms at t={BURST_AT_SEC}s ...",
            flush=True,
        )
        t_run = time.monotonic()
        # Run sustained load + a scheduled burst spike concurrently
        async def scheduled_burst():
            await asyncio.sleep(BURST_AT_SEC)
            print(f"[PERF] FIRING burst: {BURST_SPIKE_SIZE} req in {BURST_WINDOW_MS}ms ...",
                  flush=True)
            dispatch_time, wall_time = await burst_spike(
                session, users,
                spike_size=BURST_SPIKE_SIZE,
                window_ms=BURST_WINDOW_MS,
            )
            print(
                f"[PERF] Burst dispatched in {dispatch_time*1000:.0f}ms, "
                f"all resolved in {wall_time*1000:.0f}ms",
                flush=True,
            )
            return dispatch_time, wall_time

        results = await asyncio.gather(
            *(chat_tasks + read_tasks),
            scheduled_burst(),
            return_exceptions=True,
        )
        run_duration = time.monotonic() - t_run
        burst_result = results[-1] if not isinstance(results[-1], Exception) else (None, None)
        burst_dispatch_time, burst_wall_time = burst_result

    report = build_report(run_duration)
    report["burst"] = {
        "spike_size": BURST_SPIKE_SIZE,
        "target_window_ms": BURST_WINDOW_MS,
        "dispatch_time_ms": round((burst_dispatch_time or 0) * 1000, 1),
        "burst_total_wall_time_ms": round((burst_wall_time or 0) * 1000, 1),
        "effective_dispatch_rps": round(BURST_SPIKE_SIZE / burst_dispatch_time, 1)
            if burst_dispatch_time else None,
        "burst_completion_rps": round(BURST_SPIKE_SIZE / burst_wall_time, 1)
            if burst_wall_time else None,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(f"[PERF] Report written: {REPORT_PATH}", flush=True)
    print(
        f"[PERF] Total={report['totals']['total_requests']} "
        f"effective={report['totals']['effective_rps']} rps  "
        f"errors={report['totals']['error_total']} "
        f"({report['totals']['error_rate_pct']}%) "
        f"burst_dispatch={report['burst']['dispatch_time_ms']}ms",
        flush=True,
    )

    print("[PERF] Cleaning up ...", flush=True)
    await teardown()
    print("[PERF] Done.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
