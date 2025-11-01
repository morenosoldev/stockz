# Task 6.4: TradingView Chart Analysis via MCP Server

**Status**: 🔴 Not Started  
**Priority**: P1 (High)  
**Estimated Effort**: 5 hours  
**Assignee**: AI Agent  
**Created**: 2025-11-01

---

## 📋 Description

Integrate TradingView's MCP (Model Context Protocol) server to generate chart images with technical indicators for each candidate stock. Feed these chart images to a vision-capable LLM (GPT-4 Vision, Claude 3) for visual technical analysis, providing an additional signal alongside Reddit sentiment and fundamental research.

**Workflow**: Candidate Found → Generate TradingView Chart → LLM Analyzes Chart Image → Store Technical Analysis → Display in Frontend

---

## 🎯 Acceptance Criteria

### Phase 1: TradingView MCP Server Setup

- [ ] Install TradingView MCP server:

  ```bash
  # Install via npm
  npm install -g @modelcontextprotocol/server-tradingview

  # Or clone and build from source
  git clone https://github.com/modelcontextprotocol/servers
  cd servers/src/tradingview
  npm install && npm run build
  ```

- [ ] Configure MCP server in backend:

  - Add TradingView MCP client to `src/datasources/tradingview.py`
  - Set up MCP connection (stdio or SSE transport)
  - Handle authentication if required (TradingView API key)

- [ ] Add environment variables:
  ```bash
  # .env
  TRADINGVIEW_ENABLED=true
  TRADINGVIEW_MCP_PATH=/path/to/tradingview-mcp-server
  TRADINGVIEW_API_KEY=your_api_key_here  # If required
  ```

### Phase 2: Chart Generation

- [ ] Create `src/datasources/tradingview.py`:
  - **TradingViewAdapter** class (inherits from `BaseDataAdapter`)
  - **generate_chart(ticker, timeframe, indicators)**: Generate chart image
    - Timeframes: "1D" (daily), "1H" (hourly), "5m" (5-minute)
    - Indicators to include:
      - **RSI** (Relative Strength Index) - Overbought/oversold
      - **MACD** (Moving Average Convergence Divergence) - Trend
      - **Bollinger Bands** - Volatility
      - **Volume** - Trading activity
      - **EMA 20/50/200** - Moving averages
      - **Support/Resistance levels** - Key price levels
  - Returns: Chart image (PNG/JPG) + metadata
- [ ] Chart configuration template:

  ```python
  CHART_CONFIG = {
      "symbol": "{ticker}",
      "interval": "D",  # Daily
      "range": "3M",  # Last 3 months
      "studies": [
          "RSI@tv-basicstudies",  # RSI (14)
          "MACD@tv-basicstudies",  # MACD (12,26,9)
          "BB@tv-basicstudies",  # Bollinger Bands (20,2)
          "MAExp@tv-basicstudies:20",  # EMA 20
          "MAExp@tv-basicstudies:50",  # EMA 50
          "MAExp@tv-basicstudies:200"  # EMA 200
      ],
      "width": 1200,  # Chart width in pixels
      "height": 800,  # Chart height
      "theme": "dark"  # Dark mode for better contrast
  }
  ```

- [ ] Save charts to disk:
  - Path: `data/charts/{ticker}_{date}_{timeframe}.png`
  - Cache charts for 1 hour (prices update frequently)
  - Clean up old charts (delete after 7 days)

### Phase 3: Vision LLM Analysis

- [ ] Create `src/analysis/chart_analyzer.py`:
  - **ChartAnalyzer** class with vision LLM integration
  - **analyze_chart(image_path, ticker)**: Analyze chart visually
  - Use OpenAI GPT-4 Vision or Anthropic Claude 3 (Opus/Sonnet)
