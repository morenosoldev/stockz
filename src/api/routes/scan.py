"""Scan endpoint for triggering market scans.

Endpoints:
- POST /scan - Trigger a new scan (async background task)
- GET /scan/{run_id}/status - Check scan status
"""

from datetime import UTC, datetime
from datetime import date as date_type
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.ops.logging import get_logger
from src.scanner.engine import ScanConfig, ScanEngine
from src.storage.models import Run, RunStatus

logger = get_logger(__name__)

router = APIRouter(prefix="/scan", tags=["scan"])


# ============================================================================
# Request/Response Models
# ============================================================================


class ScanRequest(BaseModel):
    """Request to trigger a new scan."""

    strategies: list[str] | None = Field(
        default=None,
        description="List of strategy names to execute (null = all enabled strategies)",
        examples=[["drop5"], ["drop5", "breakout"]],
    )
    date: date_type | None = Field(
        default=None,
        description="Market date to scan (null = today)",
        examples=["2025-10-24"],
    )
    force: bool = Field(
        default=False,
        description="Force re-run even if scan already exists for date/strategy",
    )

    @field_validator("strategies")
    @classmethod
    def validate_strategies(cls, v: list[str] | None) -> list[str] | None:
        """Validate strategy names are non-empty."""
        if v is not None:
            if len(v) == 0:
                raise ValueError("strategies list cannot be empty (use null for all strategies)")
            for strategy in v:
                if not strategy or not strategy.strip():
                    raise ValueError("strategy names cannot be empty strings")
        return v


class ScanResponse(BaseModel):
    """Response from triggering a scan."""

    run_ids: list[str] = Field(description="List of run IDs for triggered scans (one per strategy)")
    status: str = Field(
        description="Initial status of the scan",
        examples=["queued", "running"],
    )
    strategies: list[str] = Field(
        description="List of strategies being executed",
    )
    date: date_type = Field(
        description="Market date being scanned",
    )
    message: str = Field(
        description="Human-readable status message",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "run_ids": ["550e8400-e29b-41d4-a716-446655440000"],
                "status": "queued",
                "strategies": ["drop5"],
                "date": "2025-10-24",
                "message": "Scan queued for execution",
            }
        }
    )


class ScanStatusResponse(BaseModel):
    """Status of a specific scan run."""

    run_id: str = Field(description="Unique run identifier")
    run_date: date_type = Field(description="Market date of the scan")
    strategy: str = Field(description="Strategy name")
    status: str = Field(
        description="Current status: pending, running, completed, failed",
        examples=["pending", "running", "completed", "failed"],
    )
    started_at: datetime | None = Field(
        default=None, description="When the scan started (null if not started)"
    )
    completed_at: datetime | None = Field(
        default=None, description="When the scan completed (null if not complete)"
    )
    duration_seconds: int | None = Field(
        default=None, description="Total duration in seconds (null if not complete)"
    )
    tickers_processed: int | None = Field(
        default=None, description="Number of tickers scanned (null if not complete)"
    )
    candidates_found: int | None = Field(
        default=None, description="Number of candidates identified (null if not complete)"
    )
    errors_count: int = Field(default=0, description="Number of errors encountered")
    error_details: dict[str, Any] | None = Field(
        default=None, description="Error information if status=failed"
    )

    @field_serializer("run_id")
    def serialize_run_id(self, run_id: UUID | str) -> str:
        """Convert UUID to string."""
        from uuid import UUID as UUIDType

        if isinstance(run_id, UUIDType):
            return str(run_id)
        return run_id

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "run_id": "550e8400-e29b-41d4-a716-446655440000",
                "run_date": "2025-10-24",
                "strategy": "drop5",
                "status": "completed",
                "started_at": "2025-10-24T16:30:00Z",
                "completed_at": "2025-10-24T16:38:45Z",
                "duration_seconds": 525,
                "tickers_processed": 1500,
                "candidates_found": 23,
                "errors_count": 0,
                "error_details": None,
            }
        },
    )


# ============================================================================
# Background Task Functions
# ============================================================================


