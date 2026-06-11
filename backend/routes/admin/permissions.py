"""routes/admin/permissions.py — Groups, capabilities, presets, cap-rules, permissions analytics (split out from routes/admin.py in iter 261)."""
from fastapi import APIRouter, HTTPException, Request
import re
import uuid
from datetime import datetime, timezone
from database import db, read_db
from dependencies import get_current_user
from services.permissions import (
    CAPABILITIES, ROLE_DEFAULTS, CAPABILITY_KEYS,
    get_effective_capabilities, migrate_role, require_cap,
)
from services.permission_audit import log_caps_change

router = APIRouter()


def _parse_expiry(exp) -> datetime | None:
    """Parse an ISO-8601 expiry string into a tz-aware datetime, or None on failure.

    Centralized so simulate / audit / breakdown stop reinventing the same try/except.
    """
    if not exp:
        return None
    try:
        dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None


def _split_active_expired(caps: list, expires: dict, now: datetime) -> tuple[list, list]:
    """Split a grants/denies list into (active, expired) based on per-cap expiry map."""
    active, expired = [], []
    for cap in caps or []:
        exp = expires.get(cap)
        dt = _parse_expiry(exp)
        entry = {"cap": cap, "expires_at": exp}
        if dt and now >= dt:
            expired.append(entry)
        else:
            active.append(entry)
    return active, expired


# ============ GROUPS / TEAMS ============

@router.get("/user/permissions")
async def get_user_permissions(request: Request):
    user = await get_current_user(request)
    uid = user.get("user_id")
    # iter 202 — TTL cache (60s per user). Cuts p99 from ~4.6s to ~10ms under load.
    from services import permissions_cache as pcache
    if uid:
        cached = await pcache.get(uid)
        if cached is not None:
            return cached

    caps = await get_effective_capabilities(user, db)
    role = migrate_role(user.get("role", "member"))

    # Legacy-compatible module permissions list (for Sidebar.js module visibility)
    # Iter 370 — `meetings` und `surveys` ergänzt, damit Gruppen-Admins die
    # zugehörigen Sidebar-Items gezielt freischalten/ausblenden können.
    # Sidebar selbst maps `meetings`→view:meetings, `surveys`→view:surveys
    # (siehe Sidebar.js Iter 370).
    MODULE_MAP = {
        "dashboard": "view:dashboard", "news": "view:news", "chat": "view:chat",
        "scheduling": "view:scheduling", "calendar": "view:calendar",
        "recordings": "view:recordings", "profile": "view:dashboard",  # profile always on
        "tasks": "view:tasks",
        "resources": "view:resources",
        "meetings": "view:meetings",
        "surveys": "view:surveys",
        "filetransfer": "view:filetransfer",
        "admin": "view:admin", "analytics": "view:analytics",
    }
    perms = ["profile"] + [k for k, v in MODULE_MAP.items() if v in caps and k != "profile"]

    group_ids = user.get("groups", []) or []
    group_names = []
    if group_ids:
        groups = await db.groups.find(
            {"group_id": {"$in": group_ids}}, {"_id": 0, "name": 1, "role_override": 1}
        ).to_list(50)
        group_names = [g.get("name", "") for g in groups]

    # Iter 372 — detect role downgrade caused by group `role_override`. The
    # auditor uncovered 434 users with role=member/moderator silently
    # downgraded to guest because they were in the "Gast" group. We now
    # surface this in the payload so the UI can render a warning banner
    # ("Effektive Rolle: Gast durch Gruppe X").
    _ROLE_RANK = {"guest": 0, "member": 1, "moderator": 2, "admin": 3}
    role_downgraded_by = None
    base_role = user.get("role", "member")
    base_role_norm = migrate_role(base_role)
    if base_role_norm != "admin":  # admins are never downgraded
        for g in groups if group_ids else []:
            ov = (g.get("role_override") or "").strip().lower()
            if ov in _ROLE_RANK and _ROLE_RANK[ov] < _ROLE_RANK.get(base_role_norm, 99):
                role_downgraded_by = {
                    "group_name": g.get("name", ""),
                    "override_role": ov,
                    "original_role": base_role_norm,
                }
                break  # report the first matching group

    payload = {
        "permissions": perms,  # legacy module list
        "capabilities": sorted(list(caps)),  # new granular caps
        "capability_labels": {
            k: {"label": label, "category": c, "description": d}
            for (k, c, label, d) in CAPABILITIES if k in caps
        },
        "role": role,
        "legacy_role": user.get("role", "member"),  # original role pre-migration
        "groups": group_names,
        # Iter 372 — null if not downgraded.
        "role_downgraded_by": role_downgraded_by,
    }
    if uid:
        await pcache.set(uid, payload)
    return payload


