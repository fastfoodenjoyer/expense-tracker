"""Bot handlers."""

from aiogram import Router

from .start import router as start_router
from .import_pdf import router as import_router
from .export import router as export_router
from .reports import router as reports_router
from .categories import router as categories_router
from .settings import router as settings_router


def setup_routers() -> Router:
    """Setup and return main router with all handlers."""
    router = Router()
    router.include_router(start_router)
    router.include_router(import_router)
    router.include_router(export_router)
    router.include_router(reports_router)
    router.include_router(categories_router)
    router.include_router(settings_router)
    return router
