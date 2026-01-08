"""
Ekranchik Modern - FastAPI Application Entry Point
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.routes import dashboard_router, catalog_router, analysis_router, signal_router
from app.api.routes.opcua import router as opcua_router
from app.api.websockets import router as websocket_router
from app.services.excel_watcher import excel_watcher
from app.services.opcua_poller import opcua_poller
from app.services.websocket_manager import websocket_manager
from app.services.hanger_service import hanger_service

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
    "app.services.ftp_service",  # FTP service - disabled
    "app.services.websocket_manager",  # WebSocket broadcasts - too verbose
]:
    logging.getLogger(noisy_logger).setLevel(logging.ERROR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup/shutdown events.
    Starts background services: ExcelWatcher, OPCUAPoller
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
    
    # OPC UA Poller - enabled by default for real-time hanger tracking
    if settings.OPCUA_ENABLED:
        await opcua_poller.start()
        opcua_poller.load_events_from_unload_service()
        logger.info("[STARTUP] OPCUAPoller started")
    else:
        logger.info("[STARTUP] OPCUAPoller disabled (OPCUA_ENABLED=False)")
    
    # Load hanger service cache
    logger.info(f"[STARTUP] Hanger Service loaded with {len(hanger_service.get_all_hangers())} cached hangers")
    
    # Load unload service
    from app.services.unload_service import unload_service
    logger.info(f"[STARTUP] Unload Service loaded with {len(unload_service.events)} events")
    
    yield
    
    # Shutdown
    logger.info("[SHUTDOWN] Stopping services...")
    
    # Stop background services
    excel_watcher.stop()
    if opcua_poller.is_running:
        await opcua_poller.stop()
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
            "opcua_poller": opcua_poller.is_running,
            "websocket_clients": websocket_manager.connection_count
        }
    }


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Ekranchik Modern API",
        "docs": "/docs",
        "health": "/health"
    }
