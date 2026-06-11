from fastapi import APIRouter, HTTPException, Request, Response, UploadFile, File
import os
import re
import uuid
import jwt
import secrets
import httpx
import asyncio
from datetime import datetime, timezone, timedelta
from database import db, logger
from dependencies import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    set_auth_cookies, get_current_user, user_response, JWT_SECRET, JWT_ALGORITHM
)
from services.storage import put_object, get_object, APP_STORAGE_PREFIX
from services.prod_ops import limiter
from services.password_policy import (
    validate_password_or_raise, check_history_or_raise, push_password_history,
    is_password_rotation_due, password_policy_meta,
)
from models import (
    RegisterRequest, LoginRequest, ForgotPasswordRequest, ResetPasswordRequest,
    GoogleSessionRequest, UpdateProfileRequest
)

router = APIRouter()

# Iter 252 — Configurable login rate limits via env (default keeps prod behaviour).
# Set LOGIN_RATE_LIMIT="100/minute" in dev/test .env to ease automated tests.
LOGIN_RATE_LIMIT = os.environ.get("LOGIN_RATE_LIMIT", "10/minute")
REGISTER_RATE_LIMIT = os.environ.get("REGISTER_RATE_LIMIT", "5/minute")


@router.post("/auth/register")
@limiter.limit(REGISTER_RATE_LIMIT)
async def register(req: RegisterRequest, request: Request, response: Response):
    email = req.email.lower().strip()
    # Iter 379 — Passwort-Richtlinie auch bei Self-Registration durchsetzen.
    validate_password_or_raise(req.password)
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    # Iter 290 — enforce signup-domain allowlist for self-registration.
    try:
        from routes.org_onboarding import is_signup_domain_allowed
        ok, allowed = await is_signup_domain_allowed(email)
        if not ok:
            domain_list = ", ".join(allowed) if allowed else "(keine konfiguriert)"
            raise HTTPException(
                status_code=403,
                detail=f"Selbst-Registrierung nur für folgende Domains erlaubt: {domain_list}",
            )
    except HTTPException:
        raise
    except Exception as _e:
        logger.warning("[REGISTER] domain check skipped: %s", _e)
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    user = {
        "user_id": user_id, "email": email,
        "password_hash": hash_password(req.password),
        # Iter 379 — Passwort-Historie + Aenderungs-Timestamp
        "password_history": [],
        "password_changed_at": datetime.now(timezone.utc).isoformat(),
        "name": req.name, "role": "user", "avatar": "",
        "language": "en", "created_at": datetime.now(timezone.utc).isoformat(),
        "email_verified": False,
        # Iter 290 — Mark this account as self-registered so the periodic
        # sweep auto-locks ONLY users who signed up themselves, never users
        # provisioned by an admin or via invitation.
        "self_registered": True,
        "status": "active",
        "groups": [],
    }
    await db.users.insert_one(user)

    # Iter 119: new users land in the default `Gast` group + get a
    # verification email (opt-in policy via `org_settings`).
    try:
        from routes.org_onboarding import assign_to_default_guest_group, send_verification_email
        gid = await assign_to_default_guest_group(user_id)
        if gid:
            user["groups"] = [gid]
        # Iter 290 — Self-registered users ALWAYS get a verification mail,
        # because they will be auto-locked after the configured grace period
        # without verification (org_settings.auto_lock_unverified_hours).
        try:
            await send_verification_email(user_id, email, req.name)
        except Exception:
            pass  # email failure must not break signup
    except Exception:
        pass

    access_token = create_access_token(user_id, email, user.get("token_version", 0))
    refresh_token = create_refresh_token(user_id, user.get("token_version", 0))
    set_auth_cookies(response, access_token, refresh_token)
    resp = user_response(user)
    resp["token"] = access_token  # Include token in response for API testing
    return resp

