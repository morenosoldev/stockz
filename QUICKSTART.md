# Quick Start Guide - Recover-Bot

## 🚀 Start Everything

### Option 1: VS Code One-Click (Recommended)
Press **F5** in VS Code - This launches the full stack automatically!

### Option 2: Manual Commands

```bash
# 1. Start PostgreSQL
make db-up

# 2. Run migrations
make db-migrate

# 3. Start FastAPI server
make dev
```

The API will be available at **http://localhost:8000**

---

## 🧪 Try the API

### Interactive Documentation
Open in your browser:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Health Check
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2025-10-25T..."
}
```

---

## 📊 Test the New Runs & Metrics Endpoints

### 1. Trigger a Scan
```bash
curl -X POST http://localhost:8000/v1/scan \
  -H "Content-Type: application/json" \
  -d '{
    "strategies": ["drop5"],
    "date": "2025-10-25"
  }'
```

Response:
```json
{
  "run_id": "uuid-here",
  "status": "queued",
  "message": "Scan started successfully"
}
```

**Note**: The first scan will take a few minutes as it fetches real market data from Yahoo Finance!

### 2. Check Run Status
```bash
# List all runs for today
curl "http://localhost:8000/v1/runs/by-date/2025-10-25"

# Get specific run details (use run_id from step 1)
curl "http://localhost:8000/v1/runs/{run_id}"
```

Response:
```json
{
  "runs": [
    {
      "run_id": "uuid",
      "run_date": "2025-10-25",
      "strategy": "drop5",
      "status": "completed",
      "started_at": "2025-10-25T12:00:00Z",
      "completed_at": "2025-10-25T12:08:30Z",
      "duration_seconds": 510,
      "tickers_processed": 30,
      "candidates_found": 5,
      "errors_count": 0
    }
  ]
}
```

### 3. View Candidates
```bash
# List candidates found by the scan
curl "http://localhost:8000/v1/candidates?date=2025-10-25&strategy=drop5&min_score=0.5"
```

Response:
```json
{
  "candidates": [
    {
      "ticker": "AAPL",
      "asof": "2025-10-25",
      "strategy": "drop5",
      "score": 0.75,
      "drop_pct": -6.5,
      "volume_rvol": 2.3,
      "price": 175.20
    }
  ],
  "total": 1,
  "page": 1,
  "limit": 100
}
```

### 4. Get Candidate Details
```bash
# Get detailed analysis for a specific ticker
curl "http://localhost:8000/v1/candidate/AAPL/2025-10-25?strategy=drop5"
```

Response includes:
- Full feature set (RSI, ATR, volume ratios, etc.)
- Score rationale (which rules triggered)
- Data attribution (source timestamps, URLs)

### 5. View Performance Metrics
```bash
# Get aggregate metrics for the last 30 days
curl "http://localhost:8000/v1/metrics?start_date=2025-09-25&end_date=2025-10-25&strategy=drop5"
```

Response:
```json
{
  "strategy": "drop5",
  "start_date": "2025-09-25",
  "end_date": "2025-10-25",
  "total_runs": 25,
  "successful_runs": 24,
  "failed_runs": 1,
  "total_candidates": 145,
  "avg_candidates_per_run": 6.0,
  "avg_score": 0.68,
  "evaluated_candidates": 120,
  "recoveries": 82,
  "hit_rate": 0.683,
  "avg_return_proxy": 0.042,
  "avg_recovery_days": 2.5
}
```

---

## 🎯 Interactive Swagger UI (Best Way to Explore!)

1. Open http://localhost:8000/docs
2. Click on any endpoint to expand it
3. Click "Try it out"
4. Fill in parameters
5. Click "Execute"
6. See the response immediately!

**Endpoints Available**:
- `GET /health` - Health check
- `POST /v1/scan` - Trigger a scan
- `GET /v1/runs/by-date/{date}` - List runs for a date (NEW!)
- `GET /v1/runs/{run_id}` - Get run details (NEW!)
- `GET /v1/candidates` - List candidates
- `GET /v1/candidate/{ticker}/{date}` - Get candidate details
- `GET /v1/metrics` - Performance metrics (NEW!)

---

## 🧪 Run Tests

```bash
# Run all tests
make test

# Run with coverage report
make test-cov

# Open coverage report in browser
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

**Current Stats**: 577 tests passing, 92% coverage

---

## 🔍 View Logs

```bash
# Tail application logs
tail -f logs/recover-bot.log

# View last 50 lines
tail -50 logs/recover-bot.log

# Search for errors
grep ERROR logs/recover-bot.log
```

---

## 🛑 Stop Everything

```bash
# Stop FastAPI (Ctrl+C in terminal or Shift+F5 in VS Code)

# Stop PostgreSQL
make db-down

# OR stop everything
docker-compose down
```

---

## 📝 Sample Workflow

Here's a complete workflow to see the new features:

```bash
# 1. Start everything
make db-up && make db-migrate && make dev

# 2. In another terminal, trigger a scan
curl -X POST http://localhost:8000/v1/scan \
  -H "Content-Type: application/json" \
  -d '{"strategies": ["drop5"]}'

# 3. Check run status (wait a few minutes for completion)
curl "http://localhost:8000/v1/runs/by-date/2025-10-25"

# 4. View candidates found
curl "http://localhost:8000/v1/candidates?date=2025-10-25"

# 5. Get performance metrics
curl "http://localhost:8000/v1/metrics?start_date=2025-10-01&end_date=2025-10-25"
```

---

## 🐛 Troubleshooting

### Database Connection Issues
```bash
# Check if PostgreSQL is running
docker ps | grep postgres

# If not running, start it
make db-up

# Check logs
docker-compose logs postgres
```

### API Not Starting
```bash
# Check for port conflicts
lsof -i :8000

# Check logs
tail -50 logs/recover-bot.log
```

### No Candidates Found
This is normal if:
- Market is closed (scan runs on live data)
- No stocks dropped 5-15% today
- Yahoo Finance API is rate-limiting

You can test with the scanner integration tests which use mock data:
```bash
pytest tests/integration/test_scanner_integration.py -v
```

---

## 🎓 Next Steps

1. **Explore the Swagger UI** at http://localhost:8000/docs
2. **Run a few scans** to build up historical data
3. **Check metrics** after running scans over multiple days
4. **Review the code** in `src/api/routes/` to understand the implementation
5. **Read the logs** to see what's happening under the hood

Enjoy! 🚀
