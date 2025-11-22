# yfinance Alternatives Analysis & Migration Plan

**Date**: November 2, 2025  
**Status**: 🔴 CRITICAL - yfinance is unreliable and causing scan failures  
**Priority**: HIGH

---

## Problem Summary

yfinance is causing critical issues:

1. **Rate Limiting (429 errors)**: Even with 2-5 second delays between calls
2. **JSONDecodeError**: `Expecting value: line 1 column 1 (char 0)` - Empty responses
3. **Unreliable Data**: "No timezone found, symbol may be delisted" for valid tickers (AAPL, NVDA, TSLA)
4. **GitHub Issues**: 116 open issues, many about rate limiting and data failures
5. **Disabled Features**: We already disabled ticker validation due to unreliability

### Current yfinance Usage

We use yfinance in **3 critical areas**:

1. **Technical Analysis** (`src/datasources/technical.py`)

   - Fetch OHLCV data (Open, High, Low, Close, Volume)
   - Calculate indicators (RSI, MACD, Bollinger Bands, ADX)
   - **Status**: Currently failing for all tickers

2. **Ticker Validation** (`src/datasources/company_detector.py`, `ticker_validator.py`)

   - Verify ticker symbols exist
   - Get company metadata
   - **Status**: DISABLED due to rate limiting

3. **Reddit Pipeline** (`src/datasources/reddit.py`)
   - Validate AI-suggested tickers
   - **Status**: Validation skipped (line 858: "TODO: yfinance validation temporarily disabled")

---

## Alternative Data Sources

### Option 1: **Polygon.io** ⭐ RECOMMENDED

**Pros:**

- ✅ Professional-grade API with reliable uptime
- ✅ Free tier: 5 API calls/minute (enough for our use case with delays)
- ✅ Stocks, options, forex, crypto support
- ✅ Real-time & historical data
- ✅ Python SDK available (`polygon-api-client`)
- ✅ Great documentation
- ✅ Used by professionals (hedge funds, trading firms)

**Cons:**

- ❌ Requires API key (free tier available)
- ❌ Free tier has rate limits (but predictable, unlike yfinance)
- ❌ Advanced features require paid plan

**Pricing:**

- Free: 5 calls/min, delayed data
- Starter ($29/mo): 100 calls/min, real-time data
- Developer ($99/mo): Unlimited calls

**Python SDK:**

```bash
pip install polygon-api-client
```

**Code Example:**

```python
from polygon import RESTClient

client = RESTClient(api_key="YOUR_API_KEY")

# Get daily bars (OHLCV)
bars = client.get_aggs("AAPL", 1, "day", "2024-01-01", "2024-12-31")

# Get ticker details
ticker_details = client.get_ticker_details("AAPL")

# Get previous close
prev_close = client.get_previous_close("AAPL")
```

**Migration Effort**: Medium (1-2 days)

---

### Option 2: **Alpha Vantage**

**Pros:**

- ✅ Free tier available (25 requests/day, 5 requests/minute)
- ✅ Good documentation
- ✅ Python library available (`alpha-vantage`)
- ✅ Stocks, forex, crypto, technical indicators
- ✅ No credit card required for free tier

**Cons:**

- ❌ Very limited free tier (25 calls/day = ~10-15 tickers/day with our needs)
- ❌ Premium required for serious use ($49.99/mo for 75 calls/min)
- ❌ API key required

**Pricing:**

- Free: 25 calls/day, 5 calls/min
- Premium ($49.99/mo): 75 calls/min
- Premium+ ($149.99/mo): 600 calls/min

**Migration Effort**: Medium (1-2 days)

---

### Option 3: **Twelve Data** ⭐ BEST FOR INTERNATIONAL + AFFORDABLE

**Pros:**

- ✅ **Supports 120+ global exchanges** (including Copenhagen for GUBRA!)
- ✅ **Affordable pricing**: $8-29/month
- ✅ US, European, Asian markets
- ✅ Good for technical analysis
- ✅ Python SDK available
- ✅ WebSocket support
- ✅ Good documentation
- ✅ OHLCV data + technical indicators built-in

**Cons:**

- ❌ API key required
- ❌ Less popular than Polygon/Alpha Vantage

**Pricing:**

- Free: 800 calls/day, 8 calls/min
- **Basic ($8/mo)**: 8,000 calls/day, 8 calls/min ⭐
- **Grow ($29/mo)**: 80,000 calls/day, 60 calls/min ⭐⭐
- Pro ($49/mo): 200,000 calls/day, 120 calls/min