@router.post("/auth/login")
@limiter.limit(LOGIN_RATE_LIMIT)
async def login(req: LoginRequest, request: Request, response: Response):
    # Iter 379 — Login akzeptiert E-Mail ODER Personalnummer als Identifier.
    # User ohne dienstliche E-Mail wurden vom Admin mit `no_email_account=True`
    # angelegt und melden sich mit ihrer Personalnummer + Passwort an.
    raw_id = req.email.lower().strip()
    email = raw_id  # Falls Login via E-Mail, ist `email` der normale Lookup-Key.
    ip = request.client.host if request.client else "unknown"
    identifier = f"{ip}:{raw_id}"
    attempt = await db.login_attempts.find_one({"identifier": identifier}, {"_id": 0})
    if attempt and attempt.get("count", 0) >= 5:
        locked_until = attempt.get("locked_until")
        if locked_until:
            if isinstance(locked_until, str):
                locked_until = datetime.fromisoformat(locked_until)
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) < locked_until:
                raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")
            else:
                await db.login_attempts.delete_one({"identifier": identifier})
    # E-Mail-Lookup, danach Fallback auf Personalnummer.
    user = await db.users.find_one({"email": raw_id}, {"_id": 0})
    if not user:
        # Personalnummer-Lookup (case-insensitive — `pn` und `PN` matchen).
        user = await db.users.find_one(
            {"personnel_number": {"$regex": f"^{re.escape(req.email.strip())}$", "$options": "i"}},
            {"_id": 0},
        )
    if not user or not verify_password(req.password, user.get("password_hash", "")):
        await db.login_attempts.update_one(
            {"identifier": identifier},
            {"$inc": {"count": 1}, "$set": {"locked_until": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()}},
            upsert=True
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")
    # Den tatsaechlich gespeicherten Email-Wert fuer die weitere Logik benutzen.
    email = user.get("email", "")
    await db.login_attempts.delete_many({"identifier": identifier})
    if user.get("status") == "inactive":
        raise HTTPException(status_code=403, detail="Konto deaktiviert")
    # Iter 290 — auto-locked accounts (self-registered, e-mail never verified
    # within the grace period) block login and ask for re-verification.
    if user.get("status") == "locked_unverified":
        raise HTTPException(
            status_code=403,
            detail="Konto gesperrt — E-Mail wurde nicht innerhalb der Frist bestätigt. "
                   "Bitte Administrator kontaktieren oder neuen Verifizierungslink anfordern.",
        )

    # Iter 188 — 2FA challenge: if the user has TOTP enabled, we issue a
    # short-lived (5 min) "challenge" token that the client exchanges via
    # /auth/2fa/verify-login for the real session.
    if user.get("totp_enabled"):
        challenge = jwt.encode(
            {
                "user_id": user["user_id"],
                "purpose": "totp_challenge",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            JWT_SECRET, algorithm=JWT_ALGORITHM,
        )
        return {
            "totp_required": True,
            "challenge_token": challenge,
            "user_email": email,  # so the UI can display a hint
        }

    access_token = create_access_token(user["user_id"], email, user.get("token_version", 0))
    refresh_token = create_refresh_token(user["user_id"], user.get("token_version", 0))
    set_auth_cookies(response, access_token, refresh_token)
    resp = user_response(user)
    resp["token"] = access_token  # Include token in response for API testing
    # Iter 379 — Passwort-Rotation: User mit veraltetem Passwort signalisieren.
    if user.get("must_change_password", False) or await is_password_rotation_due(user):
        resp["must_change_password"] = True
    return resp


# ============ 2FA / TOTP (iter 188) ============

@router.post("/auth/2fa/verify-login")
@limiter.limit(LOGIN_RATE_LIMIT)
async def verify_2fa_login(request: Request, response: Response):
    """Second leg of the 2FA login dance. Body: {challenge_token, code, mode?='totp'|'recovery'}."""
    from services import totp as totp_svc
    body = await request.json()
    challenge = body.get("challenge_token", "")
    code = (body.get("code") or "").strip()
    mode = body.get("mode") or "totp"
    if not challenge or not code:
        raise HTTPException(status_code=400, detail="challenge_token und code erforderlich")
    try:
        payload = jwt.decode(challenge, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        raise HTTPException(status_code=401, detail="Challenge ungültig oder abgelaufen")
    if payload.get("purpose") != "totp_challenge":
        raise HTTPException(status_code=401, detail="Falscher Token-Typ")
    user = await db.users.find_one({"user_id": payload["user_id"]}, {"_id": 0})
    if not user or not user.get("totp_enabled"):
        raise HTTPException(status_code=401, detail="2FA nicht aktiv")
    if mode == "recovery":
        ok, remaining = totp_svc.consume_recovery_code(user.get("totp_recovery_hashes") or [], code)
        if not ok:
            raise HTTPException(status_code=401, detail="Wiederherstellungscode ungültig")
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"totp_recovery_hashes": remaining}},
        )
    else:
        if not totp_svc.verify_code(user.get("totp_secret", ""), code):
            raise HTTPException(status_code=401, detail="TOTP-Code ungültig")
    access_token = create_access_token(user["user_id"], user["email"], user.get("token_version", 0))
    refresh_token = create_refresh_token(user["user_id"], user.get("token_version", 0))
    set_auth_cookies(response, access_token, refresh_token)
    resp = user_response(user)
    resp["token"] = access_token
    return resp


@router.post("/auth/2fa/setup")
async def setup_2fa(request: Request):
    """Generate a fresh secret + QR + recovery codes. Stores secret as
    `totp_pending_secret` until /verify-setup confirms it actually works."""
    from services import totp as totp_svc
    from services import user_cache
    user = await get_current_user(request)
    secret = totp_svc.generate_secret()
    uri = totp_svc.provisioning_uri(secret, user["email"])
    qr = totp_svc.qr_png_data_url(uri)
    recovery_codes = totp_svc.generate_recovery_codes()
    recovery_hashes = totp_svc.hash_recovery_codes(recovery_codes)
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "totp_pending_secret": secret,
            "totp_pending_recovery_hashes": recovery_hashes,
        }},
    )
    # Iter 278 — invalidate the user_cache so /verify-setup (the very next
    # request from the SPA) doesn't read a stale user document without the
    # newly-written pending secret. Without this, every first-attempt 2FA
    # setup fails with "Code ungültig" until the 5s cache TTL elapses.
    await user_cache.invalidate(user["user_id"])
    return {
        "secret": secret,
        "uri": uri,
        "qr_png": qr,
        "recovery_codes": recovery_codes,  # ONLY moment they are returned in plaintext
    }


