# AI Agent Guide - Recover-Bot Project

**Purpose**: This document provides AI coding agents with comprehensive context, structure, and guidelines to work autonomously on the Recover-Bot project.

**Last Updated**: October 24, 2025
**Project Phase**: Initial Development (Pre-MVP)

---

## Quick Reference

### Essential Commands

```bash
# Setup
make install                 # Install all dependencies
make db-up                   # Start PostgreSQL container
make db-migrate              # Run database migrations

# Development
make dev                     # Start FastAPI dev server (http://localhost:8000)
make db-reset                # Reset database (destructive!)

# Testing & Quality
make test                    # Run test suite
make test-cov                # Run tests with coverage report
make lint                    # Run linters (ruff, mypy)
make format                  # Format code (black, ruff)

# Operations
make scan                    # Run one-shot scan
make backfill                # Run backfill for historical data

# Utilities
make help                    # Show all available commands
make clean                   # Clean temporary files
```

### VS Code Integration

The project includes full VS Code integration for one-click development. All configuration files are in `.vscode/`:

**One-Click Launch** (Press **F5**):

- Automatically starts PostgreSQL container
- Runs database migrations
- Launches FastAPI with debugger attached
- Sets breakpoints anywhere in `src/`
- Hot-reload on code changes
- API available at http://localhost:8000
- Swagger docs at http://localhost:8000/docs

**Keyboard Shortcuts**:

- **F5** - Start Debugging (Full Stack)
- **Shift+F5** - Stop Debugging
- **Ctrl+Shift+F5** - Restart Debugging
- **Ctrl+Shift+D** - Open Debug Panel
- **Ctrl+Shift+B** - Run Build Task (Start Full Stack)
- **Ctrl+Shift+P** → "Tasks: Run Task" - Show all available tasks

**Available Tasks** (Terminal > Run Task or Ctrl+Shift+P):

```
Database Management:
- Start PostgreSQL       - Launch postgres:15 container
- Stop PostgreSQL        - Stop postgres container
- Run Migrations         - Apply alembic migrations

Development:
- Start Dev Server       - Run FastAPI with hot-reload (no debugger)
- Start Full Stack       - Sequential: PostgreSQL → Migrations

Testing & Quality:
- Run Tests              - Execute pytest test suite
- Run Tests with Coverage- Tests with coverage report (htmlcov/)
- Lint Code              - Run ruff + mypy
- Format Code            - Run black + ruff formatter

Operations:
- One-Shot Scan          - Trigger manual scan (scripts/one_shot_scan.py)
- Backfill Data          - Run historical backfill (scripts/backfill.py)
```

**Debug Configurations** (.vscode/launch.json):

1. **🚀 Full Stack (F5)** - Compound configuration (recommended)
   - Pre-launch task: Start Full Stack (DB + migrations)
   - Launches FastAPI with debugger
   - Use this for normal development
2. **FastAPI Debug Server** - API debugging only (assumes DB running)
3. **Python: Debug Current File** - Debug any Python file
4. **Debug Tests** - Debug pytest tests with breakpoints
5. **Debug One-Shot Scan** - Debug scan script
6. **Debug Backfill** - Debug backfill script

**Settings** (.vscode/settings.json):

- **Formatting**: Black (line-length: 100), format-on-save enabled
- **Linting**: Ruff (fast Python linter) + Mypy (type checker)
- **Testing**: Pytest with auto-discovery in `tests/`
- **Python Interpreter**: Uses workspace venv if available
- **Editor**: Rulers at 100 chars, trim trailing whitespace

**Tips**:

- Use **"Start Dev Server"** task for development without debugging (faster startup)
- Use **"Run Tests with Coverage"** to see coverage report in `htmlcov/index.html`
- SQLTools extension lets you browse database schema and run queries
- Format-on-save is enabled, but you can manually format with Shift+Alt+F

### Using Context7 MCP Server for Documentation

**IMPORTANT**: This workspace has the **Context7 MCP server** (Upstash) enabled for retrieving up-to-date library documentation.

**When to Use Context7:**

- Need current documentation for FastAPI, SQLAlchemy, Alembic, Pydantic, etc.
- Implementing features with libraries you're less familiar with
- Want to verify API signatures or best practices
- Need code examples for specific library features
- Checking for breaking changes or new features in dependencies

**How to Use:**

