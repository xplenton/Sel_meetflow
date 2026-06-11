"""routes/admin/users.py — User CRUD, invitations, force-logout, status (split out from routes/admin.py in iter 261)."""
from fastapi import APIRouter, HTTPException, Request
import os
import re
import uuid
import secrets as _secrets
from datetime import datetime, timezone
from database import db
from dependencies import get_current_user, hash_password
from services.email import send_email_real, build_invite_email_html
from services.permission_audit import log_caps_change

router = APIRouter()


# Iter 379 — Erzeugt ein Initialpasswort, das die 4-aus-4-Policy erfuellt.
# Wird beim Admin-Invite + Bulk-Import + Reset-Helper benutzt.
def _generate_compliant_temp_password(length: int = 12) -> str:
    if length < 8:
        length = 8
    upper = "ABCDEFGHJKLMNPQRSTUVWXYZ"     # Ohne I/O fuer Lesbarkeit
    lower = "abcdefghijkmnpqrstuvwxyz"     # Ohne l/o
    digits = "23456789"                     # Ohne 0/1
    specials = "!@#$%&*?+-"
    base = [
        _secrets.choice(upper),
        _secrets.choice(lower),
        _secrets.choice(digits),
        _secrets.choice(specials),
    ]
    pool = upper + lower + digits + specials
    base += [_secrets.choice(pool) for _ in range(length - 4)]
    out = list(base)
    for i in range(len(out) - 1, 0, -1):
        j = _secrets.randbelow(i + 1)
        out[i], out[j] = out[j], out[i]
    return "".join(out)

@router.get("/admin/users")
async def admin_list_users(
    request: Request,
    page: int = 0,
    limit: int = 0,
    search: str = "",
    role: str = "",
    department: str = "",
    location: str = "",
    status: str = "",
    profession: str = "",
):
    """List users. Backward-compat:
      - no query params → legacy behavior: return raw list (first 1000, newest first)
      - `page>=1 & limit>=1` → return {users, total, page, limit, pages}
        with server-side search + filters
    """
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    # Build filter document
    q = {}
    if role:
        q["role"] = role
    if department:
        q["department"] = department
    if location:
        q["location"] = location
    if profession:
        q["profession"] = profession
    if status == "active":
        q["status"] = {"$ne": "inactive"}
    elif status == "inactive":
        q["status"] = "inactive"
    elif status == "locked_unverified":
        # Iter 291 — filter for the auto-lock pipeline
        q["status"] = "locked_unverified"
    elif status == "pending_verification":
        # Iter 291 — pseudo-status: self-registered + unverified + still active
        q["self_registered"] = True
        q["email_verified"] = {"$ne": True}
        q["status"] = {"$nin": ["locked_unverified", "inactive"]}

    if search:
        import re
        rx = re.compile(re.escape(search), re.IGNORECASE)
        q["$or"] = [
            {"name": rx}, {"email": rx},
            {"department": rx}, {"location": rx}, {"profession": rx},
            # Iter 366 — Personalnummer in Schnellsuche der Admin-Userliste
            {"personnel_number": rx},
        ]

    projection = {"_id": 0, "password_hash": 0}

    # Legacy (no pagination args) → raw list to preserve backward-compat for
    # bulk consumers (GroupsPanel, PermissionsPanel, ReminderConfig, etc.)
    if page <= 0 and limit <= 0:
        users = await db.users.find(q, projection).sort("created_at", -1).to_list(1000)
        return users

    page = max(1, int(page or 1))
    limit = max(1, min(200, int(limit or 50)))
    skip = (page - 1) * limit
    total = await db.users.count_documents(q)
    users = await db.users.find(q, projection).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {
        "users": users,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": max(1, (total + limit - 1) // limit),
    }


@router.get("/admin/users/filters")
async def admin_list_user_filters(request: Request):
    """Distinct values for department, location, profession, role — for filter dropdowns."""
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    departments = sorted([d for d in (await db.users.distinct("department")) if d])
    locations = sorted([d for d in (await db.users.distinct("location")) if d])
    professions = sorted([d for d in (await db.users.distinct("profession")) if d])
    roles = sorted([d for d in (await db.users.distinct("role")) if d])
    return {"departments": departments, "locations": locations, "professions": professions, "roles": roles}


@router.get("/admin/users/export.csv")
async def admin_export_users_csv(request: Request):
    """Iter 342 — CSV-Export aller User, kompatibel mit /admin/users/bulk-import.

    Spalten exakt wie der Import erwartet:
      email, first_name, last_name, display_name, phone, department, role, group_ids

    `group_ids` wird als `;`-separierte Liste exportiert (passt zum Import-Parser).
    Admin-only. Inaktive User werden nicht ausgelassen — Admin entscheidet beim
    Re-Import was er macht.
    """
    from fastapi.responses import Response
    import csv
    import io

    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    users = await db.users.find(
        {},
        {
            "_id": 0, "email": 1, "first_name": 1, "last_name": 1, "display_name": 1,
            "phone": 1, "department": 1, "role": 1, "groups": 1, "name": 1,
        },
    ).sort("email", 1).to_list(10000)

    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        "email", "first_name", "last_name", "display_name",
        "phone", "department", "role", "group_ids",
    ])
    for u in users:
        groups = u.get("groups") or []
        # If first/last are empty but legacy `name` is set, split sensibly so
        # the round-trip CSV stays useful (first token = first_name, rest = last_name).
        first = u.get("first_name") or ""
        last = u.get("last_name") or ""
        if not (first or last) and u.get("name"):
            parts = u["name"].split(" ", 1)
            first = parts[0]
            last = parts[1] if len(parts) > 1 else ""
        writer.writerow([
            u.get("email", ""),
            first,
            last,
            u.get("display_name", ""),
            u.get("phone", ""),
            u.get("department", ""),
            u.get("role", ""),
            ";".join(groups),
        ])
    csv_bytes = buf.getvalue().encode("utf-8-sig")  # BOM → Excel öffnet UTF-8 korrekt
    filename = f"meetflow-users-{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.put("/admin/users/{user_id}")
