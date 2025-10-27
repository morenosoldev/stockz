"""Aggregate metrics API endpoints.

This module provides endpoints for querying performance metrics:
- GET /metrics: Aggregate metrics across runs and candidates

Metrics include hit rates, average returns, and candidate counts to evaluate
strategy performance over time.
"""

from datetime import date as date_type

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.ops.logging import get_logger
from src.storage.models import Candidate, EvalOutcome, Run

logger = get_logger(__name__)
router = APIRouter()


# ========================================
# Pydantic Models
# ========================================


class MetricsResponse(BaseModel):
    """Response model for aggregate metrics."""

    # Time range
    start_date: date_type | None = Field(None, description="Start date of metrics period")
    end_date: date_type | None = Field(None, description="End date of metrics period")
    strategy: str | None = Field(None, description="Strategy filter applied")

    # Run metrics
    total_runs: int = Field(..., ge=0, description="Total number of scan runs")
    successful_runs: int = Field(..., ge=0, description="Number of successful runs")
    failed_runs: int = Field(..., ge=0, description="Number of failed runs")

    # Candidate metrics
    total_candidates: int = Field(..., ge=0, description="Total candidates identified")
    avg_candidates_per_run: float | None = Field(
        None, description="Average candidates per successful run"
    )
    avg_score: float | None = Field(None, description="Average recovery probability score")

    # Evaluation metrics (if outcomes are labeled)
    evaluated_candidates: int = Field(
        ..., ge=0, description="Number of candidates with labeled outcomes"
    )
    recoveries: int | None = Field(None, description="Number of successful recoveries")
    hit_rate: float | None = Field(
        None, ge=0.0, le=1.0, description="Recovery hit rate (recoveries / evaluated)"
    )
    avg_return_proxy: float | None = Field(None, description="Average return proxy for recoveries")
    avg_recovery_days: float | None = Field(None, description="Average days to recovery")


# ========================================
# Endpoints
# ========================================


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    start_date: date_type | None = Query(None, description="Start date for metrics (inclusive)"),
    end_date: date_type | None = Query(None, description="End date for metrics (inclusive)"),
    strategy: str | None = Query(None, description="Filter by strategy name"),
    db: Session = Depends(get_db),
) -> MetricsResponse:
    """Get aggregate performance metrics across runs and candidates.

    Returns comprehensive metrics to evaluate strategy performance:
    - **Run metrics**: Total runs, success rate, failure rate
    - **Candidate metrics**: Total identified, average per run, average score
    - **Evaluation metrics**: Hit rate, average returns, recovery time

    **Time filtering**:
    - If no dates provided: Returns all-time metrics
    - If only start_date: Returns metrics from start_date onwards
    - If only end_date: Returns metrics up to end_date
    - If both: Returns metrics for the date range (inclusive)

    **Strategy filtering**:
    - If strategy provided: Returns metrics for that strategy only
    - If not provided: Returns aggregate metrics across all strategies

    **Use cases**:
    - Monitor overall system performance
    - Compare strategies over time
    - Track improvement in hit rates
    - Analyze return distributions
    - Identify best-performing periods
    """
    logger.info(
        "Fetching metrics",
        extra={
            "start_date": str(start_date) if start_date else None,
            "end_date": str(end_date) if end_date else None,
            "strategy": strategy,
        },
    )

    # Build base queries with filters
    run_query = db.query(Run)
    candidate_query = db.query(Candidate)
    outcome_query = db.query(EvalOutcome).join(Candidate)

    # Apply date filters
    if start_date:
        run_query = run_query.filter(Run.run_date >= start_date)
        candidate_query = candidate_query.filter(Candidate.asof >= start_date)
        outcome_query = outcome_query.filter(Candidate.asof >= start_date)

    if end_date:
        run_query = run_query.filter(Run.run_date <= end_date)
        candidate_query = candidate_query.filter(Candidate.asof <= end_date)
        outcome_query = outcome_query.filter(Candidate.asof <= end_date)

    # Apply strategy filter
    if strategy:
        run_query = run_query.filter(Run.strategy == strategy)
        candidate_query = candidate_query.filter(Candidate.strategy == strategy)
        outcome_query = outcome_query.filter(Candidate.strategy == strategy)

    # Calculate run metrics
    total_runs = run_query.count()
    successful_runs = run_query.filter(Run.status == "completed").count()
    failed_runs = run_query.filter(Run.status == "failed").count()

    # Calculate candidate metrics
    total_candidates = candidate_query.count()

    avg_candidates_per_run = None
    if successful_runs > 0:
        avg_candidates_per_run = round(total_candidates / successful_runs, 2)

    avg_score_result = candidate_query.with_entities(func.avg(Candidate.score)).scalar()
    avg_score = round(float(avg_score_result), 4) if avg_score_result else None

    # Calculate evaluation metrics
    evaluated_candidates = outcome_query.count()
    recoveries = None
    hit_rate = None
    avg_return_proxy = None
    avg_recovery_days = None

    if evaluated_candidates > 0:
        # Count successful recoveries
        recoveries = outcome_query.filter(EvalOutcome.recovery_detected.is_(True)).count()

        # Calculate hit rate
        if evaluated_candidates > 0:
            hit_rate = round(recoveries / evaluated_candidates, 4)

        # Calculate average return proxy for recoveries
        avg_return_result = (
            outcome_query.filter(EvalOutcome.recovery_detected.is_(True))
            .with_entities(func.avg(EvalOutcome.return_proxy))
            .scalar()
        )
        avg_return_proxy = round(float(avg_return_result), 4) if avg_return_result else None

        # Calculate average recovery days
        avg_days_result = (
            outcome_query.filter(EvalOutcome.recovery_detected.is_(True))
            .with_entities(func.avg(EvalOutcome.recovery_days))
            .scalar()
        )
        avg_recovery_days = round(float(avg_days_result), 2) if avg_days_result else None

    logger.info(
        "Metrics calculated",
        extra={
            "total_runs": total_runs,
            "total_candidates": total_candidates,
            "evaluated_candidates": evaluated_candidates,
            "hit_rate": hit_rate,
        },
    )

    return MetricsResponse(
        start_date=start_date,
        end_date=end_date,
        strategy=strategy,
        total_runs=total_runs,
        successful_runs=successful_runs,
        failed_runs=failed_runs,
        total_candidates=total_candidates,
        avg_candidates_per_run=avg_candidates_per_run,
        avg_score=avg_score,
        evaluated_candidates=evaluated_candidates,
        recoveries=recoveries,
        hit_rate=hit_rate,
        avg_return_proxy=avg_return_proxy,
        avg_recovery_days=avg_recovery_days,
    )