@router.post("/auth/2fa/verify-setup")
async def verify_2fa_setup(request: Request):
    """Body: {code} — confirm the user can produce a valid TOTP from the
    pending secret. On success the secret is committed and 2FA is active."""
    from services import totp as totp_svc
    user = await get_current_user(request)
    body = await request.json()
    code = (body.get("code") or "").strip()
    pending = user.get("totp_pending_secret")
    if not pending:
        raise HTTPException(status_code=400, detail="Kein Setup gestartet")
    if not totp_svc.verify_code(pending, code):
        raise HTTPException(status_code=401, detail="Code ungültig")
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {
            "$set": {
                "totp_enabled": True,
                "totp_secret": pending,
                "totp_recovery_hashes": user.get("totp_pending_recovery_hashes") or [],
                "totp_enabled_at": datetime.now(timezone.utc).isoformat(),
            },
            "$unset": {"totp_pending_secret": "", "totp_pending_recovery_hashes": ""},
        },
    )
    # Iter 278 — invalidate cache so subsequent /auth/me sees totp_enabled=true
    from services import user_cache
    await user_cache.invalidate(user["user_id"])
    return {"ok": True, "totp_enabled": True}


@router.post("/auth/2fa/disable")
async def disable_2fa(request: Request):
    """Body: {code} — require a fresh TOTP/recovery code before disabling."""
    from services import totp as totp_svc
    user = await get_current_user(request)
    if not user.get("totp_enabled"):
        return {"ok": True, "totp_enabled": False}
    body = await request.json()
    code = (body.get("code") or "").strip()
    mode = body.get("mode") or "totp"
    valid = False
    if mode == "totp":
        valid = totp_svc.verify_code(user.get("totp_secret", ""), code)
    elif mode == "recovery":
        valid, _ = totp_svc.consume_recovery_code(user.get("totp_recovery_hashes") or [], code)
    if not valid:
        raise HTTPException(status_code=401, detail="Code ungültig")
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {
            "$set": {"totp_enabled": False},
            "$unset": {
                "totp_secret": "", "totp_recovery_hashes": "",
                "totp_pending_secret": "", "totp_pending_recovery_hashes": "",
                "totp_enabled_at": "",
            },
        },
    )
    # Iter 278 — invalidate cache so /auth/me reflects totp_enabled=false
    from services import user_cache
    await user_cache.invalidate(user["user_id"])
    return {"ok": True, "totp_enabled": False}


@router.get("/auth/2fa/status")
async def get_2fa_status(request: Request):
    from services import totp as totp_svc
    user = await get_current_user(request)
    return totp_svc.public_status(user)


@router.post("/auth/2fa/regenerate-recovery")
async def regenerate_recovery_codes(request: Request):
    """Generate a fresh batch of 10 recovery codes. Body: {code} (TOTP)."""
    from services import totp as totp_svc
    user = await get_current_user(request)
    if not user.get("totp_enabled"):
        raise HTTPException(status_code=400, detail="2FA nicht aktiv")
    body = await request.json()
    code = (body.get("code") or "").strip()
    if not totp_svc.verify_code(user.get("totp_secret", ""), code):
        raise HTTPException(status_code=401, detail="Code ungültig")
    fresh = totp_svc.generate_recovery_codes()
    hashes = totp_svc.hash_recovery_codes(fresh)
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"totp_recovery_hashes": hashes}},
    )
    return {"recovery_codes": fresh}


# ============ DSGVO Export ============
# Note: implementation lives at /api/users/me/export below. This iteration's
# new helper services/gdpr_export.py provides a richer data dump that can be
# wired into the existing endpoint when needed.


# ============ Password Policy / Change (iter 379) ============

@router.get("/auth/password-policy")
async def get_password_policy(request: Request):
    """Liefert die aktuelle Passwort-Richtlinie + Rotations-Konfiguration
    fuer das Frontend (Register-Form, Profil-Dialog).
    """
    meta = password_policy_meta()
    # Rotations-Setting aus org_settings einbinden, falls vorhanden.
    try:
        doc = await db.org_settings.find_one({}, {"_id": 0, "password_rotation_months": 1})
        if doc and "password_rotation_months" in doc:
            meta["rotation_months"] = int(doc["password_rotation_months"])
        else:
            meta["rotation_months"] = meta["rotation_months_default"]
    except Exception:
        meta["rotation_months"] = meta["rotation_months_default"]
    return meta


@router.post("/auth/change-password")
@limiter.limit(LOGIN_RATE_LIMIT)
async def change_password(request: Request):
    """Benutzer aendert sein eigenes Passwort.

    Body: {current_password, new_password, new_password_confirm}.
    Validiert:
      * Altes Passwort korrekt
      * Neue Passwortbestaetigung identisch
      * Neue Passwort-Policy erfuellt (4-aus-4)
      * Neues Passwort nicht in den letzten PW_HISTORY_SIZE Hashes
    """
    user = await get_current_user(request)
    body = await request.json()
    current = (body.get("current_password") or "").strip()
    new_pw = body.get("new_password") or ""
    new_confirm = body.get("new_password_confirm") or ""
    if not current or not new_pw:
        raise HTTPException(status_code=400, detail="Altes und neues Passwort sind Pflicht")
    if new_pw != new_confirm:
        raise HTTPException(status_code=400, detail="Neues Passwort und Bestätigung stimmen nicht überein")
    # Hash aus DB holen (nicht aus dem cached User-Objekt — dort fehlt password_hash).
    db_user = await db.users.find_one({"user_id": user["user_id"]},
                                       {"_id": 0, "password_hash": 1, "password_history": 1})
    if not db_user or not verify_password(current, db_user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Altes Passwort ist falsch")
    if current == new_pw:
        raise HTTPException(status_code=400, detail="Neues Passwort darf nicht mit dem aktuellen identisch sein")
    validate_password_or_raise(new_pw)
    # Auch gegen Historie pruefen (inkl. aktuellem Hash, doppelter Schutz).
    history = db_user.get("password_history") or []
    all_to_check = list(history) + [db_user.get("password_hash", "")]
    check_history_or_raise(new_pw, all_to_check, verify_password)
    new_hash = hash_password(new_pw)
    new_history = push_password_history(history, db_user.get("password_hash", ""))
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "password_hash": new_hash,
            "password_history": new_history,
            "password_changed_at": datetime.now(timezone.utc).isoformat(),
            "must_change_password": False,
        }},
    )
    # Optional: alle anderen Sessions invalidieren (token_version bump).
    if body.get("logout_other_sessions"):
        new_tv = int(user.get("token_version", 0) or 0) + 1
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"token_version": new_tv}},
        )
    return {"ok": True, "changed_at": datetime.now(timezone.utc).isoformat()}


