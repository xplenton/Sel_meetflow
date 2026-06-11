"""
Organisation-wide settings + email-verification + default-guest-group
(iter 119).

Three feature areas wired into one module so the admin UI has a single
endpoint to talk to and the auth flow has a single helper to consult.

  - `GET/PUT /api/admin/org-settings` — persistent config for:
      * `email_verification_required` — new users must click the link in the
        welcome email before their account is fully active (they can still
        log in; the frontend shows a banner + blocks writes until verified).
      * `auto_promote_on_verify` — when a user verifies, replace their
        `guest` group membership with the configured `default_member_group`.
      * `default_guest_group` / `default_member_group` — group_ids used by
        the above flows. The guest group is auto-created on first boot
        with minimal permissions (chat + profile) so out-of-the-box
        behaviour is sane.
  - `POST /api/auth/verify-email?token=...` — public, used by the link
    emailed at register time.
  - `POST /api/auth/resend-verification` — authenticated, lets a user
    re-trigger the email if the first one landed in spam or expired.
  - `ensure_default_groups(db)` — idempotent startup hook.

Token storage shares the same `password_reset_tokens`-style TTL pattern
via a dedicated `email_verification_tokens` collection with
`expires_at` TTL index (24 h).
"""
from __future__ import annotations

import os
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from database import db, logger
from dependencies import get_current_user
from services.email import send_email_real


router = APIRouter()

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
_DEFAULT_GUEST_PERMISSIONS = ["chat", "profile"]
_DEFAULT_MEMBER_PERMISSIONS = [
    "dashboard", "news", "scheduling", "chat", "calendar", "recordings", "profile",
]
_TOKEN_TTL_HOURS = 24
_ORG_SETTINGS_ID = "org_settings_singleton"


# ---------------------------------------------------------------------------
# Iter 306 — System Module-Visibility Groups (Variante C)
#
# Module visibility was previously baked into ROLE_DEFAULTS. To allow finer
# admin control without doubling up, we extracted `view:*` capabilities into
# four dedicated system-managed groups. Every user is auto-synced into the
# correct subset based on their role:
#
#   role=guest      → MODULE_GROUP_GUEST
#   role=member     → MODULE_GROUP_MEMBER
#   role=moderator  → MODULE_GROUP_MEMBER + MODULE_GROUP_ADMIN + MODULE_GROUP_ANALYTICS
#   role=admin      → MODULE_GROUP_MEMBER + MODULE_GROUP_ADMIN + MODULE_GROUP_ANALYTICS
#
# These groups are marked `is_system=True` and `module_group=True` so the
# admin UI can prevent accidental deletion. Membership is recomputed
# every time a role changes.
# ---------------------------------------------------------------------------
MODULE_GROUP_GUEST = "module-grp-guest"
MODULE_GROUP_MEMBER = "module-grp-member"
MODULE_GROUP_ADMIN = "module-grp-admin"
MODULE_GROUP_ANALYTICS = "module-grp-analytics"

_MODULE_GROUP_DEFS = [
    {
        "group_id": MODULE_GROUP_GUEST,
        "name": "Modul: Gast",
        "description": "Modul-Sichtbarkeit für Gäste (Dashboard, Chat).",
        "color": "#9CA3AF",
        "capabilities": ["view:dashboard", "view:chat"],
    },
    {
        "group_id": MODULE_GROUP_MEMBER,
        "name": "Modul: Standard",
        "description": "Modul-Sichtbarkeit für reguläre Mitarbeiter — alle Endnutzer-Module.",
        "color": "#6B8E23",
        "capabilities": [
            "view:dashboard", "view:news", "view:chat", "view:meetings",
            "view:scheduling", "view:calendar", "view:recordings", "view:surveys",
            "view:tasks", "view:resources", "view:filetransfer",
        ],
    },
    {
        "group_id": MODULE_GROUP_ADMIN,
        "name": "Modul: Verwaltung",
        "description": "Zugriff auf den Verwaltungs-Bereich (Admin-Modul).",
        "color": "#4A5D4E",
        "capabilities": ["view:admin"],
    },
    {
        "group_id": MODULE_GROUP_ANALYTICS,
        "name": "Modul: Auswertungen",
        "description": "Zugriff auf das Auswertungs-Modul (Analytics & Reports).",
        "color": "#7C3AED",
        "capabilities": ["view:analytics"],
    },
]