1. **First**, resolve the library ID:

   ```
   Use mcp_upstash_conte_resolve-library-id with libraryName="fastapi"
   Returns: Context7-compatible ID like "/fastapi/fastapi"
   ```

2. **Then**, get documentation:
   ```
   Use mcp_upstash_conte_get-library-docs with:
   - context7CompatibleLibraryID: "/fastapi/fastapi"
   - topic: "background tasks" (optional, focuses docs)
   - tokens: 5000 (default, adjust as needed)
   ```

**Supported Libraries in This Project:**

- FastAPI - `/fastapi/fastapi` or `/tiangolo/fastapi`
- SQLAlchemy - `/sqlalchemy/sqlalchemy`
- Alembic - `/sqlalchemy/alembic`
- Pydantic - `/pydantic/pydantic`
- Pytest - `/pytest-dev/pytest`
- Ruff - `/astral-sh/ruff`
- And many more Python libraries

**Best Practices:**

- Use Context7 **before** implementing unfamiliar features
- Resolve library ID once, then reuse for multiple doc queries
- Specify `topic` parameter to get focused, relevant documentation
- Prefer Context7 over guessing API signatures or behavior
- Combine with code examples from docs for better results

**Example Workflow:**

```
User: "Implement FastAPI background tasks for scanning"
Agent:
1. Resolve library: mcp_upstash_conte_resolve-library-id("fastapi")
2. Get docs: mcp_upstash_conte_get-library-docs("/fastapi/fastapi", topic="background tasks")
3. Implement using current best practices from docs
4. Write tests
```

### Project Documentation

- **CONSTITUTION.md** - Project principles (facts-first, reproducibility, safety, etc.)
- **SPECIFICATION.md** - Requirements, scope, and success metrics
- **PLAN.md** - Technical architecture and design decisions
- **TASKS.md** - Implementation roadmap with tasks and dependencies
- **AGENTS.md** - This file (AI agent guidelines)

---

## Project Overview

### What is Recover-Bot?

A backend service that scans equity markets to identify "drop events" with high recovery probability using pluggable strategy modules. **NO TRADING in v1** - read-only analysis with shadow-mode evaluation.

### Core Principles (from CONSTITUTION.md)

1. **Facts-First Data**: All data must be attributed; LLMs only summarize, never invent
2. **Reproducibility**: Versioned data snapshots, features, and models
3. **Safety**: Read-only mode, no order placement
4. **Observability**: Structured logging, metrics, monitoring
5. **Modularity**: Pluggable strategy folders with clean interfaces
6. **Performance**: <10min to scan 1-2k tickers
7. **Simplicity First**: Rules-based MVP, ML comes later

### Tech Stack

- **Language**: Python 3.11+
- **Framework**: FastAPI (async web framework)
- **Database**: PostgreSQL 15+ with SQLAlchemy 2.0 ORM
- **Migrations**: Alembic
- **Scheduler**: APScheduler (in-process cron)
- **Config**: Pydantic Settings + YAML
- **Logging**: Structured JSON logs

---

## Project Structure

