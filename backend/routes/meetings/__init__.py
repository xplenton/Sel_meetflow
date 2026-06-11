from fastapi import APIRouter
from .core import router as core_router
from .ops import router as ops_router
from .reports import router as reports_router
from .live import router as live_router

router = APIRouter()
router.include_router(core_router)
router.include_router(ops_router)
router.include_router(reports_router)
router.include_router(live_router)