async def admin_update_user(user_id: str, request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    body = await request.json()
    # Iter 340 — neue Stammdaten + Groups vom Bulk-Profile-Update zulassen.
    allowed = [
        "name", "role", "department", "position", "phone", "status",
        "location", "profession", "org_unit",
        "first_name", "last_name", "display_name", "groups",
        # Iter 366 — Personalnummer als Stammdaten-Feld
        "personnel_number",
    ]
    updates = {k: v for k, v in body.items() if k in allowed and v is not None}
    # Auto-derive `name` if first/last were updated and name not explicitly set.
    if ("first_name" in updates or "last_name" in updates) and (not updates.get("name")):
        existing = await db.users.find_one(
            {"user_id": user_id},
            {"_id": 0, "first_name": 1, "last_name": 1, "name": 1},
        )
        fn = updates.get("first_name", (existing or {}).get("first_name", ""))
        ln = updates.get("last_name", (existing or {}).get("last_name", ""))
        combined = " ".join(p for p in [fn, ln] if p).strip()
        if combined:
            updates["name"] = combined
    # Iter 301 — Detect a role change so we can force a logout afterwards:
    # React keeps the user object in memory (sidebar/menu rendering depends on
    # `user.role`). Without a hard signal the affected user would still see
    # their OLD role until they manually reload. Bumping `token_version`
    # invalidates every existing access+refresh token they hold; the
    # frontend's next /auth/me silently 401s, AuthContext drops to the login
    # screen, and the freshly minted session reads the new role from DB.
    target = None
    role_changed = False
    if "role" in updates:
        target = await db.users.find_one({"user_id": user_id}, {"_id": 0, "role": 1, "token_version": 1})
        if target and target.get("role") != updates["role"]:
            role_changed = True
            updates["token_version"] = int(target.get("token_version", 0) or 0) + 1
    if updates:
        # Iter 340 — Groups-Field syncs membership table when present.
        new_groups = updates.get("groups")
        if isinstance(new_groups, list):
            existing_user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "groups": 1}) or {}
            old_groups = set(existing_user.get("groups") or [])
            new_set = {g for g in new_groups if g}
            for gid in (new_set - old_groups):
                try:
                    await db.groups.update_one({"group_id": gid}, {"$addToSet": {"members": user_id}})
                except Exception:
                    pass
            for gid in (old_groups - new_set):
                try:
                    await db.groups.update_one({"group_id": gid}, {"$pull": {"members": user_id}})
                except Exception:
                    pass
            updates["groups"] = list(new_set)
        await db.users.update_one({"user_id": user_id}, {"$set": updates})
        # iter 202 — invalidate caches when role changes
        from services import permissions_cache as pcache, user_cache as ucache
        await ucache.invalidate(user_id)
        if "role" in updates:
            await pcache.invalidate(user_id)
            # Iter 306 — re-sync module-visibility groups when role changes.
            try:
                from routes.org_onboarding import sync_user_module_groups
                await sync_user_module_groups(user_id, updates["role"])
            except Exception as _e:
                pass
    updated = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    if role_changed:
        updated["_session_invalidated"] = True
    return updated

@router.post("/admin/users/cleanup-unverified-test-users")
async def admin_cleanup_unverified_test_users(request: Request):
    """Iter 373 (L2) — Aufräum-Endpoint für unverifizierte Test-Konten.

    Identifiziert Konten, die folgende Kriterien erfüllen:
      - `email_verified` ist nicht True
      - E-Mail-Domain ist eine bekannte Test-Domain (klinik.de, meetflow.local,
        meetflow.test, test.meetflow.local, loadtest.local, test.local,
        test.com, test.de, example.com) ODER Local-Part beginnt mit
        `testuser_`, `loadtest`, `test_summary_`, `qa_`-Präfix wird
        ausgenommen.
      - Konto darf nicht der eingeloggte Admin sein.
      - Konto darf keine Aufgaben/Buchungen erstellt haben (Sicherheits-
        Stop: wir prüfen `tasks.created_by` und `resource_bookings.user_id`).

    Mit `dry_run=true` (Default) wird nur gezählt; `dry_run=false` löscht
    tatsächlich UND cascadet die Group-Memberships.
    """
    actor = await get_current_user(request)
    if actor.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    dry_run = bool(body.get("dry_run", True))

    TEST_DOMAINS = {
        "klinik.de", "meetflow.local", "meetflow.test",
        "test.meetflow.local", "loadtest.local", "test.local",
        "test.com", "test.de", "example.com",
    }
    PROTECTED_PREFIXES = ("qa_",)  # don't touch our QA fixtures

    candidates = []
    async for u in db.users.find(
        {"email_verified": {"$ne": True}},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1, "status": 1, "role": 1, "created_at": 1},
    ):
        if u["user_id"] == actor["user_id"]:
            continue
        email = (u.get("email") or "").lower()
        if not email:
            continue
        local, _, domain = email.partition("@")
        if any(local.startswith(p) for p in PROTECTED_PREFIXES):
            continue
        # match domain OR known test-prefix
        matches = (
            domain in TEST_DOMAINS
            or local.startswith("testuser_")
            or local.startswith("loadtest")
            or local.startswith("test_summary_")
            or local.startswith("freshtest_")
            or local.startswith("tokentest_")
            or local.startswith("newguest_")
        )
        if not matches:
            continue
        # Safety: skip if user has any tasks/bookings tied to them
        owns_tasks = await db.tasks.count_documents({"created_by": u["user_id"]}, limit=1) > 0
        owns_bookings = await db.resource_bookings.count_documents({"user_id": u["user_id"]}, limit=1) > 0
        if owns_tasks or owns_bookings:
            continue
        candidates.append(u)

    if dry_run:
        return {
            "dry_run": True,
            "would_delete": len(candidates),
            "sample": [
                {"email": c["email"], "user_id": c["user_id"], "status": c.get("status")}
                for c in candidates[:25]
            ],
        }

    # actual delete
    deleted_ids = [c["user_id"] for c in candidates]
    if deleted_ids:
        await db.users.delete_many({"user_id": {"$in": deleted_ids}})
        # Cascade group-membership cleanup (iter 372 pattern)
        await db.groups.update_many(
            {}, {"$pull": {"members": {"$in": deleted_ids}}}
        )
        # Invalidate caches
        try:
            from services import permissions_cache as pcache
            await pcache.invalidate_all()
        except Exception:
            pass

    return {"dry_run": False, "deleted": len(deleted_ids)}


