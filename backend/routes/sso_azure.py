"""Public auth routes for Azure AD / Entra ID Single Sign-On.

Flow:
    1. Frontend redirects to GET /api/auth/sso/azure/login
    2. Backend creates PKCE verifier + random state, stores them in a
       short-lived (10 min) HttpOnly cookie, redirects to Microsoft.
    3. Microsoft redirects back to /api/auth/sso/azure/callback?code=...&state=...
    4. Backend validates state, exchanges code for tokens, fetches user
       claims from the id_token, JIT-provisions/looks up the local user,
       sets the regular MeetFlow session cookies and redirects to /schedule.
"""
import os
import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from database import logger
from dependencies import create_access_token, create_refresh_token, set_auth_cookies
from services import sso_azure
from services.permission_audit import log_caps_change

router = APIRouter()

STATE_COOKIE = "mf_sso_azure_state"
VERIFIER_COOKIE = "mf_sso_azure_verifier"
COOKIE_MAX_AGE = 600  # 10 min for the in-flight OAuth dance


def _callback_url() -> str:
    """Backend-public callback URL — same origin as FRONTEND_URL (ingress
    routes /api/* to backend, /* to frontend on this host)."""
    origin = os.environ["FRONTEND_URL"].rstrip("/")
    return f"{origin}/api/auth/sso/azure/callback"


def _frontend_origin() -> str:
    return os.environ["FRONTEND_URL"].rstrip("/")


@router.get("/auth/sso/azure/status")
async def azure_status():
    return await sso_azure.public_status()


@router.get("/auth/sso/azure/login")
async def azure_login():
    cfg = await sso_azure.get_config_for_login()
    if not cfg:
        # Bounce back to login with a friendly error
        return RedirectResponse(f"{_frontend_origin()}/login?sso_error=disabled", status_code=302)
    state = secrets.token_urlsafe(24)
    verifier, challenge = sso_azure.make_pkce()
    url = sso_azure.build_authorize_url(cfg, _callback_url(), state, challenge)
    resp = RedirectResponse(url, status_code=302)
    # HttpOnly so JS can't read; SameSite=Lax so it survives the Microsoft round-trip.
    resp.set_cookie(STATE_COOKIE, state, max_age=COOKIE_MAX_AGE,
                    httponly=True, secure=True, samesite="lax", path="/api/auth/sso/azure")
    resp.set_cookie(VERIFIER_COOKIE, verifier, max_age=COOKIE_MAX_AGE,
                    httponly=True, secure=True, samesite="lax", path="/api/auth/sso/azure")
    return resp


@router.get("/auth/sso/azure/callback")
async def azure_callback(request: Request, code: str | None = None, state: str | None = None,
                         error: str | None = None, error_description: str | None = None):
    if error:
        logger.warning(f"[sso-azure] provider returned error: {error} - {error_description}")
        return RedirectResponse(
            f"{_frontend_origin()}/login?sso_error={error}", status_code=302,
        )
    if not code or not state:
        return RedirectResponse(f"{_frontend_origin()}/login?sso_error=missing_params", status_code=302)

    cookie_state = request.cookies.get(STATE_COOKIE) or ""
    verifier = request.cookies.get(VERIFIER_COOKIE) or ""
    if not cookie_state or cookie_state != state or not verifier:
        return RedirectResponse(f"{_frontend_origin()}/login?sso_error=state_mismatch", status_code=302)

    cfg = await sso_azure.get_config_for_login()
    if not cfg:
        return RedirectResponse(f"{_frontend_origin()}/login?sso_error=disabled", status_code=302)

    try:
        tokens = await sso_azure.exchange_code(cfg, code, _callback_url(), verifier)
        claims = sso_azure.decode_id_token(tokens.get("id_token", ""))
        user = await sso_azure.jit_provision_user(claims, cfg.get("allowed_domains") or [])
    except RuntimeError as e:
        msg = str(e).replace(" ", "+")
        return RedirectResponse(f"{_frontend_origin()}/login?sso_error={msg}", status_code=302)
    except Exception as e:
        logger.exception(f"[sso-azure] callback fatal: {e}")
        return RedirectResponse(f"{_frontend_origin()}/login?sso_error=server_error", status_code=302)

    # Issue MeetFlow session cookies.
    access = create_access_token(user["user_id"], user["email"], user.get("token_version", 0))
    refresh = create_refresh_token(user["user_id"], user.get("token_version", 0))
    resp = RedirectResponse(f"{_frontend_origin()}/schedule", status_code=302)
    set_auth_cookies(resp, access, refresh)
    # Clean up the in-flight cookies
    resp.delete_cookie(STATE_COOKIE, path="/api/auth/sso/azure")
    resp.delete_cookie(VERIFIER_COOKIE, path="/api/auth/sso/azure")

    # Audit: SSO login
    try:
        await log_caps_change(
            actor=user, target_user_id=user["user_id"],
            action="sso_login",
            details={"provider": "azure", "email": user["email"]},
            category="session", request=request,
        )
    except Exception:
        pass
    return resp


@router.post("/auth/sso/azure/logout-redirect")
async def azure_logout_redirect_info():
    """Return the Microsoft federated logout URL the SPA can navigate to
    after clearing local cookies. Optional convenience for SSO-only users."""
    cfg = await sso_azure.get_raw_config()
    if not cfg or not cfg.get("enabled") or not cfg.get("tenant_id"):
        raise HTTPException(status_code=404, detail="SSO ist nicht konfiguriert")
    origin = _frontend_origin()
    url = (
        f"https://login.microsoftonline.com/{cfg['tenant_id']}/oauth2/v2.0/logout"
        f"?post_logout_redirect_uri={origin}/login"
    )
    return {"url": url}
