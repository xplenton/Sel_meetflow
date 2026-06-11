"""License admin endpoints + middleware blocking 503 when license invalid."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from database import db
from dependencies import get_current_user
from services.license import check_license, get_current_status, is_license_active
from services.permissions import require_cap

router = APIRouter(tags=["license"])


# Endpoints jeder eingeloggte User darf sehen — der Admin-Banner im Frontend
# braucht die Info, damit User wissen, warum nichts geht.
@router.get("/license/status")
async def license_status():
    """Public-Endpoint — auch ohne Auth abrufbar.

    Iter 369 — Der Banner muss den Status anzeigen können, bevor sich der
    User einloggt (z. B. wenn die Lizenz ungültig ist und der User gar nicht
    erst durchgelassen wird). Daher kein `Depends(get_current_user)`.
    Liefert nur unkritische Metadaten.
    """
    return await get_current_status()


@router.post("/admin/license/recheck")
async def license_recheck(user=Depends(get_current_user)):
    """Admin: erzwingt sofortigen Lizenz-Check (statt 6 h zu warten).

    Nutzt die `admin.system`-Cap (gleiche wie System-Settings).
    """
    await require_cap(user, "admin.manage_integrations", db)
    fresh = await check_license(force=True)
    return fresh


# Iter 369 — Pfade, die auch ohne gültige Lizenz erreichbar bleiben müssen.
# Sonst kann der Admin sich nicht mal einloggen, um den Status zu sehen.
_LICENSE_BYPASS_PREFIXES = (
    "/api/auth/",          # Login + Refresh
    "/api/license/",       # Status-View
    "/api/admin/license/", # Recheck
    "/api/health",         # Liveness/Readiness probes
    "/health",             # Bare health alias
    "/docs",               # OpenAPI
    "/openapi.json",
    "/api/version",
)


class LicenseGuardMiddleware(BaseHTTPMiddleware):
    """Blockt API-Requests mit 503, wenn die Lizenz inaktiv ist.

    Bypass für Auth + Lizenz-Endpoints, damit der Admin sich einloggen
    und den Status reparieren kann.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path or ""
        # Nicht-API-Routen (Frontend-Build, statische Assets) immer
        # durchlassen — Reverse-Proxy entscheidet, ob React-App ausgeliefert
        # wird. Nur /api/* gating durch Lizenz.
        if not path.startswith("/api/"):
            return await call_next(request)
        # Whitelist-Bypass
        if any(path.startswith(p) for p in _LICENSE_BYPASS_PREFIXES):
            return await call_next(request)
        # Cache-Lookup (kein Server-Roundtrip pro Request!)
        try:
            active = await is_license_active()
        except Exception:
            # Bei Cache-/DB-Problem nicht alles blocken — fail-open.
            active = True
        if not active:
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Lizenz inaktiv — bitte Administrator kontaktieren.",
                    "code": "LICENSE_INVALID",
                },
            )
        return await call_next(request)