@router.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    if user["user_id"] == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    result = await db.users.delete_one({"user_id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    # Iter 372 — Cascade-Cleanup: remove this user_id from EVERY group's
    # `members` array. Without this we accumulated 1.279 stale member refs
    # across 14 groups (see iter371 audit). Single `$pull` query, idempotent.
    try:
        await db.groups.update_many({}, {"$pull": {"members": user_id}})
    except Exception as _e:
        pass  # never block the delete on group-cleanup failure
    return {"message": "User deleted"}


@router.post("/admin/users/{user_id}/verify-now")
async def admin_verify_now(user_id: str, request: Request):
    """Iter 300 — Admin manually marks a user as email-verified. Bypasses
    the email-click flow for cases where the admin onboards the user in
    person (HR onboarding, password handed over directly, etc.). Also
    unlocks `locked_unverified` accounts in the same step."""
    actor = await get_current_user(request)
    if actor.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.get("email_verified"):
        raise HTTPException(status_code=400, detail="E-Mail ist bereits verifiziert")
    now = datetime.now(timezone.utc)
    set_fields = {
        "email_verified": True,
        "email_verified_at": now,
        "email_verified_by": actor["user_id"],   # so audit can show *who* did it
        "verification_method": "admin_override",
    }
    # If the user was locked because verification expired, unlock them too
    if target.get("status") == "locked_unverified":
        set_fields["status"] = "active"
        set_fields["unlocked_by"] = actor["user_id"]
        set_fields["unlocked_at"] = now
    await db.users.update_one({"user_id": user_id}, {"$set": set_fields})
    await log_caps_change(
        actor=actor, target_user_id=user_id, action="admin_verify_user",
        category="account", request=request,
        details={
            "target_email": target.get("email", ""),
            "was_locked": target.get("status") == "locked_unverified",
            "self_registered": bool(target.get("self_registered")),
        },
    )
    # Bust caches so the user can log in straight away
    try:
        from services.user_cache import invalidate as _inv
        await _inv(user_id)
    except Exception:
        pass
    return {"ok": True, "email_verified": True,
            "status": set_fields.get("status", target.get("status"))}


@router.post("/admin/users/{user_id}/resend-verification")
async def admin_resend_verification(user_id: str, request: Request):
    """Iter 291 — Send a fresh verification email to a self-registered or
    locked_unverified user, resetting the grace timer. If the user was
    `locked_unverified`, restore status to `active` so the new mail can be
    used."""
    actor = await get_current_user(request)
    if actor.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if not target.get("self_registered"):
        raise HTTPException(status_code=400, detail="Nur selbstregistrierte Nutzer können eine erneute Verifizierung erhalten")
    if target.get("email_verified"):
        raise HTTPException(status_code=400, detail="E-Mail ist bereits verifiziert")
    # Reset grace timer by overwriting created_at to "now" — the auto-lock
    # sweep uses created_at < cutoff to determine eligibility.
    now = datetime.now(timezone.utc)
    set_fields = {
        "created_at": now.isoformat(),
        "verification_resent_at": now,
    }
    if target.get("status") == "locked_unverified":
        set_fields["status"] = "active"
        set_fields["unlocked_by"] = actor["user_id"]
        set_fields["unlocked_at"] = now
    await db.users.update_one({"user_id": user_id}, {"$set": set_fields})
    try:
        from routes.org_onboarding import send_verification_email
        await send_verification_email(user_id, target["email"], target.get("name", ""))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"E-Mail-Versand fehlgeschlagen: {e}")
    await log_caps_change(
        actor=actor, target_user_id=user_id, action="resend_verification",
        category="account", request=request,
        details={"target_email": target.get("email", ""),
                 "was_locked": target.get("status") == "locked_unverified"},
    )
    # Bust user-cache so the freshly-unlocked user can log in immediately
    try:
        from services.user_cache import invalidate as _inv
        await _inv(user_id)
    except Exception:
        pass
    return {"ok": True, "status": set_fields.get("status", target.get("status"))}


@router.post("/admin/users/{user_id}/force-logout")
async def admin_force_logout_user(user_id: str, request: Request):
    """Bump the target user's token_version so all existing access/refresh
    tokens become invalid. The user has to re-authenticate."""
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0, "user_id": 1, "token_version": 1, "email": 1})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    new_tv = int(target.get("token_version", 0) or 0) + 1
    await db.users.update_one({"user_id": user_id}, {"$set": {"token_version": new_tv}})
    await log_caps_change(
        actor=user, target_user_id=user_id, action="force_logout",
        category="session", request=request,
        details={"new_token_version": new_tv, "target_email": target.get("email", "")},
    )
    return {"user_id": user_id, "token_version": new_tv}


