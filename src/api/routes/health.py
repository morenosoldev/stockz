"""Health check endpoints for service monitoring.

Provides endpoints to check service health, database connectivity,
and system status.
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.dependencies import get_app_config, get_db
from src.ops.config import Config
from src.ops.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    timestamp: str
    version: str
    database: str
    checks: dict[str, Any] | None = None


class DetailedHealthResponse(BaseModel):
    """Detailed health check response with system info."""

    status: str
    timestamp: str
    version: str
    database: dict[str, Any]
    system: dict[str, Any]


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Basic health check",
    description="Returns basic service health status",
)
async def health_check(
    db: Session = Depends(get_db),
    config: Config = Depends(get_app_config),
) -> HealthResponse:
    """Basic health check endpoint.

    Returns:
        Basic health status with timestamp and database connectivity
    """
    # Check database connection
    db_status = "connected"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = "disconnected"
        logger.error("Database health check failed", extra={"error": str(e)})

    return HealthResponse(
        status="healthy" if db_status == "connected" else "degraded",
        timestamp=datetime.now(UTC).isoformat(),
        version=config.app.version,
        database=db_status,
    )


@router.get(
    "/health/detailed",
    response_model=DetailedHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Detailed health check",
    description="Returns detailed service health with database and system information",
)
async def detailed_health_check(
    db: Session = Depends(get_db),
    config: Config = Depends(get_app_config),
) -> DetailedHealthResponse:
    """Detailed health check with system information.

    Returns:
        Detailed health status including database version, connection pool,
        and system metrics
    """
    # Database checks
    db_info = {
        "status": "unknown",
        "version": None,
        "connection_pool": {
            "size": None,
            "checked_out": None,
        },
    }

    try:
        # Get database version (handle both PostgreSQL and SQLite)
        try:
            result = db.execute(text("SELECT version()"))  # PostgreSQL
        except Exception:
            result = db.execute(text("SELECT sqlite_version()"))  # SQLite

        version_row = result.fetchone()
        if version_row:
            db_info["version"] = str(version_row[0])
        db_info["status"] = "connected"

        # Get connection pool stats (if available)
        try:
            bind = db.get_bind()
            # Only Engine has pool attribute, not Connection
            if hasattr(bind, "pool"):
                pool = bind.pool
                # Handle both callable and property versions of size/checked_out
                if hasattr(pool, "size") and hasattr(pool, "checkedout"):
                    pool_size = pool.size() if callable(pool.size) else pool.size
                    pool_checkedout = (
                        pool.checkedout() if callable(pool.checkedout) else pool.checkedout
                    )
                    if isinstance(db_info["connection_pool"], dict):
                        db_info["connection_pool"]["size"] = pool_size
                        db_info["connection_pool"]["checked_out"] = pool_checkedout
        except Exception:
            # Pool stats not available (e.g., SQLite)
            pass

    except Exception as e:
        db_info["status"] = "disconnected"
        db_info["error"] = str(e)
        logger.error("Detailed database health check failed", extra={"error": str(e)})

    # System info
    system_info = {
        "app_name": config.app.name,
        "version": config.app.version,
        "debug_mode": config.app.debug,
        "log_level": config.app.log_level,
    }

    overall_status = "healthy" if db_info["status"] == "connected" else "degraded"

    return DetailedHealthResponse(
        status=overall_status,
        timestamp=datetime.now(UTC).isoformat(),
        version=config.app.version,
        database=db_info,
        system=system_info,
    )


@router.get(
    "/health/ready",
    status_code=status.HTTP_200_OK,
    summary="Readiness check",
    description="Kubernetes-style readiness probe - returns 200 if ready to serve traffic",
)
async def readiness_check(
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Readiness probe for Kubernetes/container orchestration.

    Returns 200 if service is ready to accept traffic, 503 otherwise.

    Returns:
        Simple ready status
    """
    try:
        # Check database is accessible
        db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        logger.error("Readiness check failed", extra={"error": str(e)})
        return {"status": "not ready", "reason": str(e)}


@router.get(
    "/health/live",
    status_code=status.HTTP_200_OK,
    summary="Liveness check",
    description="Kubernetes-style liveness probe - returns 200 if service is alive",
)
async def liveness_check() -> dict[str, str]:
    """Liveness probe for Kubernetes/container orchestration.

    Returns 200 if service is alive (doesn't check dependencies).

    Returns:
        Simple alive status
    """
    return {"status": "alive", "timestamp": datetime.now(UTC).isoformat()}
