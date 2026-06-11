"""Iter 182/183 regression tests.

1) Invite email_sent is false when provider=none (simulated) — no more
   misleading "email_sent: true".
2) Notification preferences persist and is_allowed() honours them.
"""
import asyncio
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v.strip().strip('"').strip("'"))

import httpx

API = "http://localhost:8001"


async def _admin_token(client):
    r = await client.post(f"{API}/api/auth/login", json={
        "email": "admin@meetflow.com", "password": "admin123",
    })
    r.raise_for_status()
    return r.json()["token"]


async def test_invite_email_status():
    async with httpx.AsyncClient(timeout=20) as client:
        token = await _admin_token(client)
        tag = uuid.uuid4().hex[:6]
        email = f"invitee_{tag}@loadtest.local"
        # Force provider=none by resetting config
        from motor.motor_asyncio import AsyncIOMotorClient
        mc = AsyncIOMotorClient(os.environ["MONGO_URL"])
        d = mc[os.environ["DB_NAME"]]
        await d.email_config.update_one(
            {"config_id": "global"}, {"$set": {"provider": "none"}}, upsert=True,
        )
        try:
            r = await client.post(
                f"{API}/api/admin/users/invite",
                headers={"Authorization": f"Bearer {token}"},
                json={"email": email, "name": f"Invitee {tag}", "role": "member"},
            )
            r.raise_for_status()
            body = r.json()
            assert body["email_sent"] is False, f"expected email_sent=False, got {body}"
            assert body["email_simulated"] is True, f"expected simulated=True, got {body}"
            print("✓ invite email_sent is false when provider=none")
            print(f"  email_provider={body['email_provider']} status={body['email_status']}")
        finally:
            await d.users.delete_one({"email": email})
            mc.close()


async def test_notification_prefs():
    async with httpx.AsyncClient(timeout=20) as client:
        # Create a fresh user
        tag = uuid.uuid4().hex[:6]
        email = f"nprefs_{tag}@loadtest.local"
        r = await client.post(f"{API}/api/auth/register", json={
            "email": email, "password": "Test1234!", "name": f"Notif {tag}",
        })
        r.raise_for_status()
        token = r.json()["token"]
        user_id = r.json()["user_id"]

        # Default prefs
        r = await client.get(f"{API}/api/users/me/notification-prefs",
                             headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        prefs = r.json()
        assert "news" in prefs["prefs"]
        assert prefs["prefs"]["news"]["email"] is True
        print("✓ default prefs returned")

        # Disable news/push
        r = await client.put(
            f"{API}/api/users/me/notification-prefs",
            headers={"Authorization": f"Bearer {token}"},
            json={"prefs": {"news": {"push": False}}},
        )
        r.raise_for_status()
        assert r.json()["prefs"]["news"]["push"] is False
        print("✓ partial patch works")

        # Verify is_allowed() sees it
        sys.path.insert(0, "/app/backend")
        from services.notification_prefs import is_allowed
        allowed_push = await is_allowed(user_id, "news", "push")
        allowed_email = await is_allowed(user_id, "news", "email")
        assert allowed_push is False, "is_allowed(news, push) should be False"
        assert allowed_email is True, "is_allowed(news, email) should still be True"
        print("✓ is_allowed() honours patch")

        # Quiet hours applied only to push
        await client.put(
            f"{API}/api/users/me/notification-prefs",
            headers={"Authorization": f"Bearer {token}"},
            json={"quiet_hours": {"enabled": True, "start": "00:00", "end": "23:59"},
                  "prefs": {"news": {"push": True}}},
        )
        allowed_push_quiet = await is_allowed(user_id, "news", "push")
        allowed_email_quiet = await is_allowed(user_id, "news", "email")
        assert allowed_push_quiet is False, "push during quiet hours should be blocked"
        assert allowed_email_quiet is True, "email during quiet hours should pass"
        print("✓ quiet hours only affect push")

        # Cleanup
        from motor.motor_asyncio import AsyncIOMotorClient
        mc = AsyncIOMotorClient(os.environ["MONGO_URL"])
        d = mc[os.environ["DB_NAME"]]
        await d.users.delete_one({"user_id": user_id})
        await d.notification_prefs.delete_one({"user_id": user_id})
        mc.close()


async def main():
    await test_invite_email_status()
    await test_notification_prefs()


if __name__ == "__main__":
    asyncio.run(main())
    print("ALL OK")
