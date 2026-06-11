"""
Iter 201 — Massive concurrent load test for the Tasks module.
200 simulated users running through ALL task options in parallel:
  - register/login
  - create tasks (auto-save flow simulation: POST /tasks)
  - patch fields (status, priority, due_date, tags, checklist)
  - add comments (with @mention)
  - add link-attachment
  - duplicate a task
  - apply a template (and create the template once globally)
  - search /api/tasks/search
  - filtered list GET /api/tasks?status=&priority=&assignee_id=
  - pending-count GET /api/tasks/pending-count
  - permissions GET /api/user/permissions
  - calendar feed GET /api/calendar/events
  - recurring task: create + mark-done → spawn next instance
  - delete the test task at the end

Metrics: per-operation success, p50/p95/p99 latency, total throughput, error map.
Report -> /app/test_reports/iter201_load_200users.md
"""
import asyncio
import os
import random
import string
import time
from collections import defaultdict
from statistics import median
import httpx

API_URL = os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
# iter 201 — bypass Cloudflare/Edge bot-challenge by hitting the backend directly.
# Set DIRECT=1 to use localhost; otherwise the public URL (which may be rate-limited).
if os.environ.get("DIRECT", "1") == "1":
    API = "http://localhost:8001/api"
else:
    API = f"{API_URL.rstrip('/')}/api"

NUM_USERS = 200
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PW = "admin123"

# Per-operation latency buckets and error counts
metrics = defaultdict(list)
errors = defaultdict(lambda: defaultdict(int))
error_bodies = defaultdict(list)  # capture sample 403 bodies for diagnostics
total_requests = 0
total_failures = 0
start_ts = 0.0


def _rand_str(n=6):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


async def _t(client, method, path, op, **kw):
    """Timed request helper. Records latency + errors."""
    global total_requests, total_failures
    total_requests += 1
    t0 = time.perf_counter()
    try:
        r = await client.request(method, f"{API}{path}", timeout=30.0, **kw)
        dt = (time.perf_counter() - t0) * 1000
        metrics[op].append(dt)
        if r.status_code >= 400:
            total_failures += 1
            errors[op][r.status_code] += 1
            # Capture up to 3 sample bodies per op for diagnostics
            if len(error_bodies[op]) < 3:
                try:
                    error_bodies[op].append(f"HTTP {r.status_code}: {r.text[:200]}")
                except Exception:
                    pass
            return None
        try:
            return r.json()
        except Exception:
            return r.text
    except Exception as e:
        dt = (time.perf_counter() - t0) * 1000
        metrics[op].append(dt)
        total_failures += 1
        errors[op][type(e).__name__] += 1
        return None


async def setup_admin_token(client):
    r = await client.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=30.0)
    return r.json()["token"]


async def seed_user(client, idx, suffix):
    """Pre-create one user (sequential, respects 5/min rate limit per IP).

    Strategy: register if not exists; if rate-limited, retry after backoff.
    Returns (email, password) — login happens in the parallel phase.
    """
    email = f"loaduser_{idx}_{suffix}@meetflow.test"
    password = "Test123!loadtest"
    name = f"Load User {idx}"
    # Try register; on 429, sleep + retry; on 400 (already exists), accept
    for attempt in range(8):
        try:
            r = await client.post(f"{API}/auth/register",
                                  json={"email": email, "password": password, "name": name},
                                  timeout=30.0)
            if r.status_code in (200, 400):  # 400 = already exists -> reuse
                return email, password
            if r.status_code == 429:
                # Rate-limited: wait 13s (5/min => 12s/req); jitter
                await asyncio.sleep(13 + random.random())
                continue
            return email, password  # any other code, give up retry
        except Exception:
            await asyncio.sleep(1 + random.random())
    return None, None


async def login(client, email, password):
    try:
        r = await client.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30.0)
        if r.status_code == 200:
            return r.json().get("token")
    except Exception:
        pass
    return None