@router.post("/admin/force-logout-all")
async def admin_force_logout_all(request: Request):
    """Bump the token_version of ALL users (except the caller) — global
    session invalidation. Useful after cookie-attribute changes or breaches."""
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    result = await db.users.update_many(
        {"user_id": {"$ne": user["user_id"]}},
        {"$inc": {"token_version": 1}},
    )
    await log_caps_change(
        actor=user, target_user_id="all_users", action="force_logout_all",
        category="session", request=request,
        details={"modified_count": result.modified_count},
    )
    return {"modified_count": result.modified_count}

# ============ USER INVITATION & STATUS ============

@router.post("/admin/users/bulk-invite/preview")
async def admin_bulk_invite_preview(request: Request):
    """Iter 121: preflight check for bulk-invite so admins see how many
    emails will actually be created + which are duplicates/invalid BEFORE
    sending 100 real mails. Pure read-only; no DB writes, no mails sent."""

    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    body = await request.json()
    emails_raw = body.get("emails", [])
    if isinstance(emails_raw, str):
        emails_raw = [emails_raw]
    email_re = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    seen = set()
    unique, duplicates, invalid = [], [], []
    for raw in emails_raw:
        e = (raw or "").lower().strip()
        if not e:
            continue
        if not email_re.match(e):
            invalid.append(raw)
            continue
        if e in seen:
            duplicates.append(e)
            continue
        seen.add(e)
        unique.append(e)

    existing_cursor = db.users.find({"email": {"$in": unique}}, {"_id": 0, "email": 1})
    existing = {u["email"] async for u in existing_cursor}
    new_emails = [e for e in unique if e not in existing]

    return {
        "total_input": len(emails_raw),
        "will_create": len(new_emails),
        "already_existing": sorted(existing),
        "duplicates": duplicates,
        "invalid": invalid,
        "preview_emails": new_emails[:20],  # first 20 for sanity
    }


@router.post("/admin/users/bulk-invite")
async def admin_bulk_invite(request: Request):
    """Invite many users at once, with a shared role + group (iter 119).

    Request: {"emails": ["a@x", "b@y"], "role": "member", "group_id": "grp_...",
              "send_email": true}
    - Duplicates and already-existing emails are skipped with per-row reason.
    - Emails are dispatched in parallel batches of 10 via `asyncio.gather`
      so a 100-user invite completes in ~10×email_latency (typically 5-15 s).
    - Returns per-email result rows so the UI can show a success/failure
      report without having to follow up with a separate query.
    """
    import asyncio

    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    body = await request.json()
    emails_raw = body.get("emails", [])
    if isinstance(emails_raw, str):
        emails_raw = [emails_raw]
    role = body.get("role", "member")
    group_id = body.get("group_id")
    send_email_flag = bool(body.get("send_email", True))

    # Sanitise emails: lowercase, strip, dedupe, basic shape check
    seen = set()
    emails = []
    skipped_invalid = []
    email_re = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    for raw in emails_raw:
        e = (raw or "").lower().strip()
        if not e:
            continue
        if not email_re.match(e):
            skipped_invalid.append({"email": raw, "reason": "invalid"})
            continue
        if e in seen:
            continue
        seen.add(e)
        emails.append(e)

    if not emails:
        raise HTTPException(status_code=400, detail="Keine gültigen E-Mails angegeben")
    if len(emails) > 500:
        raise HTTPException(status_code=400, detail="Maximal 500 E-Mails pro Request")

    # Which already exist?
    existing_cursor = db.users.find({"email": {"$in": emails}}, {"_id": 0, "email": 1})
    existing_emails = {u["email"] async for u in existing_cursor}

    # Create users (batch insert) for the new ones
    created = []
    frontend_url = os.environ.get("FRONTEND_URL", "")
    login_url = f"{frontend_url}/login"
    inviter_name = user.get("name", "Admin")
    now_iso = datetime.now(timezone.utc).isoformat()
    for e in emails:
        if e in existing_emails:
            continue
        uid = f"user_{uuid.uuid4().hex[:12]}"
        tmp_pw = _generate_compliant_temp_password()
        doc = {
            "user_id": uid, "email": e, "name": e.split("@")[0],
            "password_hash": hash_password(tmp_pw), "role": role, "status": "active",
            "department": "", "position": "", "phone": "", "location": "",
            "profession": "", "org_unit": "",
            "groups": [group_id] if group_id else [], "invited_by": user["user_id"],
            "must_change_password": True, "email_verified": False,
            "created_at": now_iso,
        }
        created.append({"doc": doc, "temp_password": tmp_pw})

    if created:
        await db.users.insert_many([c["doc"] for c in created])
        if group_id:
            await db.groups.update_one(
                {"group_id": group_id},
                {"$addToSet": {"members": {"$each": [c["doc"]["user_id"] for c in created]}}},
            )

    # Parallel email dispatch in batches of 10
    results = []
    for e in emails:
        if e in existing_emails:
            results.append({"email": e, "status": "skipped_existing", "email_sent": False})
            continue
    if send_email_flag and created:
        async def _send_one(row):
            e = row["doc"]["email"]
            html = build_invite_email_html(
                inviter_name, row["doc"]["name"], e, row["temp_password"], login_url, role,
            )
            try:
                res = await send_email_real(e, "MeetFlow Einladung - Ihr Zugang", html)
                # Iter 182 — only count email_sent:true if a real provider
                # accepted it; "logged" = no provider configured, silently
                # simulated.
                real_status = res.get("status")
                sent = real_status == "sent"
                return {
                    "email": e,
                    "status": "sent" if sent else (real_status or "failed"),
                    "email_sent": sent,
                    "provider": res.get("provider", "none"),
                    "error": res.get("error") if real_status == "failed" else None,
                    "simulated": real_status == "logged",
                }
            except Exception as exc:
                return {"email": e, "status": "failed", "email_sent": False, "error": str(exc)[:120]}

        # Chunk into batches of 10 to avoid flooding the provider
        batch_size = 10
        send_results = []
        for i in range(0, len(created), batch_size):
            chunk = created[i : i + batch_size]
            send_results.extend(await asyncio.gather(*[_send_one(r) for r in chunk]))
        results.extend(send_results)
    else:
        for row in created:
            results.append({"email": row["doc"]["email"], "status": "created_no_email", "email_sent": False})

    # Merge skipped-invalid into results so the UI reports every input
    results.extend([{"email": s["email"], "status": "invalid", "email_sent": False} for s in skipped_invalid])

    summary = {
        "total": len(emails_raw),
        "created": len(created),
        "skipped_existing": len(existing_emails),
        "invalid": len(skipped_invalid),
        "sent": sum(1 for r in results if r.get("email_sent")),
        "failed": sum(1 for r in results if r.get("status") == "failed"),
    }
    return {"summary": summary, "results": results}