```
/workspaces/stockz/
├── CONSTITUTION.md          # Project principles
├── SPECIFICATION.md         # Requirements & scope
├── PLAN.md                  # Technical architecture
├── TASKS.md                 # Implementation tasks
├── AGENTS.md                # This file
├── README.md                # Getting started guide
│
├── pyproject.toml           # Python dependencies & project metadata
├── alembic.ini              # Alembic configuration
├── Makefile                 # Development commands
├── .env.example             # Environment variables template
├── .gitignore               # Git ignore patterns
│
├── src/                     # Main application code
│   ├── api/                 # FastAPI application
│   │   ├── main.py          # FastAPI app initialization & lifespan
│   │   ├── dependencies.py  # Dependency injection (DB session, config)
│   │   ├── background.py    # Background task management
│   │   └── routes/          # API route handlers
│   │       ├── health.py    # GET /health
│   │       ├── scan.py      # POST /scan
│   │       ├── candidates.py# GET /candidates, /candidate/{ticker}/{asof}
│   │       ├── runs.py      # GET /runs/{date}, /runs/{run_id}
│   │       └── metrics.py   # GET /metrics
│   │
│   ├── scheduler/           # APScheduler integration
│   │   ├── jobs.py          # Scheduled job definitions
│   │   └── config.py        # Scheduler setup & configuration
│   │
│   ├── strategies/          # Strategy plug-in system
│   │   ├── base.py          # StrategyProtocol interface
│   │   ├── registry.py      # Strategy registration & discovery
│   │   ├── loader.py        # Dynamic strategy loading
│   │   └── drop5/           # Example strategy: "Drop 5% Recover"
│   │       ├── implementation.py
│   │       ├── config.yml
│   │       ├── README.md
│   │       └── tests/
│   │
│   ├── datasources/         # Data adapters with attribution
│   │   ├── base.py          # Base adapter interface & Attribution model
│   │   ├── cache.py         # Caching layer (file-based with TTL)
│   │   ├── attribution.py   # Source attribution utilities
│   │   ├── prices.py        # Price data adapter (Yahoo Finance, etc.)
│   │   └── news.py          # News/sentiment adapter
│   │
│   ├── features/            # Shared feature engineering
│   │   ├── technical.py     # ATR, RSI, SMA, EMA, Bollinger Bands
│   │   ├── volume.py        # RVOL, volume patterns
│   │   ├── price_action.py  # Gaps, drops, reversals
│   │   └── versioning.py    # Feature version tracking
│   │
│   ├── scoring/             # Rules-based scoring
│   │   ├── rules.py         # Rule definitions & evaluation
│   │   ├── calibration.py   # Map rules → 0-1 probability
│   │   └── explainer.py     # Score rationale generation
│   │
│   ├── storage/             # Database layer
│   │   ├── database.py      # DB connection & session management
│   │   ├── models.py        # SQLAlchemy models (Ticker, Run, Feature, etc.)
│   │   └── migrations/      # Alembic migrations
│   │       └── versions/
│   │
│   ├── eval/                # Evaluation & backtesting
│   │   ├── labeler.py       # Recovery outcome labeling (T+1 to T+5)
│   │   ├── metrics.py       # Hit-rate, PnL proxy calculations
│   │   └── backfill.py      # Historical outcome labeling
│   │
│   ├── scanner/             # Core scanning engine
│   │   ├── engine.py        # Main scan orchestration
│   │   ├── executor.py      # Concurrent execution (asyncio/threading)
│   │   └── pipeline.py      # Data flow pipeline
│   │
│   └── ops/                 # Operations & utilities
│       ├── config.py        # Pydantic Settings configuration
│       ├── logging.py       # Structured JSON logging setup
│       ├── metrics.py       # Prometheus-style counters (optional)
│       └── errors.py        # Error handling & retry logic
│
├── tests/                   # Test suite
│   ├── unit/                # Unit tests
│   ├── integration/         # Integration tests
│   └── strategies/          # Strategy-specific tests
│
├── scripts/                 # Utility scripts
│   ├── backfill.py          # Backfill historical outcomes
│   ├── one_shot_scan.py     # Manual scan trigger
│   └── db_seed.py           # Database seeding for development
│
├── config/                  # Configuration files
│   ├── config.yaml          # Main application configuration
│   ├── logging.yaml         # Logging configuration
│   └── strategies.yaml      # Enabled strategies list
│
├── docker/                  # Docker configuration
│   ├── Dockerfile           # FastAPI service container
│   └── docker-compose.yaml  # Postgres + API services
│
├── docs/                    # Documentation
│   ├── api.md               # API documentation
│   ├── database.md          # Database schema & ERD
│   ├── strategies.md        # Strategy development guide
│   └── deployment.md        # Deployment guide
│
├── data/                    # Data storage (gitignored)
│   ├── cache/               # Cached API responses
│   └── snapshots/           # Versioned data snapshots
│
└── logs/                    # Application logs (gitignored)
```

---

## Coding Conventions

### Python Style

- **Formatter**: Black (line length: 100)
- **Linter**: Ruff (extends flake8, pylint)
- **Type Checker**: Mypy with strict mode
- **Import Order**: isort (built into ruff)
- **Docstrings**: Google style

### Naming Conventions

```python
# Files & Modules
file_name.py                 # Snake case

# Classes
class StrategyProtocol:      # PascalCase
    pass

# Functions & Variables
def calculate_atr():         # Snake case
    max_value = 100          # Snake case

# Constants
MAX_RETRIES = 3              # UPPER_SNAKE_CASE
DEFAULT_TIMEOUT = 30

# Private/Internal
def _internal_helper():      # Leading underscore
    _temp_var = 1
```

### Type Hints

**Always use type hints** for function signatures:

```python
from typing import Dict, List, Optional, Any
from datetime import date, datetime

def get_bars(
    ticker: str,
    window: int,
    start_date: Optional[date] = None
) -> Dict[str, Any]:
    """Fetch OHLCV bars for a ticker."""
    ...
```

### Error Handling

```python
# Use specific exceptions
from src.ops.errors import DataSourceError, ConfigurationError

# Add context to errors
try:
    data = fetch_data(ticker)
except requests.HTTPError as e:
    raise DataSourceError(
        f"Failed to fetch data for {ticker}: {e}",
        ticker=ticker,
        source="yahoo_finance"
    ) from e

# Use retry decorator for transient failures
from src.ops.errors import retry_on_failure

@retry_on_failure(max_attempts=3, backoff=2.0)
def fetch_remote_data():
    ...
```

### Logging

```python
from src.ops.logging import get_logger

logger = get_logger(__name__)

# Structured logging with context
logger.info(
    "Scan completed",
    extra={
        "run_id": run_id,
        "tickers_processed": count,
        "duration_seconds": duration,
        "strategy": strategy_name
    }
)

# Use appropriate log levels
logger.debug("Detailed debugging info")
logger.info("Normal operational events")
logger.warning("Warning conditions")
logger.error("Error events", exc_info=True)
logger.critical("Critical failures")
```

### Database Operations

```python
from src.storage.database import get_db
from src.storage.models import Candidate
from sqlalchemy.orm import Session

# Use dependency injection in FastAPI
async def get_candidates(
    db: Session = Depends(get_db)
) -> List[Candidate]:
    return db.query(Candidate).all()

# Always use context managers for sessions
from src.storage.database import SessionLocal

with SessionLocal() as session:
    candidate = session.query(Candidate).first()
    session.commit()
```

### Configuration Access

```python
from src.ops.config import get_config

config = get_config()

# Access nested config
db_url = config.database.url
cron_schedule = config.scheduler.cron
api_key = config.datasources.prices.api_key
```

---

## Key Interfaces & Contracts

### Strategy Interface

Every strategy must implement `StrategyProtocol`:

```python
from typing import Protocol, Dict, Any

class StrategyProtocol(Protocol):
    """Interface for all strategies."""

    @property
    def name(self) -> str:
        """Unique strategy identifier (slug)."""
        ...

    @property
    def version(self) -> str:
        """Strategy version for reproducibility."""
        ...

    def filters(self, ticker_data: Dict[str, Any]) -> bool:
        """Pre-filter: Return True if ticker should be processed."""
        ...

    def features(self, ticker_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract strategy-specific features."""
        ...

    def score(self, features: Dict[str, Any]) -> float:
        """Compute recovery probability score (0.0 to 1.0)."""
        ...

    def label(
        self,
        entry_data: Dict[str, Any],
        outcome_data: Dict[str, Any]
    ) -> bool:
        """Label whether recovery occurred for evaluation."""
        ...
```

### Data Attribution

Every data point must include attribution:

```python
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class DataSource(Enum):
    YAHOO_FINANCE = "yahoo_finance"
    ALPHA_VANTAGE = "alpha_vantage"
    NEWS_API = "news_api"

@dataclass
class Attribution:
    source: DataSource
    timestamp: datetime
    url: Optional[str] = None
    api_endpoint: Optional[str] = None
    version: str = "1.0"
```

### Data Adapter Interface

```python
from typing import Protocol

class DataAdapterProtocol(Protocol):
    """Base interface for data adapters."""

    def fetch(self, *args, **kwargs) -> Any:
        """Fetch data with automatic caching and attribution."""
        ...

    def get_attribution(self) -> Attribution:
        """Return attribution metadata for last fetch."""
        ...
```

---

## Database Schema

### Core Tables

