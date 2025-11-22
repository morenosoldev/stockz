# Task 6.4: Technical Analysis with yfinance + pandas-ta

**Status**: 🟡 In Progress  
**Priority**: P1 (High)  
**Estimated Effort**: 4 hours  
**Assignee**: AI Agent  
**Created**: 2025-11-01  
**Updated**: 2025-11-01 (Switched from TradingView MCP to yfinance approach)

---

## 📋 Description

Add technical analysis capabilities using **yfinance** for market data and **pandas-ta** for technical indicators. Use GPT-4 to analyze the technical data and provide trading signals alongside Reddit sentiment and fundamental research.

**Key Change**: Using **yfinance + pandas-ta** instead of TradingView MCP for broader stock coverage (all US stocks, international, OTC, etc.)

**Workflow**: Candidate Found → Fetch OHLCV Data → Calculate Technical Indicators → GPT-4 Analyzes Data → Store Technical Analysis → Display in Frontend

---

## 🎯 Acceptance Criteria

### Phase 1: Setup Dependencies & Structure

- [x] Install dependencies:

  ```bash
  pip install pandas-ta mplfinance pillow
  ```

- [ ] Create module structure:

  - `src/datasources/technical.py` - Technical data adapter using yfinance
  - `src/analysis/` - New directory for analysis modules
  - `src/analysis/technical_analyzer.py` - GPT-4 technical analysis

- [ ] Add environment variables to `.env.example`:
  ```bash
  # Technical Analysis
  TECHNICAL_ANALYSIS_ENABLED=true
  TECHNICAL_ANALYSIS_LOOKBACK_DAYS=90  # Default: 3 months
  TECHNICAL_ANALYSIS_CACHE_TTL=3600    # 1 hour cache
  ```

### Phase 2: Technical Data Adapter

- [ ] Create `src/datasources/technical.py`:

  - **TechnicalDataAdapter** class (inherits from `BaseDataAdapter`)
  - **get_technical_data(ticker, lookback_days)**: Fetch OHLCV + calculate indicators
    - Use **yfinance** to fetch historical data (already installed)
    - Calculate indicators using **pandas-ta**:
      - **RSI** (14) - Relative Strength Index
      - **MACD** (12, 26, 9) - Moving Average Convergence Divergence
      - **Bollinger Bands** (20, 2) - Volatility bands
      - **SMA** (20, 50, 200) - Simple Moving Averages
      - **EMA** (20, 50) - Exponential Moving Averages
      - **ADX** (14) - Average Directional Index (trend strength)
      - **Stochastic** (14, 3, 3) - Overbought/oversold
      - **Volume** - Average volume, volume spikes
      - **ATR** (14) - Average True Range (volatility)
    - Returns: `TechnicalData` dataclass with all indicators

- [ ] Technical Data Structure:

  ```python
  @dataclass
  class TechnicalData:
      ticker: str
      as_of_date: date
      current_price: float
      price_change_pct: float  # From lookback start to current

      # Trend Indicators
      sma_20: float
      sma_50: float
      sma_200: float
      ema_20: float
      ema_50: float

      # Momentum Indicators
      rsi: float  # 0-100
      macd: float
      macd_signal: float
      macd_histogram: float
      stochastic_k: float
      stochastic_d: float

      # Volatility Indicators
      bb_upper: float
      bb_middle: float
      bb_lower: float
      bb_width: float  # Squeeze indicator
      atr: float

      # Trend Strength
      adx: float  # 0-100

      # Volume Analysis
      volume: int
      avg_volume_20d: int
      volume_ratio: float  # Current vs 20d average

      # Price Levels
      support_level: Optional[float]  # Recent low
      resistance_level: Optional[float]  # Recent high

      # Attribution
      attribution: Attribution
  ```

- [ ] Implement caching:
  - Cache key: `technical:{ticker}:{date}`
  - TTL: 1 hour (prices update frequently)
  - Use existing `Cache` class from `src/datasources/cache.py`

### Phase 3: Technical Analyzer with GPT-4

