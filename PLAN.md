# Recover-Bot Technical Plan

**Version**: 1.0.0-MVP  
**Stack**: Python FastAPI, APScheduler, SQLAlchemy + Alembic, PostgreSQL  
**Architecture**: Single-service MVP

---

## Architecture Overview

### Technology Stack
- **Language**: Python 3.11+
- **Web Framework**: FastAPI
- **Database**: PostgreSQL 15+
- **ORM**: SQLAlchemy 2.0
- **Migrations**: Alembic
- **Scheduler**: APScheduler
- **Configuration**: Pydantic Settings
- **Logging**: Structured JSON logging

### Service Design
Single FastAPI service containing:
- REST API endpoints
- Background task processor
- APScheduler cron jobs
- Strategy registry and loader

---

## Project Structure

```
/workspaces/stockz/
├── src/
│   ├── api/                      # FastAPI application
│   │   ├── __init__.py
│   │   ├── main.py               # FastAPI app initialization
│   │   ├── routes/
│   │   │   ├── health.py         # GET /health
│   │   │   ├── scan.py           # POST /scan
│   │   │   ├── candidates.py     # GET /candidates, /candidate/{ticker}/{asof}
│   │   │   ├── runs.py           # GET /runs/{date}
│   │   │   └── metrics.py        # GET /metrics
│   │   ├── dependencies.py       # FastAPI dependencies (DB session, etc.)
│   │   └── background.py         # Background task management
│   │
│   ├── scheduler/                # APScheduler integration
│   │   ├── __init__.py
│   │   ├── jobs.py               # Scheduled job definitions
│   │   └── config.py             # Scheduler configuration
│   │
│   ├── strategies/               # Strategy plug-in system
│   │   ├── __init__.py
│   │   ├── base.py               # StrategyProtocol interface
│   │   ├── registry.py           # Strategy auto-discovery and registration
│   │   ├── loader.py             # Dynamic strategy loading
│   │   └── drop5/                # Strategy #1: Drop 5% Recover
│   │       ├── __init__.py
│   │       ├── config.yml        # Strategy configuration
│   │       ├── implementation.py # Strategy implementation
│   │       ├── README.md         # Strategy documentation
│   │       └── tests/            # Strategy-specific tests
│   │
│   ├── datasources/              # Data adapters with attribution
│   │   ├── __init__.py
│   │   ├── base.py               # Base adapter interface
│   │   ├── prices.py             # Price data adapter
│   │   │   # - get_universe() -> List[str]
│   │   │   # - get_bars(ticker, window) -> DataFrame
│   │   │   # - get_atr(ticker, period) -> float
│   │   ├── news.py               # News/sentiment adapter
│   │   │   # - headlines_by_ticker(ticker, days) -> List[Headline]
│   │   │   # - sentiment(headlines) -> SentimentScore
│   │   ├── cache.py              # Caching layer for API calls
│   │   └── attribution.py       # Source attribution utilities
│   │
│   ├── features/                 # Shared feature engineering
│   │   ├── __init__.py
│   │   ├── technical.py          # ATR, RSI, moving averages
│   │   ├── volume.py             # RVOL, volume patterns
│   │   ├── price_action.py       # Gaps, drops, reversals
│   │   └── versioning.py         # Feature version tracking
│   │
│   ├── scoring/                  # Rules-based scoring system
│   │   ├── __init__.py
│   │   ├── rules.py              # Rule definitions and evaluation
│   │   ├── calibration.py        # Map rules -> 0-1 probability
│   │   └── explainer.py          # Score rationale generation
│   │
│   ├── storage/                  # Database layer
│   │   ├── __init__.py
│   │   ├── database.py           # Database connection and session
│   │   ├── models.py             # SQLAlchemy models
│   │   │   # - Ticker, Run, Feature, Candidate, EvalOutcome
│   │   └── migrations/           # Alembic migrations
│   │       ├── env.py
│   │       └── versions/
│   │
│   ├── eval/                     # Evaluation and backtesting
│   │   ├── __init__.py
│   │   ├── labeler.py            # Recovery outcome labeling
│   │   ├── metrics.py            # Hit-rate, PnL proxy calculations
│   │   └── backfill.py           # Historical outcome labeling
│   │
│   ├── ops/                      # Operations and utilities
│   │   ├── __init__.py
│   │   ├── config.py             # Pydantic settings
│   │   ├── logging.py            # Structured logging setup
│   │   ├── metrics.py            # Prometheus-style counters (optional)
│   │   └── errors.py             # Error handling and retries
│   │
│   └── scanner/                  # Core scanning engine
│       ├── __init__.py
│       ├── engine.py             # Main scan orchestration
│       ├── executor.py           # Concurrent execution
│       └── pipeline.py           # Data flow pipeline
│
├── tests/                        # Test suite
│   ├── unit/
│   ├── integration/
│   └── strategies/
│
├── scripts/                      # Utility scripts
│   ├── backfill.py               # One-shot backfill runner
│   ├── one_shot_scan.py          # Manual scan trigger
│   └── db_seed.py                # Database seeding for dev
│
├── config/                       # Configuration files
│   ├── config.yaml               # Main configuration
│   ├── logging.yaml              # Logging configuration
│   └── strategies.yaml           # Enabled strategies list
│
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yaml       # Postgres + API service
│
├── docs/                         # Documentation
│   ├── api.md                    # API documentation
│   ├── database.md               # Database schema + ERD
│   ├── strategies.md             # Strategy development guide
│   └── deployment.md             # Deployment guide
│
├── Makefile                      # Common tasks
├── pyproject.toml                # Python dependencies
├── alembic.ini                   # Alembic configuration
├── README.md                     # Getting started
├── CONSTITUTION.md               # Project principles
└── SPECIFICATION.md              # Requirements spec
```