```sql
-- Ticker universe
CREATE TABLE ticker (
    symbol VARCHAR(10) PRIMARY KEY,
    name VARCHAR(255),
    sector VARCHAR(100),
    market_cap BIGINT
);

-- Scan runs
CREATE TABLE run (
    run_id UUID PRIMARY KEY,
    run_date DATE NOT NULL,
    status VARCHAR(20),
    duration_seconds INTEGER,
    tickers_processed INTEGER,
    candidates_found INTEGER
);

-- Features (versioned)
CREATE TABLE feature (
    id UUID PRIMARY KEY,
    ticker VARCHAR(10) REFERENCES ticker(symbol),
    run_id UUID REFERENCES run(run_id),
    asof DATE NOT NULL,
    strategy VARCHAR(50) NOT NULL,
    feature_version VARCHAR(20),
    features JSONB,
    attribution JSONB
);

-- Candidates
CREATE TABLE candidate (
    id UUID PRIMARY KEY,
    ticker VARCHAR(10) REFERENCES ticker(symbol),
    run_id UUID REFERENCES run(run_id),
    asof DATE NOT NULL,
    strategy VARCHAR(50),
    score DECIMAL(5,4),
    rationale JSONB,
    attribution JSONB
);

-- Evaluation outcomes
CREATE TABLE eval_outcome (
    id UUID PRIMARY KEY,
    candidate_id UUID REFERENCES candidate(id),
    recovery_detected BOOLEAN,
    recovery_days INTEGER,
    max_recovery_pct DECIMAL(6,3),
    return_proxy DECIMAL(7,4)
);
```

---

## Common Workflows

### Adding a New Strategy

1. **Create strategy folder**:

```bash
mkdir -p src/strategies/my_strategy
cd src/strategies/my_strategy
```

2. **Create `implementation.py`**:

```python
from typing import Dict, Any
from ..base import StrategyProtocol

class MyStrategy:
    name = "my_strategy"
    version = "1.0.0"

    def filters(self, ticker_data: Dict[str, Any]) -> bool:
        # Your filtering logic
        return True

    def features(self, ticker_data: Dict[str, Any]) -> Dict[str, Any]:
        # Your feature extraction
        return {}

    def score(self, features: Dict[str, Any]) -> float:
        # Your scoring logic (must return 0.0-1.0)
        return 0.5

    def label(self, entry_data: Dict[str, Any], outcome_data: Dict[str, Any]) -> bool:
        # Your outcome labeling
        return False
```

3. **Create `config.yml`**:

```yaml
name: my_strategy
version: 1.0.0
description: "Strategy description"
parameters:
  threshold: 0.6
  window: 10
enabled: true
```

4. **Add tests** in `tests/` subdirectory

5. **Restart service** - strategy auto-discovered on startup

### Running a Scan

**Via API**:

```bash
# Trigger scan
curl -X POST http://localhost:8000/v1/scan \
  -H "Content-Type: application/json" \
  -d '{"strategies": ["drop5"]}'

# Check results
curl "http://localhost:8000/v1/candidates?date=2025-10-24&strategy=drop5"
```

**Via Script**:

```bash
python scripts/one_shot_scan.py --date 2025-10-24 --strategy drop5
```

**Via Makefile**:

```bash
make scan
```

### Database Migrations

**Create new migration**:

```bash
# Auto-generate from model changes
alembic revision --autogenerate -m "add new column"

# Manual migration
alembic revision -m "custom migration"
```

**Apply migrations**:

```bash
alembic upgrade head      # Upgrade to latest
alembic upgrade +1        # Upgrade one version
alembic downgrade -1      # Downgrade one version
alembic downgrade base    # Downgrade to empty DB
```

**Check migration status**:

```bash
alembic current           # Show current version
alembic history           # Show all migrations
```

### Testing

**Run all tests**:

```bash
make test
```

**Run specific test**:

```bash
pytest tests/unit/test_features.py::test_calculate_atr -v
```

**Run with coverage**:

```bash
make test-cov
# Coverage report in htmlcov/index.html
```

**Test a strategy**:

```bash
pytest tests/strategies/test_drop5.py -v
```

---

## API Endpoints Reference

### Health Check

```
GET /health
Response: {"status": "healthy", "database": "connected", "timestamp": "..."}
```

### Trigger Scan

```
POST /v1/scan
Body: {
  "strategies": ["drop5"],
  "date": "2025-10-24",  // optional, defaults to today
  "force": false          // optional, re-run even if exists
}
Response: {"run_id": "uuid", "status": "queued"}
```

### List Candidates

```
GET /v1/candidates?date=2025-10-24&strategy=drop5&min_score=0.5
Response: {
  "candidates": [
    {
      "ticker": "AAPL",
      "asof": "2025-10-24",
      "strategy": "drop5",
      "score": 0.75,
      "drop_pct": -5.2
    }
  ],
  "total": 23,
  "page": 1
}
```

### Candidate Detail