@router.post("/auth/logout")
async def logout(response: Response):
    # Match login cookie attributes (secure=True, samesite=none) so the browser
    # actually deletes the original cookie — mismatched attributes create a
    # ghost cookie that the browser keeps sending.
    response.set_cookie(key="access_token", value="", httponly=True, secure=True, samesite="none", max_age=0, path="/", expires=0)
    response.set_cookie(key="refresh_token", value="", httponly=True, secure=True, samesite="none", max_age=0, path="/", expires=0)
    return {"message": "Logged out"}


@router.post("/auth/logout-everywhere")
async def logout_everywhere(request: Request, response: Response):
    """Iter 274 — Force-invalidate ALL active sessions of the current user by
    bumping `token_version` in MongoDB. Every existing access/refresh token
    issued before the bump will be rejected by get_current_user/refresh_token
    (see dependencies.py — `token_tv < user_tv` check).
    Also clears the cookies on the current device so the user lands on /login.
    """
    user = await get_current_user(request)
    new_tv = int(user.get("token_version", 0) or 0) + 1
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"token_version": new_tv}},
    )
    # Invalidate per-request user cache so the next call sees the new tv.
    try:
        from services import user_cache
        await user_cache.invalidate(user["user_id"])
    except Exception:
        pass
    # Audit
    try:
        from services.permission_audit import log_caps_change
        await log_caps_change(
            actor=user, target_user_id=user["user_id"],
            action="logout_everywhere",
            details={"new_token_version": new_tv},
            category="session", request=request,
        )
    except Exception:
        pass
    response.set_cookie(key="access_token", value="", httponly=True, secure=True, samesite="none", max_age=0, path="/", expires=0)
    response.set_cookie(key="refresh_token", value="", httponly=True, secure=True, samesite="none", max_age=0, path="/", expires=0)
    return {"message": "Alle Sitzungen beendet", "token_version": new_tv}

@router.get("/auth/me")
async def get_me(request: Request):
    user = await get_current_user(request)
    data = user_response(user)
    # iter 155 — expose is_guest so the frontend can show the guest
    # welcome dialog + guest-specific UI hints without hitting another
    # endpoint on every mount.
    from services.guest_visibility import is_guest_user
    data["is_guest"] = await is_guest_user(user)
    return data


