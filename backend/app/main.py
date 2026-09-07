"""
Ekranchik Modern - FastAPI Application Entry Point
"""
import os
import time
try:
    os.environ['TZ'] = 'Europe/Moscow'
    time.tzset()
except AttributeError:
    # time.tzset() is not available on Windows
    pass

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.routes import dashboard_router, catalog_router, analysis_router, signal_router
from app.api.routes.opcua import router as opcua_router
from app.api.websockets import router as websocket_router
from app.services.excel_watcher import excel_watcher
from app.services.line_monitor import line_monitor
from app.services.opcua_service import opcua_service
from app.services.websocket_manager import websocket_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Отключаем спам логов от сетевых библиотек
for noisy_logger in [
    "asyncio", "aiohttp", "aiohttp.access",
    "httpcore", "httpx",
    "websockets", "websockets.client", "websockets.server",
    "uvicorn", "uvicorn.access", "uvicorn.error",
    "watchfiles", "watchfiles.main",
    "app.services.websocket_manager",  # WebSocket broadcasts - too verbose
]:
    logging.getLogger(noisy_logger).setLevel(logging.ERROR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup/shutdown events.
    Starts background services: ExcelWatcher, LineMonitor
    """
    # Startup
    logger.info(f"[STARTUP] Ekranchik Modern v1.0")
    logger.info(f"[STARTUP] Environment: {settings.ENVIRONMENT}")
    
    # Start ExcelWatcher
    if settings.excel_path and settings.excel_path.exists():
        excel_watcher.start()
        logger.info("[STARTUP] ExcelWatcher started")
    else:
        logger.warning("[STARTUP] Excel path not configured, ExcelWatcher not started")
    
    # OPC UA Service - пакетное чтение с защитой от зомби-сессий
    if settings.OPCUA_ENABLED:
        await opcua_service.start()
        logger.info("[STARTUP] OPC UA Service started")
        
        # Line Monitor - unified OPC UA monitoring
        await line_monitor.start()
        logger.info("[STARTUP] LineMonitor started")
    else:
        logger.info("[STARTUP] OPC UA disabled (OPCUA_ENABLED=False)")
    
    yield
    
    # Shutdown
    logger.info("[SHUTDOWN] Stopping services...")
    
    # Stop background services
    excel_watcher.stop()
    if line_monitor.is_running:
        await line_monitor.stop()
    if opcua_service.is_connected:
        await opcua_service.stop()
    await websocket_manager.close_all()
    
    logger.info("[SHUTDOWN] All services stopped")


app = FastAPI(
    title="Ekranchik Modern API",
    description="Production monitoring system for KTM-2000 factory",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(dashboard_router, prefix="/api")
app.include_router(catalog_router, prefix="/api")
app.include_router(analysis_router, prefix="/api")
app.include_router(signal_router, prefix="/api")
app.include_router(opcua_router, prefix="/api")
app.include_router(websocket_router)

# Mount static files - use project root static folder
# In development: ../static (relative to backend folder)
# In Docker: /app/static (mounted volume)
static_dir = settings.STATIC_PATH
if static_dir and static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    logger.info(f"[STARTUP] Static files mounted from: {static_dir}")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "services": {
            "excel_watcher": excel_watcher.is_running,
            "line_monitor": line_monitor.is_running,
            "websocket_clients": websocket_manager.connection_count
        }
    }


# Full mode (ADR 0002): serve frontend/dist SPA on the same port.
# Order matters: api (/api) -> ws (/ws) -> static (/static) -> health/docs
# are registered above and win; SPA mount + fallback only handle the rest.
# The catch-all is registered BEFORE the "/" mount on purpose: a Mount on "/"
# matches every path and answers 404 for missing files itself, so a fallback
# registered after it would never be reached for nested SPA routes.
_dist_dir = settings.FRONTEND_DIST_PATH
_index_html = _dist_dir / "index.html" if _dist_dir is not None else None
# SPA mode only when dist contains index.html; an empty/partial dist (e.g. failed
# frontend build) keeps the legacy JSON root instead of serving 404s everywhere.
if _dist_dir is not None and _index_html is not None and _index_html.is_file():
    _dist_resolved = _dist_dir.resolve()
    # Prefixes owned by routers/mounts/docs above: never serve index.html for them.
    _SPA_EXCLUDED_PREFIXES = frozenset({"api", "ws", "static", "health", "docs", "redoc", "openapi.json"})


    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        """Serve dist files directly, fall back to index.html for SPA routes."""
        first_segment = full_path.split("/", 1)[0]
        if first_segment in _SPA_EXCLUDED_PREFIXES:
            raise HTTPException(status_code=404)
        if full_path:
            candidate = (_dist_dir / Path(full_path)).resolve()
            if _dist_resolved not in candidate.parents:
                raise HTTPException(status_code=404)
            if candidate.is_file():
                return FileResponse(str(candidate))
        if _index_html.is_file():
            return FileResponse(str(_index_html))
        raise HTTPException(status_code=404)


    app.mount("/", StaticFiles(directory=str(_dist_dir), html=True), name="spa")
    logger.info(f"[STARTUP] SPA mounted from: {_dist_dir}")
else:


    @app.get("/")
    async def root():
        """Root endpoint"""
        return {
            "message": "Ekranchik Modern API",
            "docs": "/docs",
            "health": "/health"
        }