```
GET /v1/candidate/AAPL/2025-10-24?strategy=drop5
Response: {
  "ticker": "AAPL",
  "asof": "2025-10-24",
  "strategy": "drop5",
  "score": 0.75,
  "features": {...},
  "rationale": {
    "rules_triggered": ["oversold_rsi", "volume_spike"],
    "confidence_factors": [...]
  },
  "attribution": {...}
}
```

### Run Metadata

```
GET /v1/runs/2025-10-24
Response: {
  "runs": [{
    "run_id": "uuid",
    "date": "2025-10-24",
    "status": "completed",
    "duration_seconds": 480,
    "tickers_processed": 1500,
    "candidates_found": 23
  }]
}
```

### Metrics

```
GET /v1/metrics?start_date=2025-10-01&end_date=2025-10-24&strategy=drop5
Response: {
  "strategy": "drop5",
  "hit_rate": 0.68,
  "avg_return_proxy": 0.032,
  "total_candidates": 145,
  "total_recoveries": 99
}
```

---

## Environment Variables

Required environment variables (see `.env.example`):

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/recoverbot

# Data Sources
PRICE_API_KEY=your_api_key_here
NEWS_API_KEY=your_api_key_here

# Scheduler
CRON_SCHEDULE="30 16 * * *"  # Daily at 16:30 UTC
SCHEDULER_TIMEZONE=UTC
SCHEDULER_ENABLED=true

# Application
APP_DEBUG=false
LOG_LEVEL=INFO

# Scanner
UNIVERSE_SIZE=2000
CONCURRENCY=50
CACHE_TTL_SECONDS=3600
```

---

## Troubleshooting

### Docker Daemon Issues (Dev Container)

```bash
# If Docker commands fail with "Cannot connect to the Docker daemon" error:

# 1. Check if dockerd process is running
ps aux | grep dockerd

# 2. If running but connection fails, restart dockerd with explicit socket
sudo pkill dockerd
sleep 2
sudo /usr/bin/dockerd -H unix:///var/run/docker.sock > /tmp/dockerd.log 2>&1 &
sleep 5
docker ps  # Should work now

# 3. If still fails, check socket permissions
sudo chmod 666 /var/run/docker.sock

# 4. Verify Docker is working
docker version
docker ps

# Note: In dev containers, the Docker daemon can sometimes lose its socket connection
# after container restarts. The above steps will re-establish the connection.
```

### Database Connection Issues

```bash
# Check if PostgreSQL is running
docker compose ps postgres

# If container exists but stopped, start it
docker compose up -d postgres

# If image pull fails, ensure Docker daemon is running (see above)

# View PostgreSQL logs
docker compose logs postgres

# Reset database
make db-reset

# Re-run migrations
make db-migrate
```

### Import Errors

```bash
# Reinstall dependencies
make install

# Check Python path
python -c "import sys; print('\n'.join(sys.path))"
```

### Strategy Not Loading

```bash
# Check strategy folder structure
ls -la src/strategies/my_strategy/

# Must have: implementation.py, config.yml

# Check logs for discovery errors
grep "strategy" logs/app.log
```

### Scan Timeout

```bash
# Increase timeout in config/config.yaml
scanner:
  timeout_seconds: 1200  # Increase from 600

# Reduce concurrency if rate-limited
scanner:
  concurrency: 25  # Decrease from 50