def _module_groups_for_role(role: str) -> list[str]:
    """Map a role to the list of module-system groups the user must belong to."""
    if role == "admin" or role == "moderator":
        return [MODULE_GROUP_MEMBER, MODULE_GROUP_ADMIN, MODULE_GROUP_ANALYTICS]
    if role == "guest":
        return [MODULE_GROUP_GUEST]
    # member + any legacy role default to member
    return [MODULE_GROUP_MEMBER]


_ALL_MODULE_GROUP_IDS = {d["group_id"] for d in _MODULE_GROUP_DEFS}


async def _ensure_module_groups(database) -> None:
    """Create or refresh the four module-system groups. Idempotent — runs
    on every server boot, race-safe across multiple workers.

    Iter 384 — Capabilities-Persistenz für System-Modul-Gruppen.
    -----------------------------------------------------------------
    Vorher hat dieser Bootstrap auf JEDEM Server-Start die `capabilities`
    der vier Gruppen (`Modul: Gast/Standard/Verwaltung/Auswertungen`) per
    `$set` aus `_MODULE_GROUP_DEFS` zurückgesetzt. Effekt: Admins konnten
    z.B. „view:news" in „Modul: Standard" abhaken, die Änderung war im
    UI sichtbar, wurde aber beim nächsten Backend-Restart wieder über-
    schrieben — Schein-Edit.

    Neues Verhalten:
      * Beim **ersten** Anlegen einer Gruppe (Upsert-Insert) wird die
        Capability-Liste aus `_MODULE_GROUP_DEFS` als Default befüllt.
      * Bei **existierenden** Gruppen werden nur Metadaten (`name`,
        `description`, `color`, Flags) refresht. `capabilities` bleibt
        unangetastet — Admin-Anpassungen bleiben dauerhaft erhalten.
      * Wir markieren System-Modul-Gruppen weiterhin mit
        `is_system=True` + `module_group=True`, damit `delete_group`
        sie weiterhin schützt.

    Konsequenz: Wenn neue Module hinzukommen, muss der Admin sie aktiv
    per UI zur jeweiligen Modul-Gruppe hinzufügen (analog zu Custom-
    Gruppen). Das ist gewollt — die Admin-Entscheidungen sind die
    Source-of-Truth, nicht der Code-Default.
    """
    # Defensive: clean up any historical duplicates from before iter 306
    # (early dev boots may have inserted the same group_id twice). For each
    # group_id we keep the row with the largest member count and merge the
    # others' members into it.
    for defn in _MODULE_GROUP_DEFS:
        gid = defn["group_id"]
        dupes = await database.groups.find({"group_id": gid}, {"_id": 1, "members": 1}).to_list(50)
        if len(dupes) > 1:
            dupes.sort(key=lambda d: len(d.get("members", []) or []), reverse=True)
            keeper = dupes[0]
            merged_members = set(keeper.get("members", []) or [])
            for extra in dupes[1:]:
                merged_members.update(extra.get("members", []) or [])
                await database.groups.delete_one({"_id": extra["_id"]})
            await database.groups.update_one(
                {"_id": keeper["_id"]},
                {"$set": {"members": list(merged_members)}},
            )
            logger.info(f"[iter306] merged {len(dupes)-1} duplicate(s) of {gid} → keeping {len(merged_members)} members")

    for defn in _MODULE_GROUP_DEFS:
        gid = defn["group_id"]
        # Metadaten — werden bei jedem Boot frisch gesetzt (Namen/Beschreibung
        # dürfen sich in einer neuen Software-Version ändern, das ist OK).
        set_payload = {
            "group_id": gid,
            "name": defn["name"],
            "description": defn["description"],
            "color": defn["color"],
            "permissions": [],  # legacy field, unused
            "is_system": True,
            "module_group": True,
        }
        # Capabilities + members + created_at — nur beim INSERT setzen.
        # Bei einem späteren Boot bleiben Admin-Anpassungen der
        # `capabilities` damit erhalten (Iter 384).
        set_on_insert_payload = {
            "capabilities": list(defn["capabilities"]),
            "members": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await database.groups.update_one(
            {"group_id": gid},
            {"$set": set_payload, "$setOnInsert": set_on_insert_payload},
            upsert=True,
        )
    # Best-effort unique index so future races cannot create duplicates.
    try:
        await database.groups.create_index("group_id", unique=True)
    except Exception:
        pass


async def sync_user_module_groups(user_id: str, role: str) -> None:
    """Add `user_id` to the right module groups for their role, and remove
    them from any module groups they no longer should belong to.

    Used both by the one-time backfill and on every role change.
    """
    desired = set(_module_groups_for_role(role or "member"))
    to_remove = _ALL_MODULE_GROUP_IDS - desired

    # 1. Add to desired
    for gid in desired:
        await db.groups.update_one(
            {"group_id": gid},
            {"$addToSet": {"members": user_id}},
        )
        await db.users.update_one(
            {"user_id": user_id},
            {"$addToSet": {"groups": gid}},
        )
    # 2. Remove from undesired
    if to_remove:
        await db.groups.update_many(
            {"group_id": {"$in": list(to_remove)}},
            {"$pull": {"members": user_id}},
        )
        await db.users.update_one(
            {"user_id": user_id},
            {"$pullAll": {"groups": list(to_remove)}},
        )


async def _backfill_all_users_to_module_groups(database) -> None:
    """One-time-ish backfill: walk every user and sync them into the
    right module groups. Cheap (bulk per role bucket) and idempotent."""
    role_buckets: dict[str, list[str]] = {}
    async for u in database.users.find({}, {"_id": 0, "user_id": 1, "role": 1}):
        # Map legacy roles to the four system roles
        raw_role = (u.get("role") or "member").lower()
        if raw_role in ("admin", "moderator", "member", "guest"):
            sys_role = raw_role
        elif raw_role == "user":
            sys_role = "member"
        else:
            # autor/redakteur/freigeber/manager → member (we do NOT alter
            # functional caps here, just module visibility groups).
            sys_role = "member"
        role_buckets.setdefault(sys_role, []).append(u["user_id"])

    total = 0
    for sys_role, uids in role_buckets.items():
        desired = _module_groups_for_role(sys_role)
        undesired = list(_ALL_MODULE_GROUP_IDS - set(desired))
        # add memberships
        for gid in desired:
            await database.groups.update_one(
                {"group_id": gid},
                {"$addToSet": {"members": {"$each": uids}}},
            )
            await database.users.update_many(
                {"user_id": {"$in": uids}},
                {"$addToSet": {"groups": gid}},
            )
        # remove memberships from non-matching groups (safety net for
        # users whose role was downgraded)
        if undesired:
            await database.groups.update_many(
                {"group_id": {"$in": undesired}},
                {"$pull": {"members": {"$in": uids}}},
            )
            await database.users.update_many(
                {"user_id": {"$in": uids}},
                {"$pullAll": {"groups": undesired}},
            )
        total += len(uids)
    logger.info(f"[iter306] module-group backfill processed {total} users across {len(role_buckets)} roles")


async def _get_settings() -> dict:
    doc = await db.org_settings.find_one({"_id_key": _ORG_SETTINGS_ID}, {"_id": 0})
    if not doc:
        doc = {
            "_id_key": _ORG_SETTINGS_ID,
            "email_verification_required": False,
            "auto_promote_on_verify": True,
            "default_guest_group": None,  # filled in by ensure_default_groups
            "default_member_group": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.org_settings.insert_one(doc)
        # Strip _id that insert_one added
        doc.pop("_id", None)
    return doc


async def ensure_default_groups(database) -> None:
    """Idempotent: guarantees a `Gast` group exists and the org_settings
    point at it. Called from server startup."""
    guest = await database.groups.find_one({"name": "Gast"}, {"_id": 0})
    if not guest:
        guest = {
            "group_id": f"grp_{uuid.uuid4().hex[:10]}",
            "name": "Gast",
            "description": "Neu registrierte Nutzer mit minimalen Rechten",
            "color": "#9CA3AF",
            "members": [],
            "permissions": list(_DEFAULT_GUEST_PERMISSIONS),
            "capabilities": [],
            "is_system": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await database.groups.insert_one(guest)
        logger.info(f"[iter118] auto-created 'Gast' group {guest['group_id']}")
    member = await database.groups.find_one({"name": "Mitglied"}, {"_id": 0})
    if not member:
        member = {
            "group_id": f"grp_{uuid.uuid4().hex[:10]}",
            "name": "Mitglied",
            "description": "Standard-Gruppe für verifizierte Nutzer",
            "color": "#6B8E23",
            "members": [],
            "permissions": list(_DEFAULT_MEMBER_PERMISSIONS),
            "capabilities": [],
            "is_system": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await database.groups.insert_one(member)
        logger.info(f"[iter118] auto-created 'Mitglied' group {member['group_id']}")

    # Update settings doc to point at them (only if not already set)
    settings = await database.org_settings.find_one({"_id_key": _ORG_SETTINGS_ID}, {"_id": 0}) or {}
    updates = {}
    if not settings.get("default_guest_group"):
        updates["default_guest_group"] = guest["group_id"]
    if not settings.get("default_member_group"):
        updates["default_member_group"] = member["group_id"]
    if updates:
        await database.org_settings.update_one(
            {"_id_key": _ORG_SETTINGS_ID},
            {"$set": {**updates, "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )

    # TTL index on verification tokens
    try:
        await database.email_verification_tokens.create_index(
            "expires_at", expireAfterSeconds=0
        )
    except Exception:
        pass

    # Iter 306 — Module-visibility system groups + one-time backfill.
    await _ensure_module_groups(database)
    await _backfill_all_users_to_module_groups(database)


async def assign_to_default_guest_group(user_id: str) -> Optional[str]:
    """Add `user_id` to the configured default guest group. Returns the
    group_id used, or None if nothing happened.

    Iter 306 — Also assigns the module-visibility group matching the user's
    actual role (not necessarily "guest") so the new account actually sees
    the correct modules in the sidebar.
    """
    settings = await _get_settings()
    gid = settings.get("default_guest_group")
    if not gid:
        return None
    await db.groups.update_one({"group_id": gid}, {"$addToSet": {"members": user_id}})
    await db.users.update_one({"user_id": user_id}, {"$addToSet": {"groups": gid}})
    # Module visibility — derive from the user's actual role
    udoc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "role": 1}) or {}
    raw_role = (udoc.get("role") or "member").lower()
    sys_role = raw_role if raw_role in ("admin", "moderator", "member", "guest") else "member"
    await sync_user_module_groups(user_id, sys_role)
    return gid


async def promote_to_member_group(user_id: str) -> Optional[str]:
    """Move a user from guest → default_member_group.

    Iter 306 — Also swaps the module-visibility groups so the freshly
    verified user gains the standard sidebar.
    """
    settings = await _get_settings()
    guest_id = settings.get("default_guest_group")
    member_id = settings.get("default_member_group")
    if not member_id:
        return None
    if guest_id:
        await db.groups.update_one({"group_id": guest_id}, {"$pull": {"members": user_id}})
        await db.users.update_one({"user_id": user_id}, {"$pull": {"groups": guest_id}})
    await db.groups.update_one({"group_id": member_id}, {"$addToSet": {"members": user_id}})
    await db.users.update_one({"user_id": user_id}, {"$addToSet": {"groups": member_id}})
    # Look up the user's CURRENT role to pick the right module groups
    udoc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "role": 1}) or {}
    role = (udoc.get("role") or "member").lower()
    if role not in ("admin", "moderator", "member", "guest"):
        role = "member"
    await sync_user_module_groups(user_id, role)
    return member_id


async def is_signup_domain_allowed(email: str) -> tuple[bool, list[str]]:
    """Iter 290 — Check if a self-registration email's domain matches the
    org-configured allowlist. Returns (allowed, allowed_domains).
    If the allowlist is empty/unset, any domain is allowed (legacy behavior).
    """
    settings = await _get_settings()
    allowed = [d for d in (settings.get("allowed_signup_domains") or []) if d]
    if not allowed:
        return True, []
    domain = (email or "").split("@", 1)[-1].lower().strip()
    if not domain:
        return False, allowed
    return (domain in allowed), allowed


async def create_verification_token(user_id: str, email: str) -> str:
    token = secrets.token_urlsafe(32)
    await db.email_verification_tokens.insert_one({
        "token": token,
        "user_id": user_id,
        "email": email,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=_TOKEN_TTL_HOURS),
        "used": False,
    })
    return token


def _build_verify_email_html(name: str, verify_url: str) -> str:
    return f"""
    <div style="font-family:-apple-system,Segoe UI,sans-serif;max-width:560px;margin:0 auto;padding:32px 24px;color:#1C1F1D">
      <h2 style="font-weight:500;letter-spacing:-0.02em">Willkommen bei MeetFlow, {name or ''}!</h2>
      <p style="color:#4B5563;line-height:1.6">
        Bitte bestätige deine E-Mail-Adresse, damit du alle Funktionen nutzen kannst.
      </p>
      <p style="margin:28px 0">
        <a href="{verify_url}" style="background:#4A5D4E;color:white;padding:12px 24px;border-radius:999px;text-decoration:none;font-weight:500">
          E-Mail bestätigen
        </a>
      </p>
      <p style="color:#9CA3AF;font-size:12px;line-height:1.5">
        Der Link ist 24 Stunden gültig. Falls du diese E-Mail nicht erwartet hast, kannst du sie ignorieren.
      </p>
    </div>
    """


async def send_verification_email(user_id: str, email: str, name: str) -> dict:
    token = await create_verification_token(user_id, email)
    frontend = os.environ.get("FRONTEND_URL", "")
    verify_url = f"{frontend}/verify-email?token={token}"
    html = _build_verify_email_html(name, verify_url)
    return await send_email_real(email, "MeetFlow - E-Mail bestätigen", html)


# ===========================================================================
# Admin org-settings endpoints
# ===========================================================================
class OrgSettingsUpdate(BaseModel):
    email_verification_required: Optional[bool] = None
    auto_promote_on_verify: Optional[bool] = None
    default_guest_group: Optional[str] = None
    default_member_group: Optional[str] = None
    # Iter 290 — Self-registration domain allowlist + auto-lock unverified.
    # If `allowed_signup_domains` is non-empty, self-registration is only
    # allowed for email addresses whose domain (after the @) is in the list.
    # SSO and admin-created users are NOT subject to this check.
    allowed_signup_domains: Optional[list[str]] = None
    # When `auto_lock_unverified_hours` > 0, self-registered users whose
    # email is still unverified after that many hours get status="locked"
    # by a periodic background sweep. 0 disables auto-lock.
    auto_lock_unverified_hours: Optional[int] = None
    # Iter 379 — Passwort-Rotation in Monaten. 0 = deaktiviert. >0 = User mit
    # Passwoertern, die alter sind als N Monate, erhalten beim Login einen
    # `must_change_password`-Flag und werden zum Aendern aufgefordert.
    password_rotation_months: Optional[int] = None


@router.get("/admin/org-settings")
async def admin_get_org_settings(request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return await _get_settings()


@router.put("/admin/org-settings")
async def admin_put_org_settings(req: OrgSettingsUpdate, request: Request):
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    # Iter 290 — sanitise allowed_signup_domains: lowercase, strip, drop empties.
    if "allowed_signup_domains" in updates:
        raw = updates["allowed_signup_domains"] or []
        updates["allowed_signup_domains"] = sorted({
            (d or "").strip().lstrip("@").lower()
            for d in raw
            if isinstance(d, str) and (d or "").strip()
        })
    if "auto_lock_unverified_hours" in updates:
        try:
            updates["auto_lock_unverified_hours"] = max(0, min(168, int(updates["auto_lock_unverified_hours"])))
        except Exception:
            updates["auto_lock_unverified_hours"] = 0
    # Iter 379 — Passwort-Rotation: 0..36 Monate.
    if "password_rotation_months" in updates:
        try:
            updates["password_rotation_months"] = max(0, min(36, int(updates["password_rotation_months"])))
        except Exception:
            updates["password_rotation_months"] = 0
    if not updates:
        return await _get_settings()
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.org_settings.update_one(
        {"_id_key": _ORG_SETTINGS_ID},
        {"$set": updates},
        upsert=True,
    )
    return await _get_settings()


# ===========================================================================
# Public verification endpoints
# ===========================================================================
class VerifyEmailRequest(BaseModel):
    token: str


@router.post("/auth/verify-email")
async def verify_email(req: VerifyEmailRequest):
    doc = await db.email_verification_tokens.find_one({"token": req.token, "used": False}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=400, detail="Token ungültig oder bereits verwendet")
    # Note: TTL index deletes expired rows, but also manually check in case
    # we hit the exact second.
    expires = doc.get("expires_at")
    if isinstance(expires, str):
        expires = datetime.fromisoformat(expires)
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires and expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Token abgelaufen")

    user_id = doc["user_id"]
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"email_verified": True, "email_verified_at": datetime.now(timezone.utc).isoformat()}},
    )
    await db.email_verification_tokens.update_one({"token": req.token}, {"$set": {"used": True}})

    settings = await _get_settings()
    promoted_to = None
    if settings.get("auto_promote_on_verify", True):
        promoted_to = await promote_to_member_group(user_id)
    return {"ok": True, "user_id": user_id, "promoted_to_group": promoted_to}


@router.post("/auth/resend-verification")
async def resend_verification(request: Request):
    user = await get_current_user(request)
    if user.get("email_verified"):
        return {"ok": True, "already_verified": True}
    result = await send_verification_email(user["user_id"], user["email"], user.get("name", ""))
    return {"ok": True, "email_result": result.get("status")}