**Supported Markets:**

- US: NYSE, NASDAQ
- Europe: LSE, Euronext, Deutsche Börse, **Copenhagen Stock Exchange**
- Asia: Tokyo, Hong Kong, Singapore
- And 100+ more exchanges

**Migration Effort**: Medium (1-2 days)

---

### Option 4: **Finnhub** (Excellent International Coverage)

**Pros:**

- ✅ **Global market coverage**: US, Europe, Asia
- ✅ **Affordable**: $3,000/year = **$250/month** (but see note below)
- ✅ Great Python SDK (`finnhub-python`)
- ✅ Real-time & historical data
- ✅ Good documentation
- ✅ Reliable API

**Cons:**

- ❌ Free tier very limited (60 calls/min)
- ❌ Paid tier expensive for individuals ($250/mo)
- ❌ Better for institutional use

**Pricing:**

- Free: 60 calls/min, US stocks only
- Paid: $3,000/year ($250/mo), global markets, 900 calls/min

**Note**: Too expensive for your budget, but included for completeness.

**Migration Effort**: Medium (1-2 days)

---

### Option 5: **EOD Historical Data** ⭐ GREAT VALUE

**Pros:**

- ✅ **Excellent pricing**: $19.99-79.99/month
- ✅ **70+ global exchanges** (including Copenhagen!)
- ✅ US + International markets
- ✅ Historical & real-time data
- ✅ REST API
- ✅ Good documentation
- ✅ Unlimited API calls on paid plans

**Cons:**

- ❌ Less popular Python SDK
- ❌ Need to use REST API directly (easy)

**Pricing:**

- **All World Extended ($19.99/mo)**: 20+ exchanges, delayed data ⭐
- **All World ($79.99/mo)**: 70+ exchanges, real-time data
- **Includes**: OHLCV, fundamentals, technical indicators

**Migration Effort**: Medium (1-2 days)

---

### Option 6: **Alpaca Markets** (Trading-focused)

**Pros:**

- ✅ Free for stock data (requires account)
- ✅ Real-time & historical data
- ✅ Great Python SDK (`alpaca-trade-api`)
- ✅ Also provides trading API (for future v2 features)
- ✅ WebSocket for real-time data

**Cons:**

- ❌ Requires account signup (free, no credit card)
- ❌ Primarily for US markets
- ❌ More complex than needed (trading-focused)

**Pricing:**

- Free: Market data API (live & historical)
- Paper trading: Free
- Live trading: Commission-free

**Migration Effort**: Medium (1-2 days)

---

### Option 7: **Yahoo Finance API** (Paid, Official)

**Pros:**

- ✅ Official Yahoo Finance API (unlike yfinance)
- ✅ Reliable (unlike yfinance scraping)
- ✅ Same data as yfinance but stable

**Cons:**

- ❌ Paid only (no free tier)
- ❌ Expensive ($29/mo+)
- ❌ Less popular in Python ecosystem

**Migration Effort**: Medium-High (2-3 days)

---

### Option 8: **IEX Cloud**

**Pros:**

- ✅ Free tier: 50,000 messages/month
- ✅ Reliable API
- ✅ Python SDK available
- ✅ Good documentation

**Cons:**

- ❌ Free tier may be insufficient for large scans
- ❌ Primarily US markets
- ❌ Some data requires paid plan

**Pricing:**

- Free: 50,000 messages/month
- Launch ($9/mo): 500,000 messages/month
- Grow ($49/mo): 5,000,000 messages/month

**Migration Effort**: Medium (1-2 days)

---

## Recommendation Matrix

