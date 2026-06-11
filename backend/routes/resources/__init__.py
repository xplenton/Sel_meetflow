"""
Resources router package — combines bookings/catering/invoices/admin into a single APIRouter.
Backward-compat: `from routes.resources import router` still works.
"""
from fastapi import APIRouter

from .bookings import router as bookings_router
from .catering import router as catering_router
from .invoices import router as invoices_router
from .invoice_tracking import router as invoice_tracking_router
from .invoices_config import router as invoices_config_router
from .admin import router as admin_router
from .office_days import router as office_days_router

router = APIRouter()
router.include_router(bookings_router)
router.include_router(catering_router)
router.include_router(invoices_router)
router.include_router(invoice_tracking_router)
router.include_router(invoices_config_router)
router.include_router(admin_router)
router.include_router(office_days_router)

__all__ = ["router"]