- [ ] Vision LLM prompt template:

  ```python
  CHART_ANALYSIS_PROMPT = """
  You are a professional technical analyst reviewing a stock chart for ${TICKER}.

  The chart shows:
  - Price action (candlesticks) for the last 3 months
  - RSI (14) indicator
  - MACD indicator
  - Bollinger Bands
  - Volume bars
  - EMA 20, 50, 200 (moving averages)

  Analyze the chart and provide:

  1. TREND ANALYSIS:
     - Current trend: bullish/bearish/neutral
     - Trend strength: strong/moderate/weak
     - Key support levels visible
     - Key resistance levels visible

  2. INDICATOR SIGNALS:
     - RSI: Is it overbought (>70), oversold (<30), or neutral?
     - MACD: Bullish crossover, bearish crossover, or neutral?
     - Bollinger Bands: Price near upper band (overbought), lower band (oversold), or middle?
     - Volume: Increasing, decreasing, or stable?

  3. PATTERNS:
     - Any chart patterns visible? (head & shoulders, double top/bottom, triangle, etc.)
     - Any candlestick patterns? (hammer, doji, engulfing, etc.)

  4. TRADE SETUP:
     - Is this a good entry point? (yes/no/maybe)
     - Recommended action: BUY/SELL/HOLD
     - Risk level: low/medium/high
     - Target price (if bullish)
     - Stop loss (if entering trade)

  5. CONFIDENCE:
     - How confident are you in this analysis? (0-1)

  Return JSON:
  {
    "trend": "bullish",
    "trend_strength": "strong",
    "support_levels": [145.50, 142.00],
    "resistance_levels": [152.00, 155.00],

    "indicators": {
      "rsi": {"value": 45, "signal": "neutral"},
      "macd": {"signal": "bullish_crossover"},
      "bollinger": {"position": "lower_band", "signal": "oversold"},
      "volume": {"trend": "increasing"}
    },

    "patterns": ["falling wedge (bullish)", "hammer candle (bullish)"],

    "trade_setup": {
      "entry_point": "yes",
      "action": "BUY",
      "risk_level": "medium",
      "target_price": 158.00,
      "stop_loss": 144.00,
      "risk_reward_ratio": 2.5
    },

    "confidence": 0.75,
    "reasoning": "Falling wedge pattern with bullish divergence on RSI. Price bouncing off lower Bollinger Band. MACD showing bullish crossover. Volume increasing on upswing."
  }
  """
  ```

- [ ] Return structured `TechnicalAnalysis` model:
  ```python
  @dataclass
  class TechnicalAnalysis:
      ticker: str
      chart_image_path: str
      analyzed_at: datetime

      trend: str  # "bullish", "bearish", "neutral"
      trend_strength: str  # "strong", "moderate", "weak"
      support_levels: list[float]
      resistance_levels: list[float]

      indicators: dict  # RSI, MACD, Bollinger, Volume
      patterns: list[str]  # Chart patterns identified

      trade_setup: dict  # Entry point, action, risk, targets
      confidence: float  # 0-1
      reasoning: str
  ```

### Phase 4: Integration with Reddit Strategy

- [ ] Update `RedditSentimentStrategy._refresh_sentiment_data()`:
  - After research pipeline, generate TradingView charts
  - Analyze charts with vision LLM
  - Store technical analysis in `candidate.rationale.technical_analysis`
- [ ] Add technical analysis to score:

  ```python
  # Combine signals
  if technical_analysis.trade_setup["action"] == "BUY":
      if technical_analysis.risk_level == "low":
          score += 0.15  # Strong technical setup
      elif technical_analysis.risk_level == "medium":
          score += 0.10  # Moderate technical setup

  if technical_analysis.trade_setup["action"] == "SELL":
      score -= 0.20  # Technical says sell, reduce score

  # Bonus for pattern alignment
  bullish_patterns = ["falling wedge", "double bottom", "inverse head and shoulders"]
  if any(p in technical_analysis.patterns for p in bullish_patterns):
      score += 0.05
  ```

- [ ] Store in `candidate.rationale`:
  ```json
  {
    "llm_analysis": { ... },
    "research": { ... },
    "technical_analysis": {
      "chart_url": "/data/charts/NEM_2025-11-01_1D.png",
      "trend": "bullish",
      "trend_strength": "strong",
      "support_levels": [145.50, 142.00],
      "resistance_levels": [152.00, 155.00],
      "indicators": {
        "rsi": {"value": 45, "signal": "neutral"},
        "macd": {"signal": "bullish_crossover"},
        "bollinger": {"position": "lower_band", "signal": "oversold"}
      },
      "patterns": ["falling wedge (bullish)", "hammer candle"],
      "trade_setup": {
        "action": "BUY",
        "entry_point": true,
        "risk_level": "medium",
        "target_price": 158.00,
        "stop_loss": 144.00,
        "risk_reward_ratio": 2.5
      },
      "confidence": 0.75,
      "reasoning": "Falling wedge pattern with bullish divergence..."
    }
  }
  ```

### Phase 5: Frontend Display