```

---

## Task Completion Guidelines for AI Agents

When implementing a task:

1. **Read the relevant docs first**:

   - CONSTITUTION.md for principles
   - SPECIFICATION.md for requirements
   - PLAN.md for architecture
   - TASKS.md for task details
   - AGENTS.md (this file) for coding conventions and workflows

2. **Follow the coding conventions** above:

   - Python style (Black, Ruff, Mypy)
   - Naming conventions
   - Type hints
   - Error handling patterns
   - Logging standards

3. **Write tests alongside implementation**:

   - Unit tests in `tests/unit/`
   - Integration tests in `tests/integration/`
   - Follow existing test patterns
   - Aim for >80% code coverage

4. **Add proper logging**:

   - Use structured logging with context
   - Log at appropriate levels
   - Include relevant metadata

5. **Update documentation**:

   - Add docstrings to all functions/classes (Google style)
   - Update relevant docs/ files
   - Add usage examples
   - **Update AGENTS.md if you:**
     - Add new commands or scripts → Update "Essential Commands" or "Common Workflows"
     - Change project structure → Update "Project Structure" section
     - Introduce new conventions or patterns → Update "Coding Conventions"
     - Add new interfaces or contracts → Update "Key Interfaces & Contracts"
     - Change workflow procedures → Update "Common Workflows"
     - Add troubleshooting guidance → Update "Troubleshooting" section
     - Add new environment variables → Update "Environment Variables"
     - Change database schema → Update "Database Schema" section

6. **Validate your work**:

   - Run `make format` to format code
   - Run `make lint` (must pass with no errors)
   - Run `make test` (must pass all tests)
   - Test the actual functionality manually
   - Verify examples in AGENTS.md still work

7. **Attribution & reproducibility**:

   - Always include data attribution
   - Version all features/models
   - Make operations deterministic

8. **Before marking task complete**:
   - ✅ All acceptance criteria met
   - ✅ Tests passing (unit + integration)
   - ✅ Linters passing (ruff, mypy)
   - ✅ Code formatted (black)
   - ✅ Documentation updated (docstrings, docs/)
   - ✅ **AGENTS.md updated** (if applicable)
   - ✅ Manual testing completed
   - ✅ Examples verified

---

## Performance Considerations

### Scanning Performance

- **Target**: <10 minutes for 1,500 tickers
- **Optimization strategies**:
  - Cache aggressively (3600s TTL)
  - Batch API calls where possible
  - Use connection pooling (pool_size=10)
  - Parallelize ticker processing (concurrency=50)
  - Pre-fetch universe data
  - Use database indexes effectively

### Database Performance

- **Always use indexes** for common queries
- **Batch inserts** when possible (use `bulk_insert_mappings`)
- **Avoid N+1 queries** (use `joinedload`)
- **Use EXPLAIN ANALYZE** for slow queries

### Memory Management

- **Stream large datasets** instead of loading all at once
- **Clear caches** periodically
- **Use generators** for large result sets
- **Monitor memory usage** during scans

---

## Git Workflow

### Branch Naming

```
feature/task-1.1-project-setup
fix/scanner-timeout
docs/api-documentation
test/strategy-unit-tests
```

### Commit Messages

```
feat: implement price data adapter with caching

- Add PriceAdapter class with Yahoo Finance integration
- Implement TTL-based caching layer
- Add proper attribution for all data points
- Add unit tests with mocked responses

Closes #123
```

### Before Committing

```bash
make format      # Format code
make lint        # Run linters
make test        # Run tests
```

---

## Quick Start for AI Agents

To start working on this project:

1. **Read the context**:

   ```bash
   cat CONSTITUTION.md SPECIFICATION.md PLAN.md
   ```

2. **Setup environment**:

   ```bash
   make install
   make db-up
   make db-migrate
   ```

3. **Check current state**:

   ```bash
   # Review what's implemented
   tree src/

   # Check what works
   make test
   ```

4. **Pick a task from TASKS.md**:

   - Start with Phase 1 tasks if nothing is done
   - Check dependencies before starting
   - Read task acceptance criteria carefully

5. **Implement with TDD**:

   - Write tests first
   - Implement code
   - Run tests
   - Refactor

6. **Validate**:
   ```bash
   make lint && make test && make format
   ```

---

## Additional Resources

### External Documentation

- **FastAPI**: https://fastapi.tiangolo.com/
- **SQLAlchemy 2.0**: https://docs.sqlalchemy.org/
- **Alembic**: https://alembic.sqlalchemy.org/
- **APScheduler**: https://apscheduler.readthedocs.io/
- **Pydantic**: https://docs.pydantic.dev/

### Data Providers

- **Yahoo Finance**: https://github.com/ranaroussi/yfinance
- **Alpha Vantage**: https://www.alphavantage.co/documentation/
- **NewsAPI**: https://newsapi.org/docs

### Development Tools

- **Ruff**: https://docs.astral.sh/ruff/
- **Mypy**: https://mypy.readthedocs.io/
- **Pytest**: https://docs.pytest.org/

---

## Contact & Support

For questions about:

- **Architecture decisions**: See PLAN.md
- **Requirements**: See SPECIFICATION.md
- **Principles**: See CONSTITUTION.md
- **Implementation tasks**: See TASKS.md
- **AI agent guidelines**: This file (AGENTS.md)

---

**Remember**:

- **Facts-first**: Never invent data
- **Reproducibility**: Version everything
- **Safety**: Read-only in v1
- **Test**: Always write tests
- **Document**: Code should be self-documenting + docs

Good luck building! 🚀
