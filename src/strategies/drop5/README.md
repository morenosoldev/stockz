# Drop 5% Recovery Strategy

**Strategy Name**: `drop5`
**Version**: 1.0.0
**Type**: Rules-Based Technical Analysis

## Overview

The Drop 5% Recovery strategy identifies stocks that experience a significant single-day price drop (5-15%) with technical indicators suggesting high recovery probability. The strategy targets mean reversion opportunities where liquid stocks with oversold conditions and volume confirmation are likely to bounce back.

## Strategy Logic

### Target Scenario

This strategy looks for stocks that have:
1. **Dropped 5-15% in price** (ideal range for recovery)
2. **Become technically oversold** (RSI < 30)
3. **Shown abnormal volume** (2x+ average)
4. **Maintained liquidity** (market cap > $1B, volume > 1M shares)

### Recovery Definition

A successful recovery is defined as:
- **Price recovers 80% of the drop within 5 days**
- Example: -10% drop → +8% recovery = success

This threshold balances realistic expectations with meaningful profit potential.

## Filters

Pre-screening criteria applied before detailed analysis:

| Filter | Threshold | Rationale |
|--------|-----------|-----------|
| **Market Cap** | ≥ $1 billion | Ensures liquidity and reduces small-cap volatility |
| **Average Volume** | ≥ 1 million shares | Ensures tradability and price discovery |
| **Price Drop** | -5% to -15% | Sweet spot: significant enough for opportunity, not catastrophic |

**Implementation**: `filters()` method
- Returns `True` if ticker passes all criteria
- Returns `False` to skip ticker from further processing

## Features

Extracted features for each candidate ticker:

| Feature | Description | Calculation |
|---------|-------------|-------------|
| **drop_pct** | Price decline percentage | ((current - previous) / previous) × 100 |
| **rsi** | Relative Strength Index | 14-period RSI (0-100 scale) |
| **volume_ratio** | Relative volume | current_volume / 20-day_avg_volume |
| **sma_distance** | Distance from 20-day SMA | ((price - sma_20) / sma_20) × 100 |
| **atr** | Average True Range | 14-period ATR (volatility measure) |

**Implementation**: `features()` method
- Requires: bars (OHLCV data), indicators (pre-computed)
- Returns: Dictionary of feature values
- Handles missing data gracefully with sensible defaults

## Scoring System

Rules-based scoring (0.0 to 1.0 scale):

### Base Score: 0.5

### Scoring Factors

| Factor | Condition | Score Adjustment |
|--------|-----------|------------------|
| **Drop Magnitude** | 5% ≤ drop ≤ 15% | +0.15 (ideal range) |
|  | drop > 15% | -0.10 (too extreme) |
| **RSI Oversold** | RSI < 30 | +0.20 (strong oversold) |
|  | 30 ≤ RSI < 40 | +0.10 (mild oversold) |
|  | RSI > 70 | -0.15 (overbought) |
| **Volume Spike** | volume_ratio > 2.0 | +0.15 (strong interest) |
|  | 1.5 < volume_ratio ≤ 2.0 | +0.08 (moderate interest) |
| **Below SMA** | sma_distance < -5% | +0.10 (mean reversion opportunity) |

### Scoring Examples

**High-Probability Candidate** (Score: ~1.0):
```python
{
    "drop_pct": -7.5,        # Ideal range: +0.15
    "rsi": 25.0,             # Strong oversold: +0.20
    "volume_ratio": 2.5,     # Strong spike: +0.15
    "sma_distance": -6.0     # Below SMA: +0.10
}
# Score: 0.5 + 0.15 + 0.20 + 0.15 + 0.10 = 1.10 → 1.0 (clamped)
```

**Low-Probability Candidate** (Score: ~0.25):
```python
{
    "drop_pct": -20.0,       # Too extreme: -0.10
    "rsi": 75.0,             # Overbought: -0.15
    "volume_ratio": 0.8,     # Low volume: +0.0
    "sma_distance": 5.0      # Above SMA: +0.0
}
# Score: 0.5 - 0.10 - 0.15 = 0.25
```