- [ ] Update `CandidateDetailModal.tsx` with "Technical" tab:

  - **Chart Image Display**:

    - Full-width chart image (1200x800)
    - Zoom controls (click to enlarge)
    - Download button (save chart as PNG)

  - **Trend Summary**:

    - Large badge: 🟢 BULLISH | 🔴 BEARISH | 🟡 NEUTRAL
    - Trend strength meter
    - Support/resistance levels visualized

  - **Indicator Signals**:

    - Grid of indicator cards:
      - RSI: 45 (Neutral) ➡️
      - MACD: Bullish Crossover 📈
      - Bollinger Bands: Oversold (Lower Band) 🔽
      - Volume: Increasing 📊

  - **Patterns Detected**:

    - List of patterns with icons
    - Bullish patterns: 🟢 | Bearish patterns: 🔴

  - **Trade Setup**:

    - Action button: 🟢 BUY | 🔴 SELL | 🟡 HOLD
    - Risk level badge: Low/Medium/High
    - Entry price, target, stop loss
    - Risk/reward ratio

  - **LLM Reasoning**:
    - Full explanation of why this setup is good/bad
    - Confidence meter (0-100%)

- [ ] Add technical summary to candidate cards:
  - Small badge: "📈 BUY Setup" (green)
  - Or: "📉 SELL Signal" (red)
  - Or: "➡️ HOLD" (yellow)
  - Show risk level: 🟢 Low | 🟡 Medium | 🔴 High

### Phase 6: Configuration & Optimization

- [ ] Add to `src/strategies/reddit_sentiment/config.yml`:

  ```yaml
  technical_analysis:
    enabled: true
    chart_timeframe: "1D" # Daily charts
    chart_range: "3M" # Last 3 months
    vision_model: "gpt-4-vision-preview" # or "claude-3-opus-20240229"
    cache_charts: true
    cache_ttl_seconds: 3600 # 1 hour
    cleanup_after_days: 7

    indicators:
      - "RSI"
      - "MACD"
      - "BollingerBands"
      - "Volume"
      - "EMA_20"
      - "EMA_50"
      - "EMA_200"

    scoring:
      buy_signal_low_risk: 0.15
      buy_signal_medium_risk: 0.10
      sell_signal: -0.20
      bullish_pattern_bonus: 0.05
  ```

- [ ] Add caching to avoid regenerating charts:
  - Cache key: `tradingview_chart:{ticker}:{date}:{timeframe}`
  - TTL: 1 hour (charts update frequently)
  - Store both image and analysis results

### Testing

- [ ] Unit tests for TradingView adapter:

  - Test chart generation with mock MCP server
  - Test indicator configuration
  - Test error handling (invalid ticker, MCP timeout)

- [ ] Unit tests for chart analyzer:

  - Mock vision LLM responses
  - Test JSON parsing and validation
  - Test confidence scoring

- [ ] Integration tests:

  - Generate real chart for known ticker (AAPL)
  - Analyze with vision LLM
  - Verify structured output
  - Check chart image saved correctly

- [ ] Manual testing:
  - Generate charts for 5 different stocks
  - Review vision LLM analysis accuracy
  - Compare with actual TradingView charts
  - Validate trade setups make sense

---

## 🔗 Dependencies

- Task 5.4 (Candidate Detail Modal) ✅ - Display technical tab
- Reddit Sentiment Strategy (completed) - Integration point
- TradingView MCP Server (external dependency)

---

## ✅ Validation Steps

### Manual Testing

```bash
# Terminal 1: Start TradingView MCP server
npx @modelcontextprotocol/server-tradingview

# Terminal 2: Test chart generation
python
>>> from src.datasources.tradingview import TradingViewAdapter
>>> adapter = TradingViewAdapter()
>>>
>>> # Generate chart
>>> chart_path = adapter.generate_chart("AAPL", timeframe="1D", indicators=["RSI", "MACD", "BB"])
>>> print(chart_path)
# Should return: data/charts/AAPL_2025-11-01_1D.png
>>>
>>> # Analyze chart
>>> from src.analysis.chart_analyzer import ChartAnalyzer
>>> analyzer = ChartAnalyzer()
>>> analysis = analyzer.analyze_chart(chart_path, "AAPL")
>>> print(analysis.trade_setup)
# Should show: {"action": "BUY", "risk_level": "medium", ...}
```

### Automated Testing

