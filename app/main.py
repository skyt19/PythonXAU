"""
XAUUSD AI Farming HQ - Main Application Entry Point

This is the primary entry point for the Farming HQ trading system.
It initializes the FastAPI application, database, and core services.

SAFETY: This application is DEMO ONLY. Live trading is prohibited.
"""
import logging
import signal
import sys
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import config
from app import database
from app.database import DatabaseManager
from app.logging_config import setup_logging

# Setup logging before anything else
setup_logging(log_level=config.log_level, log_file=config.log_file)
logger = logging.getLogger(__name__)

# Global database manager
db_manager: Optional[DatabaseManager] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("=" * 70)
    logger.info("XAUUSD AI Farming HQ - Starting")
    logger.info("=" * 70)

    try:
        # Initialize database
        global db_manager
        logger.info("Initializing database...")
        db_manager = DatabaseManager(config.database_url)
        db_manager.create_tables()
        database.db_manager = db_manager
        logger.info("Database initialized successfully")

        # Create necessary directories
        logger.info("Creating directories...")
        config.create_directories()
        logger.info("Directories created")

        # Log configuration (with masked credentials)
        logger.info("Configuration:")
        masked_config = config.mask_credentials()
        for key in ['demo_only', 'dashboard_host', 'dashboard_port',
                    'mt5_server', 'mt5_symbol', 'database_url']:
            if key in masked_config:
                logger.info(f"  {key}: {masked_config[key]}")

        logger.info("=" * 70)
        logger.info("Farming HQ Ready")
        logger.info(f"Dashboard: http://{config.dashboard_host}:{config.dashboard_port}")
        logger.info("Execution: DISABLED (no execution module loaded)")
        logger.info("=" * 70)

        yield

    except Exception as e:
        logger.error(f"Failed to start application: {e}", exc_info=True)
        raise

    finally:
        logger.info("Shutting down...")
        if db_manager:
            try:
                db_manager.close()
                logger.info("Database closed")
            except Exception as e:
                logger.error(f"Error closing database: {e}")
            finally:
                database.db_manager = None
                db_manager = None
        logger.info("Shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="XAUUSD AI Farming HQ",
    description="HFM MetaTrader 5 Demo Forward Testing System",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Include API router
try:
    from app.dashboard.api import router as api_router
    app.include_router(api_router)
    logger.info("API router included")
except ImportError as e:
    logger.warning(f"Could not import API router: {e}")

try:
    from app.dashboard.forward_api import router as forward_router
    app.include_router(forward_router)
    logger.info("Forward-testing router included")
except ImportError as e:
    logger.warning(f"Could not import forward-testing router: {e}")


@app.get("/")
async def root():
    """Root endpoint with system information."""
    return {
        "service": "XAUUSD AI Farming HQ",
        "version": "1.0.0",
        "status": "operational",
        "demo_only": config.demo_only,
        "documentation": f"http://{config.dashboard_host}:{config.dashboard_port}/docs",
    }


@app.get("/health")
async def health():
    """
    Health check endpoint.

    Returns basic health status without checking external dependencies.
    """
    return {
        "status": "healthy",
        "service": "farming_hq",
        "demo_only": config.demo_only,
    }


@app.get("/status")
async def status():
    """
    Detailed status endpoint.

    Returns comprehensive system status including database and configuration.
    """
    # Check database connection
    db_status = "unknown"
    if db_manager:
        try:
            # Try to get a session to verify connection
            session = db_manager.get_session()
            session.close()
            db_status = "connected"
        except Exception as e:
            db_status = f"error: {str(e)}"
            logger.error(f"Database status check failed: {e}")
    else:
        db_status = "not_initialized"

    return {
        "service": "XAUUSD AI Farming HQ",
        "version": "1.0.0",
        "status": "operational",
        "demo_only": config.demo_only,
        "configuration": {
            "dashboard_host": config.dashboard_host,
            "dashboard_port": config.dashboard_port,
            "symbol": config.mt5_symbol,
            "timeframe": config.timeframe,
            "server": config.mt5_server,
        },
        "database": {
            "status": db_status,
            "url": config.database_url.split("///")[0] + ":///" + "***" if ":///" in config.database_url else "***",
        },
        "execution": {
            "enabled": False,
            "reason": "No execution module loaded (Phase 1)",
        },
        "components": {
            "config": "loaded",
            "database": "initialized" if db_manager else "not_initialized",
            "logging": "configured",
            "account_guard": "available",
            "mt5_client": "available",
            "strategy": "not_loaded",
            "risk_manager": "not_loaded",
            "ml_model": "not_loaded",
        }
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler to catch unhandled errors."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if config.debug_mode else "An error occurred",
        }
    )


def handle_shutdown_signal(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}, shutting down...")
    sys.exit(0)


def main():
    """
    Run the application.

    This function starts the Uvicorn server with the configured settings.
    """
    # Register signal handlers
    signal.signal(signal.SIGINT, handle_shutdown_signal)
    signal.signal(signal.SIGTERM, handle_shutdown_signal)

    try:
        # Verify configuration
        if not config.demo_only:
            logger.error("CRITICAL: DEMO_ONLY is False. Application will not start.")
            sys.exit(1)

        # Start server
        logger.info(f"Starting server on {config.dashboard_host}:{config.dashboard_port}")
        uvicorn.run(
            "app.main:app",
            host=config.dashboard_host,
            port=config.dashboard_port,
            log_level="info",
            access_log=False,
            reload=False,
        )
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
