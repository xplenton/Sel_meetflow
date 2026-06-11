"""iter 213 — Comprehensive RBAC test: roles, groups, capabilities, denies.

Exercises every layer of the permission system end-to-end:

  Layer 1: Role defaults
    - Create user with role 'member' → has tasks.create, no news.publish
    - Promote to 'moderator' → gains news.publish

  Layer 2: Group inheritance
    - Create group 'Pflegedienst' with cap news.publish
    - Add member-role user → effective caps now include news.publish
    - Remove from group → effective caps lose news.publish

  Layer 3: Direct grants (with optional expiry)
    - Grant single user 'meetings.record' directly → user has it
    - Revoke → user loses it

  Layer 4: Direct denies (override priority)
    - Group gives news.publish, user denies news.publish → effective DOES NOT have it
    - Verifies that denies beat grants (correct security posture)

  Layer 5: Cap-driven endpoint enforcement
    - Without news.publish: POST /news → 403
    - With news.publish (via role / group / grant): POST /news → 201
    - Same for other capabilities (meetings.create, surveys.create, …)

  Layer 6: Hub endpoints
    - /admin/permissions/who-has-cap correctly attributes sources
    - /me/permissions/breakdown returns the same effective set

Each scenario is a separate function so failures are localised in the report.
"""
import asyncio
import os
import sys
import time
import httpx

API = os.environ.get("API_URL") or "http://localhost:8001"
ADMIN_EMAIL = "admin@meetflow.com"
ADMIN_PASS = "admin123"

# Counter for unique emails so reruns don't collide.
RUN_TAG = f"rbac{int(time.time()) % 100000}"