```bash
# Backend tests
pytest tests/unit/test_datasources_tradingview.py -v
pytest tests/unit/test_analysis_chart_analyzer.py -v
pytest tests/integration/test_tradingview_pipeline.py -v

# Full scan with technical analysis
python scripts/one_shot_scan.py --strategy reddit_sentiment --technical-enabled
# Check database for technical_analysis in candidate.rationale
```

### Visual Validation

```bash
# Generate charts for test tickers
python scripts/generate_test_charts.py --tickers AAPL,MSFT,NEM,TSLA,NVDA

# Open charts in browser
open data/charts/*.png

# Compare with actual TradingView
# Visit: https://www.tradingview.com/chart/
# Verify indicators match
```

---

## 📦 Deliverables

### Backend - TradingView Integration

- [ ] `src/datasources/tradingview.py` (300 lines)
  - `TradingViewAdapter` class
  - `generate_chart(ticker, timeframe, indicators) -> str`
  - `_configure_chart(ticker, config) -> dict`
  - MCP client integration
  - Chart caching with TTL

### Backend - Vision Analysis

- [ ] `src/analysis/__init__.py`
- [ ] `src/analysis/chart_analyzer.py` (250 lines)
  - `ChartAnalyzer` class
  - `analyze_chart(image_path, ticker) -> TechnicalAnalysis`
  - Vision LLM integration (GPT-4V or Claude 3)
  - Structured output parsing

### Backend - Integration

- [ ] `src/strategies/reddit_sentiment/implementation.py` - Updated with technical analysis
- [ ] `src/strategies/reddit_sentiment/config.yml` - Add technical_analysis section

### Backend - Tests

- [ ] `tests/unit/test_datasources_tradingview.py` (100 lines, 10+ tests)
- [ ] `tests/unit/test_analysis_chart_analyzer.py` (120 lines, 12+ tests)
- [ ] `tests/integration/test_tradingview_pipeline.py` (80 lines, 5+ tests)

### Frontend

- [ ] `frontend/src/components/TechnicalTab.tsx` (250 lines)
  - Chart image display with zoom
  - Trend summary section
  - Indicator signals grid
  - Patterns list
  - Trade setup card
- [ ] `frontend/src/components/ChartImage.tsx` (80 lines)
  - Zoomable image component
  - Download button
  - Loading state
- [ ] `frontend/src/components/TradeSetup.tsx` (100 lines)
  - Action button (BUY/SELL/HOLD)
  - Risk level indicator
  - Price targets and stop loss
  - Risk/reward visualization

### Scripts

- [ ] `scripts/generate_test_charts.py` (50 lines)
  - Generate charts for testing
  - Batch chart generation

### Documentation

- [ ] `docs/tradingview-integration.md` - Setup and usage guide
- [ ] Update `AGENTS.md` - Add TradingView/vision LLM conventions
- [ ] Update `docs/api.md` - Document technical analysis structures

---

## 📝 Implementation Notes

### TradingView MCP Server

The TradingView MCP server provides programmatic access to TradingView charts:

```javascript
// Example MCP request
{
  "method": "chart/generate",
  "params": {
    "symbol": "NASDAQ:AAPL",
    "interval": "D",
    "range": "3M",
    "studies": [
      "RSI@tv-basicstudies",
      "MACD@tv-basicstudies"
    ],
    "width": 1200,
    "height": 800
  }
}

// Response
{
  "image": "base64_encoded_png",
  "metadata": {
    "symbol": "AAPL",
    "last_price": 178.45,
    "timestamp": "2025-11-01T16:00:00Z"
  }
}
```

### Vision LLM Options

**Option A: OpenAI GPT-4 Vision** (Recommended for accuracy):

```python
import openai

response = openai.ChatCompletion.create(
    model="gpt-4-vision-preview",
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": CHART_ANALYSIS_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
            ]
        }
    ],
    max_tokens=1000
)
```

**Option B: Anthropic Claude 3 Opus** (Best vision capability):

```python
import anthropic

response = anthropic.messages.create(
    model="claude-3-opus-20240229",
    max_tokens=1000,
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": CHART_ANALYSIS_PROMPT},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_base64}}
            ]
        }
    ]
)
```

### Chart Caching Strategy

```python
# Cache structure
cache_key = f"tradingview:{ticker}:{date}:{timeframe}"
cache_data = {
    "chart_path": "data/charts/AAPL_2025-11-01_1D.png",
    "analysis": TechnicalAnalysis(...),
    "generated_at": datetime.now()
}

# Cache for 1 hour (charts update frequently)
cache.set(cache_key, cache_data, ttl_seconds=3600)
```

