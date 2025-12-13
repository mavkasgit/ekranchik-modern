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
from app.api.websockets import router as websocket_router
from app.services.excel_watcher import excel_watcher
from app.services.ftp_poller import ftp_poller
from app.services.websocket_manager import websocket_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup/shutdown events.
    Starts background services: ExcelWatcher, FTPPoller
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
    
    # Start FTPPoller
    if settings.FTP_HOST:
        await ftp_poller.start()
        logger.info("[STARTUP] FTPPoller started")
    else:
        logger.warning("[STARTUP] FTP not configured, FTPPoller not started")
    
    yield
    
    # Shutdown
    logger.info("[SHUTDOWN] Stopping services...")
    
    # Stop background services
    excel_watcher.stop()
    await ftp_poller.stop()
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
app.include_router(websocket_router)

# Mount static files
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "services": {
            "excel_watcher": excel_watcher.is_running,
            "ftp_poller": ftp_poller.is_running,
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