@router.post("/admin/users/seed-loadtest")
async def admin_seed_loadtest_users(request: Request):
    """Quick helper (iter 119) to seed N `loadtest001..NNN@meetflow.local`
    users for bulk-invite testing. Non-destructive: skips existing."""
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    body = await request.json()
    count = max(1, min(int(body.get("count", 100)), 500))
    prefix = body.get("prefix", "loadtest")
    domain = body.get("domain", "meetflow.local")
    created = 0
    existing = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    pw_hash = hash_password("admin123")
    for i in range(1, count + 1):
        email = f"{prefix}{i:03d}@{domain}"
        if await db.users.find_one({"email": email}):
            existing += 1
            continue
        uid = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": uid, "email": email, "name": f"{prefix.title()} {i:03d}",
            "password_hash": pw_hash, "role": "user", "status": "active",
            "email_verified": False, "groups": [], "created_at": now_iso,
        })
        created += 1
    return {"created": created, "existing": existing, "total_target": count}


@router.post("/admin/users/bulk-import")
async def admin_bulk_import_users(request: Request):
    """Iter 341 — Bulk-Import per CSV mit voller Stammdaten-Erweiterung.

    Request: {"rows": [{"email":"...", "first_name":"...", ...}, ...],
              "send_email": true|false}

    Each row may contain:
        email (required), first_name, last_name, display_name, phone,
        department, role (default 'member'), group_ids (list OR
        semicolon-separated string of group_ids OR group names).

    Returns per-row {status: created|skipped_existing|invalid_email|error,
    user_id?, temp_password?, email_sent?}. Concurrency-safe insert.
    Group references can be either group_id OR group name — we resolve
    names against the groups collection so admins can paste human-friendly
    CSVs from spreadsheets.
    """
    import asyncio
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    body = await request.json()
    rows = body.get("rows", [])
    if not isinstance(rows, list) or not rows:
        raise HTTPException(status_code=400, detail="Keine Zeilen übergeben")
    if len(rows) > 500:
        raise HTTPException(status_code=400, detail="Maximal 500 Zeilen pro Request")
    send_email_flag = bool(body.get("send_email", True))

    email_re = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    # Pre-load groups once for name/id resolution.
    all_groups = await db.groups.find({}, {"_id": 0, "group_id": 1, "name": 1}).to_list(2000)
    gid_set = {g["group_id"] for g in all_groups}
    gname_to_id = {(g.get("name") or "").strip().lower(): g["group_id"] for g in all_groups if g.get("name")}

    def _resolve_groups(raw):
        """Accept list OR ';'/','-separated string of group_ids/names."""
        if not raw:
            return []
        if isinstance(raw, str):
            parts = [p.strip() for p in re.split(r"[;,]", raw) if p.strip()]
        elif isinstance(raw, list):
            parts = [str(p).strip() for p in raw if str(p).strip()]
        else:
            return []
        resolved: list[str] = []
        for p in parts:
            if p in gid_set:
                resolved.append(p)
            else:
                gid = gname_to_id.get(p.lower())
                if gid:
                    resolved.append(gid)
        # dedupe preserving order
        return list(dict.fromkeys(resolved))

    # Sanitise + dedupe within input
    seen_emails: set[str] = set()
    prepared: list[dict] = []
    results: list[dict] = []
    for raw_row in rows:
        if not isinstance(raw_row, dict):
            results.append({"status": "error", "reason": "not_an_object"})
            continue
        email = (raw_row.get("email") or "").lower().strip()
        if not email:
            results.append({"status": "invalid_email", "reason": "missing_email", "row": raw_row})
            continue
        if not email_re.match(email):
            results.append({"status": "invalid_email", "email": email})
            continue
        if email in seen_emails:
            results.append({"status": "skipped_duplicate", "email": email})
            continue
        seen_emails.add(email)
        first = (raw_row.get("first_name") or "").strip()
        last = (raw_row.get("last_name") or "").strip()
        display = (raw_row.get("display_name") or "").strip()
        full = " ".join(p for p in [first, last] if p).strip() or email.split("@")[0]
        prepared.append({
            "email": email,
            "first_name": first,
            "last_name": last,
            "display_name": display,
            "phone": (raw_row.get("phone") or "").strip(),
            "department": (raw_row.get("department") or "").strip(),
            "role": (raw_row.get("role") or "member").strip().lower(),
            "groups": _resolve_groups(raw_row.get("group_ids")),
            "name": full,
        })

    # Existing-check in one round-trip
    pending_emails = [p["email"] for p in prepared]
    existing_emails: set[str] = set()
    if pending_emails:
        async for u in db.users.find({"email": {"$in": pending_emails}}, {"_id": 0, "email": 1}):
            existing_emails.add(u["email"])

    frontend_url = os.environ.get("FRONTEND_URL", "")
    login_url = f"{frontend_url}/login"
    inviter_name = user.get("name", "Admin")
    now_iso = datetime.now(timezone.utc).isoformat()
    docs_to_insert: list[dict] = []
    rows_for_email: list[dict] = []
    for p in prepared:
        if p["email"] in existing_emails:
            results.append({"status": "skipped_existing", "email": p["email"]})
            continue
        uid = f"user_{uuid.uuid4().hex[:12]}"
        temp_password = _generate_compliant_temp_password()
        docs_to_insert.append({
            "user_id": uid, "email": p["email"],
            "name": p["name"], "first_name": p["first_name"], "last_name": p["last_name"],
            "display_name": p["display_name"], "phone": p["phone"],
            "department": p["department"], "position": "",
            "location": "", "profession": "", "org_unit": "",
            "role": p["role"] or "member", "status": "active",
            "groups": p["groups"], "invited_by": user["user_id"],
            "must_change_password": True,
            "password_hash": hash_password(temp_password),
            "created_at": now_iso,
        })
        rows_for_email.append({
            "user_id": uid, "email": p["email"], "name": p["display_name"] or p["name"],
            "role": p["role"] or "member", "temp_password": temp_password, "groups": p["groups"],
        })

    if docs_to_insert:
        try:
            await db.users.insert_many(docs_to_insert, ordered=False)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"DB-Fehler beim Einfügen: {e}")
        # Fan-out group membership in parallel
        group_updates = []
        for doc in docs_to_insert:
            for gid in (doc.get("groups") or []):
                group_updates.append((gid, doc["user_id"]))
        if group_updates:
            await asyncio.gather(
                *(db.groups.update_one({"group_id": gid}, {"$addToSet": {"members": uid}})
                  for gid, uid in group_updates),
                return_exceptions=True,
            )

    # Send invite mails in parallel batches of 10. Each failure is captured
    # per row so the UI can show "23 created, 2 mail failures".
    async def _send_one(r):
        if not send_email_flag:
            return {**r, "status": "created", "email_sent": False, "email_simulated": False}
        try:
            html = build_invite_email_html(inviter_name, r["name"], r["email"], r["temp_password"], login_url, r["role"])
            email_result = await send_email_real(r["email"], "MeetFlow Einladung - Ihr Zugang", html)
            return {
                **r,
                "status": "created",
                "email_sent": bool(email_result.get("sent")),
                "email_simulated": bool(email_result.get("simulated")),
                "email_error": email_result.get("error"),
            }
        except Exception as e:
            return {**r, "status": "created", "email_sent": False, "email_error": str(e)[:200]}

    for i in range(0, len(rows_for_email), 10):
        batch = rows_for_email[i:i + 10]
        results.extend(await asyncio.gather(*(_send_one(r) for r in batch), return_exceptions=False))

    summary = {
        "total": len(rows),
        "created": sum(1 for r in results if r.get("status") == "created"),
        "skipped_existing": sum(1 for r in results if r.get("status") == "skipped_existing"),
        "skipped_duplicate": sum(1 for r in results if r.get("status") == "skipped_duplicate"),
        "invalid_email": sum(1 for r in results if r.get("status") == "invalid_email"),
        "mails_sent": sum(1 for r in results if r.get("email_sent")),
        "mail_failed": sum(1 for r in results if r.get("status") == "created" and not r.get("email_sent") and not r.get("email_simulated") and send_email_flag is not False),
    }
    return {"summary": summary, "results": results}