async def user_workflow(idx, email, token, template_id):
    """One simulated user runs through every task feature once.
    Token is pre-issued to bypass login rate-limits.
    """
    async with httpx.AsyncClient() as client:
        if not token:
            errors["token"]["missing"] += 1
            return
        headers = {"Authorization": f"Bearer {token}"}

        # 1) GET /user/permissions (capability check) — multiple page-loads
        # In real usage Sidebar polls + every page navigation hits this. Simulate
        # 5 calls per user spread across the workflow.
        await _t(client, "GET", "/user/permissions", "permissions", headers=headers)

        # 2) GET /tasks/pending-count (sidebar polling)
        await _t(client, "GET", "/tasks/pending-count", "pending_count", headers=headers)

        # 3) POST /tasks (auto-save flow)
        title = f"Load Task {idx} {_rand_str(4)}"
        task = await _t(client, "POST", "/tasks", "create_task", headers=headers, json={
            "title": title,
            "description": "load-test description",
            "priority": random.choice(["low", "normal", "high", "urgent"]),
            "due_date": "2026-12-31",
            "tags": [f"loadtest-{idx % 10}"],
            "checklist": [{"id": f"cl_{i}", "text": f"step {i}", "done": False} for i in range(3)],
        })
        if not task or not task.get("task_id"):
            return
        task_id = task["task_id"]

        # 4) PUT /tasks/{id} multiple field updates (priority, status, tags)
        await _t(client, "PUT", f"/tasks/{task_id}", "update_priority", headers=headers, json={"priority": "high"})
        await _t(client, "PUT", f"/tasks/{task_id}", "update_status_in_progress", headers=headers, json={"status": "in_progress"})
        await _t(client, "PUT", f"/tasks/{task_id}", "update_tags", headers=headers, json={"tags": ["bulk", "loadtest", f"u{idx}"]})

        # 5) POST /tasks/{id}/comments (add comment) — backend field is 'content'
        await _t(client, "POST", f"/tasks/{task_id}/comments", "add_comment", headers=headers, json={"content": f"Comment from user {idx}"})

        # 6) POST /tasks/{id}/attachments/link (add link)
        await _t(client, "POST", f"/tasks/{task_id}/attachments/link", "add_link", headers=headers, json={"url": f"https://example.com/{idx}", "name": f"Link {idx}"})

        # 7) POST /tasks/{id}/duplicate
        await _t(client, "POST", f"/tasks/{task_id}/duplicate", "duplicate_task", headers=headers, json={})

        # 8) POST /tasks/from-template/{template_id}
        if template_id:
            await _t(client, "POST", f"/tasks/from-template/{template_id}", "from_template", headers=headers, json={})

        # 9) Recurring task — create + mark done → spawn next instance
        rec_task = await _t(client, "POST", "/tasks", "create_recurring", headers=headers, json={
            "title": f"Recurring {idx}",
            "due_date": "2026-03-01",
            "recurrence": {"pattern": "weekly", "interval": 1},
        })
        if rec_task and rec_task.get("task_id"):
            await _t(client, "PUT", f"/tasks/{rec_task['task_id']}", "recur_mark_done",
                     headers=headers, json={"status": "done"})

        # 10) GET /tasks?status=in_progress (filter)
        await _t(client, "GET", "/tasks?status=in_progress", "list_filtered", headers=headers)

        # 11) GET /tasks/search?q=Load
        await _t(client, "GET", "/tasks/search?q=Load", "search", headers=headers)

        # 12) GET /tasks/{id}/history (activity log)
        await _t(client, "GET", f"/tasks/{task_id}/history", "history", headers=headers)

        # 13) GET /tasks/{id} (refresh details)
        await _t(client, "GET", f"/tasks/{task_id}", "get_task", headers=headers)

        # 14) GET /calendar/events (task should appear here)
        await _t(client, "GET", "/calendar/events", "calendar_feed", headers=headers)

        # 15) DELETE /tasks/{id} (clean up own task)
        await _t(client, "DELETE", f"/tasks/{task_id}", "delete_task", headers=headers)

        # 16) Simulate 4 more permissions calls (mimics page navigations through
        # Dashboard/News/Chat/Calendar). Demonstrates iter202 cache benefit.
        for _ in range(4):
            await _t(client, "GET", "/user/permissions", "permissions", headers=headers)


async def seed_users_bulk(suffix):
    """Bulk-seed N users directly in MongoDB AND issue JWT tokens
    (bypasses register/login rate limits). Returns list of (email, token).
    """
    import sys
    sys.path.insert(0, "/app/backend")
    from database import db
    from dependencies import hash_password, create_access_token
    from datetime import datetime, timezone
    import uuid as _uuid

    creds = []
    docs = []
    pwd_hash = hash_password("Test123!loadtest")
    for i in range(NUM_USERS):
        email = f"loaduser_{i}_{suffix}@meetflow.test"
        existing = await db.users.find_one({"email": email}, {"_id": 0, "user_id": 1, "token_version": 1})
        if existing:
            tok = create_access_token(existing["user_id"], email, existing.get("token_version", 0))
            creds.append((email, tok))
            continue
        uid = f"user_{_uuid.uuid4().hex[:12]}"
        docs.append({
            "user_id": uid,
            "email": email,
            "password_hash": pwd_hash,
            "name": f"Load User {i}",
            "role": "user", "avatar": "",
            "language": "en",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "email_verified": True,
            "groups": [],
            "_loadtest": True,
            "token_version": 0,
        })
        tok = create_access_token(uid, email, 0)
        creds.append((email, tok))
    if docs:
        await db.users.insert_many(docs)
    return creds


