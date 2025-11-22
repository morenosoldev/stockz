"""FastAPI application initialization and configuration.

Main entry point for the Recover-Bot API service.
Includes middleware, exception handlers, and route registration.
"""

# CRITICAL: Load .env BEFORE any imports that use get_config()
# This ensures environment variables are available when modules initialize
from dotenv import load_dotenv

load_dotenv()

# Now safe to import modules that call get_config() at module level
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.routes import candidates, chat, health, metrics, runs, scan, streaming
from src.ops.config import get_config
from src.ops.logging import get_logger

# Suppress noisy third-party HTTP client logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager for startup/shutdown events.

    Handles:
    - Startup: Initialize connections, load strategies, etc.
    - Shutdown: Close connections, cleanup resources
    """
    # Startup
    logger.info("Starting Recover-Bot API service")
    config = get_config()
    logger.info(
        "Application configured",
        extra={
            "app_name": config.app.name,
            "version": config.app.version,
            "debug": config.app.debug,
            "environment": "development" if config.app.debug else "production",
        },
    )

    # Structlog SSE processor is already configured during logging setup
    logger.info("Real-time SSE streaming ready (in-memory stats tracking)")

    # TODO: Initialize database connection pool
    # TODO: Load and register strategies
    # TODO: Initialize cache

    yield

    # Shutdown
    logger.info("Shutting down Recover-Bot API service")
    # TODO: Close database connections
    # TODO: Flush cache
    # TODO: Cancel background tasks


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    config = get_config()

    app = FastAPI(
        title="Recover-Bot API",
        description="Stock recovery candidate detection service - read-only analysis for drop recovery strategies",
        version=config.app.version,
        debug=config.app.debug,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: Configure from environment in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request logging middleware
    @app.middleware("http")
    async def log_requests(request: Request, call_next: Any) -> Response:
        """Log all HTTP requests with timing information."""
        start_time = datetime.now(UTC)

        # Log request
        logger.info(
            "Request started",
            extra={
                "method": request.method,
                "path": request.url.path,
                "query": str(request.url.query) if request.url.query else None,
                "client": request.client.host if request.client else None,
            },
        )

        # Process request
        response: Response = await call_next(request)

        # Calculate duration
        duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

        # Log response
        logger.info(
            "Request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )

        return response

    # Exception handlers
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Handle HTTP exceptions with structured logging."""
        logger.warning(
            "HTTP exception",
            extra={
                "path": request.url.path,
                "status_code": exc.status_code,
                "detail": exc.detail,
            },
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.status_code,
                    "message": exc.detail,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle request validation errors."""
        # Convert validation errors to JSON-serializable format
        errors = []
        for error in exc.errors():
            error_dict = {
                "field": " -> ".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
            # Only include input if it's serializable
            if "input" in error:
                try:
                    import json

                    json.dumps(error["input"])
                    error_dict["input"] = error["input"]
                except (TypeError, ValueError):
                    error_dict["input"] = str(error["input"])
            errors.append(error_dict)

        logger.warning(
            "Validation error",
            extra={
                "path": request.url.path,
                "errors": errors,
            },
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": 422,
                    "message": "Request validation failed",
                    "details": errors,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle unexpected exceptions."""
        logger.error(
            "Unhandled exception",
            extra={
                "path": request.url.path,
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
            exc_info=True,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": 500,
                    "message": "Internal server error",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            },
        )

    # Register routes
    app.include_router(health.router, prefix="/v1", tags=["Health"])
    app.include_router(scan.router, prefix="/v1", tags=["Scan"])
    app.include_router(streaming.router, prefix="/v1", tags=["Streaming"])
    app.include_router(chat.router, prefix="/v1", tags=["Chat"])
    app.include_router(candidates.router, prefix="/v1", tags=["Candidates"])
    app.include_router(runs.router, prefix="/v1", tags=["Runs"])
    app.include_router(metrics.router, prefix="/v1", tags=["Metrics"])

    # Root redirect to docs
    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        """Redirect root to API documentation."""
        return {
            "message": "Recover-Bot API",
            "version": config.app.version,
            "docs": "/docs",
            "health": "/v1/health",
        }

    return app


# Create application instance
app = create_app()
