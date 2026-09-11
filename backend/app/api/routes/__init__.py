# API Routes
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.catalog import router as catalog_router
from app.api.routes.signal import router as signal_router

__all__ = [
    "dashboard_router",
    "catalog_router",
    "signal_router",
]