- [ ] Create `src/analysis/technical_analyzer.py`:

  - **TechnicalAnalyzer** class
  - **analyze_technical_data(technical_data: TechnicalData)**: Analyze using GPT-4
  - Use GPT-4 (text-only, no vision needed since we're passing structured data)
  - **TECHNICAL_ANALYSIS_PROMPT** template (see below)

- [ ] Technical Analysis Prompt:

  ```python
  TECHNICAL_ANALYSIS_PROMPT = """
  You are a professional technical analyst. Analyze the following technical data for {ticker} and provide trading signals.

  **Current Price**: ${current_price} ({price_change_pct:+.2f}% from 90 days ago)

  **Trend Indicators:**
  - SMA(20): ${sma_20} | SMA(50): ${sma_50} | SMA(200): ${sma_200}
  - EMA(20): ${ema_20} | EMA(50): ${ema_50}
  - Price vs SMA(200): {position} ({"Above" if current_price > sma_200 else "Below"})

  **Momentum:**
  - RSI(14): {rsi:.1f} ({rsi_interpretation})
  - MACD: {macd:.2f} | Signal: {macd_signal:.2f} | Histogram: {macd_histogram:.2f}
  - Stochastic: K={stochastic_k:.1f}, D={stochastic_d:.1f}

  **Volatility:**
  - Bollinger Bands: Upper=${bb_upper:.2f}, Middle=${bb_middle:.2f}, Lower=${bb_lower:.2f}
  - BB Width: {bb_width:.4f} ({bb_interpretation})
  - ATR(14): ${atr:.2f}

  **Trend Strength:**
  - ADX(14): {adx:.1f} ({adx_interpretation})

  **Volume:**
  - Current Volume: {volume:,}
  - 20-day Avg: {avg_volume_20d:,}
  - Volume Ratio: {volume_ratio:.2f}x

  **Support/Resistance:**
  - Support: ${support_level:.2f}
  - Resistance: ${resistance_level:.2f}

  Provide a JSON response with the following structure:
  {{
    "overall_signal": "BULLISH" | "BEARISH" | "NEUTRAL",
    "signal_strength": 0.0 to 1.0,
    "key_signals": [
      {{"indicator": "RSI", "signal": "OVERSOLD", "weight": 0.8}},
      {{"indicator": "MACD", "signal": "BULLISH_CROSS", "weight": 0.6}}
    ],
    "price_targets": {{
      "support": float,
      "resistance": float,
      "stop_loss": float
    }},
    "risk_assessment": "LOW" | "MEDIUM" | "HIGH",
    "summary": "2-3 sentence technical summary",
    "confidence": 0.0 to 1.0
  }}
  """
  ```

- [ ] Technical Analysis Output:
  ```python
  @dataclass
  class TechnicalAnalysis:
      ticker: str
      as_of_date: date
      overall_signal: str  # BULLISH, BEARISH, NEUTRAL
      signal_strength: float  # 0.0 to 1.0
      key_signals: List[Dict[str, Any]]  # List of triggered signals
      price_targets: Dict[str, float]  # support, resistance, stop_loss
      risk_assessment: str  # LOW, MEDIUM, HIGH
      summary: str
      confidence: float  # 0.0 to 1.0
      attribution: Attribution  # OpenAI GPT-4 attribution
  ```

### Phase 4: Integration with RedditSentimentStrategy

- [ ] Update `src/strategies/reddit_sentiment/implementation.py`:

  - Import `TechnicalDataAdapter` and `TechnicalAnalyzer`
  - Add technical analysis to `_refresh_sentiment_data()` method
  - Call **after** research pipeline (Task 6.2) completes
  - Integrate technical signals into scoring logic

- [ ] Integration Flow:

  ```python
  async def _refresh_sentiment_data(self, ticker: str, asof: date) -> None:
      # ... existing Reddit sentiment code ...

      # ... existing research pipeline (Task 6.2) ...

      # NEW: Technical analysis
      if self.config.technical_analysis_enabled:
          try:
              # Fetch technical data
              technical_data = self.technical_adapter.get_technical_data(
                  ticker=ticker,
                  lookback_days=self.config.technical_lookback_days
              )

              # Analyze with GPT-4
              technical_analysis = self.technical_analyzer.analyze_technical_data(
                  technical_data=technical_data
              )

              # Store in cache for scoring
              self._technical_cache[ticker] = {
                  "data": technical_data,
                  "analysis": technical_analysis
              }

              logger.info(
                  "Technical analysis complete",
                  extra={
                      "ticker": ticker,
                      "signal": technical_analysis.overall_signal,
                      "strength": technical_analysis.signal_strength
                  }
              )
          except Exception as e:
              logger.warning(
                  "Technical analysis failed",
                  extra={"ticker": ticker, "error": str(e)},
                  exc_info=True
              )
              # Don't fail entire scan, continue without technical data
  ```

- [ ] Update `score()` method to include technical signals:

  ```python
  def score(self, features: Dict[str, Any]) -> float:
      base_score = # ... existing sentiment score ...

      # ... existing research adjustments (Task 6.2) ...

      # NEW: Technical analysis adjustments
      if self.config.technical_analysis_enabled:
          technical_data = self._technical_cache.get(features["ticker"])
          if technical_data:
              analysis = technical_data["analysis"]

              # Adjust based on technical signal
              if analysis.overall_signal == "BULLISH":
                  technical_boost = analysis.signal_strength * 0.15  # Max +0.15
                  base_score += technical_boost
                  logger.debug(f"Technical boost: +{technical_boost:.3f}")
              elif analysis.overall_signal == "BEARISH":
                  technical_penalty = analysis.signal_strength * 0.20  # Max -0.20
                  base_score -= technical_penalty
                  logger.debug(f"Technical penalty: -{technical_penalty:.3f}")

              # Penalize high risk
              if analysis.risk_assessment == "HIGH":
                  base_score -= 0.10

      return max(0.0, min(1.0, base_score))  # Clamp to [0, 1]
  ```

- [ ] Update `features()` method to expose technical data:

  ```python
  def features(self, ticker: str, asof: date) -> Dict[str, Any]:
      features = # ... existing features ...

      # NEW: Add technical analysis to features
      if self.config.technical_analysis_enabled:
          technical_data = self._technical_cache.get(ticker)
          if technical_data:
              features["technical_analysis"] = {
                  "signal": technical_data["analysis"].overall_signal,
                  "strength": technical_data["analysis"].signal_strength,
                  "key_signals": technical_data["analysis"].key_signals,
                  "summary": technical_data["analysis"].summary,
                  "rsi": technical_data["data"].rsi,
                  "macd_histogram": technical_data["data"].macd_histogram,
                  "bb_width": technical_data["data"].bb_width,
                  "adx": technical_data["data"].adx,
                  "volume_ratio": technical_data["data"].volume_ratio
              }

      return features
  ```

- [ ] Store technical analysis in `candidate.rationale`:
  ```python
  rationale = {
      # ... existing rationale fields ...

      # NEW: Technical analysis
      "technical_analysis": {
          "signal": "BULLISH",
          "strength": 0.75,
          "key_signals": [...],
          "price_targets": {...},
          "risk": "MEDIUM",
          "summary": "Strong uptrend with oversold RSI...",
          "confidence": 0.80
      } if technical analysis available else None
  }
  ```

### Phase 5: Configuration

- [ ] Add to `src/strategies/reddit_sentiment/config.yml`:

  ```yaml
  # ... existing config ...

  # Technical Analysis Configuration
  technical_analysis:
    enabled: true
    lookback_days: 90 # 3 months of historical data
    cache_ttl_seconds: 3600 # 1 hour

    # Scoring weights
    scoring:
      bullish_boost_max: 0.15 # Max score increase for bullish signal
      bearish_penalty_max: 0.20 # Max score decrease for bearish signal
      high_risk_penalty: 0.10 # Penalty for high-risk assessment

      # Minimum signal strength to apply adjustments
      min_signal_strength: 0.5
  ```

- [ ] Update `src/ops/config.py`:

  - Add `technical_analysis_enabled` to global config
  - Add `technical_lookback_days` default value
  - Add `technical_cache_ttl` default value

- [ ] Update `.env.example`:
  ```bash
  # Technical Analysis
  TECHNICAL_ANALYSIS_ENABLED=true
  TECHNICAL_ANALYSIS_LOOKBACK_DAYS=90
  TECHNICAL_ANALYSIS_CACHE_TTL=3600
  ```

### Phase 6: Unit Tests

- [ ] Create `tests/unit/datasources/test_technical.py`:

  - Test `TechnicalDataAdapter.get_technical_data()`
  - Mock yfinance responses
  - Test indicator calculations (pandas-ta)
  - Test caching behavior
  - Test error handling (invalid ticker, no data)

- [ ] Create `tests/unit/analysis/test_technical_analyzer.py`:

  - Test `TechnicalAnalyzer.analyze_technical_data()`
  - Mock GPT-4 API responses
  - Test JSON parsing from LLM
  - Test signal interpretation (bullish, bearish, neutral)
  - Test error handling (API failures)

- [ ] Create `tests/integration/technical/test_technical_integration.py`:

  - End-to-end test: Fetch real data → Calculate indicators → Analyze
  - Test with real tickers (AAPL, TSLA, SPY)
  - Validate indicator values are reasonable
  - Mark as `@pytest.mark.integration` for optional execution

- [ ] Update `tests/unit/strategies/test_reddit_sentiment.py`:
  - Add tests for technical analysis integration
  - Test score adjustments based on technical signals
  - Test graceful degradation (technical analysis fails)

---

## 📦 Dependencies

- **yfinance** (already installed) - Market data fetching
- **pandas-ta** (new) - Technical indicators library
- **mplfinance** (optional) - Chart generation for debugging
- **pillow** (optional) - Image manipulation
- **openai** (already installed) - GPT-4 API

---

## 🔧 Installation Commands

```bash
# Install new dependencies
pip install pandas-ta mplfinance pillow

# Update pyproject.toml
# Add to dependencies:
#   "pandas-ta>=0.3.14",
#   "mplfinance>=0.12.10",
#   "pillow>=10.0.0",
```

---

## 🚀 Example Usage

```python
from src.datasources.technical import TechnicalDataAdapter
from src.analysis.technical_analyzer import TechnicalAnalyzer

# Initialize adapters
technical_adapter = TechnicalDataAdapter()
technical_analyzer = TechnicalAnalyzer()

# Fetch technical data
technical_data = technical_adapter.get_technical_data(
    ticker="AAPL",
    lookback_days=90
)

print(f"RSI: {technical_data.rsi:.1f}")
print(f"MACD Histogram: {technical_data.macd_histogram:.2f}")
print(f"Bollinger Width: {technical_data.bb_width:.4f}")

# Analyze with GPT-4
analysis = technical_analyzer.analyze_technical_data(technical_data)

print(f"Signal: {analysis.overall_signal}")
print(f"Strength: {analysis.signal_strength:.2f}")
print(f"Summary: {analysis.summary}")
print(f"Key Signals: {analysis.key_signals}")
```

---

## 📝 Implementation Notes

### Why yfinance + pandas-ta?

1. **Universal Coverage**: Works for **all stocks** (US, international, OTC, crypto)
2. **No API Limits**: yfinance is free and unlimited
3. **Already Installed**: yfinance is in dependencies
4. **Proven Library**: pandas-ta is the standard for Python technical analysis
5. **Simpler Architecture**: No external MCP server needed

### Technical Indicators Explanation

- **RSI < 30**: Oversold (potential buy signal)
- **RSI > 70**: Overbought (potential sell signal)
- **MACD Histogram > 0**: Bullish momentum
- **MACD Histogram < 0**: Bearish momentum
- **Bollinger Band Width < 0.05**: Squeeze (volatility breakout coming)
- **ADX > 25**: Strong trend
- **ADX < 20**: Weak/no trend
- **Price > SMA(200)**: Long-term uptrend
- **Stochastic > 80**: Overbought

### GPT-4 Analysis Strategy

Instead of vision analysis of charts, we:

1. Calculate all indicators numerically
2. Format as structured text prompt
3. GPT-4 interprets the numbers (faster, cheaper, more accurate)
4. Returns structured JSON with signals

**Benefits**:

- No chart generation needed (faster)
- More precise (exact values vs visual estimation)
- Cheaper API calls (text < images)
- Easier to test (mock responses)

---

## ⚠️ Edge Cases

1. **Ticker not found in yfinance**:

   - Log warning, skip technical analysis
   - Don't fail entire scan

2. **Not enough historical data** (new IPO):

   - Require minimum 30 days
   - Skip if insufficient data

3. **GPT-4 API failure**:

   - Retry once with exponential backoff
   - If still fails, skip technical analysis

4. **Invalid indicator values** (NaN, inf):

   - Replace with None
   - Document in attribution

5. **Market closed / stale data**:
   - Cache for 1 hour during market hours
   - Cache for 12 hours outside market hours

---

## ✅ Success Metrics

- **Coverage**: Technical analysis runs for >95% of candidates
- **Performance**: Technical data fetch + analysis < 5 seconds per ticker
- **Accuracy**: Manual spot-check of 20 tickers shows reasonable signals
- **Integration**: Score adjustments improve backtest hit-rate by >5%
- **Reliability**: <1% failure rate for valid US stock tickers

---

## 🎯 Next Steps After Completion

1. **Task 6.5**: Backtest with historical data to validate technical signals
2. **Task 6.6**: Fine-tune scoring weights based on backtest results
3. **Task 6.7**: Add chart generation for frontend display (optional)
4. **Task 6.8**: Implement real-time alerts for strong technical signals

---

**Key Advantage**: This approach works for **any ticker mentioned on Reddit**, not just NASDAQ/NYSE. Perfect for WSB, which mentions everything from penny stocks to mega-caps!