**Implementation**: `score()` method
- Returns: Float between 0.0 and 1.0
- Uses `validate_score()` to clamp values and handle NaN/Inf

## Recovery Labeling

**Implementation**: `label()` method

Used for backtesting and evaluation. Labels whether recovery occurred.

### Inputs
- **entry_data**: Candidate data at time of identification
  - `entry_price`: Price when candidate was identified
  - `features.drop_pct`: The initial drop percentage
- **outcome_data**: Data after recovery window (T+5 days)
  - `max_price`: Highest price reached in recovery window

### Logic
```python
recovery_pct = ((max_price - entry_price) / entry_price) × 100
target_recovery = abs(drop_pct) × 0.8

label = recovery_pct >= target_recovery  # True if recovered
```

### Example
```python
entry_price = 100.0
drop_pct = -10.0  # Stock dropped 10%
max_price = 108.5  # Highest price in next 5 days

recovery_pct = (108.5 - 100.0) / 100.0 × 100 = 8.5%
target = 10.0 × 0.8 = 8.0%

label = 8.5% >= 8.0% = True  # Recovery occurred
```

## Configuration

**File**: `config.yml`

```yaml
name: drop5
version: 1.0.0
description: "5-15% drop recovery strategy with volume confirmation"
enabled: true

parameters:
  # Filter thresholds
  min_market_cap: 1000000000    # $1 billion
  min_avg_volume: 1000000        # 1 million shares
  min_drop_pct: 5.0              # Minimum drop percentage
  max_drop_pct: 15.0             # Maximum drop percentage

  # Scoring parameters
  rsi_oversold: 30               # Strong oversold threshold
  rsi_mild_oversold: 40          # Mild oversold threshold
  rsi_overbought: 70             # Overbought threshold
  volume_spike_strong: 2.0       # Strong volume spike ratio
  volume_spike_moderate: 1.5     # Moderate volume spike ratio
  sma_distance_threshold: -5.0   # Below SMA threshold

  # Recovery parameters
  recovery_window_days: 5        # Days to check for recovery
  recovery_threshold: 0.8        # 80% of drop must be recovered
```

## Usage Examples

### Basic Usage

```python
from src.strategies.drop5.implementation import Drop5Strategy

strategy = Drop5Strategy()

# Filter ticker
ticker_data = {
    "market_cap": 5_000_000_000,
    "avg_volume": 2_000_000,
    "price_change_pct": -7.5,
}

if strategy.filters(ticker_data):
    print("Ticker passes filter")
```

### Feature Extraction

```python
ticker_data = {
    "bars": [
        {"close": 100.0, "volume": 1_000_000},
        {"close": 92.5, "volume": 3_000_000},
    ],
    "indicators": {
        "rsi": 28.0,
        "volume_20d_avg": 1_500_000,
        "sma_20": 105.0,
        "atr": 2.3,
    },
}

features = strategy.features(ticker_data)
print(f"Drop: {features['drop_pct']:.2f}%")
print(f"RSI: {features['rsi']:.1f}")
print(f"Volume Ratio: {features['volume_ratio']:.2f}x")
```

### Scoring

```python
features = {
    "drop_pct": -7.5,
    "rsi": 28.0,
    "volume_ratio": 2.0,
    "sma_distance": -4.8,
    "atr": 2.3,
}

score = strategy.score(features)
print(f"Recovery Probability: {score:.2%}")

if score >= 0.7:
    print("High-probability candidate")
```

### Recovery Labeling

```python
entry_data = {
    "entry_price": 92.5,
    "features": {"drop_pct": -7.5},
}

outcome_data = {
    "max_price": 98.5,  # Max price in next 5 days
}

recovered = strategy.label(entry_data, outcome_data)
print(f"Recovery occurred: {recovered}")
```

## Performance Metrics

### Expected Outcomes

Based on historical backtesting (to be implemented):