def execute_scan_task(
    strategies: list[str] | None,
    scan_date: date_type,
    run_ids: list[str],
) -> None:
    """Execute scan in background.

    This function runs asynchronously after the API returns a response.
    It creates a new database session and executes the scan engine.

    Args:
        strategies: List of strategy names (None = all enabled)
        scan_date: Market date to scan
        run_ids: Pre-generated run IDs to use
    """
    from src.storage.database import SessionLocal

    logger.info(
        "Starting background scan task",
        extra={
            "strategies": strategies,
            "date": scan_date.isoformat(),
            "run_ids": run_ids,
        },
    )

    # Get first run_id for logging context
    primary_run_id = run_ids[0] if run_ids else None

    # Create new database session for background task
    db = SessionLocal()

    try:
        # Update run status to running
        for run_id in run_ids:
            run = db.query(Run).filter(Run.run_id == run_id).first()
            if run:
                run.status = RunStatus.RUNNING.value  # type: ignore[assignment]
                run.started_at = datetime.now()  # type: ignore[assignment]

                # Log with run_id context for SSE streaming
                logger.info(
                    "Scan started",
                    run_id=run_id,
                    strategy=run.strategy,
                    date=scan_date.isoformat(),
                )
        db.commit()

        # Emit initial log event
        if primary_run_id:
            logger.info(
                "Initializing scan engine...",
                run_id=primary_run_id,
            )

        # Create scan configuration
        config = ScanConfig(
            strategies=strategies,
            universe_size=None,  # Use full universe
            min_score=0.5,
            max_workers=10,
            timeout_seconds=30,
            lookback_days=20,
        )

        if primary_run_id:
            logger.info(
                "Loading ticker universe...",
                run_id=primary_run_id,
            )

        # Execute scan (pass run_ids for logging context)
        engine = ScanEngine(db_session=db)

        # Bind run_id to logger for this execution context
        # Note: ScanEngine will need to log with run_id context

        if primary_run_id:
            logger.info(
                f"Starting scan with {len(strategies or [])} strategies",
                run_id=primary_run_id,
                strategies=strategies,
            )

        # Execute scan with pre-created run_ids
        results = engine.run_scan(scan_config=config, asof=scan_date, run_ids=run_ids)

        # Update run status to completed
        for run_id in run_ids:
            run = db.query(Run).filter(Run.run_id == run_id).first()
            if run:
                run.status = RunStatus.COMPLETED.value  # type: ignore[assignment]
                run.completed_at = datetime.now(UTC)  # type: ignore[assignment]
                # Calculate duration
                now = datetime.now(UTC)
                if run.started_at:
                    started_at: datetime = run.started_at  # type: ignore[assignment]
                    duration = int((now - started_at).total_seconds())
                else:
                    duration = 0
                run.duration_seconds = duration  # type: ignore[assignment]
                run.candidates_found = len(results)  # type: ignore[assignment]

                logger.info(
                    "Scan completed successfully",
                    run_id=run_id,
                    candidates_found=len(results),
                    date=scan_date.isoformat(),
                )
        db.commit()

    except Exception as e:
        # Log error for each run_id
        for run_id in run_ids:
            logger.error(
                f"Scan failed: {str(e)}",
                run_id=run_id,
                error=str(e),
                error_type=type(e).__name__,
            )

        logger.error(
            "Background scan failed",
            extra={
                "strategies": strategies,
                "date": scan_date.isoformat(),
                "error": str(e),
            },
            exc_info=True,
        )

        # Update run status to failed
        for run_id in run_ids:
            run = db.query(Run).filter(Run.run_id == run_id).first()
            if run:
                run.status = RunStatus.FAILED.value  # type: ignore[assignment]
                run.completed_at = datetime.now()  # type: ignore[assignment]
                run.error_details = {"error": str(e), "type": type(e).__name__}
        db.commit()

    finally:
        db.close()


# ============================================================================
# Endpoints
# ============================================================================


