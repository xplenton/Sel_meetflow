"""routes/admin/ — admin endpoints, split into users / permissions / system in iter 261.

Backward-compat: `from routes.admin import router` still works.
"""
from fastapi import APIRouter

from .users import router as users_router
from .permissions import router as permissions_router
from .system import router as system_router
from .sso import router as sso_router
from .maintenance import router as maintenance_router

router = APIRouter()
router.include_router(users_router)
router.include_router(permissions_router)
router.include_router(system_router)
router.include_router(sso_router)
router.include_router(maintenance_router)

__all__ = ["router"]
