"""
FastAPI application factory and main entry point.
"""
import logging
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routes import router
from app.services.context import get_context_manager
from app import __version__

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - handles startup/shutdown."""
    # Startup
    logger.info(f"Starting Wayland AI Companion Server v{__version__}")
    
    settings = get_settings()
    logger.info(f"Ollama URL: {settings.ollama_base_url}")
    logger.info(f"Vision model: {settings.vision_model}")
    logger.info(f"Reasoning model: {settings.reasoning_model}")
    
    # Initialize context manager (loads personas and todos)
    try:
        context_mgr = await get_context_manager()
        logger.info("Context manager initialized")
    except Exception as e:
        logger.error(f"Failed to initialize context manager: {e}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Wayland AI Companion Server")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    
    app = FastAPI(
        title="Wayland AI Desktop Companion",
        description="A context-aware AI companion for Arch Linux / Wayland desktops",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )
    
    # CORS middleware (restrictive by default)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://localhost"],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["X-API-Key", "Content-Type"],
    )
    
    # Include routes
    app.include_router(router, prefix="/api/v1")
    
    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        ssl_certfile=settings.ssl_certfile,
        ssl_keyfile=settings.ssl_keyfile,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info"
    )
