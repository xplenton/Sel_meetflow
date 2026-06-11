"""
Resources/admin router package.

Iter 318 — Split out of the legacy 1477-line monolith `admin.py` into
focused sub-modules. The combined `router` is exposed here so existing
imports (`from .admin import router`) keep working unchanged.

Sub-modules:
  - crud           — Resource CRUD + image/QR + maintenance + small misc
  - floorplans     — Floorplan CRUD + items + blackouts + utilization-by-sub
  - master_data    — Cost centers + accounts (+ legacy migration helper)
  - analytics      — Dashboards, snapshot, occupancy, no-show, by-department,
                     in-office, driving-log, Outlook stub, deprecated licenses,
                     upload-config
  - demo_seed      — POST /resources-seed-demo (idempotent demo data)
"""
from fastapi import APIRouter

from .crud import router as crud_router
from .floorplans import router as floorplans_router
from .master_data import router as master_data_router
from .analytics import router as analytics_router
from .demo_seed import router as demo_seed_router

router = APIRouter(tags=["resources-admin"])
router.include_router(crud_router)
router.include_router(floorplans_router)
router.include_router(master_data_router)
router.include_router(analytics_router)
router.include_router(demo_seed_router)

__all__ = ["router"]