---

## API Endpoints

### 1. Health Check
```
GET /health
Response: {"status": "healthy", "database": "connected", "timestamp": "..."}
```

### 2. Trigger Scan
```
POST /scan
Body: {"strategies": ["drop5"], "force": false}
Response: {"run_id": "uuid", "status": "queued"}
```

### 3. List Candidates
```
GET /candidates?date=2025-10-24&strategy=drop5&min_score=0.5
Response: {
  "candidates": [
    {
      "ticker": "AAPL",
      "asof": "2025-10-24",
      "strategy": "drop5",
      "score": 0.75,
      "drop_pct": -5.2,
      "attribution": {...}
    }
  ]
}
```

### 4. Candidate Detail
```
GET /candidate/{ticker}/{asof}?strategy=drop5
Response: {
  "ticker": "AAPL",
  "asof": "2025-10-24",
  "strategy": "drop5",
  "score": 0.75,
  "features": {...},
  "rationale": {...},
  "attribution": {...}
}
```

### 5. Run Metadata
```
GET /runs/{date}
Response: {
  "runs": [
    {
      "run_id": "uuid",
      "date": "2025-10-24",
      "status": "completed",
      "duration_seconds": 480,
      "tickers_processed": 1500,
      "candidates_found": 23,
      "errors": 0
    }
  ]
}
```

### 6. Metrics
```
GET /metrics?start_date=2025-10-01&end_date=2025-10-24&strategy=drop5
Response: {
  "strategy": "drop5",
  "period": {...},
  "hit_rate": 0.68,
  "avg_return_proxy": 0.032,
  "total_candidates": 145,
  "total_recoveries": 99
}
```

---

## Data Flow

### 1. Daily Scheduled Scan
```
APScheduler (16:30 UTC)
  ↓
Queue Scan Job
  ↓
Universe Loader → [AAPL, MSFT, GOOGL, ...]
  ↓
Parallel Processing (asyncio/ThreadPoolExecutor)
  ↓
For each ticker:
  - Fetch price data (cached)
  - Fetch news data (cached)
  - Extract features
  - Apply strategy filters
  - Compute score
  - If score > threshold → persist Candidate
  ↓
Update Run metadata
  ↓
Trigger evaluation job (async)
```

### 2. Manual Scan Trigger
```
POST /scan
  ↓
Background Task
  ↓
Same flow as scheduled scan
  ↓
Return run_id immediately
```

### 3. Evaluation/Labeling
```
Separate job (daily at 17:00 UTC)
  ↓
Fetch yesterday's candidates
  ↓
For each candidate:
  - Fetch T+1 to T+5 price data
  - Check recovery conditions
  - Label outcome (success/failure)
  - Calculate return proxy
  ↓
Update EvalOutcome table
  ↓
Recalculate aggregate metrics
```

---

## Database Schema (PostgreSQL)

### Entity Relationship Diagram (ERD)