---

## 🐛 Edge Cases

1. **TradingView MCP server is down**

   - Gracefully skip technical analysis
   - Log error but don't fail entire scan
   - Return `technical_analysis: null` in rationale

2. **Chart generation timeout**

   - Set timeout: 30 seconds max
   - Retry once with exponential backoff
   - If still fails, skip technical analysis

3. **Vision LLM returns invalid JSON**

   - Parse with error handling
   - Fall back to partial analysis
   - Log warning with raw response

4. **Ticker not found on TradingView**

   - Handle gracefully (some stocks not on TradingView)
   - Try alternative symbols (e.g., add exchange prefix)
   - Skip if still not found

5. **Chart too large (> 5MB)**

   - Resize image before sending to vision LLM
   - Compress PNG with optimization
   - Or reduce chart dimensions (800x600 instead of 1200x800)

6. **Vision LLM API cost**
   - GPT-4V: ~$0.01 per image
   - Claude 3: ~$0.015 per image
   - Cache aggressively to reduce API calls
   - Consider enabling only for high-confidence candidates (score > 0.6)

---

## ✨ Success Metrics

- [ ] Chart generation completes in <10 seconds per ticker
- [ ] Vision LLM analysis completes in <15 seconds per chart
- [ ] 95%+ of charts generated successfully
- [ ] Vision LLM returns valid JSON 98%+ of the time
- [ ] Technical signals align with actual chart patterns (manual spot-check)
- [ ] Trade setups have positive accuracy (backtest with historical data)
- [ ] Total technical analysis pipeline adds <30 seconds to scan time
- [ ] Charts cached effectively (90%+ cache hit rate on repeated scans)
- [ ] Users find technical tab helpful (subjective feedback)

---

## 🎨 UI/UX Mockup - Technical Tab

```
┌─────────────────────────────────────────────────────────────┐
│  Technical Analysis - AAPL                                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                                                         │ │
│  │  [TradingView Chart Image - 1200x800]                  │ │
│  │  - Candlesticks (3 months)                             │ │
│  │  - RSI indicator (bottom panel)                        │ │
│  │  - MACD indicator (bottom panel)                       │ │
│  │  - Bollinger Bands (overlaid)                          │ │
│  │  - Volume bars (bottom)                                │ │
│  │  - EMA 20/50/200 (overlaid)                            │ │
│  │                                                         │ │
│  │                    [🔍 Zoom] [⬇️ Download]             │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌─ Trend Summary ──────────────────────────────────────┐   │
│  │  🟢 BULLISH (Strong)                                  │   │
│  │  Support: $145.50, $142.00                            │   │
│  │  Resistance: $152.00, $155.00                         │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─ Indicator Signals ──────────────────────────────────┐   │
│  │  📊 RSI: 45 (Neutral) ➡️                             │   │
│  │  📈 MACD: Bullish Crossover 🟢                        │   │
│  │  📉 Bollinger: Lower Band (Oversold) 🔽              │   │
│  │  📊 Volume: Increasing 📊                             │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─ Patterns Detected ──────────────────────────────────┐   │
│  │  🟢 Falling Wedge (Bullish)                           │   │
│  │  🟢 Hammer Candle (Bullish)                           │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─ Trade Setup ────────────────────────────────────────┐   │
│  │  [🟢 BUY Setup]  Risk: 🟡 Medium  Confidence: 75%   │   │
│  │                                                        │   │
│  │  Entry: $148.00                                        │   │
│  │  Target: $158.00 (+6.7%)                               │   │
│  │  Stop Loss: $144.00 (-2.7%)                            │   │
│  │  Risk/Reward: 2.5:1                                    │   │
│  │                                                        │   │
│  │  "Falling wedge pattern with bullish divergence on    │   │
│  │   RSI. Price bouncing off lower Bollinger Band.       │   │
│  │   MACD showing bullish crossover. Volume increasing   │   │
│  │   on upswing."                                         │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 💡 Future Enhancements (Optional)

- [ ] **Multi-timeframe analysis**: Analyze 1D, 1H, 15m charts for confluence
- [ ] **Historical accuracy tracking**: Track if vision LLM trade setups work
- [ ] **Custom indicator combinations**: Let users configure which indicators
- [ ] **Real-time chart updates**: WebSocket connection to update charts live
- [ ] **Chart comparison**: Compare current chart to similar past patterns
- [ ] **Backtesting**: Test trade setups on historical data automatically
