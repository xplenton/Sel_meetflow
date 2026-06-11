"""Iter 179 regression — read-receipts end-to-end via REST.

Two users (alice, bob) are in a conversation. Alice sends a message; Bob
marks the conversation as read via `POST /api/chat/conversations/{id}/mark-read`.
Alice then fetches `/read-status` and must see Bob's `last_read` timestamp
>= her message's `created_at`.
"""
import os
import sys
import uuid
import asyncio
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
    alice_email = f"alice_{tag}@loadtest.local"
    bob_email = f"bob_{tag}@loadtest.local"

    async with httpx.AsyncClient(timeout=15.0) as client:
        alice_token, alice_id = await register(client, alice_email, f"Alice {tag}")
        bob_token, bob_id = await register(client, bob_email, f"Bob {tag}")

        # Alice creates direct conversation with Bob
        r = await client.post(
            f"{API}/api/chat/conversations",
            headers={"Authorization": f"Bearer {alice_token}"},
            json={"type": "direct", "member_ids": [bob_id]},
        )
        r.raise_for_status()
        conv_id = r.json()["conversation_id"]

        # Alice sends a message
        r = await client.post(
            f"{API}/api/chat/conversations/{conv_id}/messages",
            headers={"Authorization": f"Bearer {alice_token}"},
            json={"content": "Hallo Bob!"},
        )
        r.raise_for_status()
        msg_created_at = r.json().get("created_at")
        assert msg_created_at, "message missing created_at"

        # Bob marks as read
        r = await client.post(
            f"{API}/api/chat/conversations/{conv_id}/mark-read",
            headers={"Authorization": f"Bearer {bob_token}"},
        )
        r.raise_for_status()
        bob_last_read = r.json()["last_read"]
        assert bob_last_read >= msg_created_at, \
            f"Bob's last_read ({bob_last_read}) should be >= message ts ({msg_created_at})"
        print("✓ Bob's mark-read ISO is >= message created_at")

        # Alice fetches read-status, must see Bob's timestamp
        r = await client.get(
            f"{API}/api/chat/conversations/{conv_id}/read-status",
            headers={"Authorization": f"Bearer {alice_token}"},
        )
        r.raise_for_status()
        rs = r.json()["read_status"]
        assert bob_id in rs, f"Bob not in read_status: {rs}"
        assert rs[bob_id] >= msg_created_at, \
            f"Alice sees Bob's last_read={rs[bob_id]}, msg_ts={msg_created_at}"
        print("✓ Alice sees Bob's read-receipt")

        # Non-member cannot fetch
        r = await client.post(
            f"{API}/api/auth/register",
            json={"email": f"eve_{tag}@loadtest.local", "password": "Test1234!", "name": "Eve"},
        )
        eve_token = r.json()["token"]
        r = await client.get(
            f"{API}/api/chat/conversations/{conv_id}/read-status",
            headers={"Authorization": f"Bearer {eve_token}"},
        )
        assert r.status_code == 404, f"Eve should get 404, got {r.status_code}"
        print("✓ non-member gets 404")

        # Cleanup
        from motor.motor_asyncio import AsyncIOMotorClient
        mc = AsyncIOMotorClient(os.environ["MONGO_URL"])
        d = mc[os.environ["DB_NAME"]]
        await d.users.delete_many({"email": {"$in": [alice_email, bob_email, f"eve_{tag}@loadtest.local"]}})
        await d.conversations.delete_one({"conversation_id": conv_id})
        await d.messages.delete_many({"conversation_id": conv_id})
        mc.close()


if __name__ == "__main__":
    asyncio.run(main())
    print("ALL OK")