```
┌──────────────┐
│   Ticker     │
├──────────────┤
│ symbol PK    │
│ name         │
│ sector       │
│ market_cap   │
└──────────────┘
       │
       │ 1:N
       ↓
┌──────────────────────┐
│      Run             │
├──────────────────────┤
│ run_id PK            │
│ run_date             │
│ status               │
│ started_at           │
│ completed_at         │
│ duration_seconds     │
│ tickers_processed    │
│ candidates_found     │
│ error_count          │
│ config_snapshot JSON │
└──────────────────────┘
       │
       │ 1:N
       ↓
┌────────────────────────────┐
│      Feature               │
├────────────────────────────┤
│ id PK                      │
│ ticker FK                  │
│ run_id FK                  │
│ asof                       │
│ strategy                   │
│ feature_version            │
│ features JSON              │
│ attribution JSON           │
│ created_at                 │
├────────────────────────────┤
│ INDEX: (ticker, asof, strategy)
└────────────────────────────┘
       │
       │ 1:N
       ↓
┌────────────────────────────┐
│     Candidate              │
├────────────────────────────┤
│ id PK                      │
│ ticker FK                  │
│ run_id FK                  │
│ feature_id FK              │
│ asof                       │
│ strategy                   │
│ score                      │
│ drop_pct                   │
│ rationale JSON             │
│ attribution JSON           │
│ created_at                 │
├────────────────────────────┤
│ INDEX: (asof, strategy)    │
│ INDEX: (ticker, asof)      │
└────────────────────────────┘
       │
       │ 1:1
       ↓
┌────────────────────────────┐
│    EvalOutcome             │
├────────────────────────────┤
│ id PK                      │
│ candidate_id FK            │
│ evaluated_at               │
│ recovery_detected          │
│ recovery_days              │
│ max_recovery_pct           │
│ return_proxy               │
│ label_version              │
│ created_at                 │
└────────────────────────────┘
```

### Table Definitions

#### Ticker
```sql
CREATE TABLE ticker (
    symbol VARCHAR(10) PRIMARY KEY,
    name VARCHAR(255),
    sector VARCHAR(100),
    market_cap BIGINT,
    updated_at TIMESTAMP DEFAULT NOW()
);
```

#### Run
```sql
CREATE TABLE run (
    run_id UUID PRIMARY KEY,
    run_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL, -- queued, running, completed, failed
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds INTEGER,
    tickers_processed INTEGER,
    candidates_found INTEGER,
    error_count INTEGER DEFAULT 0,
    config_snapshot JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_run_date ON run(run_date);
```

#### Feature
```sql
CREATE TABLE feature (
    id UUID PRIMARY KEY,
    ticker VARCHAR(10) REFERENCES ticker(symbol),
    run_id UUID REFERENCES run(run_id),
    asof DATE NOT NULL,
    strategy VARCHAR(50) NOT NULL,
    feature_version VARCHAR(20) NOT NULL,
    features JSONB NOT NULL,
    attribution JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_feature_lookup ON feature(ticker, asof, strategy);
CREATE INDEX idx_feature_run ON feature(run_id);
```

#### Candidate
```sql
CREATE TABLE candidate (
    id UUID PRIMARY KEY,
    ticker VARCHAR(10) REFERENCES ticker(symbol),
    run_id UUID REFERENCES run(run_id),
    feature_id UUID REFERENCES feature(id),
    asof DATE NOT NULL,
    strategy VARCHAR(50) NOT NULL,
    score DECIMAL(5,4) NOT NULL, -- 0.0000 to 1.0000
    drop_pct DECIMAL(6,3),
    rationale JSONB,
    attribution JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_candidate_asof_strategy ON candidate(asof, strategy);
CREATE INDEX idx_candidate_ticker_asof ON candidate(ticker, asof);
CREATE INDEX idx_candidate_score ON candidate(score);
```

#### EvalOutcome
```sql
CREATE TABLE eval_outcome (
    id UUID PRIMARY KEY,
    candidate_id UUID REFERENCES candidate(id),
    evaluated_at TIMESTAMP NOT NULL,
    recovery_detected BOOLEAN NOT NULL,
    recovery_days INTEGER,
    max_recovery_pct DECIMAL(6,3),
    return_proxy DECIMAL(7,4),
    label_version VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_eval_candidate ON eval_outcome(candidate_id);
```

---

## Strategy Interface

### StrategyProtocol (base.py)

