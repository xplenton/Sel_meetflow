"""Admin routes for SSO configuration (Azure / Entra ID)."""
import os

import httpx
from fastapi import APIRouter, HTTPException, Request

from dependencies import get_current_user
from services import sso_azure
from services.permission_audit import log_caps_change
from services.permissions import require_cap
from database import db


router = APIRouter()


def _callback_url() -> str:
    origin = os.environ["FRONTEND_URL"].rstrip("/")
    return f"{origin}/api/auth/sso/azure/callback"


@router.get("/admin/sso/azure")
async def admin_get_azure_config(request: Request):
    admin = await get_current_user(request)
    await require_cap(admin, "admin.manage_integrations", db)
    cfg = await sso_azure.admin_view()
    cfg["redirect_uri"] = _callback_url()
    return cfg


@router.put("/admin/sso/azure")
async def admin_save_azure_config(request: Request):
    admin = await get_current_user(request)
    await require_cap(admin, "admin.manage_integrations", db)
    body = await request.json()
    result = await sso_azure.save_config(body, admin)
    result["redirect_uri"] = _callback_url()
    await log_caps_change(
        actor=admin, target_user_id="",
        action="sso_config_update",
        details={
            "provider": "azure",
            "enabled": result["enabled"],
            "tenant_id_set": bool(result.get("tenant_id")),
            "client_id_set": bool(result.get("client_id")),
            "secret_present": result.get("has_secret", False),
            "allowed_domains": result.get("allowed_domains") or [],
        },
        category="integrations", request=request,
    )
    return result


@router.post("/admin/sso/azure/test")
async def admin_test_azure_config(request: Request):
    """Validate the saved config by hitting Microsoft's OIDC discovery
    endpoint for the configured tenant. Does NOT verify the client secret
    (that only succeeds during the actual user login)."""
    admin = await get_current_user(request)
    await require_cap(admin, "admin.manage_integrations", db)
    cfg = await sso_azure.get_raw_config() or {}
    tenant = (cfg.get("tenant_id") or "").strip()
    client_id = (cfg.get("client_id") or "").strip()
    if not tenant or not client_id or not cfg.get("client_secret_enc"):
        raise HTTPException(status_code=400,
                            detail="Konfiguration unvollständig (Tenant ID, Client ID, Client Secret erforderlich)")
    url = f"https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Verbindung zu Microsoft fehlgeschlagen: {e}")
    if resp.status_code != 200:
        raise HTTPException(status_code=400,
                            detail=f"Tenant ID ungültig (Microsoft antwortete mit {resp.status_code})")
    data = resp.json()
    return {
        "ok": True,
        "issuer": data.get("issuer"),
        "authorization_endpoint": data.get("authorization_endpoint"),
        "token_endpoint": data.get("token_endpoint"),
        "redirect_uri": _callback_url(),
    }
