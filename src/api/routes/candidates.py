"""Candidate listing and detail API endpoints.

This module provides endpoints for querying recovery candidates identified by scan runs:
- GET /candidates: List candidates with filtering, pagination, and sorting
- GET /candidate/{ticker}/{asof}: Get detailed candidate information

All endpoints return candidates with full attribution metadata for transparency.
"""

from datetime import date as date_type
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, desc
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from src.api.dependencies import get_db
from src.ops.logging import get_logger
from src.storage.models import Candidate, Run, Ticker
from src.strategies.registry import StrategyRegistry

logger = get_logger(__name__)
router = APIRouter()


# ========================================
# Pydantic Models
# ========================================


class CandidateItem(BaseModel):
    """Individual candidate item in list response."""

    model_config = ConfigDict(from_attributes=True)

    ticker: str = Field(..., description="Stock ticker symbol")
    asof: date_type = Field(..., description="Market date of identification")
    strategy: str = Field(..., description="Strategy that identified this candidate")
    score: float = Field(..., ge=0.0, le=1.0, description="Recovery probability score (0-1)")
    price: float | None = Field(None, description="Price at identification")
    drop_pct: float | None = Field(None, description="Drop percentage that triggered alert")
    volume_rvol: float | None = Field(None, description="Relative volume vs average")
    run_id: str = Field(..., description="UUID of the scan run")


class CandidateListResponse(BaseModel):
    """Response model for candidate listing."""

    candidates: list[CandidateItem] = Field(..., description="List of candidates")
    total: int = Field(..., ge=0, description="Total number of candidates matching filters")
    page: int = Field(..., ge=1, description="Current page number (1-indexed)")
    page_size: int = Field(..., ge=1, description="Number of items per page")
    filters: dict[str, Any] = Field(..., description="Applied filters for reference")


class CandidateDetailResponse(BaseModel):
    """Response model for detailed candidate view."""

    model_config = ConfigDict(from_attributes=True)

    # Basic info
    ticker: str = Field(..., description="Stock ticker symbol")
    name: str | None = Field(None, description="Company name")
    sector: str | None = Field(None, description="Industry sector")
    asof: date_type = Field(..., description="Market date of identification")
    strategy: str = Field(..., description="Strategy that identified this candidate")

    # Scoring
    score: float = Field(..., ge=0.0, le=1.0, description="Recovery probability score (0-1)")
    price: float | None = Field(None, description="Price at identification")
    drop_pct: float | None = Field(None, description="Drop percentage that triggered alert")
    volume_rvol: float | None = Field(None, description="Relative volume vs average")

    # Explainability
    rationale: dict[str, Any] = Field(..., description="Score rationale and confidence factors")

    # Attribution
    attribution: dict[str, Any] = Field(..., description="Data source attribution for transparency")

    # Run metadata
    run_id: str = Field(..., description="UUID of the scan run")
    run_status: str = Field(..., description="Status of the scan run")


# ========================================
# Endpoints
# ========================================