async def cleanup_users_bulk(suffix):
    import sys
    sys.path.insert(0, "/app/backend")
    from database import db
    r = await db.users.delete_many({"_loadtest": True, "email": {"$regex": f"_{suffix}@meetflow.test$"}})
    print(f"Cleaned up {r.deleted_count} test users")


async def main():
    global start_ts

    # 1) Admin: create a shared template that all users will apply
    async with httpx.AsyncClient() as client:
        admin_token = await setup_admin_token(client)
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        tpl = await client.post(f"{API}/task-templates", headers=admin_headers, json={
            "name": "Load Test Template",
            "title": "Load Test Title from Template",
            "priority": "normal",
            "tags": ["loadtest", "template"],
            "checklist": [{"text": "tpl step 1", "done": False}, {"text": "tpl step 2", "done": False}],
        })
        template_id = tpl.json().get("template_id") if tpl.status_code == 200 else None
        print(f"Template created: {template_id}")

    # 2) Bulk-seed users via direct MongoDB insert (faster than HTTP register).
    suffix = _rand_str(6)
    print(f"Bulk-seeding {NUM_USERS} users in MongoDB...")
    seed_start = time.perf_counter()
    creds = await seed_users_bulk(suffix)
    print(f"Seeded {len(creds)} users in {time.perf_counter() - seed_start:.2f}s")

    # 3) Spawn N concurrent user workflows (using pre-issued tokens)
    print(f"Spawning {len(creds)} concurrent user workflows ...")
    start_ts = time.perf_counter()
    work_tasks = [
        asyncio.create_task(user_workflow(i, em, tok, template_id))
        for i, (em, tok) in enumerate(creds)
    ]
    await asyncio.gather(*work_tasks, return_exceptions=True)
    elapsed = time.perf_counter() - start_ts

    # 4) Cleanup: admin deletes the template + test users
    async with httpx.AsyncClient() as client:
        if template_id:
            await client.delete(f"{API}/task-templates/{template_id}", headers=admin_headers, timeout=30.0)
    await cleanup_users_bulk(suffix)

    # 4) Report
    lines = []
    lines.append(f"# Iter 201 — Tasks Module Load Test ({NUM_USERS} concurrent users)\n")
    lines.append(f"**Elapsed:** {elapsed:.1f}s · **Total requests:** {total_requests} · **Failures:** {total_failures} ({100 * total_failures / max(total_requests, 1):.2f}%) · **Throughput:** {total_requests / elapsed:.1f} req/s\n")
    lines.append("\n## Per-operation metrics\n")
    lines.append("| Operation | Count | p50 ms | p95 ms | p99 ms | Max ms | Errors |")
    lines.append("|---|---:|---:|---:|---:|---:|---|")

    def pct(arr, p):
        if not arr:
            return 0
        s = sorted(arr)
        return s[min(int(len(s) * p), len(s) - 1)]

    for op in sorted(metrics.keys()):
        arr = metrics[op]
        e = errors.get(op, {})
        e_str = ", ".join(f"{k}:{v}" for k, v in sorted(e.items(), key=lambda kv: str(kv[0]))) or "—"
        lines.append(f"| {op} | {len(arr)} | {median(arr):.0f} | {pct(arr, 0.95):.0f} | {pct(arr, 0.99):.0f} | {max(arr):.0f} | {e_str} |")

    lines.append("\n## Error summary\n")
    if not errors:
        lines.append("*No errors observed.*")
    else:
        for op, e in sorted(errors.items()):
            lines.append(f"- **{op}**: " + ", ".join(f"`{k}`={v}" for k, v in sorted(e.items(), key=lambda kv: str(kv[0]))))
            for sample in error_bodies.get(op, [])[:2]:
                lines.append(f"    - sample: `{sample}`")

    report_path = "/app/test_reports/iter201_load_200users.md"
    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    print(f"\nReport written: {report_path}")
    print("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
