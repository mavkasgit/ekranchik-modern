"""
Ekranchik Modern - FastAPI Application Entry Point
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup/shutdown events.
    Starts background services: ExcelWatcher, FTPPoller, TelegramBot
    """
    # Startup
    print(f"[STARTUP] Ekranchik Modern v1.0")
    print(f"[STARTUP] Environment: {settings.ENVIRONMENT}")
    
    # TODO: Initialize database
    # TODO: Start ExcelWatcher
    # TODO: Start FTPPoller  
    # TODO: Start TelegramBot
    
    yield
    
    # Shutdown
    print("[SHUTDOWN] Stopping services...")
    # TODO: Stop background services


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

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": "1.0.0"}


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Ekranchik Modern API",
        "docs": "/docs",
        "health": "/health"
    }
