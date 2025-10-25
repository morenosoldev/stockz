# Recover-Bot Backend Specification

**Project**: Recover-Bot Backend (FastAPI, cron scanner, strategy folders)  
**Version**: 1.0.0-MVP  
**Date**: October 24, 2025

## Goal

Build a backend service that scans a large-cap equity universe on a schedule, identifies "drop ≥ X%" events, enriches with company/sector/news context, and computes a "Recovery Probability" (0–1).

**No trading in v1.** Persist candidates + features; expose via API. Run daily cron + manual trigger.

## Technology Stack

- **Language**: Python 3.11+
- **Web Framework**: FastAPI
- **Database**: PostgreSQL
- **ORM**: SQLAlchemy
- **Scheduler**: APScheduler (integrated with FastAPI)
- **Data Sources**: Configurable adapters (EOD/intraday price, news headlines)

## Core User Stories

1. **As an operator**, I can run `/scan` now or rely on a scheduled job.
2. **As a user**, I can `GET /candidates` (today, or by date) and see rationale + inputs.
3. **As a researcher**, I can add new strategies by creating a new folder and have it appear without touching core code.
4. **As a researcher**, I can query evaluation results (hit-rate, simple PnL proxy) for prior days.

## Scope (MVP)

### Strategy System
- **Strategy #1**: "Drop 5% then recover" as reference implementation
- **Plug-in Architecture**: Each strategy in `/strategies/<slug>` with interface:
  - `features()` - Feature engineering logic
  - `score()` - Scoring function returning 0-1 probability
  - `filters()` - Pre-filtering criteria
  - `label()` - Outcome labeling for evaluation

### Data Layer
- **Price Adapter**: EOD or intraday snapshot with attribution
- **News Adapter**: Simple headline sentiment with:
  - Headline polarity scoring
  - Risk keyword flags
  - Source attribution (URLs)

### Scoring
- **Rules-Based v1**: No ML in MVP
- **Output**: Probability-like score 0–1
- **Rationale**: Store which rules/features contributed to score

### Storage (PostgreSQL)
Tables:
- `runs` - Scan execution metadata
- `candidates` - Identified drop events with scores
- `features` - Versioned feature data per ticker/date
- `evaluations` - Outcome labels and metrics

### Scheduler
- **APScheduler** integrated within FastAPI service
- **Daily Cron**: Configurable time (e.g., after market close)
- **Manual Trigger**: POST `/scan` endpoint

## API Endpoints

### Core Endpoints
```
GET  /health                          - Health check
POST /scan                            - Trigger manual scan
GET  /candidates                      - List candidates (with filters: date, strategy)
GET  /candidate/{ticker}/{asof}       - Detail view with full rationale
GET  /runs/{date}                     - Scan run metadata
GET  /metrics                         - Aggregate metrics (hit-rate, coverage)
```

### Query Parameters
- `date` - ISO date or "today"
- `strategy` - Filter by strategy slug
- `min_score` - Minimum recovery probability

## Strategy Interface

Each strategy in `/strategies/<strategy_slug>/` must implement:

```python
class Strategy:
    """Base strategy interface."""

    def features(self, ticker_data: TickerData) -> Dict[str, Any]:
        """Extract features from raw ticker data."""

    def filters(self, ticker_data: TickerData) -> bool:
        """Return True if ticker passes pre-filters."""

    def score(self, features: Dict[str, Any]) -> float:
        """Compute recovery probability score (0-1)."""

    def label(self, entry_data: TickerData, outcome_data: TickerData) -> bool:
        """Label whether recovery occurred for evaluation."""
```

### Strategy Folder Structure
```
/strategies/
  /drop-5pct-recover/
    __init__.py
    strategy.py          # Implements Strategy interface
    config.yaml          # Strategy-specific configuration
    README.md            # Strategy documentation
    tests/               # Strategy-specific tests
```

## Definition of "Recovery"

**Configurable per strategy.** Default for MVP:

- **Recovery Detected**: Price hits +k·ATR or 50% retrace of the drop within D sessions
- **Default Parameters**:
  - k = 1.0 (ATR multiplier)
  - D = 5 (sessions)
  - Retrace = 50% of drop

Used for:
- Labeling historical outcomes
- Live evaluation metrics

## Non-Goals (v1)

❌ Placing orders  
❌ Complex web UI (basic JSON APIs only)  
❌ Expensive LLM research across the whole web  
❌ Real-time streaming data (batch-oriented)  
❌ Multi-asset classes (equities only)

## Constraints

- **Cost/Latency**: Keep API calls minimal; use caching aggressively
- **Missing Data**: Tolerate gracefully with fallbacks
- **Attribution**: All summaries include source URIs
- **Audit Trail**: Store LLM prompts/outputs if used
- **Source Attribution**: Every data point traceable to source

## Performance Targets

- **Universe Size**: 1,000-2,000 large-cap tickers
- **Scan Duration**: p50 < 10 minutes on single node
- **Concurrency**: Parallel processing with rate limiting
- **Cache Hit Rate**: >80% for repeated scans same day

## Success Metrics

### Operational
- ✅ Daily scans complete successfully 99%+ of the time
- ✅ p50 scan duration < 10 minutes for ~1-2k tickers
- ✅ API response time p95 < 500ms (excluding scan endpoint)

### Strategy Performance
- ✅ Shadow-mode win rate ≥ baseline (random drop picks) over 30 trading days
- ✅ Data quality: <1% missing attributions
- ✅ Reproducibility: Same inputs → same outputs

## Deliverables

1. ✅ Running FastAPI service with all core endpoints
2. ✅ Strategy folder template and auto-loader
3. ✅ Strategy #1: "Drop 5% Recover" implementation
4. ✅ Backfill script for outcome labeling
5. ✅ Documentation:
   - README with getting started guide
   - API documentation (OpenAPI/Swagger)
   - Strategy development guide
   - Database schema documentation

## Development Phases

### Phase 1: Foundation (Week 1)
- Project structure and dependencies
- Database schema and migrations
- Data adapter interfaces

### Phase 2: Core Engine (Week 2)
- Strategy framework and loader
- Batch scanner implementation
- Strategy #1 implementation

### Phase 3: API & Scheduler (Week 3)
- FastAPI endpoints
- APScheduler integration
- Testing and optimization

### Phase 4: Evaluation & Docs (Week 4)
- Backfill script
- Metrics calculation
- Documentation and examples

## Open Questions

- [ ] Which price data provider for MVP? (Yahoo Finance, Alpha Vantage, Polygon?)
- [ ] Which news API? (NewsAPI, Finnhub, custom scraper?)
- [ ] Universe definition: S&P 500? Russell 1000? Custom list?
- [ ] Deployment target: Docker? Kubernetes? VM?
- [ ] Monitoring/alerting stack: Prometheus? Datadog? CloudWatch?

---

**See also**: [CONSTITUTION.md](./CONSTITUTION.md) for project principles and guidelines.
