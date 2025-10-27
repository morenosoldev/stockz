"""SQLAlchemy models for database schema.

Core principles:
- UUID primary keys for distributed systems
- Explicit versioning for reproducibility
- Use JSONB/JSON for flexible structured data
- Foreign key constraints for referential integrity
- Indexes for common query patterns
"""

import uuid
from enum import Enum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.storage.database import Base


# Use JSONB for PostgreSQL, JSON for other databases (e.g., SQLite in tests)
def JSONType() -> JSON:
    """Return appropriate JSON type for the database dialect."""
    return JSON().with_variant(JSONB(), "postgresql")  # type: ignore[no-untyped-call]


class Ticker(Base):
    """Universe of tickers that can be scanned.

    This table stores the ticker universe metadata. It's loaded from
    external sources (e.g., S&P 500, NASDAQ 100) and updated periodically.
    """

    __tablename__ = "ticker"

    symbol = Column(String(10), primary_key=True, doc="Stock ticker symbol (e.g., AAPL)")
    name = Column(String(255), nullable=False, doc="Company name")
    sector = Column(String(100), nullable=True, doc="Industry sector")
    industry = Column(String(100), nullable=True, doc="Industry classification")
    market_cap = Column(BigInteger, nullable=True, doc="Market capitalization in USD")
    is_active = Column(
        Boolean, default=True, nullable=False, doc="Whether ticker is active for scanning"
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    features = relationship("Feature", back_populates="ticker", cascade="all, delete-orphan")
    candidates = relationship("Candidate", back_populates="ticker", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Ticker(symbol={self.symbol}, name={self.name})>"


class RunStatus(str, Enum):
    """Status of a scan run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Run(Base):
    """Scan run metadata.

    Tracks each execution of the scanner, including timing,
    status, and performance metrics.
    """

    __tablename__ = "run"

    run_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_date = Column(Date, nullable=False, doc="Market date of the scan (not execution time)")
    strategy = Column(String(50), nullable=False, doc="Strategy name (e.g., 'drop5')")
    status = Column(
        String(20),
        nullable=False,
        default="pending",
        doc="Run status: pending, running, completed, failed",
    )

    # Timing
    started_at = Column(DateTime(timezone=True), nullable=True, doc="Scan start time")
    completed_at = Column(DateTime(timezone=True), nullable=True, doc="Scan completion time")
    duration_seconds = Column(Integer, nullable=True, doc="Total scan duration")

    # Metrics
    tickers_processed = Column(Integer, nullable=True, doc="Number of tickers scanned")
    candidates_found = Column(Integer, nullable=True, doc="Number of candidates identified")
    errors_count = Column(Integer, default=0, nullable=False, doc="Number of errors encountered")

    # Metadata
    config_snapshot: Any = Column(
        JSONType(), nullable=True, doc="Snapshot of config used for this run (reproducibility)"
    )
    error_details: Any = Column(
        JSONType(), nullable=True, doc="Structured error information if status=failed"
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    features = relationship("Feature", back_populates="run", cascade="all, delete-orphan")
    candidates = relationship("Candidate", back_populates="run", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("idx_run_date_strategy", "run_date", "strategy"),
        Index("idx_run_status", "status"),
        UniqueConstraint("run_date", "strategy", name="uq_run_date_strategy"),
    )

    def __repr__(self) -> str:
        return f"<Run(run_id={self.run_id}, date={self.run_date}, strategy={self.strategy})>"


class Feature(Base):
    """Versioned feature storage.

    Stores computed features for each ticker/strategy/date combination.
    Features are versioned for reproducibility and A/B testing.
    """

    __tablename__ = "feature"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker_symbol = Column(
        String(10), ForeignKey("ticker.symbol", ondelete="CASCADE"), nullable=False
    )
    run_id = Column(
        UUID(as_uuid=True), ForeignKey("run.run_id", ondelete="CASCADE"), nullable=False
    )
    asof = Column(Date, nullable=False, doc="Market date for which features were computed")
    strategy = Column(String(50), nullable=False, doc="Strategy that generated these features")

    # Versioning
    feature_version = Column(
        String(20), nullable=False, doc="Feature schema version (e.g., 'v1.2.0')"
    )

    # Feature data (flexible JSONB)
    features: Any = Column(
        JSONType(),
        nullable=False,
        doc="Feature dictionary (e.g., {'atr_14': 2.5, 'rsi_14': 35.2})",
    )

    # Attribution
    attribution: Any = Column(
        JSONType(),
        nullable=False,
        doc="Data source attribution (source, timestamp, url, api_endpoint)",
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    ticker = relationship("Ticker", back_populates="features")
    run = relationship("Run", back_populates="features")

    # Indexes
    __table_args__ = (
        Index("idx_feature_ticker_asof_strategy", "ticker_symbol", "asof", "strategy"),
        Index("idx_feature_strategy_asof", "strategy", "asof"),
        UniqueConstraint(
            "ticker_symbol", "run_id", "strategy", name="uq_feature_ticker_run_strategy"
        ),
    )

    def __repr__(self) -> str:
        return f"<Feature(ticker={self.ticker_symbol}, asof={self.asof}, strategy={self.strategy})>"


class Candidate(Base):
    """Scored recovery candidates.

    Represents tickers that passed strategy filters and received
    a recovery probability score. Includes rationale for explainability.
    """

    __tablename__ = "candidate"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker_symbol = Column(
        String(10), ForeignKey("ticker.symbol", ondelete="CASCADE"), nullable=False
    )
    run_id = Column(
        UUID(as_uuid=True), ForeignKey("run.run_id", ondelete="CASCADE"), nullable=False
    )
    asof = Column(Date, nullable=False, doc="Market date of candidate identification")
    strategy = Column(String(50), nullable=False, doc="Strategy that identified this candidate")

    # Scoring
    score = Column(
        Numeric(5, 4),
        nullable=False,
        doc="Recovery probability score (0.0000 to 1.0000)",
    )

    # Context (from features or supplemental data)
    price = Column(Numeric(12, 2), nullable=True, doc="Price at identification")
    drop_pct = Column(Numeric(6, 3), nullable=True, doc="Drop percentage that triggered alert")
    volume_rvol = Column(Numeric(6, 2), nullable=True, doc="Relative volume (vs avg)")

    # Explainability
    rationale: Any = Column(
        JSONType(),
        nullable=False,
        doc="Score rationale (rules triggered, confidence factors, etc.)",
    )

    # Attribution
    attribution: Any = Column(
        JSONType(),
        nullable=False,
        doc="Data source attribution for all data used in scoring",
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    ticker = relationship("Ticker", back_populates="candidates")
    run = relationship("Run", back_populates="candidates")
    outcome = relationship(
        "EvalOutcome", back_populates="candidate", uselist=False, cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("idx_candidate_asof_strategy", "asof", "strategy"),
        Index("idx_candidate_ticker_asof", "ticker_symbol", "asof"),
        Index("idx_candidate_score", "score"),
        UniqueConstraint(
            "ticker_symbol", "asof", "strategy", name="uq_candidate_ticker_asof_strategy"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Candidate(ticker={self.ticker_symbol}, asof={self.asof}, "
            f"score={self.score}, strategy={self.strategy})>"
        )


class EvalOutcome(Base):
    """Evaluation outcomes for backtesting.

    Stores whether a candidate actually recovered and performance metrics.
    Used for strategy evaluation and calibration.
    """

    __tablename__ = "eval_outcome"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(
        UUID(as_uuid=True),
        ForeignKey("candidate.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # Recovery detection
    recovery_detected = Column(Boolean, nullable=False, doc="Whether recovery criteria were met")
    recovery_days = Column(Integer, nullable=True, doc="Days until recovery (T+1, T+2, ..., T+5)")
    max_recovery_pct = Column(
        Numeric(6, 3), nullable=True, doc="Maximum recovery percentage within window"
    )

    # Performance metrics
    return_t1 = Column(Numeric(7, 4), nullable=True, doc="Return at T+1 (1 day)")
    return_t3 = Column(Numeric(7, 4), nullable=True, doc="Return at T+3 (3 days)")
    return_t5 = Column(Numeric(7, 4), nullable=True, doc="Return at T+5 (5 days)")
    return_proxy = Column(
        Numeric(7, 4), nullable=True, doc="Proxy return for calibration (e.g., T+3 return)"
    )

    # Outcome labeling metadata
    labeled_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    labeling_version = Column(
        String(20), nullable=False, doc="Labeling logic version for reproducibility"
    )
    outcome_data: Any = Column(
        JSONType(), nullable=True, doc="Raw outcome data (prices, volumes, etc.) for auditing"
    )

    # Relationships
    candidate = relationship("Candidate", back_populates="outcome")

    # Indexes
    __table_args__ = (
        Index("idx_outcome_recovery", "recovery_detected"),
        Index("idx_outcome_labeled_at", "labeled_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<EvalOutcome(candidate_id={self.candidate_id}, "
            f"recovery={self.recovery_detected}, days={self.recovery_days})>"
        )