| Metric | Target | Notes |
|--------|--------|-------|
| **Hit Rate** | > 60% | Percentage of candidates that recover |
| **Avg Recovery** | 5-8% | Average gain on successful recoveries |
| **Max Drawdown** | < -3% | Risk on failed recoveries |
| **Win/Loss Ratio** | > 2:1 | Risk-reward profile |

*Note: These are target metrics. Actual performance will be validated in Task 2.8 (Backtesting).*

## Risk Considerations

### Risks

1. **Catastrophic News**: Strategy cannot predict company-specific disasters (fraud, bankruptcy)
2. **Market Crashes**: May fail during broad market selloffs
3. **Liquidity Events**: Flash crashes or circuit breakers
4. **Earnings Misses**: Post-earnings drops may not recover quickly

### Mitigations

1. **News Sentiment**: Future integration with news adapter to filter negative catalysts
2. **Market Context**: Check overall market trend (VIX, S&P 500)
3. **Stop Losses**: Implement 5% stop-loss in production
4. **Position Sizing**: Never risk more than 2% per candidate

## Development

### Testing

```bash
# Run Drop5 strategy tests
pytest tests/strategies/test_drop5.py -v

# Run with coverage
pytest tests/strategies/test_drop5.py --cov=src.strategies.drop5

# Expected: 45 tests, 100% coverage
```

### Extending the Strategy

To modify scoring logic:

1. Edit `src/strategies/drop5/implementation.py`
2. Update `score()` method
3. **Increment version** in `config.yml` and implementation
4. Add tests in `tests/strategies/test_drop5.py`
5. Document changes in this README

### Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-10-25 | Initial implementation with filters, features, scoring, labeling |

## Dependencies

- `src.strategies.base.BaseStrategy` - Base strategy interface
- `src.features.technical` - Technical indicators (RSI, ATR, SMA)
- `src.features.volume` - Volume analysis (RVOL)
- `src.features.price_action` - Price pattern detection
- `src.datasources.prices` - Price data fetching

## References

### Technical Indicators

- **RSI**: J. Welles Wilder, "New Concepts in Technical Trading Systems" (1978)
- **Bollinger Bands**: John Bollinger, "Bollinger on Bollinger Bands" (2001)
- **Volume Analysis**: Marc Chaikin's volume confirmation principles

### Mean Reversion Research

- Werner F.M. DeBondt and Richard H. Thaler, "Does the Stock Market Overreact?" (1985)
- Andrew W. Lo and A. Craig MacKinlay, "When Are Contrarian Profits Due to Stock Market Overreaction?" (1990)

## FAQ

### Q: Why 5-15% drop range?

**A**: Drops < 5% have less profit potential. Drops > 15% often indicate fundamental problems that prevent quick recovery. The 5-15% range balances opportunity with manageable risk.

### Q: Why 80% recovery threshold?

**A**: Full recovery (100%) is too strict and misses good partial recoveries. 80% provides meaningful profit while being achievable in the 5-day window.

### Q: Can I change the recovery window?

**A**: Yes, update `recovery_window_days` in `config.yml`. Common alternatives: 3 days (aggressive), 10 days (conservative).

### Q: How does this handle overnight gaps?

**A**: The strategy uses close-to-close changes, so overnight gaps are included in the drop calculation. Intraday drops are not detected in v1.

### Q: What about dividends?

**A**: Yahoo Finance provides adjusted prices that account for dividends and splits. No manual adjustment needed.

## Next Steps

1. **Integration**: Connect with scanner engine (Task 2.8)
2. **Backtesting**: Validate hit-rate and PnL metrics
3. **Optimization**: Tune thresholds using historical data
4. **News Filter**: Add negative catalyst detection
5. **Portfolio**: Combine with position sizing and risk management

## Contact

For questions or suggestions about this strategy:
- See `docs/strategies.md` for general strategy development guide
- Check `TASKS.md` for implementation status
- Review test suite in `tests/strategies/test_drop5.py`

---

**Last Updated**: October 25, 2025
**Status**: ✅ Implementation Complete (Tests: 45/45 passing, Coverage: 100%)