```python
from typing import Protocol, Dict, Any, List
from datetime import date

class StrategyProtocol(Protocol):
    """Interface that all strategies must implement."""

    @property
    def name(self) -> str:
        """Unique strategy identifier (slug)."""
        ...

    @property
    def version(self) -> str:
        """Strategy version for reproducibility."""
        ...

    @property
    def config_schema(self) -> Dict[str, Any]:
        """JSON schema for strategy configuration."""
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

### Strategy Auto-Discovery

Loader scans `/src/strategies/*/implementation.py` for classes implementing `StrategyProtocol`. Each strategy folder must contain:
- `implementation.py` - Strategy class
- `config.yml` - Strategy parameters
- `README.md` - Documentation

---

## Configuration Management

### config/config.yaml
```yaml
app:
  name: "recover-bot"
  version: "1.0.0"
  debug: false

database:
  url: "postgresql://user:pass@localhost:5432/recoverbot"
  pool_size: 10
  max_overflow: 20

scheduler:
  cron: "30 16 * * *"  # Daily at 16:30 UTC
  timezone: "UTC"
  enabled: true

scanner:
  universe_size: 2000
  concurrency: 50
  timeout_seconds: 600
  cache_ttl_seconds: 3600

strategies:
  enabled:
    - drop5
  score_threshold: 0.3

datasources:
  prices:
    provider: "yahoo_finance"  # or alpha_vantage, polygon
    api_key: "${PRICE_API_KEY}"
    cache_enabled: true

  news:
    provider: "news_api"
    api_key: "${NEWS_API_KEY}"
    max_headlines_per_ticker: 10
    days_lookback: 7

logging:
  level: "INFO"
  format: "json"
  file: "logs/app.log"

monitoring:
  prometheus_enabled: false
  metrics_port: 9090
```

---

## Extensibility: Adding a New Strategy

### 1. Create Strategy Folder
```bash
mkdir -p src/strategies/my_strategy
cd src/strategies/my_strategy
```

### 2. Create implementation.py
```python
from typing import Dict, Any
from ..base import StrategyProtocol

class MyStrategy(StrategyProtocol):
    name = "my_strategy"
    version = "1.0.0"

    @property
    def config_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "threshold": {"type": "number"},
                "window": {"type": "integer"}
            }
        }

    def filters(self, ticker_data: Dict[str, Any]) -> bool:
        # Pre-filtering logic
        return True

    def features(self, ticker_data: Dict[str, Any]) -> Dict[str, Any]:
        # Feature extraction
        return {}

    def score(self, features: Dict[str, Any]) -> float:
        # Scoring logic
        return 0.5

    def label(self, entry_data: Dict[str, Any], outcome_data: Dict[str, Any]) -> bool:
        # Outcome labeling
        return False
```

### 3. Create config.yml
```yaml
name: my_strategy
version: 1.0.0
description: "My custom recovery strategy"
parameters:
  threshold: 0.6
  window: 10
```

### 4. Add Strategy Documentation
Create `README.md` explaining the strategy logic, parameters, and expected performance.

### 5. Restart Service
The strategy loader automatically discovers and registers the new strategy on startup. No code changes to core system required.

---

## Deliverables

### Phase 1: Foundation (Week 1)
- [ ] Project structure setup
- [ ] pyproject.toml with dependencies
- [ ] Database schema + ERD diagram
- [ ] Alembic migrations (initial)
- [ ] Docker Compose (Postgres + API)
- [ ] Makefile with common tasks

### Phase 2: Core Engine (Week 2)
- [ ] StrategyProtocol interface
- [ ] Strategy loader and registry
- [ ] Strategy #1: Drop 5% implementation
- [ ] Data adapters (prices, news) with caching
- [ ] Shared feature helpers (ATR, RSI, etc.)
- [ ] Scanner engine with concurrency

### Phase 3: API & Scheduler (Week 3)
- [ ] FastAPI routes (/health, /scan, /candidates, /runs, /metrics)
- [ ] APScheduler integration
- [ ] Background task processing
- [ ] Structured logging
- [ ] Error handling and retries

### Phase 4: Evaluation & Documentation (Week 4)
- [ ] Evaluation labeler (T+1/T+5 recovery)
- [ ] Metrics calculation (hit-rate, PnL proxy)
- [ ] Backfill script
- [ ] README with getting started
- [ ] API documentation (OpenAPI/Swagger)
- [ ] Strategy development guide
- [ ] Deployment guide

---

## Makefile Targets

```makefile
.PHONY: help install dev db-up db-down db-migrate scan backfill test lint

help:
	@echo "Available targets:"
	@echo "  install     - Install dependencies"
	@echo "  dev         - Run development server"
	@echo "  db-up       - Start PostgreSQL container"
	@echo "  db-down     - Stop PostgreSQL container"
	@echo "  db-migrate  - Run Alembic migrations"
	@echo "  scan        - Run one-shot scan"
	@echo "  backfill    - Run backfill labeling"
	@echo "  test        - Run test suite"
	@echo "  lint        - Run linters"

install:
	pip install -e .

dev:
	uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

db-up:
	docker-compose up -d postgres

db-down:
	docker-compose down

db-migrate:
	alembic upgrade head

scan:
	python scripts/one_shot_scan.py

backfill:
	python scripts/backfill.py --days 30

test:
	pytest tests/ -v --cov=src

lint:
	ruff check src/
	mypy src/
```

---

## Next Steps

1. ✅ Review and approve this technical plan
2. ⏭️ Initialize project structure and dependencies (`/speckit.tasks`)
3. ⏭️ Begin implementation phase-by-phase
4. ⏭️ Set up CI/CD pipeline
5. ⏭️ Deploy and monitor MVP

---

**See also**:
- [CONSTITUTION.md](./CONSTITUTION.md) - Project principles
- [SPECIFICATION.md](./SPECIFICATION.md) - Requirements and scope
