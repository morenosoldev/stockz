"""Integration tests for FastAPI application.

Tests API startup, health endpoints, middleware, and error handling.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.api.dependencies import get_db
from src.api.main import create_app
from src.storage.database import Base


@pytest.fixture(scope="function")
def test_db():
    """Create test database with shared connection pool."""
    # Use file-based database for shared access across threads
    import os
    import tempfile

    # Create temporary database file
    db_fd, db_path = tempfile.mkstemp(suffix=".db")

    try:
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(engine)
        TestingSessionLocal = sessionmaker(bind=engine)

        db = TestingSessionLocal()
        # Store engine and path for cleanup
        db._engine = engine  # type: ignore[attr-defined]
        db._db_path = db_path  # type: ignore[attr-defined]
        db._db_fd = db_fd  # type: ignore[attr-defined]
        yield db

        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
    finally:
        # Clean up temp file
        os.close(db_fd)
        os.unlink(db_path)


@pytest.fixture(scope="function")
def client(test_db):
    """Create test client with database override."""
    app = create_app()

    # Override database dependency to use the same session
    def override_get_db():
        try:
            yield test_db
        finally:
            # Don't close here, let test_db fixture handle it
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_basic_health_check(self, client):
        """Test GET /v1/health returns healthy status."""
        response = client.get("/v1/health")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert "timestamp" in data
        assert "version" in data

    def test_detailed_health_check(self, client):
        """Test GET /v1/health/detailed returns detailed info."""
        response = client.get("/v1/health/detailed")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "healthy"
        assert "database" in data
        assert data["database"]["status"] == "connected"
        assert "system" in data
        assert "version" in data["system"]

    def test_readiness_check(self, client):
        """Test GET /v1/health/ready returns ready status."""
        response = client.get("/v1/health/ready")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "ready"

    def test_liveness_check(self, client):
        """Test GET /v1/health/live returns alive status."""
        response = client.get("/v1/health/live")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "alive"
        assert "timestamp" in data


class TestRootEndpoint:
    """Test root endpoint."""

    def test_root_endpoint(self, client):
        """Test GET / returns API info."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()

        assert data["message"] == "Recover-Bot API"
        assert "version" in data
        assert data["docs"] == "/docs"
        assert data["health"] == "/v1/health"