@router.get("/auth/ws-token")
async def get_ws_token(request: Request):
    """Issue a short-lived token for WebSocket connections.

    Browsers (esp. Safari on iOS and some cross-origin setups) inconsistently
    forward HttpOnly cookies on WebSocket upgrade requests. The frontend calls
    this endpoint over normal HTTPS (cookies reliably sent), receives a tiny
    5-minute JWT, and appends it as `?token=...` to the wss:// URL. The WS
    handler accepts both mechanisms. See services/auth.py _authenticate_ws.
    """
    user = await get_current_user(request)
    short_token = jwt.encode({
        "user_id": user["user_id"],
        "email": user.get("email", ""),
        "tv": int(user.get("token_version", 0) or 0),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {"token": short_token, "expires_in": 300}


@router.get("/users/me/email-preferences")
async def get_email_preferences(request: Request):
    user = await get_current_user(request)
    prefs = user.get("email_preferences") or {}
    return {
        "newsletter_enabled": bool(prefs.get("newsletter_enabled", True)),
        "meeting_invites_enabled": bool(prefs.get("meeting_invites_enabled", True)),
        "digest_frequency": prefs.get("digest_frequency", "immediate"),
    }


@router.get("/users/me/privacy")
async def get_privacy_settings(request: Request):
    """Iter 238 — Privacy-Toggles (z.B. fuer In-Office-Widget Opt-Out).
    Iter 323 — Erweitert um `dm_policy` (siehe `services/dm_policy.py`)."""
    user = await get_current_user(request)
    return {
        "hide_from_office_widget": bool(user.get("hide_from_office_widget", False)),
        # Iter 323 — DM-Policy: wer darf mich anschreiben?
        #   everyone | same_department | managers_plus | nobody
        "dm_policy": user.get("dm_policy") or "everyone",
    }


@router.put("/users/me/privacy")
async def update_privacy_settings(request: Request):
    user = await get_current_user(request)
    body = await request.json()
    clean: dict = {}
    if "hide_from_office_widget" in (body or {}):
        clean["hide_from_office_widget"] = bool(body["hide_from_office_widget"])
    if "dm_policy" in (body or {}):
        # Validate against the canonical enum so a typo can't silently break
        # the gate in `dm_policy.may_dm()`.
        val = str(body["dm_policy"] or "").strip().lower()
        if val not in {"everyone", "same_department", "managers_plus", "nobody"}:
            raise HTTPException(status_code=400, detail=f"Ungültige dm_policy: {val!r}")
        clean["dm_policy"] = val
    if not clean:
        raise HTTPException(status_code=400, detail="Keine zulaessigen Felder")
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": clean})
    # Iter 238 — invalidate user_cache so the next GET shows the new value.
    from services import user_cache as ucache
    await ucache.invalidate(user["user_id"])
    return {"message": "Privatsphaere-Einstellungen gespeichert", **clean}


@router.put("/users/me/email-preferences")
async def update_email_preferences(request: Request):
    user = await get_current_user(request)
    body = await request.json()
    allowed_keys = {"newsletter_enabled", "meeting_invites_enabled", "digest_frequency"}
    clean = {f"email_preferences.{k}": v for k, v in (body or {}).items() if k in allowed_keys}
    if not clean:
        raise HTTPException(status_code=400, detail="Keine zulaessigen Felder")
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": clean})
    # Audit the change (especially newsletter opt-in/out for DSGVO compliance)
    if "email_preferences.newsletter_enabled" in clean:
        from services.email_preferences import set_newsletter_enabled
        await set_newsletter_enabled(
            user["user_id"], bool(clean["email_preferences.newsletter_enabled"]), source="profile"
        )
    return {"message": "Einstellungen gespeichert"}


@router.get("/unsubscribe/{token}")
async def unsubscribe_preview(token: str):
    """Return a minimal preview of the user to unsubscribe — no auth needed (signed token)."""
    from services.email_preferences import verify_unsubscribe_token
    user_id = verify_unsubscribe_token(token)
    if not user_id:
        raise HTTPException(status_code=400, detail="Ungültiger Unsubscribe-Link")
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "email_preferences": 1, "name": 1})
    if not user:
        raise HTTPException(status_code=404, detail="Nutzer nicht gefunden")
    prefs = user.get("email_preferences") or {}
    return {
        "email": user.get("email", ""),
        "name": user.get("name", ""),
        "newsletter_enabled": bool(prefs.get("newsletter_enabled", True)),
    }


@router.post("/unsubscribe/{token}")
async def unsubscribe_confirm(token: str):
    """Confirm the one-click unsubscribe — no auth needed (signed token)."""
    from services.email_preferences import verify_unsubscribe_token, set_newsletter_enabled
    user_id = verify_unsubscribe_token(token)
    if not user_id:
        raise HTTPException(status_code=400, detail="Ungültiger Unsubscribe-Link")
    await set_newsletter_enabled(user_id, False, source="unsubscribe_link")
    return {"message": "Du wurdest erfolgreich aus dem Newsletter ausgetragen"}


@router.post("/unsubscribe/{token}/resubscribe")
async def resubscribe(token: str):
    """Re-enable newsletter subscription via the same token."""
    from services.email_preferences import verify_unsubscribe_token, set_newsletter_enabled
    user_id = verify_unsubscribe_token(token)
    if not user_id:
        raise HTTPException(status_code=400, detail="Ungültiger Link")
    await set_newsletter_enabled(user_id, True, source="resubscribe_link")
    return {"message": "Newsletter-Abo reaktiviert"}


@router.post("/users/me/onboarding-complete")
async def onboarding_complete(request: Request):
    """Persist the onboarding-done flag serverside so it survives device changes / cache wipes."""
    from datetime import datetime, timezone
    user = await get_current_user(request)
    now = datetime.now(timezone.utc).isoformat()
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"onboarding_completed_at": now}},
    )
    return {"onboarding_completed_at": now}


@router.post("/users/me/guest-onboarding-complete")
async def guest_onboarding_complete(request: Request):
    """Mark the guest-welcome tour as seen. Separate from the main-app
    onboarding so switching a user between regular <-> guest roles still
    triggers the right dialog (iter 155)."""
    from datetime import datetime, timezone
    user = await get_current_user(request)
    now = datetime.now(timezone.utc).isoformat()
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"guest_onboarded_at": now}},
    )
    return {"guest_onboarded_at": now}