| Provider           | Free Tier     | Paid Tier        | International     | Reliability | Ease of Use | **Score**  |
| ------------------ | ------------- | ---------------- | ----------------- | ----------- | ----------- | ---------- |
| **Twelve Data**    | 800 calls/day | **$8-29/mo** ⭐  | ✅ 120+ exchanges | ⭐⭐⭐⭐    | ⭐⭐⭐⭐    | **9/10**   |
| **EOD Historical** | ❌            | **$19.99/mo** ⭐ | ✅ 70+ exchanges  | ⭐⭐⭐⭐    | ⭐⭐⭐      | **8.5/10** |
| Polygon.io         | 5 calls/min   | $29/mo           | ❌ US only        | ⭐⭐⭐⭐⭐  | ⭐⭐⭐⭐⭐  | **7/10**   |
| Alpha Vantage      | 25 calls/day  | $49.99/mo        | ✅ Global         | ⭐⭐⭐⭐    | ⭐⭐⭐⭐    | **7.5/10** |
| Alpaca             | Free          | Free             | ❌ US only        | ⭐⭐⭐⭐⭐  | ⭐⭐⭐      | **7/10**   |
| Finnhub            | 60 calls/min  | $250/mo          | ✅ Global         | ⭐⭐⭐⭐⭐  | ⭐⭐⭐⭐    | **6/10**   |
| IEX Cloud          | 50k msg/mo    | $9-49/mo         | ❌ US only        | ⭐⭐⭐⭐    | ⭐⭐⭐⭐    | **6.5/10** |

---

## 🎯 RECOMMENDED SOLUTION: **Twelve Data** (Basic Plan - $8/mo)

**Why Twelve Data:**

1. **International Coverage**: Supports Copenhagen Stock Exchange (GUBRA ✅)
2. **Affordable**: $8/month for 8,000 calls/day (far more than you need)
3. **Reliable**: No random 429 errors like yfinance
4. **Easy Migration**: Similar API to yfinance, Python SDK available
5. **Scalable**: Can upgrade to $29/mo for 60 calls/min if needed

**Estimated Daily Usage** (for 290 posts, ~50 unique tickers):

- Technical analysis: ~50 tickers × 1 call = 50 calls
- With 5-second delays: 50 × 5 seconds = 4.2 minutes
- **Basic plan limit**: 8,000 calls/day, 8 calls/min
- **Your usage**: ~50 calls/day (0.6% of daily limit)

**Cost Analysis:**

- $8/month = $0.27/day
- With 50 calls/day = **$0.0054 per API call**
- Extremely affordable for your use case!

**Supports Your Use Case:**

- ✅ US stocks (AAPL, NVDA, TSLA, etc.)
- ✅ European stocks (GUBRA on Copenhagen exchange)
- ✅ Technical indicators (RSI, MACD, etc.)
- ✅ OHLCV historical data
- ✅ Ticker validation

---

## Alternative Recommendation: **EOD Historical Data** ($19.99/mo)

If you need more exchanges or want real-time data, **EOD Historical Data** at $19.99/mo is excellent:

- 70+ exchanges (vs 120+ for Twelve Data)
- Unlimited API calls
- Delayed data (15-20 min)
- Good for international coverage

---

## Migration Plan

### Phase 1: Create Abstraction Layer (1 day)

**Goal**: Decouple our code from yfinance

1. Create `src/datasources/market_data.py` with abstract interface:

   ```python
   class MarketDataAdapter(Protocol):
       def get_ohlcv(ticker, start, end) -> pd.DataFrame
       def get_ticker_info(ticker) -> dict
       def validate_ticker(ticker) -> bool
   ```

2. Create `src/datasources/market_data_twelve.py` implementing the interface
3. Create `src/datasources/market_data_yfinance.py` (fallback wrapper)

**Files to Create:**

- `src/datasources/market_data.py` (base interface)
- `src/datasources/market_data_twelve.py` (Twelve Data implementation)
- `src/datasources/market_data_yfinance.py` (yfinance wrapper for fallback)

---

### Phase 2: Migrate Technical Analysis (0.5 days)

**Goal**: Replace yfinance in `technical.py`

**Files to Modify:**

- `src/datasources/technical.py`

**Changes:**

```python
# OLD
import yfinance as yf
stock = yf.Ticker(ticker)
df = stock.history(period=f"{lookback_days}d")

# NEW
from src.datasources.market_data import get_market_data_adapter
adapter = get_market_data_adapter()  # Returns Twelve Data or fallback
df = adapter.get_ohlcv(ticker, start_date, end_date)
```

---

### Phase 3: Migrate Ticker Validation (0.5 days)

**Goal**: Re-enable ticker validation with reliable source

**Files to Modify:**

- `src/datasources/company_detector.py`
- `src/datasources/ticker_validator.py`
- `src/datasources/reddit.py` (re-enable validation)

**Changes:**

```python
# In company_detector.py
def validate_ticker(self, ticker: str) -> bool:
    adapter = get_market_data_adapter()
    return adapter.validate_ticker(ticker)
```

**Re-enable in reddit.py** (line 858):

