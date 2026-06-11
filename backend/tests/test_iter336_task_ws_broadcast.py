"""Iter 336 — Live-Update fan-out test for Tasks.

We open a WebSocket as user A, then user B creates / updates / deletes
a task assigned to user A. User A's socket MUST receive `task-created`,
`task-updated` and `task-deleted` frames.

Run: python3 /app/backend/tests/test_iter336_task_ws_broadcast.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid

import aiohttp

BASE = os.environ.get("WS_BASE_URL") or "http://localhost:8001"
WS_BASE = BASE.replace("http://", "ws://").replace("https://", "wss://")


async def login(session: aiohttp.ClientSession, email: str, password: str) -> tuple[str, str]:
    async with session.post(
        f"{BASE}/api/auth/login",
        json={"email": email, "password": password},
    ) as r:
        if r.status != 200:
            raise RuntimeError(f"login failed {r.status}: {await r.text()}")
        data = await r.json()
        return data.get("token") or data.get("access_token"), data["user_id"]


async def ensure_user(admin_token: str, email: str, password: str, name: str) -> str:
    """Create the user if missing — return their user_id."""
    async with aiohttp.ClientSession() as s:
        # Try login first
        async with s.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}) as r:
            if r.status == 200:
                data = await r.json()
                return data["user_id"]
        # Else register
        async with s.post(
            f"{BASE}/api/auth/register",
            json={"email": email, "password": password, "name": name},
        ) as r:
            if r.status not in (200, 201):
                raise RuntimeError(f"register {email} failed: {r.status} {await r.text()}")
            data = await r.json()
            return data.get("user_id") or data.get("user", {}).get("user_id")


async def collect_ws(uid: str, token: str, q: asyncio.Queue, stop: asyncio.Event):
    url = f"{WS_BASE}/api/ws/chat/{uid}"
    async with aiohttp.ClientSession() as s:
        try:
            async with s.ws_connect(url, headers={"Authorization": f"Bearer {token}"}) as ws:
                while not stop.is_set():
                    try:
                        msg = await asyncio.wait_for(ws.receive(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            await q.put(json.loads(msg.data))
                        except Exception:
                            pass
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break
        except Exception as e:
            print(f"[ws-{uid[:8]}] error: {e}")


async def main() -> int:
    async with aiohttp.ClientSession() as s:
        admin_token, admin_uid = await login(s, "admin@meetflow.com", "admin123")
    print(f"admin user_id = {admin_uid}")

    bob_email = f"bob_ws_{uuid.uuid4().hex[:6]}@meetflow.test"
    bob_uid = await ensure_user(admin_token, bob_email, "Bob12345!", "Bob WS Test")
    print(f"bob user_id   = {bob_uid}")

    async with aiohttp.ClientSession() as s:
        bob_token, _ = await login(s, bob_email, "Bob12345!")

    # Bob opens a WS, admin will fire CRUD operations assigning Bob.
    bob_q: asyncio.Queue = asyncio.Queue()
    stop = asyncio.Event()
    ws_task = asyncio.create_task(collect_ws(bob_uid, bob_token, bob_q, stop))
    await asyncio.sleep(1.5)  # let the WS connect

    # 1) admin creates a task assigned to bob
    async with aiohttp.ClientSession() as s:
        h = {"Authorization": f"Bearer {admin_token}"}
        async with s.post(f"{BASE}/api/tasks", headers=h, json={
            "title": "Live-Test Task",
            "description": "auto",
            "assignee_ids": [bob_uid],
            "status": "open",
        }) as r:
            task = await r.json()
            assert r.status == 200, f"create failed: {r.status} {task}"
        tid = task["task_id"]
        # 2) admin updates status
        async with s.put(f"{BASE}/api/tasks/{tid}", headers=h, json={"status": "in_progress"}) as r:
            assert r.status == 200, f"update failed: {await r.text()}"
        # 3) admin deletes the task
        async with s.delete(f"{BASE}/api/tasks/{tid}", headers=h) as r:
            assert r.status == 200, f"delete failed: {await r.text()}"

    # Drain queue for 3s
    received = []
    try:
        for _ in range(50):
            try:
                msg = await asyncio.wait_for(bob_q.get(), timeout=0.3)
                received.append(msg)
            except asyncio.TimeoutError:
                if any(m.get("type") == "task-deleted" for m in received):
                    break
    finally:
        stop.set()
        try:
            await asyncio.wait_for(ws_task, timeout=2)
        except asyncio.TimeoutError:
            ws_task.cancel()

    task_events = [m for m in received if isinstance(m, dict) and isinstance(m.get("type"), str) and m["type"].startswith("task-")]
    print(f"Received {len(task_events)} task events:")
    for m in task_events:
        print(f"   - {m['type']:<14} task_id={m.get('task_id','?')[:18]} actor={m.get('actor_id','?')[:18]}")

    types = {m["type"] for m in task_events}
    expected = {"task-created", "task-updated", "task-deleted"}
    missing = expected - types
    if missing:
        print(f"FAIL — missing event types: {missing}")
        return 1
    print("PASS — all 3 task events delivered to Bob over WebSocket")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