@router.post("/users/me/notify-host")
async def guest_notify_host(request: Request):
    """Guest pings their inviter: "Ich bin jetzt online, wie geht's weiter?"
    (iter 156). Looks up `invited_by`, pushes a chat-WS toast + web-push.
    Rate-limited to once per hour so a guest can't spam their host.
    """
    from datetime import datetime, timezone
    user = await get_current_user(request)
    host_id = user.get("invited_by")
    if not host_id:
        raise HTTPException(status_code=400, detail="Kein Gastgeber hinterlegt")
    # Rate limit: 1 ping per hour per guest
    last_ts = user.get("last_host_notify_at")
    if last_ts:
        try:
            last_dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            from datetime import timedelta
            if datetime.now(timezone.utc) - last_dt < timedelta(hours=1):
                raise HTTPException(status_code=429, detail="Bitte warte eine Stunde, bevor du deinen Gastgeber erneut benachrichtigst.")
        except HTTPException:
            raise
        except Exception:
            pass
    guest_name = user.get("name") or (user.get("email") or "").split("@")[0] or "Dein Gast"
    title = f"👋 {guest_name}"
    body = "ist jetzt online und wartet auf dich."
    # WS toast (instant in-app banner)
    try:
        from routes.chat import chat_ws
        await chat_ws.send_to_user(host_id, {
            "type": "guest-notify",
            "guest_id": user["user_id"],
            "guest_name": guest_name,
            "title": title,
            "body": body,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass
    # Web-push (works even when host's tab is closed)
    try:
        from services.news_push import send_push_to_user
        await send_push_to_user(host_id, title=title, body=body, data={
            "url": "/chat",
            "tag": f"guest-notify-{user['user_id']}",
            "kind": "guest_notify",
        })
    except Exception:
        pass
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"last_host_notify_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True, "host_id": host_id}


# ============ CalDAV / ICS Subscription (read-only) ============
@router.get("/users/me/caldav-config")
async def caldav_get_config(request: Request):
    user = await get_current_user(request)
    from services.caldav_sync import get_user_config
    cfg = await get_user_config(user["user_id"])
    # Mask password
    cfg.pop("password", None)
    return cfg


@router.put("/users/me/caldav-config")
async def caldav_put_config(request: Request):
    user = await get_current_user(request)
    body = await request.json() or {}
    from services.caldav_sync import set_user_config
    return await set_user_config(user["user_id"], body)


@router.post("/users/me/caldav-sync")
async def caldav_sync_now(request: Request):
    user = await get_current_user(request)
    from services.caldav_sync import sync_user_calendar
    try:
        return await sync_user_calendar(user["user_id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync-Fehler: {e}")


@router.get("/users/me/caldav-events")
async def caldav_list_events(request: Request, days: int = 30):
    """Return the user's synced external events for the next `days` days."""
    user = await get_current_user(request)
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    end = (now + timedelta(days=max(1, min(365, days)))).isoformat()
    events = await db.external_calendar_events.find(
        {"user_id": user["user_id"], "start": {"$gte": now.isoformat(), "$lte": end}},
        {"_id": 0},
    ).sort("start", 1).to_list(500)
    return {"events": events, "count": len(events)}


# ============ Busy Slots (Terminfindung Blockaden) ============
@router.get("/users/me/busy-slots")
async def busy_slots_list(request: Request, start: str = "", end: str = ""):
    user = await get_current_user(request)
    from services.busy_slots import list_busy_slots
    slots = await list_busy_slots(user["user_id"], start or None, end or None)
    return {"slots": slots, "count": len(slots)}


@router.post("/users/me/busy-slots")
async def busy_slots_create(request: Request):
    user = await get_current_user(request)
    body = await request.json() or {}
    from services.busy_slots import create_busy_slot
    try:
        slot = await create_busy_slot(
            user["user_id"],
            start_iso=body.get("start") or "",
            end_iso=body.get("end") or "",
            title=body.get("title") or "",
            source_id=body.get("source_id"),
            source=body.get("source") or "manual",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return slot


@router.delete("/users/me/busy-slots/{slot_id}")
async def busy_slots_delete(slot_id: str, request: Request):
    user = await get_current_user(request)
    from services.busy_slots import delete_busy_slot
    ok = await delete_busy_slot(user["user_id"], slot_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Slot nicht gefunden")
    return {"deleted": True}

@router.post("/auth/refresh")
async def refresh_token(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        # Refresh token payload uses `user_id` (see dependencies.create_refresh_token)
        user_id = payload.get("user_id") or payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid refresh token payload")
        user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        # Session invalidation: if admin bumped token_version after this refresh
        # token was issued, reject it.
        token_tv = int(payload.get("tv", 0) or 0)
        user_tv = int(user.get("token_version", 0) or 0)
        if token_tv < user_tv:
            raise HTTPException(status_code=401, detail="Session invalidated")
        access_token = create_access_token(user["user_id"], user["email"], user_tv)
        # Mirror the cookie attributes used by set_auth_cookies() so subsequent
        # cross-origin requests continue to carry the cookie on the preview URL.
        response.set_cookie(
            key="access_token", value=access_token, httponly=True,
            secure=True, samesite="none", max_age=3600, path="/",
        )
        try:
            from services.health_metrics import log_auth_refresh
            await log_auth_refresh(user["user_id"], request)
        except Exception:
            pass
        return {"message": "Token refreshed"}
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

@router.post("/auth/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(req: ForgotPasswordRequest, request: Request):
    email = req.email.lower().strip()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user:
        return {"message": "If the email exists, a reset link has been sent"}
    # Iter 379 — No-Email-User koennen kein Passwort per Mail zuruecksetzen,
    # da sie keine echte E-Mail-Adresse haben. Sie muessen den Admin kontaktieren.
    # Antwort bleibt absichtlich generisch, damit man keine User-IDs erraten kann.
    if user.get("no_email_account"):
        return {"message": "If the email exists, a reset link has been sent"}
    token = secrets.token_urlsafe(32)
    await db.password_reset_tokens.insert_one({
        "token": token, "user_id": user["user_id"], "email": email,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), "used": False,
    })
    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    reset_url = f"{frontend_url}/reset-password?token={token}"
    # Try to dispatch via email; only log a masked preview as dev fallback so the
    # raw token never appears in production logs (security finding iter 101).
    try:
        from services.email import send_email_real
        await send_email_real(
            to_email=email,
            subject="MeetFlow – Passwort zurücksetzen",
            html_content=(
                f"<p>Hallo {user.get('name','')},</p>"
                f"<p>klicke auf den folgenden Link, um dein Passwort zurückzusetzen "
                f"(gültig für 1 Stunde):</p>"
                f"<p><a href=\"{reset_url}\">{reset_url}</a></p>"
                f"<p>Falls du das nicht angefordert hast, ignoriere diese Nachricht.</p>"
            ),
        )
    except Exception as e:
        # Fallback for dev/test environments: log ONLY a masked token preview.
        logger.warning(
            f"[auth] Password reset email dispatch failed ({e}); "
            f"token tail only: …{token[-6:]} for user_id={user['user_id']}"
        )
    return {"message": "If the email exists, a reset link has been sent"}

@router.post("/auth/reset-password")
@limiter.limit("5/minute")
async def reset_password(req: ResetPasswordRequest, request: Request):
    token_doc = await db.password_reset_tokens.find_one({"token": req.token, "used": False}, {"_id": 0})
    if not token_doc:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    expires_at = token_doc["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=400, detail="Token expired")
    # Iter 379 — Auch beim Forgot-Password-Flow Policy + Historie erzwingen.
    validate_password_or_raise(req.password)
    db_user = await db.users.find_one({"user_id": token_doc["user_id"]},
                                       {"_id": 0, "password_hash": 1, "password_history": 1}) or {}
    history = db_user.get("password_history") or []
    check_history_or_raise(req.password, list(history) + [db_user.get("password_hash", "")], verify_password)
    await db.users.update_one(
        {"user_id": token_doc["user_id"]},
        {"$set": {
            "password_hash": hash_password(req.password),
            "password_history": push_password_history(history, db_user.get("password_hash", "")),
            "password_changed_at": datetime.now(timezone.utc).isoformat(),
            "must_change_password": False,
        }},
    )
    await db.password_reset_tokens.update_one({"token": req.token}, {"$set": {"used": True}})
    return {"message": "Password reset successful"}


# (Iter 379) Old weak /auth/change-password handler removed — the new
# policy-enforced version lives above, near /auth/password-policy.


@router.post("/auth/google-session")
async def google_session(req: GoogleSessionRequest, response: Response):
    # REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    async with httpx.AsyncClient() as http_client:
        resp = await http_client.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": req.session_id}
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid Google session")
    google_data = resp.json()
    email = google_data["email"].lower()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        user = {
            "user_id": user_id, "email": email,
            "name": google_data.get("name", email.split("@")[0]),
            "avatar": google_data.get("picture", ""), "role": "user",
            "language": "en", "password_hash": "",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(user)
    else:
        if not user.get("avatar") and google_data.get("picture"):
            await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"avatar": google_data["picture"]}})
            user["avatar"] = google_data["picture"]
    access_token = create_access_token(user["user_id"], email, user.get("token_version", 0))
    refresh_token_val = create_refresh_token(user["user_id"], user.get("token_version", 0))
    set_auth_cookies(response, access_token, refresh_token_val)
    return user_response(user)



@router.get("/users/profile")
async def get_profile(request: Request):
    return await get_current_user(request)

@router.put("/users/profile")
async def update_profile(req: UpdateProfileRequest, request: Request):
    user = await get_current_user(request)
    updates = {}
    if req.name is not None:
        updates["name"] = req.name
    if req.avatar is not None:
        updates["avatar"] = req.avatar
    if req.language is not None:
        updates["language"] = req.language
    if req.auto_reply_enabled is not None:
        updates["auto_reply_enabled"] = req.auto_reply_enabled
    if req.auto_reply_message is not None:
        updates["auto_reply_message"] = req.auto_reply_message
    # Iter 340 — Stammdaten-Erweiterung im Self-Profile.
    if req.first_name is not None:
        updates["first_name"] = req.first_name
    if req.last_name is not None:
        updates["last_name"] = req.last_name
    if req.display_name is not None:
        updates["display_name"] = req.display_name
    if req.phone is not None:
        updates["phone"] = req.phone
    if req.department is not None:
        updates["department"] = req.department
    # Auto-derive `name` from first/last if not explicitly provided.
    if ("first_name" in updates or "last_name" in updates) and req.name is None:
        fn = updates.get("first_name", user.get("first_name", ""))
        ln = updates.get("last_name", user.get("last_name", ""))
        combined = " ".join(p for p in [fn, ln] if p).strip()
        if combined:
            updates["name"] = combined
    if updates:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": updates})
        # Iter 340 — invalidate user_cache so /auth/me returns the new values instantly.
        try:
            from services import user_cache
            await user_cache.invalidate(user["user_id"])
        except Exception:
            pass
    updated = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    updated.pop("password_hash", None)
    return updated

@router.post("/users/avatar")
async def upload_avatar(request: Request, file: UploadFile = File(...)):
    user = await get_current_user(request)
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "png"
    if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
        raise HTTPException(status_code=400, detail="Invalid image format")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")
    path = f"{APP_STORAGE_PREFIX}/avatars/{user['user_id']}_{uuid.uuid4().hex[:6]}.{ext}"
    try:
        result = await asyncio.to_thread(put_object, path, data, file.content_type or "image/png")
        avatar_path = result.get("path", path)
        avatar_url = f"/api/users/avatar/{user['user_id']}"
        updated_at = datetime.now(timezone.utc).isoformat()
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {
                "avatar": avatar_url,
                "avatar_storage_path": avatar_path,
                "avatar_updated_at": updated_at,
            }},
        )
        # Iter 275 — invalidate user_cache so /auth/me returns the new avatar instantly
        try:
            from services import user_cache
            await user_cache.invalidate(user["user_id"])
        except Exception:
            pass
        return {"avatar": avatar_url, "avatar_updated_at": updated_at, "message": "Avatar uploaded"}
    except Exception as e:
        logger.error(f"Avatar upload failed: {e}")
        raise HTTPException(status_code=500, detail="Avatar upload failed")

@router.get("/users/avatar/{user_id}")
async def get_avatar(user_id: str):
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user or not user.get("avatar_storage_path"):
        raise HTTPException(status_code=404, detail="No avatar")
    try:
        data, ct = await asyncio.to_thread(get_object, user["avatar_storage_path"])
        return Response(content=data, media_type=ct)
    except Exception:
        raise HTTPException(status_code=500, detail="Avatar not available")




# ---------- DSGVO / GDPR Article 20 (Data Portability) ----------

@router.get("/users/me/export")
async def export_my_data(request: Request):
    """Export all personal data the user has ever created on the platform.
    Fulfills DSGVO Art. 20 (right to data portability). Returns a single JSON
    blob with every collection the user appears in.

    Iter 188 — switched to the centralised `services.gdpr_export.build_user_export`
    helper which covers the same surface but keeps section names stable for
    legacy tests via the optional `legacy` query parameter.
    """
    from services.gdpr_export import build_user_export
    user = await get_current_user(request)
    rich = await build_user_export(user)
    # Flatten the rich structure into the historical flat-keys schema for
    # backward compatibility with iter102 security tests + the existing
    # frontend ProfilePage.
    legacy = {
        "generated_at": rich["_meta"]["exported_at"],
        "profile": rich["profile"],
        "meetings_hosted": rich["meetings"]["hosted"],
        "meeting_participations": rich["meetings"]["participations"],
        "chat_conversations": [{"conversation_id": cid} for cid in rich["chat"]["conversation_ids"]],
        "chat_messages": rich["meetings"]["chat_messages"],
        "news_posts_authored": rich["news"]["authored_posts"],
        "news_comments": rich["news"]["comments"],
        "news_reactions": rich["news"]["reactions"],
        "news_read_receipts": rich["news"]["reads"],
        "news_question_votes": [],
        "news_poll_votes": [],
        "survey_responses": rich["surveys"]["responses"],
        "schedule_polls_created": rich["scheduling"]["polls"],
        "schedule_votes": rich["scheduling"]["votes"],
        "busy_slots": rich["calendar"]["busy_slots"],
        "focus_times": rich["meetings"]["focus_times"],
        "action_items_assigned": rich["meetings"]["action_items_assigned"],
        "notifications": [],  # not aggregated in service (would leak system messages)
        "audit_log_entries": rich["audit"]["permission_changes"],
        "push_subscriptions": rich["notifications"]["push_subscriptions"],
        # Iter 188 — also expose the new richer structure for clients that
        # want it. Older clients ignore unknown keys.
        "_iter188": rich,
    }
    logger.info(f"[dsgvo] user {user['user_id']} requested full data export")
    return legacy


@router.delete("/users/me")
async def delete_my_account(request: Request):
    """DSGVO Art. 17 (right to erasure). Pseudonymizes the user profile and
    scrubs personal identifiers from content that must stay for integrity
    reasons (e.g. a published news post the whole org has already read).
    Hard-deletes all private collections.
    """
    user = await get_current_user(request)
    uid = user["user_id"]

    await db.notifications.delete_many({"user_id": uid})
    await db.push_subscriptions.delete_many({"user_id": uid})
    await db.busy_slots.delete_many({"user_id": uid})
    await db.focus_times.delete_many({"user_id": uid})
    await db.chat_messages.delete_many({"sender_id": uid})
    await db.news_reactions.delete_many({"user_id": uid})
    await db.news_read_receipts.delete_many({"user_id": uid})
    await db.password_reset_tokens.delete_many({"user_id": uid})

    anon_name = f"Gelöschter Nutzer {uid[-6:]}"
    await db.news_comments.update_many({"author_id": uid}, {"$set": {"author_name": anon_name, "author_id": f"deleted_{uid[-6:]}"}})
    await db.news_posts.update_many({"author_id": uid}, {"$set": {"author_name": anon_name}})
    await db.meetings.update_many({"host_id": uid}, {"$set": {"host_name": anon_name}})

    await db.users.delete_one({"user_id": uid})
    logger.info(f"[dsgvo] user {uid} account deleted + data scrubbed")

    from fastapi import Response as FastResp
    resp = FastResp(content='{"message":"Account gelöscht"}', media_type="application/json")
    resp.set_cookie("access_token", "", httponly=True, secure=True, samesite="none", max_age=0, path="/")
    resp.set_cookie("refresh_token", "", httponly=True, secure=True, samesite="none", max_age=0, path="/")
    return resp
