"""Bookings sub-package — split out of the monolithic bookings.py in iter 347.

Layout:
  - `crud.py`      : create / read / update / cancel + conflict-check endpoint
  - `approval.py`  : approve, pending-count, check-in/out, auto-release
  - `series.py`    : recurring + combo (multi-sub-room) bookings
  - `reporting.py` : damage reports + slot suggestions

The catering attachment pipeline that `create_booking` triggers lives in
`services/catering_request_factory.py` (extracted in iter 348).

The combined `router` re-exports endpoints under the same paths as before;
no API URL changes vs. iter 346.
"""
from fastapi import APIRouter

from .crud import router as crud_router
from .approval import router as approval_router
from .series import router as series_router
from .reporting import router as reporting_router

router = APIRouter()
router.include_router(crud_router)
router.include_router(approval_router)
router.include_router(series_router)
router.include_router(reporting_router)

__all__ = ["router"]
