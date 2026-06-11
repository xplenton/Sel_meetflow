"""Bulk-seed additional load-test users to reach a total of 500.
Writes directly to MongoDB to avoid rate-limit on /invite.

Emails: loadtest051@meetflow.local … loadtest500@meetflow.local
Password: Test123!  (hashed with the app's hash_password helper)
Roles/departments/locations/professions rotated round-robin.
"""
import asyncio
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, "/app/backend")

from database import db  # noqa: E402
from dependencies import hash_password  # noqa: E402


DEPARTMENTS = ["IT", "HR", "Sales", "Marketing", "Operations", "Finance", "Legal", "Support", "Pflege", "Radiologie"]
LOCATIONS = ["Berlin", "Munich", "Hamburg", "Frankfurt", "Cologne", "Stuttgart", "Leipzig", "Bremen"]
PROFESSIONS = ["Arzt", "Pflegerin", "Developer", "Manager", "Analyst", "Designer", "Consultant", "Sekretariat"]
ROLES = ["member", "member", "member", "member", "moderator"]  # weighted


async def seed():
    start = 51
    end = 500
    password_hash = hash_password("Test123!")
    existing = set()
    async for u in db.users.find({"email": {"$regex": r"^loadtest\d+@meetflow\.local$"}}, {"_id": 0, "email": 1}):
        existing.add(u["email"])
    batch = []
    created = 0
    for i in range(start, end + 1):
        email = f"loadtest{i:03d}@meetflow.local"
        if email in existing:
            continue
        batch.append({
            "user_id": f"user_{uuid.uuid4().hex[:12]}",
            "email": email,
            "password_hash": password_hash,
            "name": f"Loadtest User {i:03d}",
            "role": ROLES[i % len(ROLES)],
            "department": DEPARTMENTS[i % len(DEPARTMENTS)],
            "location": LOCATIONS[i % len(LOCATIONS)],
            "profession": PROFESSIONS[i % len(PROFESSIONS)],
            "groups": [],
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_seen_at": datetime.now(timezone.utc).isoformat(),
            "capabilities": [],
        })
        if len(batch) >= 100:
            await db.users.insert_many(batch)
            created += len(batch)
            batch = []
    if batch:
        await db.users.insert_many(batch)
        created += len(batch)
    total = await db.users.count_documents({"email": {"$regex": r"^loadtest\d+@meetflow\.local$"}})
    print(f"created_now={created} total_loadtest_users={total}")


if __name__ == "__main__":
    asyncio.run(seed())
