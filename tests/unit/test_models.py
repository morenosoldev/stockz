"""Tests for database models.

Tests SQLAlchemy model definitions, relationships, constraints, and indexes.
"""

import uuid
from datetime import date

from sqlalchemy import inspect

from src.storage.database import Base
from src.storage.models import Candidate, EvalOutcome, Feature, Run, Ticker


def test_ticker_model():
    """Test Ticker model structure."""
    ticker = Ticker(
        symbol="AAPL",
        name="Apple Inc.",
        sector="Technology",
        industry="Consumer Electronics",
        market_cap=3000000000000,
        is_active=True,
    )

    assert ticker.symbol == "AAPL"
    assert ticker.name == "Apple Inc."
    assert ticker.is_active is True
    assert repr(ticker) == "<Ticker(symbol=AAPL, name=Apple Inc.)>"


def test_run_model():
    """Test Run model structure."""
    run = Run(
        run_id=uuid.uuid4(),
        run_date=date(2025, 10, 24),
        strategy="drop5",
        status="pending",
        tickers_processed=1500,
        candidates_found=23,
        errors_count=0,
    )

    assert run.strategy == "drop5"
    assert run.status == "pending"
    assert run.errors_count == 0


def test_feature_model():
    """Test Feature model structure."""
    feature = Feature(
        ticker_symbol="AAPL",
        run_id=uuid.uuid4(),
        asof=date(2025, 10, 24),
        strategy="drop5",
        feature_version="v1.0.0",
        features={"atr_14": 2.5, "rsi_14": 35.2, "drop_pct": -5.3},
        attribution={
            "source": "yahoo_finance",
            "timestamp": "2025-10-24T16:00:00Z",
            "api_endpoint": "/v8/finance/chart/AAPL",
        },
    )

    assert feature.ticker_symbol == "AAPL"
    assert feature.features["atr_14"] == 2.5
    assert feature.attribution["source"] == "yahoo_finance"


def test_candidate_model():
    """Test Candidate model structure."""
    candidate = Candidate(
        ticker_symbol="AAPL",
        run_id=uuid.uuid4(),
        asof=date(2025, 10, 24),
        strategy="drop5",
        score=0.75,
        price=180.50,
        drop_pct=-5.2,
        volume_rvol=2.3,
        rationale={
            "rules_triggered": ["oversold_rsi", "volume_spike"],
            "confidence_factors": [0.8, 0.7],
        },
        attribution={"source": "yahoo_finance"},
    )

    assert candidate.score == 0.75
    assert candidate.drop_pct == -5.2
    assert len(candidate.rationale["rules_triggered"]) == 2


def test_eval_outcome_model():
    """Test EvalOutcome model structure."""
    outcome = EvalOutcome(
        candidate_id=uuid.uuid4(),
        recovery_detected=True,
        recovery_days=3,
        max_recovery_pct=6.8,
        return_t1=0.015,
        return_t3=0.045,
        return_t5=0.038,
        return_proxy=0.045,
        labeling_version="v1.0.0",
    )

    assert outcome.recovery_detected is True
    assert outcome.recovery_days == 3
    assert outcome.return_proxy == 0.045


def test_all_tables_registered():
    """Test that all models are registered with Base metadata."""
    tables = Base.metadata.tables.keys()

    expected_tables = {"ticker", "run", "feature", "candidate", "eval_outcome"}
    assert expected_tables.issubset(tables), f"Missing tables: {expected_tables - tables}"


def test_ticker_indexes():
    """Test that Ticker table has no explicit indexes (just PK)."""
    inspector = inspect(Ticker)
    # Primary key on 'symbol'
    assert inspector.primary_key[0].name == "symbol"


def test_run_indexes():
    """Test that Run table has proper indexes."""
    table = Run.__table__
    index_names = {idx.name for idx in table.indexes}

    assert "idx_run_date_strategy" in index_names
    assert "idx_run_status" in index_names

    # Check unique constraint
    constraint_names = {const.name for const in table.constraints}
    assert "uq_run_date_strategy" in constraint_names


def test_feature_indexes():
    """Test that Feature table has proper indexes."""
    table = Feature.__table__
    index_names = {idx.name for idx in table.indexes}

    assert "idx_feature_ticker_asof_strategy" in index_names
    assert "idx_feature_strategy_asof" in index_names

    # Check unique constraint
    constraint_names = {const.name for const in table.constraints}
    assert "uq_feature_ticker_run_strategy" in constraint_names


def test_candidate_indexes():
    """Test that Candidate table has proper indexes."""
    table = Candidate.__table__
    index_names = {idx.name for idx in table.indexes}

    assert "idx_candidate_asof_strategy" in index_names
    assert "idx_candidate_ticker_asof" in index_names
    assert "idx_candidate_score" in index_names

    # Check unique constraint
    constraint_names = {const.name for const in table.constraints}
    assert "uq_candidate_ticker_asof_strategy" in constraint_names


def test_eval_outcome_indexes():
    """Test that EvalOutcome table has proper indexes."""
    table = EvalOutcome.__table__
    index_names = {idx.name for idx in table.indexes}

    assert "idx_outcome_recovery" in index_names
    assert "idx_outcome_labeled_at" in index_names


def test_foreign_key_relationships():
    """Test that foreign key relationships are properly defined."""
    # Feature -> Ticker
    feature_fks = [fk.target_fullname for fk in Feature.__table__.foreign_keys]
    assert "ticker.symbol" in feature_fks
    assert "run.run_id" in feature_fks

    # Candidate -> Ticker and Run
    candidate_fks = [fk.target_fullname for fk in Candidate.__table__.foreign_keys]
    assert "ticker.symbol" in candidate_fks
    assert "run.run_id" in candidate_fks

    # EvalOutcome -> Candidate
    outcome_fks = [fk.target_fullname for fk in EvalOutcome.__table__.foreign_keys]
    assert "candidate.id" in outcome_fks


def test_cascade_deletes():
    """Test that cascade delete is configured on relationships."""
    # Ticker.features should cascade delete
    ticker_features_rel = Ticker.features.property
    assert "delete-orphan" in ticker_features_rel.cascade

    # Run.features should cascade delete
    run_features_rel = Run.features.property
    assert "delete-orphan" in run_features_rel.cascade

    # Candidate.outcome should cascade delete
    candidate_outcome_rel = Candidate.outcome.property
    assert "delete-orphan" in candidate_outcome_rel.cascade