@router.get("/candidates", response_model=CandidateListResponse)
async def list_candidates(
    date: date_type | None = Query(
        None, description="Filter by market date (YYYY-MM-DD). Defaults to most recent."
    ),
    strategy: str | None = Query(None, description="Filter by strategy name"),
    min_score: float | None = Query(
        None, ge=0.0, le=1.0, description="Minimum recovery probability score"
    ),
    limit: int = Query(50, ge=1, le=500, description="Number of results per page"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    sort_by: str = Query(
        "score",
        pattern="^(score|drop_pct|ticker|volume_rvol)$",
        description="Sort field: score, drop_pct, ticker, or volume_rvol",
    ),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order: asc or desc"),
    db: Session = Depends(get_db),
) -> CandidateListResponse:
    """List recovery candidates with filtering, pagination, and sorting.

    Returns a paginated list of candidates identified by scan runs. Results can be
    filtered by date, strategy, and minimum score. Supports sorting by multiple fields.

    **Default behavior** (no filters):
    - Returns candidates from the most recent scan date
    - All strategies included
    - All scores included
    - Sorted by score (highest first)

    **Pagination**:
    - Use `limit` and `offset` for pagination
    - Default: 50 items per page
    - Maximum: 500 items per page

    **Sorting**:
    - `score`: Recovery probability (default: descending)
    - `drop_pct`: Drop percentage (default: descending for largest drops)
    - `ticker`: Alphabetical by ticker symbol
    - `volume_rvol`: Relative volume
    """
    logger.info(
        "Listing candidates",
        extra={
            "date": str(date) if date else None,
            "strategy": strategy,
            "min_score": min_score,
            "limit": limit,
            "offset": offset,
            "sort_by": sort_by,
            "sort_order": sort_order,
        },
    )

    # Validate strategy if provided
    if strategy:
        registry = StrategyRegistry()
        available = registry.list_strategies(enabled_only=True, names_only=True)
        if strategy not in available:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Strategy '{strategy}' not found. Available strategies: {', '.join(available)}",
            )

    # Build query
    query = db.query(Candidate)

    # Apply filters
    if date:
        query = query.filter(Candidate.asof == date)
    else:
        # Get most recent date with candidates
        latest_date = db.query(Candidate.asof).order_by(desc(Candidate.asof)).limit(1).scalar()
        if latest_date:
            query = query.filter(Candidate.asof == latest_date)
            date = latest_date  # For filters dict in response

    if strategy:
        query = query.filter(Candidate.strategy == strategy)

    if min_score is not None:
        query = query.filter(Candidate.score >= min_score)

    # Get total count before pagination
    total = query.count()

    # Apply sorting
    sort_column: ColumnElement[Any]
    if sort_by == "score":
        sort_column = Candidate.score
    elif sort_by == "drop_pct":
        sort_column = Candidate.drop_pct
    elif sort_by == "ticker":
        sort_column = Candidate.ticker_symbol
    else:  # volume_rvol
        sort_column = Candidate.volume_rvol

    if sort_order == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(sort_column)

    # Apply pagination
    query = query.limit(limit).offset(offset)

    # Execute query
    candidates = query.all()

    # Convert to response models using model_validate for proper ORM conversion
    items = [
        CandidateItem.model_validate(
            {
                "ticker": c.ticker_symbol,
                "asof": c.asof,
                "strategy": c.strategy,
                "score": float(c.score),
                "price": float(c.price) if c.price else None,
                "drop_pct": float(c.drop_pct) if c.drop_pct else None,
                "volume_rvol": float(c.volume_rvol) if c.volume_rvol else None,
                "run_id": str(c.run_id),
            }
        )
        for c in candidates
    ]

    # Calculate page number (1-indexed)
    page = (offset // limit) + 1

    logger.info(
        "Candidates listed",
        extra={
            "total": total,
            "returned": len(items),
            "page": page,
            "page_size": limit,
        },
    )

    return CandidateListResponse(
        candidates=items,
        total=total,
        page=page,
        page_size=limit,
        filters={
            "date": str(date) if date else None,
            "strategy": strategy,
            "min_score": min_score,
            "sort_by": sort_by,
            "sort_order": sort_order,
        },
    )


@router.get("/candidate/{ticker}/{asof}", response_model=CandidateDetailResponse)
async def get_candidate_detail(
    ticker: str,
    asof: date_type,
    strategy: str | None = Query(None, description="Filter by strategy name"),
    db: Session = Depends(get_db),
) -> CandidateDetailResponse:
    """Get detailed information for a specific candidate.

    Returns comprehensive details including:
    - Full scoring rationale and confidence factors
    - Data source attribution for transparency
    - Company information (name, sector)
    - Associated scan run metadata

    If multiple strategies identified the same ticker on the same date,
    use the `strategy` query parameter to specify which one. If not provided,
    returns the candidate with the highest score.
    """
    logger.info(
        "Fetching candidate detail",
        extra={"ticker": ticker, "asof": str(asof), "strategy": strategy},
    )

    # Build query
    query = db.query(Candidate).filter(
        and_(Candidate.ticker_symbol == ticker.upper(), Candidate.asof == asof)
    )

    if strategy:
        query = query.filter(Candidate.strategy == strategy)

    # If no strategy specified, get the one with highest score
    query = query.order_by(desc(Candidate.score))

    candidate = query.first()

    if not candidate:
        if strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Candidate not found: {ticker} on {asof} for strategy '{strategy}'",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Candidate not found: {ticker} on {asof}",
            )

    # Get ticker info
    ticker_info = db.query(Ticker).filter(Ticker.symbol == candidate.ticker_symbol).first()

    # Get run info
    run_info = db.query(Run).filter(Run.run_id == candidate.run_id).first()

    logger.info(
        "Candidate detail retrieved",
        extra={
            "ticker": ticker,
            "asof": str(asof),
            "strategy": candidate.strategy,
            "score": float(candidate.score),
        },
    )

    return CandidateDetailResponse.model_validate(
        {
            "ticker": candidate.ticker_symbol,
            "name": ticker_info.name if ticker_info else None,
            "sector": ticker_info.sector if ticker_info else None,
            "asof": candidate.asof,
            "strategy": candidate.strategy,
            "score": float(candidate.score),
            "price": float(candidate.price) if candidate.price else None,
            "drop_pct": float(candidate.drop_pct) if candidate.drop_pct else None,
            "volume_rvol": float(candidate.volume_rvol) if candidate.volume_rvol else None,
            "rationale": candidate.rationale,
            "attribution": candidate.attribution,
            "run_id": str(candidate.run_id),
            "run_status": run_info.status if run_info else "unknown",
        }
    )