@router.post("/admin/users/invite")
async def admin_invite_user(request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    body = await request.json()
    # Iter 379 — Admin darf User ohne echte E-Mail anlegen (z.B. Pflegekräfte
    # ohne dienstliche E-Mail). Pflichtfelder verschieben sich dann auf
    # `personnel_number` + Initialpasswort. Im Hintergrund wird eine
    # synthetische Adresse `<personnel_number>@no-email.local` gesetzt,
    # damit alle bestehenden Email-Indizes/Constraints funktionieren.
    no_email = bool(body.get("no_email", False))
    email = body.get("email", "").lower().strip()
    # Iter 379 — Optionales Initialpasswort vom Admin. Falls leer, generieren
    # wir wie bisher ein 4-aus-4-konformes Temp-Passwort. Bei `no_email=True`
    # MUSS der Admin ein Initialpasswort setzen (sonst kann er es nirgendwo
    # nachschauen, weil keine Einladungsmail rausgeht).
    initial_password = (body.get("initial_password") or "").strip()
    # Iter 340 — Stammdaten-Erweiterung: Vorname/Nachname/Anzeigename
    # + automatische Ableitung von `name` falls leer.
    first_name = (body.get("first_name") or "").strip()
    last_name = (body.get("last_name") or "").strip()
    display_name = (body.get("display_name") or "").strip()
    legacy_name = (body.get("name") or "").strip()
    full_name = legacy_name or " ".join(p for p in [first_name, last_name] if p).strip()
    role = body.get("role", "member")
    # Iter 340 — Backwards-compat: legacy `group_id` (single) AND new
    # `group_ids` (array) both accepted; we always store an array.
    group_ids_raw = body.get("group_ids")
    if isinstance(group_ids_raw, list):
        group_ids = [g for g in group_ids_raw if g]
    elif body.get("group_id"):
        group_ids = [body["group_id"]]
    else:
        group_ids = []
    department = (body.get("department") or "").strip()
    phone = (body.get("phone") or "").strip()
    # Iter 374 — alle Stammdaten als Pflicht-/Optional-Felder akzeptieren.
    # Pflicht (per User-Entscheidung): email + first_name + last_name +
    # role + department + position + personnel_number. Optional: display_name,
    # phone, location, profession, org_unit, language, groups, cap_grants,
    # cap_denies, must_change_password.
    position = (body.get("position") or "").strip()
    location = (body.get("location") or "").strip()
    profession = (body.get("profession") or "").strip()
    org_unit = (body.get("org_unit") or "").strip()
    personnel_number = (body.get("personnel_number") or "").strip()
    language = (body.get("language") or "de").strip() or "de"
    cap_grants_raw = body.get("cap_grants") or []
    cap_denies_raw = body.get("cap_denies") or []
    cap_grants = [c for c in cap_grants_raw if isinstance(c, str) and c] if isinstance(cap_grants_raw, list) else []
    cap_denies = [c for c in cap_denies_raw if isinstance(c, str) and c] if isinstance(cap_denies_raw, list) else []
    must_change_password = bool(body.get("must_change_password", True))

    if not email and not no_email:
        raise HTTPException(status_code=400, detail="E-Mail erforderlich")
    # Iter 374 — Pflichtfelder-Validierung (User-Entscheidung: Email + alle
    # Stammdaten Pflicht). Macht die Datenbank von Anfang an sauber.
    # Iter 379 — Wenn `no_email=True`, ist Personalnummer + Initialpasswort
    # Pflicht (statt Email).
    missing = []
    if not first_name:
        missing.append("Vorname")
    if not last_name:
        missing.append("Nachname")
    if not department:
        missing.append("Abteilung")
    if not position:
        missing.append("Position")
    if not personnel_number:
        missing.append("Personalnummer")
    if no_email and not initial_password:
        missing.append("Initial-Passwort")
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Pflichtfelder fehlen: {', '.join(missing)}",
        )
    # Iter 379 — Initialpasswort gegen Policy validieren, wenn Admin eines gesetzt hat.
    if initial_password:
        from services.password_policy import validate_password_or_raise
        validate_password_or_raise(initial_password)
    # Iter 379 — Synthetische E-Mail fuer no_email-User. Ermoeglicht eindeutigen
    # Index/Constraint und behandelt diese User wie alle anderen in Chat/Mentions.
    if no_email:
        # personnel_number kann Sonderzeichen enthalten — auf safe-chars reduzieren.
        safe_pn = re.sub(r"[^A-Za-z0-9_.\-]", "_", personnel_number).lower()
        email = f"{safe_pn}@no-email.local"
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=409, detail="Benutzer existiert bereits")
    # Doppelte Personalnummer abfangen (häufiger HR-Fehler).
    pn_clash = await db.users.find_one({"personnel_number": personnel_number}, {"_id": 0, "email": 1})
    if pn_clash:
        raise HTTPException(
            status_code=409,
            detail=f"Personalnummer bereits vergeben ({pn_clash.get('email','?')})",
        )
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    # Iter 379 — Admin-gesetztes Initial-PW hat Vorrang, sonst zufaellig generiert.
    temp_password = initial_password or _generate_compliant_temp_password()
    new_user = {
        "user_id": user_id, "email": email,
        # Iter 379 — Flag fuer „kein echtes E-Mail-Konto". Wird im Frontend
        # genutzt um die `@no-email.local`-Adresse zu verbergen und keine
        # E-Mail-Funktionen (Forgot-PW, Notifications-per-Mail, Verify) anzubieten.
        "no_email_account": no_email,
        # Bei no_email-Usern markieren wir die synthetische E-Mail direkt als
        # verifiziert — sonst greift `auto_lock_unverified_hours`.
        "email_verified": True if no_email else False,
        "email_verified_at": datetime.now(timezone.utc).isoformat() if no_email else None,
        "verification_method": "admin-no-email" if no_email else None,
        "name": full_name or email.split("@")[0],
        "first_name": first_name,
        "last_name": last_name,
        "display_name": display_name,
        "phone": phone,
        "password_hash": hash_password(temp_password),
        "role": role, "status": "active",
        "department": department, "position": position,
        "location": location, "profession": profession, "org_unit": org_unit,
        "personnel_number": personnel_number,
        "language": language,
        "groups": group_ids, "invited_by": user["user_id"],
        "must_change_password": must_change_password,
        # Direct grants/denies (iter374): optional, leeres Array wenn nicht angegeben.
        "cap_grants": cap_grants,
        "cap_denies": cap_denies,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(new_user)
    # Fan-out group memberships
    for gid in group_ids:
        try:
            await db.groups.update_one({"group_id": gid}, {"$addToSet": {"members": user_id}})
        except Exception:
            pass
    frontend_url = os.environ.get("FRONTEND_URL", "")
    login_url = f"{frontend_url}/login"
    invite_name = display_name or full_name or email.split("@")[0]
    # Iter 379 — No-Email-User: keine Einladungsmail rausgehen — die Zugangs-
    # daten muss der Admin direkt aus der API-Response lesen und persoenlich
    # weitergeben.
    if no_email:
        return {
            "user_id": user_id,
            "email": None,
            "no_email_account": True,
            "personnel_number": personnel_number,
            "temp_password": temp_password,
            "email_sent": False,
            "email_provider": "none",
            "email_status": "skipped_no_email",
            "email_error": None,
            "email_simulated": False,
            "message": "User ohne E-Mail angelegt. Bitte Zugangsdaten persoenlich übermitteln.",
        }
    html = build_invite_email_html(user.get("name", "Admin"), invite_name, email, temp_password, login_url, role)
    email_result = await send_email_real(email, "MeetFlow Einladung - Ihr Zugang", html)
    # Iter 182 — only report email_sent:true when a REAL provider actually
    # accepted the message. "logged" means the provider is 'none' and the
    # mail was only simulated — hiding that behind email_sent:true was the
    # root cause of "invite email doesn't arrive".
    real_status = email_result.get("status")
    email_sent = real_status == "sent"
    return {
        "user_id": user_id, "email": email, "temp_password": temp_password,
        "email_sent": email_sent,
        "email_provider": email_result.get("provider", "none"),
        "email_status": real_status,
        "email_error": email_result.get("error") if real_status == "failed" else None,
        "email_simulated": real_status == "logged",
    }

@router.put("/admin/users/{user_id}/status")
async def admin_toggle_user_status(user_id: str, request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    if user["user_id"] == user_id:
        raise HTTPException(status_code=400, detail="Eigenen Status nicht ändern")
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")
    new_status = "inactive" if target.get("status", "active") == "active" else "active"
    await db.users.update_one({"user_id": user_id}, {"$set": {"status": new_status}})
    return {"user_id": user_id, "status": new_status}

@router.put("/admin/users/{user_id}/profile")
async def admin_update_user_profile(user_id: str, request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    body = await request.json()
    # Iter 340 — neue Stammdaten-Felder (first_name, last_name, display_name)
    # vom Profil-Update akzeptieren. `name` bleibt erhalten (Backwards-compat),
    # wird aber automatisch aus first/last neu zusammengesetzt wenn explizit
    # leer übergeben.
    allowed = [
        "name", "role", "department", "position", "phone", "status",
        "location", "profession", "org_unit",
        "first_name", "last_name", "display_name",
        # Iter 366 — Personalnummer auch über self-update zulassen.
        "personnel_number",
    ]
    updates = {k: v for k, v in body.items() if k in allowed and v is not None}
    # Auto-derive `name` from first/last if name is being cleared
    if ("first_name" in updates or "last_name" in updates) and (not updates.get("name")):
        existing = await db.users.find_one({"user_id": user_id}, {"_id": 0, "first_name": 1, "last_name": 1, "name": 1})
        fn = updates.get("first_name", existing.get("first_name") if existing else "")
        ln = updates.get("last_name", existing.get("last_name") if existing else "")
        combined = " ".join(p for p in [fn, ln] if p).strip()
        if combined:
            updates["name"] = combined
    if updates:
        await db.users.update_one({"user_id": user_id}, {"$set": updates})
    return await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})


# Iter 379 — Admin-only Passwort-Reset (Wiederherstellungs-Weg fuer User
# ohne E-Mail). Funktioniert fuer ALLE User, ist aber besonders fuer no_email-
# Accounts gedacht, die nicht den /auth/forgot-password-Flow nutzen koennen.
@router.post("/admin/users/{user_id}/reset-password")
async def admin_reset_user_password(user_id: str, request: Request):
    admin = await get_current_user(request)
    if admin.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    body = await request.json()
    new_password = (body.get("new_password") or "").strip()
    # Wenn kein Passwort uebergeben wurde -> Zufallspasswort erzeugen.
    if not new_password:
        new_password = _generate_compliant_temp_password()
    # Policy strikt erzwingen (auch wenn Admin "verkurzt" eingibt).
    from services.password_policy import validate_password_or_raise
    validate_password_or_raise(new_password)
    target = await db.users.find_one({"user_id": user_id},
                                      {"_id": 0, "email": 1, "password_hash": 1, "password_history": 1,
                                       "personnel_number": 1, "no_email_account": 1})
    if not target:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")
    from services.password_policy import push_password_history
    history = target.get("password_history") or []
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "password_hash": hash_password(new_password),
            "password_history": push_password_history(history, target.get("password_hash", "")),
            "password_changed_at": datetime.now(timezone.utc).isoformat(),
            # User muss beim naechsten Login wieder selbst aendern.
            "must_change_password": True,
            # Token-Version bumpen -> bestehende Sessions invalidieren.
            "token_version": int((await db.users.find_one({"user_id": user_id}, {"_id": 0, "token_version": 1}) or {}).get("token_version", 0) or 0) + 1,
        }},
    )
    return {
        "ok": True,
        "user_id": user_id,
        "new_password": new_password,
        "no_email_account": bool(target.get("no_email_account")),
        "email": target.get("email") if not target.get("no_email_account") else None,
        "personnel_number": target.get("personnel_number"),
        "message": (
            "Passwort zurückgesetzt. Bitte übermittle das neue Passwort persoenlich."
            if target.get("no_email_account") else
            "Passwort zurückgesetzt. User muss es beim nächsten Login wieder ändern."
        ),
    }