```python
# OLD
# TODO: yfinance validation temporarily disabled due to rate limiting

# NEW
if self.company_detector.validate_ticker(ticker):
    valid_tickers.append(ticker)
```

---

### Phase 4: Testing & Rollout (0.5 days)

1. Unit tests for new adapters
2. Integration test with real Polygon API
3. Run full scan with new data source
4. Monitor for errors
5. Keep yfinance as fallback for 1 week

---

## Configuration

Add to `.env`:

```bash
# Market Data Provider (twelve_data, polygon, alpha_vantage, or yfinance)
MARKET_DATA_PROVIDER=twelve_data

# API Keys
TWELVE_DATA_API_KEY=your_key_here
POLYGON_API_KEY=your_key_here  # Fallback (optional)
```

Add to `config.yaml`:

```yaml
market_data:
  provider: twelve_data # Primary provider
  fallback_provider: yfinance # Fallback if primary fails
  rate_limit_delay: 5 # Seconds between calls (8 calls/min = 7.5s between calls)
  cache_ttl: 3600 # Cache responses for 1 hour
```

---

## Implementation Checklist

- [ ] Sign up for Twelve Data Basic plan ($8/mo) - Get API key at https://twelvedata.com/pricing
- [ ] Install `twelvedata`: `pip install twelvedata`
- [ ] Create abstraction layer (`market_data.py`)
- [ ] Implement Twelve Data adapter (`market_data_twelve.py`)
- [ ] Migrate `technical.py` to use new adapter
- [ ] Migrate `company_detector.py` to use new adapter
- [ ] Migrate `ticker_validator.py` to use new adapter
- [ ] Re-enable ticker validation in `reddit.py`
- [ ] Add configuration to `.env` and `config.yaml`
- [ ] Write tests for new adapters
- [ ] Test with GUBRA (Copenhagen exchange) to verify international support
- [ ] Run integration test
- [ ] Monitor production for 1 week
- [ ] Remove yfinance dependency if successful

---

## Estimated Timeline

| Phase                       | Duration     | Effort     |
| --------------------------- | ------------ | ---------- |
| Phase 1: Abstraction Layer  | 1 day        | Medium     |
| Phase 2: Technical Analysis | 0.5 days     | Easy       |
| Phase 3: Ticker Validation  | 0.5 days     | Easy       |
| Phase 4: Testing & Rollout  | 0.5 days     | Easy       |
| **TOTAL**                   | **2.5 days** | **Medium** |

---

## Risk Mitigation

1. **Keep yfinance as fallback** for 1-2 weeks
2. **Gradual rollout**: Test with Twelve Data first, fallback to yfinance on errors
3. **Monitoring**: Log all API calls and failures
4. **Rate limiting**: Enforce 7.5-second delays (8 calls/min limit)
5. **Caching**: Cache all responses for 1 hour to reduce API calls
6. **Cost monitoring**: Track API usage to stay within 8,000 calls/day limit

---

## Cost Breakdown

**Twelve Data Basic Plan ($8/mo):**

- 8,000 calls/day
- 8 calls/min
- All markets (120+ exchanges)
- Historical + real-time data

**Your Estimated Usage:**

- ~50 calls/day for technical analysis
- ~10 calls/day for ticker validation
- **Total: ~60 calls/day (0.75% of limit)**

**Monthly Cost:**

- Fixed: $8/month
- Per-call cost: $0.0033 per call
- **Total: $8/month** (well within budget)

---

## Next Steps

**RECOMMENDED DECISION:**

1. ✅ **Twelve Data Basic ($8/mo)** - BEST VALUE for international coverage

   - Supports GUBRA (Copenhagen) and all your stocks
   - 8,000 calls/day >> your ~60 calls/day
   - Affordable and reliable

2. ⚠️ **EOD Historical Data ($19.99/mo)** - Alternative if you need more features

   - 70+ exchanges, unlimited API calls
   - Better for high-volume usage

3. ⚠️ **Twelve Data Grow ($29/mo)** - If you need faster rate limits (60 calls/min)

**Once confirmed, I will:**

1. Provide Twelve Data API signup instructions
2. Create the abstraction layer code
3. Implement Twelve Data adapter with Copenhagen exchange support
4. Migrate all yfinance usage
5. Re-enable ticker validation
6. Test with both US stocks (AAPL) and international stocks (GUBRA)

---

**Ready to proceed with Twelve Data ($8/mo)?** 🎯