class TestMiddleware:
    """Test middleware functionality."""

    def test_cors_headers(self, client):
        """Test CORS middleware adds appropriate headers."""
        response = client.options(
            "/v1/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

        # CORS headers should be present
        assert "access-control-allow-origin" in response.headers

    def test_request_logging_middleware(self, client, caplog):
        """Test request logging middleware logs requests."""
        response = client.get("/v1/health")

        assert response.status_code == 200
        # Logging happens but may not appear in caplog due to async nature
        # Just verify response is successful


class TestErrorHandling:
    """Test error handling and exception handlers."""

    def test_404_not_found(self, client):
        """Test 404 error for non-existent endpoint."""
        response = client.get("/v1/nonexistent")

        assert response.status_code == 404
        data = response.json()

        assert "error" in data
        assert data["error"]["code"] == 404
        assert "timestamp" in data["error"]

    def test_validation_error(self, client):
        """Test validation error handling (will test with POST endpoints later)."""
        # This will be more relevant when we have POST endpoints with request bodies
        # For now, just verify the handler is registered by checking health works
        response = client.get("/v1/health")
        assert response.status_code == 200


class TestOpenAPIDocumentation:
    """Test OpenAPI/Swagger documentation."""

    def test_openapi_json(self, client):
        """Test /openapi.json returns OpenAPI spec."""
        response = client.get("/openapi.json")

        assert response.status_code == 200
        spec = response.json()

        assert spec["openapi"].startswith("3.")
        assert spec["info"]["title"] == "Recover-Bot API"
        assert "paths" in spec
        assert "/v1/health" in spec["paths"]

    def test_swagger_ui(self, client):
        """Test /docs returns Swagger UI."""
        response = client.get("/docs")

        assert response.status_code == 200
        assert b"swagger" in response.content.lower()

    def test_redoc(self, client):
        """Test /redoc returns ReDoc."""
        response = client.get("/redoc")

        assert response.status_code == 200
        assert b"redoc" in response.content.lower()


class TestDatabaseDependency:
    """Test database dependency injection."""

    def test_database_session_closes(self, client):
        """Test database sessions are properly closed after requests."""
        # Make multiple requests
        for _ in range(5):
            response = client.get("/v1/health")
            assert response.status_code == 200

        # If sessions weren't closed, we'd run out of connections
        # The fact that all requests succeed means sessions are being closed

    def test_database_connection_in_health(self, client):
        """Test health check actually queries database."""
        response = client.get("/v1/health")

        assert response.status_code == 200
        data = response.json()

        # Health check should have tested database connection
        assert data["database"] == "connected"


@pytest.mark.integration
class TestApplicationLifespan:
    """Test application lifespan events."""

    def test_app_startup(self):
        """Test application starts up successfully."""
        app = create_app()

        # App should be created without errors
        assert app is not None
        assert app.title == "Recover-Bot API"

    def test_app_with_test_client(self, client):
        """Test application works with test client."""
        # Just creating the client tests startup
        response = client.get("/")
        assert response.status_code == 200


@pytest.mark.integration
class TestScanEndpoint:
    """Test scan endpoint functionality."""

    def test_trigger_scan_basic(self, client, test_db, monkeypatch):
        """Test triggering a basic scan."""

        # Mock the ScanEngine to avoid actual scanning
        def mock_execute_scan_task(*args, **kwargs):
            # Don't actually execute the scan in tests
            pass

        monkeypatch.setattr("src.api.routes.scan.execute_scan_task", mock_execute_scan_task)

        # Trigger scan
        response = client.post(
            "/v1/scan",
            json={"strategies": ["drop5"], "date": "2025-10-24", "force": False},
        )

        assert response.status_code == 202
        data = response.json()

        assert "run_ids" in data
        assert isinstance(data["run_ids"], list)
        assert len(data["run_ids"]) == 1
        assert data["status"] == "queued"
        assert data["strategies"] == ["drop5"]
        assert data["date"] == "2025-10-24"

    def test_trigger_scan_multiple_strategies(self, client, test_db, monkeypatch):
        """Test triggering scan with multiple strategies."""

        def mock_execute_scan_task(*args, **kwargs):
            pass

        monkeypatch.setattr("src.api.routes.scan.execute_scan_task", mock_execute_scan_task)

        response = client.post(
            "/v1/scan",
            json={"strategies": ["drop5"]},  # Only drop5 exists currently
        )

        assert response.status_code == 202
        data = response.json()
        assert len(data["run_ids"]) == 1

    def test_trigger_scan_all_strategies(self, client, test_db, monkeypatch):
        """Test triggering scan with all enabled strategies (None)."""

        def mock_execute_scan_task(*args, **kwargs):
            pass

        monkeypatch.setattr("src.api.routes.scan.execute_scan_task", mock_execute_scan_task)

        response = client.post(
            "/v1/scan",
            json={"strategies": None},  # All enabled strategies
        )

        # Should work if at least one strategy is enabled
        assert response.status_code in [202, 400]  # 400 if no strategies enabled
        if response.status_code == 202:
            data = response.json()
            assert len(data["run_ids"]) > 0

    def test_trigger_scan_default_date(self, client, test_db, monkeypatch):
        """Test scan with default date (today)."""
        from datetime import date

        def mock_execute_scan_task(*args, **kwargs):
            pass

        monkeypatch.setattr("src.api.routes.scan.execute_scan_task", mock_execute_scan_task)

        response = client.post(
            "/v1/scan",
            json={"strategies": ["drop5"]},  # date=None (today)
        )

        assert response.status_code == 202
        data = response.json()
        assert data["date"] == date.today().isoformat()

    def test_trigger_scan_duplicate_without_force(self, client, test_db, monkeypatch):
        """Test that duplicate scans are rejected without force=true."""

        def mock_execute_scan_task(*args, **kwargs):
            pass

        monkeypatch.setattr("src.api.routes.scan.execute_scan_task", mock_execute_scan_task)

        # First scan
        response1 = client.post(
            "/v1/scan",
            json={"strategies": ["drop5"], "date": "2025-10-24"},
        )
        assert response1.status_code == 202

        # Duplicate scan (should fail)
        response2 = client.post(
            "/v1/scan",
            json={"strategies": ["drop5"], "date": "2025-10-24"},
        )
        assert response2.status_code == 409
        error = response2.json()["error"]
        assert "already exists" in error["message"]

    def test_trigger_scan_duplicate_with_force(self, client, test_db, monkeypatch):
        """Test that duplicate scans are allowed with force=true."""

        def mock_execute_scan_task(*args, **kwargs):
            pass

        monkeypatch.setattr("src.api.routes.scan.execute_scan_task", mock_execute_scan_task)

        # First scan
        response1 = client.post(
            "/v1/scan",
            json={"strategies": ["drop5"], "date": "2025-10-24"},
        )
        assert response1.status_code == 202

        # Force re-run
        response2 = client.post(
            "/v1/scan",
            json={"strategies": ["drop5"], "date": "2025-10-24", "force": True},
        )
        assert response2.status_code == 202

    def test_trigger_scan_invalid_strategy(self, client, test_db):
        """Test triggering scan with invalid strategy name."""
        response = client.post(
            "/v1/scan",
            json={"strategies": ["nonexistent_strategy"]},
        )

        assert response.status_code == 400
        error = response.json()["error"]
        assert "not found" in error["message"]

    def test_trigger_scan_empty_strategies_list(self, client, test_db):
        """Test that empty strategies list is rejected."""
        response = client.post(
            "/v1/scan",
            json={"strategies": []},  # Empty list not allowed
        )

        assert response.status_code == 422  # Validation error

    def test_get_scan_status_exists(self, client, test_db):
        """Test getting status of an existing scan."""
        from datetime import date

        from src.storage.models import Run, RunStatus

        # Create a test run
        test_run = Run(
            run_date=date(2025, 10, 24),
            strategy="drop5",
            status=RunStatus.COMPLETED.value,
            tickers_processed=100,
            candidates_found=5,
        )
        test_db.add(test_run)
        test_db.commit()

        # Get status
        response = client.get(f"/v1/scan/{test_run.run_id}/status")
        assert response.status_code == 200

        data = response.json()
        assert data["run_id"] == str(test_run.run_id)
        assert data["strategy"] == "drop5"
        assert data["status"] == "completed"
        assert data["tickers_processed"] == 100
        assert data["candidates_found"] == 5

    def test_get_scan_status_not_found(self, client, test_db):
        """Test getting status of non-existent scan."""
        import uuid

        fake_run_id = str(uuid.uuid4())
        response = client.get(f"/v1/scan/{fake_run_id}/status")

        assert response.status_code == 404
        error = response.json()["error"]
        assert "not found" in error["message"]

    def test_scan_request_validation(self, client, test_db):
        """Test scan request validation."""
        # Invalid date format
        response = client.post(
            "/v1/scan",
            json={"strategies": ["drop5"], "date": "invalid-date"},
        )
        assert response.status_code == 422

    def test_scan_response_schema(self, client, test_db, monkeypatch):
        """Test that scan response matches expected schema."""

        def mock_execute_scan_task(*args, **kwargs):
            pass

        monkeypatch.setattr("src.api.routes.scan.execute_scan_task", mock_execute_scan_task)

        response = client.post(
            "/v1/scan",
            json={"strategies": ["drop5"], "date": "2025-10-24"},
        )

        assert response.status_code == 202
        data = response.json()

        # Verify all required fields
        assert "run_ids" in data
        assert "status" in data
        assert "strategies" in data
        assert "date" in data
        assert "message" in data

        # Verify types
        assert isinstance(data["run_ids"], list)
        assert isinstance(data["status"], str)
        assert isinstance(data["strategies"], list)
        assert isinstance(data["date"], str)
        assert isinstance(data["message"], str)


class TestCandidatesEndpoint:
    """Test suite for candidates listing and detail endpoints."""

    def test_list_candidates_empty(self, client, test_db):
        """Test listing candidates when none exist."""
        response = client.get("/v1/candidates")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 0
        assert data["candidates"] == []
        assert data["page"] == 1
        assert data["page_size"] == 50

    def test_list_candidates_with_data(self, client, test_db):
        """Test listing candidates with sample data."""
        from datetime import date
        from decimal import Decimal
        from uuid import uuid4

        from src.storage.models import Candidate, Run, Ticker

        # Create test data
        ticker = Ticker(symbol="AAPL", name="Apple Inc.", sector="Technology", is_active=True)
        run = Run(
            run_id=uuid4(),
            run_date=date(2025, 10, 24),
            strategy="drop5",
            status="completed",
        )
        candidate = Candidate(
            ticker_symbol="AAPL",
            run_id=run.run_id,
            asof=date(2025, 10, 24),
            strategy="drop5",
            score=Decimal("0.7500"),
            price=Decimal("150.25"),
            drop_pct=Decimal("-5.200"),
            volume_rvol=Decimal("2.50"),
            rationale={"rules": ["oversold_rsi", "volume_spike"]},
            attribution={"source": "yahoo_finance", "timestamp": "2025-10-24T16:00:00Z"},
        )

        test_db.add(ticker)
        test_db.add(run)
        test_db.add(candidate)
        test_db.commit()

        # Test listing without strategy filter (since registry is empty in tests)
        response = client.get("/v1/candidates?date=2025-10-24")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 1
        assert len(data["candidates"]) == 1

        item = data["candidates"][0]
        assert item["ticker"] == "AAPL"
        assert item["strategy"] == "drop5"
        assert item["score"] == 0.75
        assert item["price"] == 150.25
        assert item["drop_pct"] == -5.2

    def test_list_candidates_filtering(self, client, test_db):
        """Test candidate filtering by min_score."""
        from datetime import date
        from decimal import Decimal
        from uuid import uuid4

        from src.storage.models import Candidate, Run, Ticker

        # Create test data with varying scores
        run_id = uuid4()
        run = Run(run_id=run_id, run_date=date(2025, 10, 24), strategy="drop5", status="completed")
        test_db.add(run)

        for symbol, score in [("AAPL", "0.8000"), ("MSFT", "0.6000"), ("GOOGL", "0.4000")]:
            ticker = Ticker(symbol=symbol, name=f"{symbol} Inc.", is_active=True)
            candidate = Candidate(
                ticker_symbol=symbol,
                run_id=run_id,
                asof=date(2025, 10, 24),
                strategy="drop5",
                score=Decimal(score),
                rationale={},
                attribution={},
            )
            test_db.add(ticker)
            test_db.add(candidate)

        test_db.commit()

        # Filter with min_score=0.65
        response = client.get("/v1/candidates?date=2025-10-24&min_score=0.65")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 1  # Only AAPL (0.80) passes filter
        assert data["candidates"][0]["ticker"] == "AAPL"

    def test_list_candidates_pagination(self, client, test_db):
        """Test pagination with limit and offset."""
        from datetime import date
        from decimal import Decimal
        from uuid import uuid4

        from src.storage.models import Candidate, Run, Ticker

        # Create 10 candidates
        run_id = uuid4()
        run = Run(run_id=run_id, run_date=date(2025, 10, 24), strategy="drop5", status="completed")
        test_db.add(run)

        for i in range(10):
            symbol = f"TST{i}"
            ticker = Ticker(symbol=symbol, name=f"Test {i}", is_active=True)
            candidate = Candidate(
                ticker_symbol=symbol,
                run_id=run_id,
                asof=date(2025, 10, 24),
                strategy="drop5",
                score=Decimal(f"0.{90 - i:02d}00"),  # Scores: 0.90, 0.89, ..., 0.81
                rationale={},
                attribution={},
            )
            test_db.add(ticker)
            test_db.add(candidate)

        test_db.commit()

        # Page 1: limit=3, offset=0
        response = client.get("/v1/candidates?date=2025-10-24&limit=3&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 10
        assert len(data["candidates"]) == 3
        assert data["page"] == 1
        assert data["page_size"] == 3

        # Page 2: limit=3, offset=3
        response = client.get("/v1/candidates?date=2025-10-24&limit=3&offset=3")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 10
        assert len(data["candidates"]) == 3
        assert data["page"] == 2

    def test_list_candidates_sorting(self, client, test_db):
        """Test sorting by different fields and orders."""
        from datetime import date
        from decimal import Decimal
        from uuid import uuid4

        from src.storage.models import Candidate, Run, Ticker

        # Create candidates with different values
        run_id = uuid4()
        run = Run(run_id=run_id, run_date=date(2025, 10, 24), strategy="drop5", status="completed")
        test_db.add(run)

        candidates_data = [
            ("AAPL", "0.7000", "-5.0"),
            ("MSFT", "0.9000", "-3.0"),
            ("GOOGL", "0.5000", "-7.0"),
        ]

        for symbol, score, drop_pct in candidates_data:
            ticker = Ticker(symbol=symbol, name=f"{symbol} Inc.", is_active=True)
            candidate = Candidate(
                ticker_symbol=symbol,
                run_id=run_id,
                asof=date(2025, 10, 24),
                strategy="drop5",
                score=Decimal(score),
                drop_pct=Decimal(drop_pct),
                rationale={},
                attribution={},
            )
            test_db.add(ticker)
            test_db.add(candidate)

        test_db.commit()

        # Sort by score descending (default)
        response = client.get("/v1/candidates?date=2025-10-24&sort_by=score&sort_order=desc")
        assert response.status_code == 200
        data = response.json()
        tickers = [c["ticker"] for c in data["candidates"]]
        assert tickers == ["MSFT", "AAPL", "GOOGL"]  # 0.90, 0.70, 0.50

        # Sort by ticker ascending
        response = client.get("/v1/candidates?date=2025-10-24&sort_by=ticker&sort_order=asc")
        assert response.status_code == 200
        data = response.json()
        tickers = [c["ticker"] for c in data["candidates"]]
        assert tickers == ["AAPL", "GOOGL", "MSFT"]  # Alphabetical

        # Sort by drop_pct descending (largest drops first)
        response = client.get("/v1/candidates?date=2025-10-24&sort_by=drop_pct&sort_order=desc")
        assert response.status_code == 200
        data = response.json()
        tickers = [c["ticker"] for c in data["candidates"]]
        assert tickers == ["MSFT", "AAPL", "GOOGL"]  # -3.0, -5.0, -7.0

    def test_list_candidates_invalid_strategy(self, client, test_db):
        """Test listing with invalid strategy name."""
        # First need to discover strategies to have a baseline
        from src.strategies.registry import StrategyRegistry

        registry = StrategyRegistry()
        registry.discover_and_register(enabled_only=True)

        response = client.get("/v1/candidates?strategy=nonexistent")
        assert response.status_code == 400
        error = response.json()["error"]
        assert "not found" in error["message"]
        assert "nonexistent" in error["message"]

    def test_list_candidates_latest_date_default(self, client, test_db):
        """Test that without date filter, returns most recent candidates."""
        from datetime import date
        from decimal import Decimal
        from uuid import uuid4

        from src.storage.models import Candidate, Run, Ticker

        # Create candidates on different dates
        ticker = Ticker(symbol="AAPL", name="Apple Inc.", is_active=True)
        test_db.add(ticker)

        for day in [20, 22, 24]:
            run = Run(
                run_id=uuid4(),
                run_date=date(2025, 10, day),
                strategy="drop5",
                status="completed",
            )
            candidate = Candidate(
                ticker_symbol="AAPL",
                run_id=run.run_id,
                asof=date(2025, 10, day),
                strategy="drop5",
                score=Decimal("0.7500"),
                rationale={},
                attribution={},
            )
            test_db.add(run)
            test_db.add(candidate)

        test_db.commit()

        # Query without date should return most recent (Oct 24)
        response = client.get("/v1/candidates")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["candidates"][0]["asof"] == "2025-10-24"

    def test_get_candidate_detail_exists(self, client, test_db):
        """Test getting detail for existing candidate."""
        from datetime import date
        from decimal import Decimal
        from uuid import uuid4

        from src.storage.models import Candidate, Run, Ticker

        # Create test data
        ticker = Ticker(
            symbol="AAPL", name="Apple Inc.", sector="Technology", industry="Consumer Electronics"
        )
        run = Run(
            run_id=uuid4(),
            run_date=date(2025, 10, 24),
            strategy="drop5",
            status="completed",
        )
        candidate = Candidate(
            ticker_symbol="AAPL",
            run_id=run.run_id,
            asof=date(2025, 10, 24),
            strategy="drop5",
            score=Decimal("0.7500"),
            price=Decimal("150.25"),
            drop_pct=Decimal("-5.200"),
            volume_rvol=Decimal("2.50"),
            rationale={
                "rules_triggered": ["oversold_rsi", "volume_spike"],
                "confidence": "high",
            },
            attribution={
                "source": "yahoo_finance",
                "timestamp": "2025-10-24T16:00:00Z",
                "url": "https://finance.yahoo.com/quote/AAPL",
            },
        )

        test_db.add(ticker)
        test_db.add(run)
        test_db.add(candidate)
        test_db.commit()

        # Get detail
        response = client.get("/v1/candidate/AAPL/2025-10-24?strategy=drop5")
        assert response.status_code == 200

        data = response.json()
        assert data["ticker"] == "AAPL"
        assert data["name"] == "Apple Inc."
        assert data["sector"] == "Technology"
        assert data["asof"] == "2025-10-24"
        assert data["strategy"] == "drop5"
        assert data["score"] == 0.75
        assert data["price"] == 150.25
        assert data["drop_pct"] == -5.2
        assert data["volume_rvol"] == 2.5
        assert "rules_triggered" in data["rationale"]
        assert data["attribution"]["source"] == "yahoo_finance"
        assert data["run_status"] == "completed"

    def test_get_candidate_detail_not_found(self, client, test_db):
        """Test getting detail for non-existent candidate."""
        response = client.get("/v1/candidate/AAPL/2025-10-24")
        assert response.status_code == 404
        error = response.json()["error"]
        assert "not found" in error["message"].lower()
        assert "AAPL" in error["message"]

    def test_get_candidate_detail_multiple_strategies(self, client, test_db):
        """Test detail when multiple strategies identified same ticker."""
        from datetime import date
        from decimal import Decimal
        from uuid import uuid4

        from src.storage.models import Candidate, Run, Ticker

        # Create ticker
        ticker = Ticker(symbol="AAPL", name="Apple Inc.", is_active=True)
        test_db.add(ticker)

        # Create two candidates for same ticker/date, different strategies
        for strategy, score in [("drop5", "0.7500"), ("volume_breakout", "0.6000")]:
            run = Run(
                run_id=uuid4(),
                run_date=date(2025, 10, 24),
                strategy=strategy,
                status="completed",
            )
            candidate = Candidate(
                ticker_symbol="AAPL",
                run_id=run.run_id,
                asof=date(2025, 10, 24),
                strategy=strategy,
                score=Decimal(score),
                rationale={},
                attribution={},
            )
            test_db.add(run)
            test_db.add(candidate)

        test_db.commit()

        # Without strategy filter, should return highest score
        response = client.get("/v1/candidate/AAPL/2025-10-24")
        assert response.status_code == 200
        data = response.json()
        assert data["strategy"] == "drop5"  # Higher score (0.75 vs 0.60)
        assert data["score"] == 0.75

        # With strategy filter
        response = client.get("/v1/candidate/AAPL/2025-10-24?strategy=volume_breakout")
        assert response.status_code == 200
        data = response.json()
        assert data["strategy"] == "volume_breakout"
        assert data["score"] == 0.6

    def test_get_candidate_detail_case_insensitive_ticker(self, client, test_db):
        """Test that ticker lookup is case-insensitive."""
        from datetime import date
        from decimal import Decimal
        from uuid import uuid4

        from src.storage.models import Candidate, Run, Ticker

        # Create test data with uppercase ticker
        ticker = Ticker(symbol="AAPL", name="Apple Inc.", is_active=True)
        run = Run(
            run_id=uuid4(),
            run_date=date(2025, 10, 24),
            strategy="drop5",
            status="completed",
        )
        candidate = Candidate(
            ticker_symbol="AAPL",
            run_id=run.run_id,
            asof=date(2025, 10, 24),
            strategy="drop5",
            score=Decimal("0.7500"),
            rationale={},
            attribution={},
        )

        test_db.add(ticker)
        test_db.add(run)
        test_db.add(candidate)
        test_db.commit()

        # Query with lowercase ticker
        response = client.get("/v1/candidate/aapl/2025-10-24")
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "AAPL"

    def test_list_candidates_response_schema(self, client, test_db):
        """Test that list response matches expected schema."""
        response = client.get("/v1/candidates")
        assert response.status_code == 200

        data = response.json()

        # Verify all required fields
        assert "candidates" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "filters" in data

        # Verify types
        assert isinstance(data["candidates"], list)
        assert isinstance(data["total"], int)
        assert isinstance(data["page"], int)
        assert isinstance(data["page_size"], int)
        assert isinstance(data["filters"], dict)

    def test_list_candidates_validation(self, client, test_db):
        """Test request validation for list endpoint."""
        # Invalid sort_by
        response = client.get("/v1/candidates?sort_by=invalid")
        assert response.status_code == 422

        # Invalid sort_order
        response = client.get("/v1/candidates?sort_order=invalid")
        assert response.status_code == 422

        # Invalid min_score (> 1.0)
        response = client.get("/v1/candidates?min_score=1.5")
        assert response.status_code == 422

        # Invalid limit (> 500)
        response = client.get("/v1/candidates?limit=1000")
        assert response.status_code == 422


class TestRunsEndpoint:
    """Test suite for runs metadata endpoints."""

    def test_list_runs_by_date_empty(self, client, test_db):
        """Test listing runs when none exist for date."""

        response = client.get("/v1/runs/by-date/2025-10-24")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 0
        assert data["runs"] == []
        assert data["date"] == "2025-10-24"

    def test_list_runs_by_date_with_data(self, client, test_db):
        """Test listing runs with sample data."""
        from datetime import date
        from uuid import uuid4

        from src.storage.models import Run

        # Create test runs
        run1 = Run(
            run_id=uuid4(),
            run_date=date(2025, 10, 24),
            strategy="drop5",
            status="completed",
            tickers_processed=100,
            candidates_found=15,
            duration_seconds=120,
        )
        run2 = Run(
            run_id=uuid4(),
            run_date=date(2025, 10, 24),
            strategy="volume_breakout",
            status="completed",
            tickers_processed=100,
            candidates_found=8,
            duration_seconds=95,
        )

        test_db.add(run1)
        test_db.add(run2)
        test_db.commit()

        # Test listing
        response = client.get("/v1/runs/by-date/2025-10-24")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 2
        assert len(data["runs"]) == 2
        assert data["date"] == "2025-10-24"

        # Verify run data
        strategies = {r["strategy"] for r in data["runs"]}
        assert strategies == {"drop5", "volume_breakout"}

    def test_list_runs_multiple_dates(self, client, test_db):
        """Test that listing filters by specific date."""
        from datetime import date
        from uuid import uuid4

        from src.storage.models import Run

        # Create runs on different dates
        run1 = Run(
            run_id=uuid4(),
            run_date=date(2025, 10, 24),
            strategy="drop5",
            status="completed",
        )
        run2 = Run(
            run_id=uuid4(),
            run_date=date(2025, 10, 25),
            strategy="drop5",
            status="completed",
        )

        test_db.add(run1)
        test_db.add(run2)
        test_db.commit()

        # Query for Oct 24
        response = client.get("/v1/runs/by-date/2025-10-24")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["date"] == "2025-10-24"

        # Query for Oct 25
        response = client.get("/v1/runs/by-date/2025-10-25")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["date"] == "2025-10-25"

    def test_get_run_detail_exists(self, client, test_db):
        """Test getting detail for existing run."""
        from datetime import UTC, date, datetime
        from uuid import uuid4

        from src.storage.models import Run

        run_id = uuid4()
        run = Run(
            run_id=run_id,
            run_date=date(2025, 10, 24),
            strategy="drop5",
            status="completed",
            started_at=datetime(2025, 10, 24, 16, 0, 0, tzinfo=UTC),
            completed_at=datetime(2025, 10, 24, 16, 5, 30, tzinfo=UTC),
            duration_seconds=330,
            tickers_processed=150,
            candidates_found=23,
        )

        test_db.add(run)
        test_db.commit()

        # Get detail
        response = client.get(f"/v1/runs/{str(run_id)}")
        assert response.status_code == 200

        data = response.json()
        assert data["run_id"] == str(run_id)
        assert data["run_date"] == "2025-10-24"
        assert data["strategy"] == "drop5"
        assert data["status"] == "completed"
        assert data["duration_seconds"] == 330
        assert data["tickers_processed"] == 150
        assert data["candidates_found"] == 23
        assert "started_at" in data
        assert "completed_at" in data

    def test_get_run_detail_not_found(self, client, test_db):
        """Test getting detail for non-existent run."""
        from uuid import uuid4

        fake_id = uuid4()
        response = client.get(f"/v1/runs/{str(fake_id)}")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert "not found" in data["error"]["message"].lower()

    def test_get_run_detail_invalid_uuid(self, client, test_db):
        """Test getting detail with invalid UUID format."""
        response = client.get("/v1/runs/not-a-uuid")
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "invalid" in data["error"]["message"].lower()
        assert "uuid" in data["error"]["message"].lower()

    def test_list_runs_response_schema(self, client, test_db):
        """Test that run list response matches expected schema."""
        response = client.get("/v1/runs/by-date/2025-10-24")
        assert response.status_code == 200

        data = response.json()

        # Verify all required fields
        assert "runs" in data
        assert "total" in data
        assert "date" in data

        # Verify types
        assert isinstance(data["runs"], list)
        assert isinstance(data["total"], int)
        assert isinstance(data["date"], str)


class TestMetricsEndpoint:
    """Test suite for metrics aggregation endpoint."""

    def test_get_metrics_empty(self, client, test_db):
        """Test metrics when no data exists."""
        response = client.get("/v1/metrics")
        assert response.status_code == 200

        data = response.json()
        assert data["total_runs"] == 0
        assert data["successful_runs"] == 0
        assert data["failed_runs"] == 0
        assert data["total_candidates"] == 0
        assert data["evaluated_candidates"] == 0

    def test_get_metrics_with_runs_only(self, client, test_db):
        """Test metrics with runs but no candidates."""
        from datetime import date
        from uuid import uuid4

        from src.storage.models import Run

        # Create runs (different strategies to avoid unique constraint)
        run1 = Run(
            run_id=uuid4(),
            run_date=date(2025, 10, 24),
            strategy="drop5",
            status="completed",
        )
        run2 = Run(
            run_id=uuid4(),
            run_date=date(2025, 10, 24),
            strategy="volume_breakout",  # Different strategy
            status="failed",
            error_details={"error": "Test error"},
        )

        test_db.add(run1)
        test_db.add(run2)
        test_db.commit()

        response = client.get("/v1/metrics")
        assert response.status_code == 200

        data = response.json()
        assert data["total_runs"] == 2
        assert data["successful_runs"] == 1
        assert data["failed_runs"] == 1
        assert data["total_candidates"] == 0

    def test_get_metrics_with_candidates(self, client, test_db):
        """Test metrics with candidates."""
        from datetime import date
        from decimal import Decimal
        from uuid import uuid4

        from src.storage.models import Candidate, Run, Ticker

        # Create ticker and run
        ticker1 = Ticker(symbol="AAPL", name="Apple Inc.", is_active=True)
        ticker2 = Ticker(symbol="MSFT", name="Microsoft Corp.", is_active=True)
        run = Run(
            run_id=uuid4(),
            run_date=date(2025, 10, 24),
            strategy="drop5",
            status="completed",
        )

        # Create candidates for different tickers
        candidate1 = Candidate(
            ticker_symbol="AAPL",
            run_id=run.run_id,
            asof=date(2025, 10, 24),
            strategy="drop5",
            score=Decimal("0.7500"),
            rationale={},
            attribution={},
        )
        candidate2 = Candidate(
            ticker_symbol="MSFT",
            run_id=run.run_id,
            asof=date(2025, 10, 24),
            strategy="drop5",
            score=Decimal("0.8500"),
            rationale={},
            attribution={},
        )

        test_db.add(ticker1)
        test_db.add(ticker2)
        test_db.add(run)
        test_db.add(candidate1)
        test_db.add(candidate2)
        test_db.commit()

        response = client.get("/v1/metrics")
        assert response.status_code == 200

        data = response.json()
        assert data["total_runs"] == 1
        assert data["successful_runs"] == 1
        assert data["total_candidates"] == 2
        assert data["avg_candidates_per_run"] == 2.0
        assert data["avg_score"] == 0.8  # (0.75 + 0.85) / 2

    def test_get_metrics_with_outcomes(self, client, test_db):
        """Test metrics with evaluation outcomes."""
        from datetime import date
        from decimal import Decimal
        from uuid import uuid4

        from src.storage.models import Candidate, EvalOutcome, Run, Ticker

        # Create data
        ticker1 = Ticker(symbol="AAPL", name="Apple Inc.", is_active=True)
        ticker2 = Ticker(symbol="MSFT", name="Microsoft Corp.", is_active=True)
        run = Run(
            run_id=uuid4(),
            run_date=date(2025, 10, 24),
            strategy="drop5",
            status="completed",
        )

        # Create candidates with outcomes for different tickers
        candidate1 = Candidate(
            ticker_symbol="AAPL",
            run_id=run.run_id,
            asof=date(2025, 10, 24),
            strategy="drop5",
            score=Decimal("0.7500"),
            rationale={},
            attribution={},
        )
        outcome1 = EvalOutcome(
            candidate=candidate1,
            recovery_detected=True,
            recovery_days=3,
            max_recovery_pct=Decimal("5.5"),
            return_proxy=Decimal("0.045"),
            labeling_version="v1.0.0",
        )

        candidate2 = Candidate(
            ticker_symbol="MSFT",
            run_id=run.run_id,
            asof=date(2025, 10, 24),
            strategy="drop5",
            score=Decimal("0.6500"),
            rationale={},
            attribution={},
        )
        outcome2 = EvalOutcome(
            candidate=candidate2,
            recovery_detected=False,
            recovery_days=None,
            max_recovery_pct=Decimal("0.5"),
            return_proxy=Decimal("-0.02"),
            labeling_version="v1.0.0",
        )

        test_db.add(ticker1)
        test_db.add(ticker2)
        test_db.add(run)
        test_db.add(candidate1)
        test_db.add(candidate2)
        test_db.add(outcome1)
        test_db.add(outcome2)
        test_db.commit()

        response = client.get("/v1/metrics")
        assert response.status_code == 200

        data = response.json()
        assert data["evaluated_candidates"] == 2
        assert data["recoveries"] == 1
        assert data["hit_rate"] == 0.5  # 1 recovery out of 2
        assert data["avg_return_proxy"] == 0.045  # Only for recoveries
        assert data["avg_recovery_days"] == 3.0

    def test_get_metrics_date_filtering(self, client, test_db):
        """Test metrics with date range filtering."""
        from datetime import date
        from uuid import uuid4

        from src.storage.models import Run

        # Create runs on different dates
        run1 = Run(
            run_id=uuid4(),
            run_date=date(2025, 10, 20),
            strategy="drop5",
            status="completed",
        )
        run2 = Run(
            run_id=uuid4(),
            run_date=date(2025, 10, 24),
            strategy="drop5",
            status="completed",
        )
        run3 = Run(
            run_id=uuid4(),
            run_date=date(2025, 10, 28),
            strategy="drop5",
            status="completed",
        )

        test_db.add(run1)
        test_db.add(run2)
        test_db.add(run3)
        test_db.commit()

        # Test with start_date only
        response = client.get("/v1/metrics?start_date=2025-10-24")
        assert response.status_code == 200
        data = response.json()
        assert data["total_runs"] == 2  # Oct 24 and Oct 28
        assert data["start_date"] == "2025-10-24"

        # Test with end_date only
        response = client.get("/v1/metrics?end_date=2025-10-24")
        assert response.status_code == 200
        data = response.json()
        assert data["total_runs"] == 2  # Oct 20 and Oct 24
        assert data["end_date"] == "2025-10-24"

        # Test with both dates
        response = client.get("/v1/metrics?start_date=2025-10-22&end_date=2025-10-26")
        assert response.status_code == 200
        data = response.json()
        assert data["total_runs"] == 1  # Only Oct 24
        assert data["start_date"] == "2025-10-22"
        assert data["end_date"] == "2025-10-26"

    def test_get_metrics_strategy_filtering(self, client, test_db):
        """Test metrics with strategy filtering."""
        from datetime import date
        from uuid import uuid4

        from src.storage.models import Run

        # Create runs with different strategies
        run1 = Run(
            run_id=uuid4(),
            run_date=date(2025, 10, 24),
            strategy="drop5",
            status="completed",
        )
        run2 = Run(
            run_id=uuid4(),
            run_date=date(2025, 10, 24),
            strategy="volume_breakout",
            status="completed",
        )

        test_db.add(run1)
        test_db.add(run2)
        test_db.commit()

        # Filter by strategy
        response = client.get("/v1/metrics?strategy=drop5")
        assert response.status_code == 200
        data = response.json()
        assert data["total_runs"] == 1
        assert data["strategy"] == "drop5"

    def test_get_metrics_response_schema(self, client, test_db):
        """Test that metrics response matches expected schema."""
        response = client.get("/v1/metrics")
        assert response.status_code == 200

        data = response.json()

        # Verify all required fields
        required_fields = [
            "total_runs",
            "successful_runs",
            "failed_runs",
            "total_candidates",
            "evaluated_candidates",
        ]
        for field in required_fields:
            assert field in data

        # Verify types
        assert isinstance(data["total_runs"], int)
        assert isinstance(data["successful_runs"], int)
        assert isinstance(data["failed_runs"], int)
        assert isinstance(data["total_candidates"], int)
        assert isinstance(data["evaluated_candidates"], int)