@router.get("/admin/capabilities")
async def list_capabilities(request: Request):
    """List all available capabilities with their German labels — for admin UI."""
    user = await get_current_user(request)
    await require_cap(user, "admin.manage_roles", db)
    return {
        "capabilities": [
            {"key": k, "category": c, "label": label, "description": d}
            for (k, c, label, d) in CAPABILITIES
        ],
        "role_defaults": {r: sorted(list(caps)) for r, caps in ROLE_DEFAULTS.items()},
    }



@router.get("/admin/groups")
async def list_groups(request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    groups = await db.groups.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return groups

@router.post("/admin/groups")
async def create_group(request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name erforderlich")
    # Case-insensitive duplicate-name check
    existing = await db.groups.find_one({"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}, {"_id": 0, "group_id": 1})
    if existing:
        raise HTTPException(status_code=409, detail="Gruppenname existiert bereits")
    # Iter 289 — Convenience default: a group literally called "Gast" or
    # "Guest" auto-downgrades to the guest role unless the admin explicitly
    # set a different role_override.
    role_override_default = None
    if name.lower() in ("gast", "guest", "gäste", "gaeste", "guests"):
        role_override_default = "guest"
    group_id = f"grp_{uuid.uuid4().hex[:10]}"
    group = {
        "group_id": group_id, "name": name,
        "description": body.get("description", ""),
        "color": body.get("color", "#4A5D4E"),
        "permissions": body.get("permissions", ["scheduling", "dashboard", "calendar", "recordings", "profile"]),
        "capabilities": [c for c in (body.get("capabilities") or []) if c in CAPABILITY_KEYS],
        # Iter 289 — optional role_override: when set, downgrades the
        # effective base-role of every member in this group (e.g. guest).
        "role_override": (body.get("role_override") or role_override_default or "").strip().lower() or None,
        "members": body.get("members", []),
        "created_by": user["user_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.groups.insert_one(group)
    for mid in group["members"]:
        await db.users.update_one({"user_id": mid}, {"$addToSet": {"groups": group_id}})
    return await db.groups.find_one({"group_id": group_id}, {"_id": 0})

@router.put("/admin/groups/{group_id}")
async def update_group(group_id: str, request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    body = await request.json()
    allowed = ["name", "description", "color", "permissions", "capabilities", "role_override"]
    updates = {k: v for k, v in body.items() if k in allowed}
    # Iter 289 — normalise role_override
    if "role_override" in updates:
        v = (updates["role_override"] or "")
        if isinstance(v, str):
            v = v.strip().lower()
            updates["role_override"] = v if v in ("guest", "member", "moderator", "admin") else None
        else:
            updates["role_override"] = None
    if "name" in updates:
        new_name = (updates["name"] or "").strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="Name erforderlich")
        dup = await db.groups.find_one({
            "name": {"$regex": f"^{re.escape(new_name)}$", "$options": "i"},
            "group_id": {"$ne": group_id},
        }, {"_id": 0, "group_id": 1})
        if dup:
            raise HTTPException(status_code=409, detail="Gruppenname existiert bereits")
        updates["name"] = new_name
    if updates:
        await db.groups.update_one({"group_id": group_id}, {"$set": updates})
        # iter 202 — group capabilities affect all members; bulk-invalidate.
        if "capabilities" in updates or "permissions" in updates or "role_override" in updates:
            from services import permissions_cache as pcache
            await pcache.invalidate_all()
    return await db.groups.find_one({"group_id": group_id}, {"_id": 0})

@router.delete("/admin/groups/{group_id}")
async def delete_group(group_id: str, request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    group = await db.groups.find_one({"group_id": group_id}, {"_id": 0})
    if not group:
        raise HTTPException(status_code=404, detail="Gruppe nicht gefunden")
    # Iter 306 — protect module-system groups from deletion; users would lose
    # all module visibility immediately and there is no UI to recreate them.
    if group.get("module_group") or group.get("is_system"):
        raise HTTPException(
            status_code=403,
            detail="System-Gruppe kann nicht gelöscht werden (Modul-Sichtbarkeit / Onboarding)",
        )
    await db.users.update_many({"groups": group_id}, {"$pull": {"groups": group_id}})
    await db.groups.delete_one({"group_id": group_id})
    # iter 202 — affected users lose group caps; bulk-invalidate.
    from services import permissions_cache as pcache
    await pcache.invalidate_all()
    return {"message": "Gruppe gelöscht"}

@router.post("/admin/groups/{group_id}/members")
async def add_group_member(group_id: str, request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    body = await request.json()
    user_id = body.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id erforderlich")
    await db.groups.update_one({"group_id": group_id}, {"$addToSet": {"members": user_id}})
    await db.users.update_one({"user_id": user_id}, {"$addToSet": {"groups": group_id}})
    # iter 213 — invalidate BOTH caches for the added member; user_cache holds
    # the user doc with stale `groups` list, permissions_cache the resolved set.
    from services import permissions_cache as pcache, user_cache as ucache
    await pcache.invalidate(user_id)
    await ucache.invalidate(user_id)
    return await db.groups.find_one({"group_id": group_id}, {"_id": 0})

@router.delete("/admin/groups/{group_id}/members/{member_id}")
async def remove_group_member(group_id: str, member_id: str, request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    await db.groups.update_one({"group_id": group_id}, {"$pull": {"members": member_id}})
    await db.users.update_one({"user_id": member_id}, {"$pull": {"groups": group_id}})
    # iter 213 — invalidate BOTH caches for the removed member.
    from services import permissions_cache as pcache, user_cache as ucache
    await pcache.invalidate(member_id)
    await ucache.invalidate(member_id)
    return await db.groups.find_one({"group_id": group_id}, {"_id": 0})


@router.post("/admin/groups/cleanup-stale-members")
async def cleanup_stale_group_members(request: Request):
    """Iter 372 — Remove member-references that point to deleted users.

    Audit (iter 371) uncovered 1.279 stale `members` entries across the
    `Modul: Standard` and other groups because pre-iter372 user-deletes
    did not cascade-clean group memberships. This endpoint is idempotent
    and safe to run from the admin UI ("Gruppen → Wartung").

    Returns counters per cleaned group.
    """
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    existing_ids = set()
    cursor = db.users.find({}, {"_id": 0, "user_id": 1})
    # Iter 372 — `to_list(None)` to materialise every user (motor's default
    # batch can otherwise leave entries un-iterated in some envs).
    async for u in cursor:
        existing_ids.add(u["user_id"])
    cleaned = []
    total_removed = 0
    async for grp in db.groups.find({}, {"_id": 0, "group_id": 1, "name": 1, "members": 1}):
        members = grp.get("members") or []
        kept = [m for m in members if m in existing_ids]
        removed = len(members) - len(kept)
        if removed > 0:
            await db.groups.update_one(
                {"group_id": grp["group_id"]},
                {"$set": {"members": kept}},
            )
            cleaned.append({
                "group_id": grp["group_id"],
                "name": grp.get("name", ""),
                "removed": removed,
                "remaining": len(kept),
            })
            total_removed += removed

    # Invalidate cache — group-membership changes affect effective caps.
    if total_removed > 0:
        from services import permissions_cache as pcache
        await pcache.invalidate_all()

    return {"total_removed": total_removed, "groups_cleaned": cleaned}


# ============ CAPABILITIES & PER-USER OVERRIDES ============

@router.put("/admin/users/{user_id}/capabilities")
async def update_user_capabilities(user_id: str, request: Request):
    """Set direct cap_grants / cap_denies on a user (admin override).

    Optional cap_expires: {cap_key: iso_string_or_null} — per-capability expiration
    (useful for vacation coverage grants).
    """
    admin = await get_current_user(request)
    await require_cap(admin, "admin.manage_roles", db)
    body = await request.json()
    grants = [c for c in (body.get("grants") or []) if c in CAPABILITY_KEYS]
    denies = [c for c in (body.get("denies") or []) if c in CAPABILITY_KEYS]
    expires_raw = body.get("expires") or {}
    cap_expires = {}
    if isinstance(expires_raw, dict):
        for k, v in expires_raw.items():
            if k in CAPABILITY_KEYS and (k in grants or k in denies) and isinstance(v, str) and v:
                cap_expires[k] = v
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "cap_grants": grants,
            "cap_denies": denies,
            "cap_expires": cap_expires,
            "caps_updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    # iter 213 — invalidate BOTH caches: permissions_cache holds the resolved
    # capability set, user_cache (5s TTL) holds the user document itself.
    # Without invalidating user_cache, the next request would re-resolve from
    # a cached user doc with the old cap_grants/cap_denies and the new caps
    # would silently not take effect for up to 5 seconds.
    from services import permissions_cache as pcache, user_cache as ucache
    await pcache.invalidate(user_id)
    await ucache.invalidate(user_id)
    await log_caps_change(admin, user_id, "set_caps",
                          {"grants": grants, "denies": denies, "expires": cap_expires})
    return {"ok": True, "grants": grants, "denies": denies, "expires": cap_expires}


# ============ CAPABILITY PRESETS (DB-backed) ============

async def _get_db_preset(preset_id: str):
    return await db.presets.find_one({"preset_id": preset_id}, {"_id": 0})


@router.get("/admin/presets")
async def list_presets(request: Request):
    """Return all capability presets (built-in + custom) from DB."""
    admin = await get_current_user(request)
    await require_cap(admin, "admin.manage_roles", db)
    docs = await db.presets.find({}, {"_id": 0}).sort("builtin", -1).to_list(200)
    return {"presets": docs}


@router.post("/admin/presets")
async def create_preset(request: Request):
    """Create a custom capability preset."""
    admin = await get_current_user(request)
    await require_cap(admin, "admin.manage_roles", db)
    body = await request.json()
    label = (body.get("label") or "").strip()
    if not label:
        raise HTTPException(status_code=400, detail="Label erforderlich")
    caps = [c for c in (body.get("capabilities") or []) if c in CAPABILITY_KEYS]
    preset_id = body.get("preset_id") or f"custom_{uuid.uuid4().hex[:8]}"
    if await db.presets.find_one({"preset_id": preset_id}):
        raise HTTPException(status_code=409, detail="Preset-ID existiert bereits")
    doc = {
        "preset_id": preset_id, "label": label,
        "description": body.get("description", ""),
        "capabilities": caps, "builtin": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": admin["user_id"],
    }
    await db.presets.insert_one(doc)
    await log_caps_change(admin, "", "create_preset",
                          {"preset_id": preset_id, "label": label, "caps": caps})
    doc.pop("_id", None)
    return doc


@router.put("/admin/presets/{preset_id}")
async def update_preset(preset_id: str, request: Request):
    admin = await get_current_user(request)
    await require_cap(admin, "admin.manage_roles", db)
    existing = await _get_db_preset(preset_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Preset nicht gefunden")
    if existing.get("builtin"):
        raise HTTPException(status_code=403, detail="Built-in Presets können nicht geaendert werden")
    body = await request.json()
    updates = {}
    if "label" in body:
        updates["label"] = str(body["label"])
    if "description" in body:
        updates["description"] = str(body["description"])
    if "capabilities" in body:
        updates["capabilities"] = [c for c in body["capabilities"] if c in CAPABILITY_KEYS]
    if updates:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.presets.update_one({"preset_id": preset_id}, {"$set": updates})
        await log_caps_change(admin, "", "update_preset",
                              {"preset_id": preset_id, "updates": updates})
    return await _get_db_preset(preset_id)


@router.delete("/admin/presets/{preset_id}")
async def delete_preset(preset_id: str, request: Request):
    admin = await get_current_user(request)
    await require_cap(admin, "admin.manage_roles", db)
    existing = await _get_db_preset(preset_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Preset nicht gefunden")
    if existing.get("builtin"):
        raise HTTPException(status_code=403, detail="Built-in Presets können nicht gelöscht werden")
    await db.presets.delete_one({"preset_id": preset_id})
    await log_caps_change(admin, "", "delete_preset",
                          {"preset_id": preset_id, "label": existing.get("label")})
    return {"ok": True}


@router.post("/admin/presets/{preset_id}/apply-to-user/{user_id}")
async def apply_preset_to_user(preset_id: str, user_id: str, request: Request):
    """Apply a preset to a user — adds preset caps to their cap_grants (merged)."""
    admin = await get_current_user(request)
    await require_cap(admin, "admin.manage_roles", db)
    preset = await _get_db_preset(preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset nicht gefunden")
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "user_id": 1, "cap_grants": 1})
    if u is None:
        raise HTTPException(status_code=404, detail="Nutzer nicht gefunden")
    existing = set(u.get("cap_grants", []) or [])
    caps = preset.get("capabilities", []) or []
    added = [c for c in caps if c not in existing]
    existing.update(caps)
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"cap_grants": sorted(list(existing)),
                  "caps_updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    await log_caps_change(admin, user_id, "apply_preset",
                          {"preset_id": preset_id, "label": preset.get("label"),
                           "caps_added": added, "caps_all": caps})
    return {"ok": True, "applied": caps, "preset_id": preset_id}


@router.post("/admin/presets/{preset_id}/apply-to-group/{group_id}")
async def apply_preset_to_group(preset_id: str, group_id: str, request: Request):
    """Apply a preset to a group — adds preset caps to group.capabilities (merged)."""
    admin = await get_current_user(request)
    await require_cap(admin, "admin.manage_roles", db)
    preset = await _get_db_preset(preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset nicht gefunden")
    g = await db.groups.find_one({"group_id": group_id}, {"_id": 0, "group_id": 1, "capabilities": 1})
    if g is None:
        raise HTTPException(status_code=404, detail="Gruppe nicht gefunden")
    existing = set(g.get("capabilities", []) or [])
    caps = preset.get("capabilities", []) or []
    existing.update(caps)
    await db.groups.update_one(
        {"group_id": group_id},
        {"$set": {"capabilities": sorted(list(existing))}},
    )
    await log_caps_change(admin, "", "apply_preset",
                          {"preset_id": preset_id, "group_id": group_id, "caps_all": caps})
    return {"ok": True, "applied": caps, "preset_id": preset_id}


@router.post("/admin/presets/{preset_id}/apply-to-users")
async def bulk_apply_preset(preset_id: str, request: Request):
    """Bulk apply a preset to multiple users at once."""
    admin = await get_current_user(request)
    await require_cap(admin, "admin.manage_roles", db)
    preset = await _get_db_preset(preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset nicht gefunden")
    body = await request.json()
    user_ids = [str(uid) for uid in (body.get("user_ids") or []) if isinstance(uid, str)]
    if not user_ids:
        raise HTTPException(status_code=400, detail="user_ids erforderlich")
    caps = preset.get("capabilities", []) or []
    updated = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    async for u in db.users.find({"user_id": {"$in": user_ids}}, {"_id": 0, "user_id": 1, "cap_grants": 1}):
        existing = set(u.get("cap_grants", []) or [])
        existing.update(caps)
        await db.users.update_one(
            {"user_id": u["user_id"]},
            {"$set": {"cap_grants": sorted(list(existing)), "caps_updated_at": now_iso}},
        )
        updated += 1
    await log_caps_change(admin, "", "bulk_apply",
                          {"preset_id": preset_id, "label": preset.get("label"),
                           "user_ids": user_ids, "affected_count": updated, "caps": caps})
    return {"ok": True, "updated": updated, "preset_id": preset_id}


# ============ AUTO-ASSIGN RULES ============

@router.get("/admin/cap-rules")
async def list_cap_rules(request: Request):
    admin = await get_current_user(request)
    await require_cap(admin, "admin.manage_roles", db)
    rules = await db.cap_rules.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"rules": rules}


@router.post("/admin/cap-rules")
async def create_cap_rule(request: Request):
    admin = await get_current_user(request)
    await require_cap(admin, "admin.manage_roles", db)
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name erforderlich")
    when = body.get("when") or {}
    apply = body.get("apply") or {}
    if not apply.get("preset_id") and not apply.get("caps"):
        raise HTTPException(status_code=400, detail="Mindestens ein Preset oder Capabilities erforderlich")
    rule = {
        "rule_id": f"rule_{uuid.uuid4().hex[:10]}",
        "name": name, "description": body.get("description", ""),
        "enabled": body.get("enabled", True),
        "when": {
            "department": when.get("department") or "",
            "location": when.get("location") or "",
            "profession": when.get("profession") or "",
            "role": when.get("role") or "",
        },
        "apply": {
            "preset_id": apply.get("preset_id") or "",
            "caps": [c for c in (apply.get("caps") or []) if c in CAPABILITY_KEYS],
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": admin["user_id"],
    }
    await db.cap_rules.insert_one(rule)
    await log_caps_change(admin, "", "create_rule",
                          {"rule_id": rule["rule_id"], "name": name})
    rule.pop("_id", None)
    return rule


@router.put("/admin/cap-rules/{rule_id}")
async def update_cap_rule(rule_id: str, request: Request):
    admin = await get_current_user(request)
    await require_cap(admin, "admin.manage_roles", db)
    existing = await db.cap_rules.find_one({"rule_id": rule_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Regel nicht gefunden")
    body = await request.json()
    updates = {}
    for k in ("name", "description", "enabled", "when", "apply"):
        if k in body:
            updates[k] = body[k]
    if updates:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.cap_rules.update_one({"rule_id": rule_id}, {"$set": updates})
        await log_caps_change(admin, "", "update_rule", {"rule_id": rule_id})
    return await db.cap_rules.find_one({"rule_id": rule_id}, {"_id": 0})


@router.delete("/admin/cap-rules/{rule_id}")
async def delete_cap_rule(rule_id: str, request: Request):
    admin = await get_current_user(request)
    await require_cap(admin, "admin.manage_roles", db)
    await db.cap_rules.delete_one({"rule_id": rule_id})
    await log_caps_change(admin, "", "delete_rule", {"rule_id": rule_id})
    return {"ok": True}


def _user_matches_rule(user: dict, when: dict) -> bool:
    for field in ("department", "location", "profession", "role"):
        cond = ((when or {}).get(field, "") or "").strip()
        if cond and (user.get(field, "") or "").strip().lower() != cond.lower():
            return False
    return True


async def _resolve_rule_caps(rule: dict) -> list:
    caps = list(rule.get("apply", {}).get("caps") or [])
    pid = rule.get("apply", {}).get("preset_id")
    if pid:
        p = await _get_db_preset(pid)
        if p:
            caps.extend(p.get("capabilities") or [])
    return list(set(caps))


@router.post("/admin/cap-rules/run")
async def run_cap_rules(request: Request):
    """Manually trigger the rule engine for all active users. Idempotent."""
    admin = await get_current_user(request)
    await require_cap(admin, "admin.manage_roles", db)
    body = {}
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            body = await request.json()
        except (ValueError, KeyError):
            body = {}
    only_rule_id = body.get("rule_id") if isinstance(body, dict) else None

    query = {"enabled": True}
    if only_rule_id:
        query["rule_id"] = only_rule_id
    rules = await db.cap_rules.find(query, {"_id": 0}).to_list(200)
    if not rules:
        return {"rules_run": 0, "users_affected": 0, "details": []}

    details = []
    total_affected = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for rule in rules:
        caps_to_add = await _resolve_rule_caps(rule)
        if not caps_to_add:
            details.append({"rule_id": rule["rule_id"], "name": rule.get("name"), "affected": 0})
            continue
        affected = 0
        async for u in db.users.find(
            {"status": {"$ne": "inactive"}},
            {"_id": 0, "user_id": 1, "department": 1, "location": 1, "profession": 1, "role": 1, "cap_grants": 1},
        ):
            if not _user_matches_rule(u, rule.get("when", {})):
                continue
            existing = set(u.get("cap_grants", []) or [])
            added = [c for c in caps_to_add if c not in existing]
            if not added:
                continue
            existing.update(caps_to_add)
            await db.users.update_one(
                {"user_id": u["user_id"]},
                {"$set": {"cap_grants": sorted(list(existing)), "caps_updated_at": now_iso}},
            )
            affected += 1
            await log_caps_change(admin, u["user_id"], "auto_assign",
                                  {"rule_id": rule["rule_id"], "rule_name": rule.get("name"),
                                   "caps_added": added})
        total_affected += affected
        details.append({"rule_id": rule["rule_id"], "name": rule.get("name"), "affected": affected})

    return {"rules_run": len(rules), "users_affected": total_affected, "details": details}


# ============ SIMULATOR ============

@router.get("/admin/users/{user_id}/simulate")
async def simulate_user_permissions(user_id: str, request: Request):
    """Detailed capability breakdown for a user — useful for 'why can they do X?' debugging.

    Returns which caps come from role, groups, direct grants (with expiry state),
    and which are effectively active.
    """
    admin = await get_current_user(request)
    await require_cap(admin, "admin.manage_roles", db)
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Nutzer nicht gefunden")

    role = migrate_role(u.get("role", "member"))
    role_caps = sorted(list(ROLE_DEFAULTS.get(role, set())))

    group_ids = u.get("groups", []) or []
    groups_data = []
    group_caps_all = set()
    if group_ids:
        async for g in db.groups.find(
            {"group_id": {"$in": group_ids}}, {"_id": 0, "group_id": 1, "name": 1, "capabilities": 1}
        ):
            caps = g.get("capabilities", []) or []
            groups_data.append({"group_id": g["group_id"], "name": g.get("name", ""), "capabilities": caps})
            group_caps_all.update(caps)

    grants = u.get("cap_grants", []) or []
    denies = u.get("cap_denies", []) or []
    expires = u.get("cap_expires", {}) or {}

    now = datetime.now(timezone.utc)
    active_grants, expired_grants = _split_active_expired(grants, expires, now)
    active_denies, expired_denies = _split_active_expired(denies, expires, now)

    effective = await get_effective_capabilities(u, db)

    return {
        "user": {
            "user_id": u.get("user_id"), "name": u.get("name"), "email": u.get("email"),
            "role": role, "legacy_role": u.get("legacy_role"),
        },
        "role_defaults": role_caps,
        "groups": groups_data,
        "group_caps_all": sorted(list(group_caps_all)),
        "direct_grants_active": active_grants,
        "direct_grants_expired": expired_grants,
        "direct_denies_active": active_denies,
        "direct_denies_expired": expired_denies,
        "effective": sorted(list(effective)),
        "effective_count": len(effective),
    }


# ============ ITER 212 — UNIFIED PERMISSIONS HUB ============

@router.get("/admin/permissions/who-has-cap/{cap}")
async def who_has_capability(cap: str, request: Request):
    """„Wer darf X?" — list every user that effectively has the given capability,
    annotated with the source(s): role / group(s) / direct grant.

    Used by the consolidated Permissions-Hub in admin to answer the most common
    governance question: 'Who exactly can publish news / record meetings / …?'
    """
    admin = await get_current_user(request)
    await require_cap(admin, "admin.manage_roles", db)
    if cap not in CAPABILITY_KEYS:
        raise HTTPException(status_code=400, detail="Unbekannte Capability")

    matching_group_ids = []
    matching_group_names = {}
    async for g in db.groups.find(
        {"capabilities": cap},
        {"_id": 0, "group_id": 1, "name": 1},
    ):
        matching_group_ids.append(g["group_id"])
        matching_group_names[g["group_id"]] = g.get("name", "")

    matching_roles = [r for r, caps in ROLE_DEFAULTS.items() if cap in caps]

    or_branches = []
    if matching_roles:
        or_branches.append({"role": {"$in": matching_roles}})
    if matching_group_ids:
        or_branches.append({"groups": {"$in": matching_group_ids}})
    or_branches.append({"cap_grants": cap})
    if not or_branches:
        return {"capability": cap, "users": []}

    users_out = []
    async for u in read_db.users.find(
        {"$or": or_branches},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1, "role": 1, "groups": 1,
         "cap_grants": 1, "cap_denies": 1, "cap_expires": 1},
    ):
        sources = []
        role = migrate_role(u.get("role", "member"))
        if cap in ROLE_DEFAULTS.get(role, set()):
            sources.append({"type": "role", "label": role})
        for gid in (u.get("groups") or []):
            if gid in matching_group_ids:
                sources.append({"type": "group", "id": gid, "label": matching_group_names.get(gid, gid)})
        if cap in (u.get("cap_grants") or []):
            sources.append({"type": "grant", "expires_at": (u.get("cap_expires") or {}).get(cap)})
        # Denies could remove the cap — verify it's actually effective.
        effective = await get_effective_capabilities(u, db)
        if cap not in effective:
            continue
        users_out.append({
            "user_id": u["user_id"],
            "name": u.get("name") or u.get("email"),
            "email": u.get("email"),
            "role": role,
            "sources": sources,
        })
    users_out.sort(key=lambda x: (x["role"] != "admin", (x["name"] or "").lower()))
    return {"capability": cap, "count": len(users_out), "users": users_out}


@router.get("/admin/permissions/audit")
async def permissions_audit(request: Request):
    """Find inconsistencies admins should clean up:
      - Direct grants that are already covered by role or any of the user's groups.
      - Expired grants/denies still in user docs.
      - Groups with capabilities but no members (orphan).
    """
    admin = await get_current_user(request)
    await require_cap(admin, "admin.manage_roles", db)

    redundant_grants = []
    expired_entries = []
    direct_grants_summary = []  # iter 373 R3
    now = datetime.now(timezone.utc)

    async for u in read_db.users.find(
        {"$or": [{"cap_grants": {"$ne": []}}, {"cap_denies": {"$ne": []}}]},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1, "role": 1, "groups": 1,
         "cap_grants": 1, "cap_denies": 1, "cap_expires": 1},
    ):
        role = migrate_role(u.get("role", "member"))
        role_caps = ROLE_DEFAULTS.get(role, set())
        group_caps = set()
        if u.get("groups"):
            async for g in db.groups.find(
                {"group_id": {"$in": u["groups"]}}, {"_id": 0, "capabilities": 1}
            ):
                group_caps.update(g.get("capabilities", []) or [])
        for cap in (u.get("cap_grants") or []):
            if cap in role_caps or cap in group_caps:
                redundant_grants.append({
                    "user_id": u["user_id"], "name": u.get("name") or u.get("email"),
                    "cap": cap,
                    "covered_by": "role" if cap in role_caps else "group",
                })
        expires = u.get("cap_expires") or {}
        for cap, exp in expires.items():
            dt = _parse_expiry(exp)
            if dt and now >= dt:
                expired_entries.append({
                    "user_id": u["user_id"], "name": u.get("name") or u.get("email"),
                    "cap": cap, "expired_at": exp,
                })
        # iter 373 R3 — surface users with ANY direct grants/denies so the
        # admin can review whether group-based mgmt would be cleaner.
        grants = u.get("cap_grants") or []
        denies = u.get("cap_denies") or []
        if grants or denies:
            direct_grants_summary.append({
                "user_id": u["user_id"],
                "name": u.get("name") or u.get("email"),
                "email": u.get("email"),
                "role": role,
                "grants": grants,
                "denies": denies,
                "expires": expires,
            })

    orphan_groups = []
    async for g in db.groups.find({}, {"_id": 0, "group_id": 1, "name": 1, "members": 1, "capabilities": 1}):
        if not g.get("members") and g.get("capabilities"):
            orphan_groups.append({
                "group_id": g["group_id"], "name": g.get("name", ""),
                "capability_count": len(g.get("capabilities", [])),
            })

    return {
        "redundant_grants": redundant_grants,
        "expired_entries": expired_entries,
        "orphan_groups": orphan_groups,
        "direct_grants_summary": direct_grants_summary,
        "total_issues": len(redundant_grants) + len(expired_entries) + len(orphan_groups),
    }


@router.get("/admin/groups/{group_id}/impact")
async def group_capability_impact(group_id: str, request: Request):
    """Live preview for the GroupsPanel: how many users does this group affect,
    and which caps does each member gain *only* from this group (not from role)?"""
    admin = await get_current_user(request)
    await require_cap(admin, "admin.manage_groups", db)
    group = await db.groups.find_one({"group_id": group_id}, {"_id": 0})
    if not group:
        raise HTTPException(status_code=404, detail="Gruppe nicht gefunden")

    member_ids = group.get("members") or []
    group_caps = set(group.get("capabilities") or [])
    impact = []
    if member_ids:
        async for u in read_db.users.find(
            {"user_id": {"$in": member_ids}},
            {"_id": 0, "user_id": 1, "name": 1, "email": 1, "role": 1, "cap_grants": 1, "groups": 1},
        ):
            role = migrate_role(u.get("role", "member"))
            role_caps = ROLE_DEFAULTS.get(role, set())
            grants = set(u.get("cap_grants") or [])
            unique_from_group = sorted(group_caps - role_caps - grants)
            impact.append({
                "user_id": u["user_id"], "name": u.get("name") or u.get("email"),
                "role": role, "unique_caps": unique_from_group,
            })
    return {
        "group_id": group_id, "name": group.get("name"),
        "member_count": len(member_ids),
        "capability_count": len(group_caps),
        "impact": impact,
    }


# ============ ITER 212 — END-USER SELF-SERVICE ============

@router.get("/me/permissions/breakdown")
async def my_permissions_breakdown(request: Request):
    """End-user-friendly „What can I do and why?" page.

    Same shape as /admin/users/{id}/simulate but for self only — no admin
    capability required so every user can see their own permissions."""
    user = await get_current_user(request)
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Nutzer nicht gefunden")

    role = migrate_role(u.get("role", "member"))
    role_caps = sorted(list(ROLE_DEFAULTS.get(role, set())))

    groups_data = []
    if u.get("groups"):
        async for g in db.groups.find(
            {"group_id": {"$in": u["groups"]}},
            {"_id": 0, "group_id": 1, "name": 1, "capabilities": 1, "color": 1},
        ):
            groups_data.append({
                "group_id": g["group_id"], "name": g.get("name", ""),
                "color": g.get("color", "#4A5D4E"),
                "capabilities": g.get("capabilities") or [],
            })

    effective = await get_effective_capabilities(u, db)

    return {
        "role": role,
        "role_defaults": role_caps,
        "groups": groups_data,
        "direct_grants": list(u.get("cap_grants") or []),
        "direct_denies": list(u.get("cap_denies") or []),
        "expires": u.get("cap_expires") or {},
        "effective": sorted(list(effective)),
        "effective_count": len(effective),
    }
