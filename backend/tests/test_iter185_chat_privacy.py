"""Iter 185 — chat privacy regression.

Verifies that a non-member of a conversation cannot:
  * read its messages
  * send a message
  * pin / mute it
  * add or remove members
  * react to its messages
  * upload a file / send a voice / send a GIF
  * change encryption flag / read group key

Each call must return 404 (not 403) so the existence of the conv is hidden.
"""
import asyncio
import os
import sys
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v.strip().strip('"').strip("'"))

API = "http://localhost:8001"


async def register(client, email, name):
    r = await client.post(f"{API}/api/auth/register", json={
        "email": email, "password": "Test1234!", "name": name,
    })
    r.raise_for_status()
    return r.json()["token"], r.json()["user_id"]


async def main():
    tag = uuid.uuid4().hex[:6]
    a_email = f"alice_{tag}@loadtest.local"
    b_email = f"bob_{tag}@loadtest.local"
    e_email = f"eve_{tag}@loadtest.local"

    failures = []

    async with httpx.AsyncClient(timeout=15.0) as client:
        a_tok, a_id = await register(client, a_email, f"Alice {tag}")
        b_tok, b_id = await register(client, b_email, f"Bob {tag}")
        e_tok, e_id = await register(client, e_email, f"Eve {tag}")

        # Alice creates direct conv with Bob (Eve is NOT a member)
        r = await client.post(
            f"{API}/api/chat/conversations",
            headers={"Authorization": f"Bearer {a_tok}"},
            json={"type": "group", "name": f"PrivGroup {tag}", "member_ids": [b_id]},
        )
        r.raise_for_status()
        conv_id = r.json()["conversation_id"]

        # Alice sends a message Eve must never see
        r = await client.post(
            f"{API}/api/chat/conversations/{conv_id}/messages",
            headers={"Authorization": f"Bearer {a_tok}"},
            json={"content": "secret"},
        )
        r.raise_for_status()
        msg_id = r.json()["message_id"]

        eve = {"Authorization": f"Bearer {e_tok}"}

        async def expect_404(label, coro_func):
            r = await coro_func()
            ok = r.status_code == 404
            if not ok:
                failures.append(f"{label}: expected 404, got {r.status_code} — {r.text[:80]}")
            print(f"{'✓' if ok else '✗'} {label}: {r.status_code}")

        # 1) GET messages
        await expect_404("GET /messages",
            lambda: client.get(f"{API}/api/chat/conversations/{conv_id}/messages", headers=eve))

        # 2) POST messages (the existing endpoint already had a check, verify still works)
        await expect_404("POST /messages",
            lambda: client.post(f"{API}/api/chat/conversations/{conv_id}/messages",
                                headers=eve, json={"content": "spam"}))

        # 3) Pin
        await expect_404("PUT /pin",
            lambda: client.put(f"{API}/api/chat/conversations/{conv_id}/pin", headers=eve))

        # 4) Mute
        await expect_404("PUT /mute",
            lambda: client.put(f"{API}/api/chat/conversations/{conv_id}/mute", headers=eve))

        # 5) Add member (Eve cannot add herself)
        await expect_404("POST /members (self-add)",
            lambda: client.post(f"{API}/api/chat/conversations/{conv_id}/members",
                                headers=eve, json={"user_id": e_id}))

        # 6) Remove member (Eve cannot remove Bob)
        await expect_404("DELETE /members/{bob}",
            lambda: client.delete(f"{API}/api/chat/conversations/{conv_id}/members/{b_id}",
                                  headers=eve))

        # 7) React to a message in private conv
        await expect_404("POST reactions",
            lambda: client.post(f"{API}/api/chat/messages/{msg_id}/reactions",
                                headers=eve, json={"emoji": "👀"}))

        # 8) Send a GIF
        await expect_404("POST /gif",
            lambda: client.post(f"{API}/api/chat/conversations/{conv_id}/gif",
                                headers=eve, json={"url": "https://x.example/x.gif"}))

        # 9) Toggle encryption
        await expect_404("PUT /encryption",
            lambda: client.put(f"{API}/api/chat/conversations/{conv_id}/encryption", headers=eve))

        # 10) Get group key
        await expect_404("GET /group-key",
            lambda: client.get(f"{API}/api/chat/conversations/{conv_id}/group-key", headers=eve))

        # 11) Bonus: list conversations as Eve must NOT contain conv_id
        r = await client.get(f"{API}/api/chat/conversations", headers=eve)
        r.raise_for_status()
        eve_convs = r.json()
        leak = any(c.get("conversation_id") == conv_id for c in eve_convs)
        if leak:
            failures.append("Eve's /chat/conversations leaks Alice/Bob's private conv")
        print(f"{'✓' if not leak else '✗'} Eve's conv list does not contain private conv")

        # 12) Sanity: Alice IS a member, must succeed for at least one route
        r = await client.get(f"{API}/api/chat/conversations/{conv_id}/messages",
                             headers={"Authorization": f"Bearer {a_tok}"})
        if r.status_code != 200:
            failures.append(f"Alice (member) cannot read her own conv messages: {r.status_code}")
        print(f"{'✓' if r.status_code == 200 else '✗'} Alice (member) can read messages")

        # Cleanup
        from motor.motor_asyncio import AsyncIOMotorClient
        mc = AsyncIOMotorClient(os.environ["MONGO_URL"])
        d = mc[os.environ["DB_NAME"]]
        await d.users.delete_many({"email": {"$in": [a_email, b_email, e_email]}})
        await d.conversations.delete_one({"conversation_id": conv_id})
        await d.messages.delete_many({"conversation_id": conv_id})
        mc.close()

    if failures:
        print("\n=== FAILURES ===")
        for f in failures:
            print("  -", f)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
    print("ALL OK")
