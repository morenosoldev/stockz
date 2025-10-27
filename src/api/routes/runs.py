"""Run metadata API endpoints.

This module provides endpoints for querying scan run metadata:
- GET /runs/{date}: List all runs for a specific date
- GET /runs/{run_id}: Get detailed information about a specific run

All endpoints return run metadata with timing, status, and performance metrics.
"""

from datetime import date as date_type
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.ops.logging import get_logger
from src.storage.models import Run

logger = get_logger(__name__)

router = APIRouter()


# ========================================
# Pydantic Models
# ========================================


class RunItem(BaseModel):
    """Individual run item in list response."""

    model_config = ConfigDict(from_attributes=True)

    run_id: str = Field(..., description="UUID of the scan run")
    run_date: date_type = Field(..., description="Market date of the scan")
    strategy: str = Field(..., description="Strategy name")
    status: str = Field(..., description="Run status: pending, running, completed, failed")
    duration_seconds: int | None = Field(None, description="Scan duration in seconds")
    tickers_processed: int | None = Field(None, description="Number of tickers processed")
    candidates_found: int | None = Field(None, description="Number of candidates found")
    errors_count: int = Field(default=0, description="Number of errors encountered")


class RunListResponse(BaseModel):
    """Response model for run listing."""

    runs: list[RunItem] = Field(..., description="List of runs")
    total: int = Field(..., ge=0, description="Total number of runs")
    date: date_type = Field(..., description="Queried date")


class RunDetailResponse(BaseModel):
    """Response model for detailed run view."""

    model_config = ConfigDict(from_attributes=True)

    run_id: str = Field(..., description="UUID of the scan run")
    run_date: date_type = Field(..., description="Market date of the scan")
    strategy: str = Field(..., description="Strategy name")
    status: str = Field(..., description="Run status: pending, running, completed, failed")

    # Timing
    started_at: str | None = Field(None, description="Scan start time (ISO 8601)")
    completed_at: str | None = Field(None, description="Scan completion time (ISO 8601)")
    duration_seconds: int | None = Field(None, description="Scan duration in seconds")

    # Metrics
    tickers_processed: int | None = Field(None, description="Number of tickers processed")
    candidates_found: int | None = Field(None, description="Number of candidates found")
    errors_count: int = Field(default=0, description="Number of errors encountered")

    # Error handling
    error_details: dict[Any, Any] | None = Field(None, description="Detailed error information")


# ========================================
# Endpoints
# ========================================


@router.get("/runs/by-date/{date}", response_model=RunListResponse)
async def list_runs_by_date(
    date: date_type,
    db: Session = Depends(get_db),
) -> RunListResponse:
    """List all scan runs for a specific date.

    Returns all runs (across all strategies) that were executed for the given market date.
    This includes runs in any status: pending, running, completed, or failed.

    **Use cases**:
    - Check which strategies ran on a specific date
    - Monitor scan execution status
    - Troubleshoot failed scans
    - Track scan performance over time

    **Response**:
    - Returns runs sorted by start time (most recent first)
    - Includes timing and performance metrics when available
    - Shows error details for failed runs
    """
    logger.info("Listing runs by date", extra={"date": str(date)})

    # Query all runs for the date
    runs = db.query(Run).filter(Run.run_date == date).order_by(Run.started_at.desc()).all()

    total = len(runs)

    # Convert to response models using model_validate for proper ORM conversion
    items = [
        RunItem.model_validate(
            {
                "run_id": str(r.run_id),
                "run_date": r.run_date,
                "strategy": r.strategy,
                "status": r.status,
                "duration_seconds": r.duration_seconds,
                "tickers_processed": r.tickers_processed,
                "candidates_found": r.candidates_found,
                "errors_count": r.errors_count,
            }
        )
        for r in runs
    ]

    logger.info("Runs listed", extra={"date": str(date), "total": total})

    return RunListResponse(runs=items, total=total, date=date)


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
async def get_run_detail(
    run_id: str,
    db: Session = Depends(get_db),
) -> RunDetailResponse:
    """Get detailed information about a specific run.

    Returns comprehensive details about a scan run including:
    - Timing information (start, completion, duration)
    - Performance metrics (tickers processed, candidates found)
    - Status and error information
    - Strategy configuration

    **Use cases**:
    - Monitor scan progress (for running scans)
    - Analyze scan performance
    - Debug failed scans
    - Audit scan execution
    """
    logger.info("Fetching run detail", extra={"run_id": run_id})

    # Parse UUID
    try:
        run_uuid = UUID(run_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid run_id format: {run_id}. Expected UUID.",
        ) from e

    # Query run
    run = db.query(Run).filter(Run.run_id == run_uuid).first()

    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run not found: {run_id}",
        )

    logger.info(
        "Run detail retrieved",
        extra={"run_id": run_id, "strategy": run.strategy, "status": run.status},
    )

    return RunDetailResponse.model_validate(
        {
            "run_id": str(run.run_id),
            "run_date": run.run_date,
            "strategy": run.strategy,
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "duration_seconds": run.duration_seconds,
            "tickers_processed": run.tickers_processed,
            "candidates_found": run.candidates_found,
            "errors_count": run.errors_count,
            "error_details": run.error_details,
        }
    )
