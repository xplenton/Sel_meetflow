"""Microsoft Entra ID (Azure AD) Single Sign-On.

OIDC Authorization-Code flow with PKCE. Config (tenant_id, client_id,
encrypted client_secret, enabled flag, optional button label) is stored in
MongoDB collection `sso_config` keyed by `provider="azure"`, so admins can
configure it through the Admin GUI without redeploying.

JIT provisioning: unknown emails are created with role="user". Existing
local accounts are matched by email and signed in (no automatic role
promotion). Local password login keeps working in parallel.
"""
import base64
import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
import jwt as pyjwt

from database import db, logger
from services.sso_crypto import decrypt, encrypt

PROVIDER = "azure"
GRAPH_SCOPE = "openid profile email User.Read offline_access"


# --------------------------- config helpers --------------------------- #

async def get_raw_config() -> dict | None:
    return await db.sso_config.find_one({"provider": PROVIDER}, {"_id": 0})


async def get_config_for_login() -> dict | None:
    """Return decrypted runtime config IF enabled, else None."""
    cfg = await get_raw_config()
    if not cfg or not cfg.get("enabled"):
        return None
    if not (cfg.get("tenant_id") and cfg.get("client_id") and cfg.get("client_secret_enc")):
        return None
    return {
        "tenant_id": cfg["tenant_id"],
        "client_id": cfg["client_id"],
        "client_secret": decrypt(cfg["client_secret_enc"]),
        "button_label": cfg.get("button_label") or "Mit Microsoft anmelden",
        "allowed_domains": cfg.get("allowed_domains") or [],
    }


async def public_status() -> dict:
    """Safe-to-expose status for the login page."""
    cfg = await get_raw_config()
    if not cfg or not cfg.get("enabled"):
        return {"enabled": False}
    ready = bool(cfg.get("tenant_id") and cfg.get("client_id") and cfg.get("client_secret_enc"))
    return {
        "enabled": ready,
        "button_label": cfg.get("button_label") or "Mit Microsoft anmelden",
    }


async def admin_view() -> dict:
    """Config view for the admin UI (secret masked)."""
    cfg = await get_raw_config() or {}
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "tenant_id": cfg.get("tenant_id", ""),
        "client_id": cfg.get("client_id", ""),
        "client_secret": "***" if cfg.get("client_secret_enc") else "",
        "has_secret": bool(cfg.get("client_secret_enc")),
        "button_label": cfg.get("button_label") or "Mit Microsoft anmelden",
        "allowed_domains": cfg.get("allowed_domains") or [],
        "updated_at": cfg.get("updated_at"),
        "updated_by": cfg.get("updated_by"),
    }


async def save_config(payload: dict, actor: dict) -> dict:
    """Upsert config. If payload['client_secret'] is empty OR starts with '***',
    keep the stored encrypted value (so masked round-trips don't wipe it).
    """
    existing = await get_raw_config() or {}
    raw_secret = (payload.get("client_secret") or "").strip()
    if raw_secret and not raw_secret.startswith("***"):
        secret_enc = encrypt(raw_secret)
    else:
        secret_enc = existing.get("client_secret_enc", "")

    # Sanitize allowed_domains -> list of lowercase strings, no empties
    domains_in = payload.get("allowed_domains") or []
    if isinstance(domains_in, str):
        domains_in = [d.strip() for d in domains_in.split(",")]
    allowed = [d.strip().lower() for d in domains_in if d and d.strip()]

    doc = {
        "provider": PROVIDER,
        "enabled": bool(payload.get("enabled", False)),
        "tenant_id": (payload.get("tenant_id") or "").strip(),
        "client_id": (payload.get("client_id") or "").strip(),
        "client_secret_enc": secret_enc,
        "button_label": (payload.get("button_label") or "").strip() or "Mit Microsoft anmelden",
        "allowed_domains": allowed,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": actor.get("email", ""),
    }
    await db.sso_config.update_one({"provider": PROVIDER}, {"$set": doc}, upsert=True)
    return await admin_view()


# --------------------------- OIDC flow -------------------------------- #

def _authority(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id}"


def make_pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    return verifier, challenge


def build_authorize_url(cfg: dict, redirect_uri: str, state: str, code_challenge: str) -> str:
    params = {
        "client_id": cfg["client_id"],
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": GRAPH_SCOPE,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{_authority(cfg['tenant_id'])}/oauth2/v2.0/authorize?{urlencode(params)}"


async def exchange_code(cfg: dict, code: str, redirect_uri: str, code_verifier: str) -> dict:
    """Exchange auth code for tokens. Returns the raw token response."""
    data = {
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "scope": GRAPH_SCOPE,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }
    url = f"{_authority(cfg['tenant_id'])}/oauth2/v2.0/token"
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            url, data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code != 200:
        logger.warning(f"[sso-azure] token exchange failed: {resp.status_code} {resp.text[:300]}")
        raise RuntimeError(f"Token-Tausch fehlgeschlagen ({resp.status_code})")
    return resp.json()


def decode_id_token(id_token: str) -> dict:
    """Decode without signature verification — we just exchanged it over HTTPS
    against Microsoft using our client_secret, so we trust the channel. For
    full signature validation, we'd fetch the JWKS from
    {authority}/discovery/v2.0/keys — left as a hardening step.
    """
    try:
        return pyjwt.decode(id_token, options={"verify_signature": False})
    except Exception as e:
        logger.warning(f"[sso-azure] id_token decode failed: {e}")
        raise RuntimeError("ID-Token ungültig")


async def jit_provision_user(claims: dict, allowed_domains: list[str]) -> dict:
    """Look up the user by email or create a new one (role=user)."""
    email = (claims.get("email") or claims.get("preferred_username") or "").lower().strip()
    if not email or "@" not in email:
        raise RuntimeError("Microsoft-Konto hat keine E-Mail-Adresse zurückgegeben")

    if allowed_domains:
        domain = email.split("@", 1)[1]
        if domain not in allowed_domains:
            raise RuntimeError(f"Diese E-Mail-Domain ({domain}) ist nicht freigeschaltet")

    user = await db.users.find_one({"email": email}, {"_id": 0})
    if user:
        if user.get("status") == "inactive":
            raise RuntimeError("Konto deaktiviert")
        return user

    user_id = f"user_{uuid.uuid4().hex[:12]}"
    name = claims.get("name") or email.split("@")[0]
    new_user = {
        "user_id": user_id,
        "email": email,
        "name": name,
        "role": "user",
        "avatar": "",
        "language": "de",
        "password_hash": "",  # SSO-only — no local password
        "sso_provider": PROVIDER,
        "sso_subject": claims.get("oid") or claims.get("sub"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "email_verified": True,  # Microsoft validated the email already
        "groups": [],
    }
    await db.users.insert_one(new_user)

    # Best-effort: drop the new user into the default Gast group (matches /auth/register flow)
    try:
        from routes.org_onboarding import assign_to_default_guest_group
        gid = await assign_to_default_guest_group(user_id)
        if gid:
            new_user["groups"] = [gid]
    except Exception:
        pass

    logger.info(f"[sso-azure] JIT-provisioned new user {email} ({user_id})")
    new_user.pop("_id", None)
    return new_user