@router.post("", response_model=ScanResponse, status_code=202)
async def trigger_scan(
    request: ScanRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ScanResponse:
    """Trigger a new market scan.

    This endpoint initiates a scan asynchronously and returns immediately
    with run IDs. The actual scan executes in the background.

    **Process**:
    1. Validate request parameters
    2. Check for existing runs (unless force=true)
    3. Create Run records in database with status=pending
    4. Queue background task
    5. Return run IDs immediately

    **Status Codes**:
    - 202: Scan queued successfully
    - 400: Invalid request (empty strategies, etc.)
    - 409: Scan already exists for date/strategy (unless force=true)
    - 500: Server error

    Args:
        request: Scan request parameters
        background_tasks: FastAPI background tasks
        db: Database session

    Returns:
        ScanResponse with run IDs and status
    """
    from src.strategies.registry import get_registry

    scan_date = request.date or date_type.today()
    strategies = request.strategies

    logger.info(
        "Scan request received",
        extra={
            "strategies": strategies,
            "date": scan_date.isoformat(),
            "force": request.force,
        },
    )

    # Resolve strategies (None = all enabled)
    registry = get_registry()
    registry.discover_and_register()

    if strategies is None:
        # Get all enabled strategies (type-safe via overload)
        enabled_strategies = registry.list_strategies(enabled_only=True, names_only=True)
        if not enabled_strategies:
            raise HTTPException(
                status_code=400,
                detail="No enabled strategies found. Please enable at least one strategy.",
            )
        strategies = enabled_strategies
    else:
        # Validate requested strategies exist (type-safe via overload)
        available = registry.list_strategies(enabled_only=False, names_only=True)
        for strategy_name in strategies:
            if strategy_name not in available:
                raise HTTPException(
                    status_code=400,
                    detail=f"Strategy '{strategy_name}' not found. "
                    f"Available: {', '.join(available)}",
                )

    # At this point, strategies is guaranteed to be list[str], not None
    assert strategies is not None

    # Check for existing runs (unless force=true)
    run_ids = []
    existing_runs = []

    for strategy_name in strategies:
        existing = (
            db.query(Run).filter(Run.run_date == scan_date, Run.strategy == strategy_name).first()
        )

        if existing and not request.force:
            existing_runs.append(strategy_name)
        elif existing and request.force:
            # Delete existing run and cascade delete features/candidates
            db.delete(existing)
            db.commit()
            logger.info(
                "Deleted existing run (force=true)",
                extra={
                    "run_id": str(existing.run_id),
                    "strategy": strategy_name,
                    "date": scan_date.isoformat(),
                },
            )

    if existing_runs:
        raise HTTPException(
            status_code=409,
            detail=f"Scan already exists for {scan_date} with strategies: "
            f"{', '.join(existing_runs)}. Use force=true to re-run.",
        )

    # Create Run records with status=pending
    for strategy_name in strategies:
        run = Run(
            run_date=scan_date,
            strategy=strategy_name,
            status=RunStatus.PENDING.value,
        )
        db.add(run)
        db.flush()  # Get run_id without committing
        run_ids.append(str(run.run_id))

    db.commit()

    logger.info(
        "Created run records",
        extra={
            "run_ids": run_ids,
            "strategies": strategies,
            "date": scan_date.isoformat(),
        },
    )

    # Pre-register interrupt flags so scans can be stopped immediately
    import threading

    from src.scanner.engine import _interrupt_flags

    for run_id in run_ids:
        _interrupt_flags[run_id] = threading.Event()

    logger.debug(
        "Registered interrupt flags for scans",
        extra={"run_ids": run_ids},
    )

    # Queue background task
    background_tasks.add_task(
        execute_scan_task,
        strategies=strategies,
        scan_date=scan_date,
        run_ids=run_ids,
    )

    return ScanResponse(
        run_ids=run_ids,
        status="queued",
        strategies=strategies,
        date=scan_date,
        message=f"Scan queued for execution with {len(strategies)} "
        f"{'strategy' if len(strategies) == 1 else 'strategies'}",
    )


@router.get("/{run_id}/status", response_model=ScanStatusResponse)
async def get_scan_status(
    run_id: str,
    db: Session = Depends(get_db),
) -> ScanStatusResponse:
    """Get status of a specific scan run.

    **Status Values**:
    - `pending`: Scan created but not started
    - `running`: Scan currently executing
    - `completed`: Scan finished successfully
    - `failed`: Scan encountered errors
    - `stopped`: Scan interrupted by user

    **Status Codes**:
    - 200: Status retrieved successfully
    - 404: Run ID not found

    Args:
        run_id: Unique run identifier
        db: Database session

    Returns:
        ScanStatusResponse with current status
    """
    import uuid

    # Convert string to UUID
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid UUID format: {run_id}",
        ) from e

    run = db.query(Run).filter(Run.run_id == run_uuid).first()

    if not run:
        raise HTTPException(
            status_code=404,
            detail=f"Scan run '{run_id}' not found",
        )

    # Use model_validate for proper ORM conversion
    return ScanStatusResponse.model_validate(
        {
            "run_id": str(run.run_id),
            "run_date": run.run_date,
            "strategy": run.strategy,
            "status": run.status,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "duration_seconds": run.duration_seconds,
            "tickers_processed": run.tickers_processed,
            "candidates_found": run.candidates_found,
            "errors_count": run.errors_count,
            "error_details": run.error_details,
        }
    )


@router.delete("/{run_id}/stop")
async def stop_scan(
    run_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Stop a running scan mid-execution.

    Gracefully interrupts the scan, saving all partial results processed so far.
    The Run status will be updated to "stopped" and partial results will be available.

    **Status Codes**:
    - 200: Stop request successful, scan will terminate
    - 409: Scan already completed/stopped/failed
    - 404: Run ID not found

    Args:
        run_id: Unique run identifier
        db: Database session

    Returns:
        Dict with message and status
    """
    import uuid

    from src.scanner.engine import request_interrupt

    # Convert string to UUID
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid UUID format: {run_id}",
        ) from e

    # Check if run exists
    run = db.query(Run).filter(Run.run_id == run_uuid).first()

    if not run:
        raise HTTPException(
            status_code=404,
            detail=f"Scan run '{run_id}' not found",
        )

    # Check if scan is still running
    if run.status != RunStatus.RUNNING.value:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot stop scan - status is '{run.status}' (must be 'running')",
        )

    # Request interrupt
    interrupted = request_interrupt(run_id)

    if not interrupted:
        # Run was in database as running but not found in interrupt flags
        # This can happen if the scan just finished
        logger.warning("Interrupt requested but run_id not found in active scans", run_id=run_id)
        raise HTTPException(
            status_code=409,
            detail="Scan may have already completed - refresh status",
        )

    logger.info(
        "Scan stop requested",
        run_id=run_id,
        strategy=run.strategy,
        tickers_processed=run.tickers_processed or 0,
    )

    return {
        "message": "Scan stop requested - partial results will be saved",
        "run_id": run_id,
        "status": "stopping",
    }