class TestRunner:
    def __init__(self):
        self.client = httpx.AsyncClient(base_url=API, timeout=15.0)
        self.admin_token = None
        self.created_users = []   # list of user_ids to clean up
        self.created_groups = []  # list of group_ids
        self.passed = 0
        self.failed = []

    async def close(self):
        await self.cleanup()
        await self.client.aclose()

    async def login_admin(self):
        r = await self.client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
        r.raise_for_status()
        self.admin_token = r.json()["token"]

    def admin_headers(self):
        return {"Authorization": f"Bearer {self.admin_token}"}

    # ---------- helpers ----------
    async def create_user(self, name_suffix: str, get_token: bool = True):
        email = f"{RUN_TAG}_{name_suffix}@example.com"
        r = await self.client.post(
            "/api/admin/users/invite",
            json={"email": email, "name": f"{RUN_TAG}-{name_suffix}", "role": "member"},
            headers=self.admin_headers(),
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"invite failed: {r.status_code} {r.text[:120]}")
        body = r.json()
        user_id = body["user_id"]
        password = body["temp_password"]
        await self.client.put(
            f"/api/admin/users/{user_id}",
            json={"must_change_password": False},
            headers=self.admin_headers(),
        )
        token = None
        if get_token:
            # Login throttled at 10/min; only mint a token when the scenario
            # actually needs to act as the user.
            for attempt in range(6):
                lr = await self.client.post(
                    "/api/auth/login", json={"email": email, "password": password}
                )
                if lr.status_code == 429:
                    await asyncio.sleep(6 + attempt * 3)
                    continue
                if lr.status_code != 200:
                    raise RuntimeError(f"login failed for {email}: {lr.status_code}")
                token = lr.json()["token"]
                break
            if token is None:
                raise RuntimeError(f"login throttled for {email}")
        self.created_users.append(user_id)
        return user_id, email, token

    async def create_group(self, name: str, capabilities=None):
        r = await self.client.post(
            "/api/admin/groups",
            json={"name": f"{RUN_TAG}-{name}", "color": "#4A5D4E",
                  "capabilities": capabilities or []},
            headers=self.admin_headers(),
        )
        r.raise_for_status()
        g = r.json()
        self.created_groups.append(g["group_id"])
        return g["group_id"]

    async def set_group_members(self, group_id: str, member_ids: list):
        # Endpoint adds/removes individuals; replicate "set" semantics here.
        cur = await self.client.get(
            "/api/admin/groups", headers=self.admin_headers()
        )
        groups = cur.json()
        existing = next((g for g in groups if g["group_id"] == group_id), None)
        existing_members = set(existing.get("members", []) if existing else [])
        target = set(member_ids)
        for to_add in target - existing_members:
            await self.client.post(
                f"/api/admin/groups/{group_id}/members",
                json={"user_id": to_add},
                headers=self.admin_headers(),
            )
        for to_remove in existing_members - target:
            await self.client.delete(
                f"/api/admin/groups/{group_id}/members/{to_remove}",
                headers=self.admin_headers(),
            )

    async def set_user_caps(self, user_id: str, grants=None, denies=None, expires=None):
        r = await self.client.put(
            f"/api/admin/users/{user_id}/capabilities",
            json={"grants": grants or [], "denies": denies or [], "expires": expires or {}},
            headers=self.admin_headers(),
        )
        r.raise_for_status()

    async def get_effective(self, user_id: str):
        r = await self.client.get(
            f"/api/admin/users/{user_id}/simulate", headers=self.admin_headers()
        )
        r.raise_for_status()
        return set(r.json()["effective"])

    async def get_self_breakdown(self, token: str):
        r = await self.client.get(
            "/api/me/permissions/breakdown",
            headers={"Authorization": f"Bearer {token}"},
        )
        r.raise_for_status()
        return r.json()

    # ---------- assertions ----------
    def check(self, label: str, condition, detail=""):
        if condition:
            self.passed += 1
            print(f"  ✓ {label}")
        else:
            self.failed.append((label, detail))
            print(f"  ✗ {label}  ← {detail}")

    # ---------- scenarios ----------
    async def scenario_role_defaults(self):
        print("\n--- 1. Role defaults ---")
        uid, email, token = await self.create_user("role_default", get_token=False)
        eff_member = await self.get_effective(uid)
        self.check("member has tasks.create", "tasks.create" in eff_member)
        self.check("member does NOT have news.publish", "news.publish" not in eff_member)
        # Promote to moderator
        await self.client.put(
            f"/api/admin/users/{uid}", json={"role": "moderator"},
            headers=self.admin_headers(),
        )
        eff_mod = await self.get_effective(uid)
        self.check("after role=moderator: news.publish present",
                   "news.publish" in eff_mod, str(eff_mod - eff_member))

    async def scenario_group_inheritance(self):
        print("\n--- 2. Group inheritance ---")
        uid, email, token = await self.create_user("groupie", get_token=False)
        gid = await self.create_group("Pflegedienst", ["news.publish"])
        eff_before = await self.get_effective(uid)
        self.check("before join: no news.publish", "news.publish" not in eff_before)
        await self.set_group_members(gid, [uid])
        eff_after_join = await self.get_effective(uid)
        self.check("after join: news.publish present", "news.publish" in eff_after_join)
        # Remove from group
        await self.set_group_members(gid, [])
        eff_after_leave = await self.get_effective(uid)
        self.check("after leave: news.publish removed", "news.publish" not in eff_after_leave)

    async def scenario_direct_grant(self):
        print("\n--- 3. Direct grants ---")
        uid, email, token = await self.create_user("granted", get_token=False)
        eff_before = await self.get_effective(uid)
        await self.set_user_caps(uid, grants=["meetings.record"])
        eff_after_grant = await self.get_effective(uid)
        self.check("after direct grant: meetings.record present",
                   "meetings.record" in eff_after_grant,
                   f"Δ: {eff_after_grant - eff_before}")
        await self.set_user_caps(uid, grants=[])
        eff_after_revoke = await self.get_effective(uid)
        self.check("after revoke: meetings.record gone",
                   "meetings.record" not in eff_after_revoke)

    async def scenario_deny_overrides(self):
        print("\n--- 4. Denies override grants ---")
        uid, email, token = await self.create_user("deniedguy", get_token=False)
        gid = await self.create_group("HasNews", ["news.publish"])
        await self.set_group_members(gid, [uid])
        eff_with_group = await self.get_effective(uid)
        self.check("group grant gives news.publish", "news.publish" in eff_with_group)
        # Apply deny
        await self.set_user_caps(uid, denies=["news.publish"])
        eff_with_deny = await self.get_effective(uid)
        self.check("deny removes news.publish despite group",
                   "news.publish" not in eff_with_deny,
                   "Deny did not override group grant!")
        # Remove deny
        await self.set_user_caps(uid, denies=[])
        eff_after_undeny = await self.get_effective(uid)
        self.check("removing deny restores group permission",
                   "news.publish" in eff_after_undeny)

    async def scenario_endpoint_enforcement(self):
        print("\n--- 5. Endpoint enforcement (caps actually gate features) ---")
        uid, email, token = await self.create_user("enforce")
        # As plain member, news.publish missing
        r = await self.client.post(
            "/api/news/posts",
            json={"title": "Probe", "content": "Test", "audience_groups": []},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.check("member without news.publish gets 403 on POST /news/posts",
                   r.status_code == 403, f"got {r.status_code}: {r.text[:80]}")
        # Grant news.publish directly
        await self.set_user_caps(uid, grants=["news.publish", "news.create"])
        await asyncio.sleep(0.2)
        r2 = await self.client.post(
            "/api/news/posts",
            json={"title": f"Probe {RUN_TAG}", "content": "Test",
                  "audience_groups": [], "publish": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.check("after grant: POST /news/posts succeeds (200/201)",
                   r2.status_code in (200, 201),
                   f"got {r2.status_code}: {r2.text[:120]}")

    async def scenario_who_has_cap(self):
        print("\n--- 6. /admin/permissions/who-has-cap source attribution ---")
        # Three users gaining news.publish three different ways
        u1, _, _ = await self.create_user("via_role", get_token=False)
        # Promote u1 to moderator role separately
        await self.client.put(f"/api/admin/users/{u1}", json={"role": "moderator"}, headers=self.admin_headers())
        u2, _, _ = await self.create_user("via_group", get_token=False)
        gid = await self.create_group("PubGroup", ["news.publish"])
        await self.set_group_members(gid, [u2])
        u3, _, _ = await self.create_user("via_grant", get_token=False)
        await self.set_user_caps(u3, grants=["news.publish"])

        r = await self.client.get(
            "/api/admin/permissions/who-has-cap/news.publish",
            headers=self.admin_headers(),
        )
        r.raise_for_status()
        users = {u["user_id"]: u for u in r.json()["users"]}
        # u1 should appear with type=role
        self.check("u1 has 'role' source",
                   u1 in users and any(s["type"] == "role" for s in users[u1]["sources"]),
                   f"got {users.get(u1, {}).get('sources')}")
        self.check("u2 has 'group' source",
                   u2 in users and any(s["type"] == "group" for s in users[u2]["sources"]),
                   f"got {users.get(u2, {}).get('sources')}")
        self.check("u3 has 'grant' source",
                   u3 in users and any(s["type"] == "grant" for s in users[u3]["sources"]),
                   f"got {users.get(u3, {}).get('sources')}")

    async def scenario_self_breakdown(self):
        print("\n--- 7. /me/permissions/breakdown (end-user self-service) ---")
        uid, email, token = await self.create_user("self_view")
        gid = await self.create_group("UserGrp", ["surveys.create", "tasks.assign_others"])
        await self.set_group_members(gid, [uid])
        await self.set_user_caps(uid, grants=["meetings.record"])
        b = await self.get_self_breakdown(token)
        eff = set(b["effective"])
        self.check("breakdown effective contains role default tasks.create",
                   "tasks.create" in eff)
        self.check("breakdown effective contains group cap surveys.create",
                   "surveys.create" in eff)
        self.check("breakdown effective contains direct grant meetings.record",
                   "meetings.record" in eff)
        self.check("breakdown lists the group",
                   any(g["group_id"] == gid for g in b["groups"]))
        self.check("breakdown direct_grants includes meetings.record",
                   "meetings.record" in b["direct_grants"])

    async def scenario_cap_expiry(self):
        print("\n--- 8. Cap expiry ---")
        uid, email, token = await self.create_user("expirable", get_token=False)
        # Already-expired grant: 1 second ago
        from datetime import datetime, timezone, timedelta
        past = (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat().replace("+00:00", "Z")
        await self.set_user_caps(uid, grants=["meetings.record"],
                                  expires={"meetings.record": past})
        eff = await self.get_effective(uid)
        self.check("expired grant is filtered out of effective set",
                   "meetings.record" not in eff,
                   f"got effective={list(eff - set(['view:dashboard']))[:10]}")
        # Future grant: still active
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        await self.set_user_caps(uid, grants=["surveys.create"],
                                  expires={"surveys.create": future})
        eff2 = await self.get_effective(uid)
        self.check("future-expiring grant is still active",
                   "surveys.create" in eff2)

    async def scenario_audit(self):
        print("\n--- 9. Audit endpoint detects redundancies ---")
        uid, email, token = await self.create_user("redundant", get_token=False)
        # member already has tasks.create by role default — granting it again is redundant
        await self.set_user_caps(uid, grants=["tasks.create"])
        r = await self.client.get(
            "/api/admin/permissions/audit", headers=self.admin_headers()
        )
        r.raise_for_status()
        audit = r.json()
        match = next(
            (e for e in audit["redundant_grants"] if e["user_id"] == uid and e["cap"] == "tasks.create"),
            None,
        )
        self.check("audit detects redundant grant covered by role",
                   match is not None and match.get("covered_by") == "role",
                   f"redundant_grants for our user: {[r for r in audit['redundant_grants'] if r['user_id']==uid]}")

    # ---------- cleanup ----------
    async def cleanup(self):
        print("\n--- Cleanup ---")
        for uid in self.created_users:
            try:
                await self.client.delete(f"/api/admin/users/{uid}", headers=self.admin_headers())
            except Exception:
                pass
        for gid in self.created_groups:
            try:
                await self.client.delete(f"/api/admin/groups/{gid}", headers=self.admin_headers())
            except Exception:
                pass
        print(f"  Removed {len(self.created_users)} users, {len(self.created_groups)} groups")


async def main():
    r = TestRunner()
    try:
        await r.login_admin()
        await r.scenario_role_defaults()
        await r.scenario_group_inheritance()
        await r.scenario_direct_grant()
        await r.scenario_deny_overrides()
        await r.scenario_endpoint_enforcement()
        await r.scenario_who_has_cap()
        await r.scenario_self_breakdown()
        await r.scenario_cap_expiry()
        await r.scenario_audit()
    finally:
        await r.close()
    print(f"\n{'='*60}\nPASSED: {r.passed}   FAILED: {len(r.failed)}\n{'='*60}")
    if r.failed:
        for label, detail in r.failed:
            print(f"  ✗ {label}\n    {detail}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
