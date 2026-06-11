from fastapi import APIRouter
from .posts import router as posts_router
from .workflow import router as workflow_router
from .push import router as push_router

router = APIRouter()
router.include_router(posts_router)
router.include_router(workflow_router)
router.include_router(push_router)
