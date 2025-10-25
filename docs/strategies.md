# Strategy Development Guide

## Overview

Recover-Bot uses a **plug-in architecture** for strategies, allowing you to add new recovery detection strategies without modifying core code. Each strategy implements a standard interface (`StrategyProtocol`) and is automatically discovered at runtime.

This guide covers:
- Strategy interface specification
- Creating a new strategy
- Configuration and testing
- Best practices

---

## Strategy Interface

All strategies must implement the `StrategyProtocol` interface defined in `src/strategies/base.py`.

### Required Properties

#### `name: str`
Unique strategy identifier (slug format: lowercase, hyphens/underscores).

**Example**: `"drop5"`, `"gap_reversal"`, `"oversold-bounce"`

#### `version: str`
Semantic version string for reproducibility.

**Example**: `"1.0.0"`, `"2.3.1"`

#### `config_schema: type[StrategyConfig]`
Pydantic model class for configuration validation.

**Default**: `StrategyConfig` (can be extended for custom parameters)

---

### Required Methods

#### `filters(ticker_data: dict[str, Any]) -> bool`
**Purpose**: Pre-filter tickers before fetching detailed data.

**When Called**: First stage of pipeline, before expensive API calls.

**Input**: Basic ticker metadata
```python
{
    "symbol": "AAPL",
    "name": "Apple Inc.",
    "sector": "Technology",
    "market_cap": 2_800_000_000_000,  # $2.8T
    "avg_volume": 50_000_000,
    "current_price": 185.50,
    "price_change_pct": -5.2
}
```

**Output**: `True` to process ticker, `False` to skip

**Performance**: Should be fast (~1ms) using only basic data

**Example**:
```python
def filters(self, ticker_data: dict[str, Any]) -> bool:
    """Only process liquid stocks with sufficient drop."""
    return (
        ticker_data["market_cap"] > 1_000_000_000  # $1B+ market cap
        and ticker_data["avg_volume"] > 1_000_000  # 1M+ daily volume
        and ticker_data["price_change_pct"] < -3.0  # At least -3% drop
    )
```

---

#### `features(ticker_data: dict[str, Any]) -> dict[str, Any]`
**Purpose**: Extract strategy-specific features from detailed data.

**When Called**: After `filters()` passes, with full OHLCV data loaded.

**Input**: Detailed ticker data
```python
{
    "symbol": "AAPL",
    "asof": date(2025, 10, 24),
    "bars": [
        {"date": "2025-10-20", "open": 190, "high": 192, "low": 188, "close": 191, "volume": 45_000_000},
        {"date": "2025-10-21", "open": 191, "high": 193, "low": 189, "close": 192, "volume": 50_000_000},
        # ... last N days
    ],
    "indicators": {
        "atr": 3.5,
        "rsi": 28.5,
        "sma_20": 195.2,
        "sma_50": 198.7,
        "ema_12": 194.1,
        "volume_20d_avg": 48_000_000
    },
    "attribution": {
        "source": "yahoo_finance",
        "timestamp": "2025-10-24T16:30:00Z",
        "url": "https://query1.finance.yahoo.com/..."
    }
}
```

**Output**: Dictionary of computed features (must be JSON-serializable)

**Storage**: Features are stored in database for reproducibility and backtesting

**Example**:
```python
def features(self, ticker_data: dict[str, Any]) -> dict[str, Any]:
    """Compute drop recovery features."""
    bars = ticker_data["bars"]
    current = bars[-1]
    previous = bars[-2]
    indicators = ticker_data["indicators"]

    drop_pct = ((current["close"] - previous["close"]) / previous["close"]) * 100
    volume_ratio = current["volume"] / indicators["volume_20d_avg"]
    sma_distance = ((current["close"] - indicators["sma_20"]) / indicators["sma_20"]) * 100

    return {
        "drop_pct": drop_pct,
        "rsi": indicators["rsi"],
        "volume_ratio": volume_ratio,
        "sma_distance": sma_distance,
        "atr": indicators["atr"]
    }
```

---

#### `score(features: dict[str, Any]) -> float`
**Purpose**: Compute recovery probability from features.

**Input**: Feature dictionary from `features()` method

**Output**: Score between `0.0` (no recovery expected) and `1.0` (high confidence)

**Constraints**:
- Must return value in range [0.0, 1.0]
- Return values <0 or >1 will be clamped (with warning)
- NaN or Inf raises `ValueError`

**Interpretation**:
- `< 0.3`: Low probability, unlikely candidate
- `0.3 - 0.6`: Medium probability, monitor
- `> 0.6`: High probability, strong candidate
- `> 0.8`: Very high probability, top candidate

**Example** (Rules-based):
```python
def score(self, features: dict[str, Any]) -> float:
    """Compute recovery score using rules."""
    score = 0.5  # Base score

    # Factor 1: Drop magnitude (-5% to -15% ideal)
    drop = abs(features["drop_pct"])
    if 5 <= drop <= 15:
        score += 0.15
    elif drop > 15:
        score -= 0.1  # Too extreme

    # Factor 2: RSI oversold
    if features["rsi"] < 30:
        score += 0.20  # Oversold
    elif features["rsi"] > 70:
        score -= 0.15  # Overbought

    # Factor 3: Volume spike
    if features["volume_ratio"] > 2.0:
        score += 0.15  # High interest

    # Factor 4: Distance from SMA
    if features["sma_distance"] < -5:
        score += 0.10  # Below moving average

    return max(0.0, min(1.0, score))  # Clamp to [0, 1]
```

**Example** (ML-based - future):
```python
def score(self, features: dict[str, Any]) -> float:
    """Compute recovery score using trained model."""
    # Load pre-trained model
    model = self._load_model(self.config.parameters["model_path"])

    # Convert features to model input format
    X = self._features_to_array(features)

    # Predict probability
    probability = model.predict_proba(X)[0, 1]  # Probability of recovery

    return float(probability)
```

---

#### `label(entry_data: dict[str, Any], outcome_data: dict[str, Any]) -> bool`
**Purpose**: Label whether recovery occurred (for backtesting and evaluation).

**When Called**: During backfill or evaluation, after recovery window has passed.

**Input**:

`entry_data` - State at candidate identification:
```python
{
    "symbol": "AAPL",
    "entry_date": date(2025, 10, 24),
    "entry_price": 185.50,
    "features": {
        "drop_pct": -5.2,
        "rsi": 28.5,
        # ... all features from features()
    }
}
```

`outcome_data` - Data after recovery window:
```python
{
    "bars": [
        # OHLCV bars from entry_date to entry_date + window
        {"date": "2025-10-24", "close": 185.50},
        {"date": "2025-10-25", "close": 187.00},
        {"date": "2025-10-28", "close": 190.00},
        # ...
    ],
    "max_price": 192.50,  # Highest close in window
    "close_price": 190.00,  # Final close in window
    "returns": {
        "t1": 0.008,  # T+1 return
        "t3": 0.024,  # T+3 return
        "t5": 0.021   # T+5 return
    }
}
```

**Output**: `True` if recovery occurred, `False` otherwise

**Purpose**: Used to calculate hit-rate, precision, and calibrate scores

**Example**:
```python
def label(self, entry_data: dict[str, Any], outcome_data: dict[str, Any]) -> bool:
    """Label recovery: 80% of drop recovered within 5 days."""
    entry_price = entry_data["entry_price"]
    drop_pct = abs(entry_data["features"]["drop_pct"])
    max_price = outcome_data["max_price"]

    # Recovery percentage
    recovery_pct = ((max_price - entry_price) / entry_price) * 100

    # Recovered if at least 80% of drop is reversed
    target_recovery = drop_pct * 0.8
    return recovery_pct >= target_recovery
```

---

## Creating a New Strategy

### Step 1: Create Strategy Folder

```bash
mkdir -p src/strategies/my_strategy
cd src/strategies/my_strategy
```

### Step 2: Create `implementation.py`

```python
"""My Strategy - [Brief Description]."""

from typing import Any

from src.strategies.base import BaseStrategy


class MyStrategy(BaseStrategy):
    """[Detailed description of strategy logic]."""

    name = "my_strategy"
    version = "1.0.0"

    def filters(self, ticker_data: dict[str, Any]) -> bool:
        """[Filter description]."""
        # Your filtering logic
        return True

    def features(self, ticker_data: dict[str, Any]) -> dict[str, Any]:
        """[Feature description]."""
        # Your feature extraction
        return {}

    def score(self, features: dict[str, Any]) -> float:
        """[Scoring description]."""
        # Your scoring logic
        score = 0.5
        return self.validate_score(score)  # Clamps to [0, 1]

    def label(
        self, entry_data: dict[str, Any], outcome_data: dict[str, Any]
    ) -> bool:
        """[Labeling description]."""
        # Your recovery definition
        return False
```

### Step 3: Create `config.yml`

```yaml
name: my_strategy
version: 1.0.0
description: "My custom recovery strategy"
enabled: true
parameters:
  # Strategy-specific parameters
  min_drop_pct: 5.0
  max_drop_pct: 15.0
  rsi_oversold: 30
  volume_threshold: 2.0
  recovery_window: 5  # days
  recovery_threshold: 0.8  # 80% of drop
```

### Step 4: Create Tests

Create `tests/test_my_strategy.py`:

```python
"""Tests for my_strategy."""

import pytest

from src.strategies.my_strategy.implementation import MyStrategy


@pytest.fixture
def strategy():
    """Create strategy instance for testing."""
    return MyStrategy()


def test_filters(strategy):
    """Test filter logic."""
    # Test case: should pass filter
    ticker_data = {
        "symbol": "AAPL",
        "market_cap": 2_000_000_000_000,
        "avg_volume": 50_000_000,
        "price_change_pct": -5.2
    }
    assert strategy.filters(ticker_data) is True

    # Test case: should fail filter (low volume)
    ticker_data["avg_volume"] = 500_000
    assert strategy.filters(ticker_data) is False


def test_features(strategy):
    """Test feature extraction."""
    ticker_data = {
        "symbol": "AAPL",
        "bars": [...],  # Mock OHLCV data
        "indicators": {...}  # Mock indicators
    }
    features = strategy.features(ticker_data)

    assert "drop_pct" in features
    assert isinstance(features["drop_pct"], (int, float))


def test_score_range(strategy):
    """Test score is in valid range."""
    features = {"drop_pct": -5.0, "rsi": 25}
    score = strategy.score(features)

    assert 0.0 <= score <= 1.0


def test_label(strategy):
    """Test recovery labeling."""
    entry_data = {
        "entry_price": 100.0,
        "features": {"drop_pct": -5.0}
    }
    outcome_data = {
        "max_price": 104.0,  # Recovered 80% of 5% drop
        "returns": {"t5": 0.04}
    }

    # Should label as recovery (4% gain >= 80% of 5% drop)
    assert strategy.label(entry_data, outcome_data) is True
```

### Step 5: Test Your Strategy

```bash
# Run strategy tests
pytest tests/test_my_strategy.py -v

# Run all tests
make test

# Check code quality
make lint
```

### Step 6: Enable Strategy

Strategy is auto-discovered if:
1. Located in `src/strategies/my_strategy/implementation.py`
2. Class implements `StrategyProtocol`
3. `config.yml` has `enabled: true`

To enable/disable in main config:

```yaml
# config/config.yaml
strategies:
  enabled_strategies:
    - drop5
    - my_strategy  # Add your strategy
```

---

## Best Practices

### 1. Keep Filters Fast
Filters are called for ALL tickers before fetching data. Keep logic simple:

✅ **Good**: Basic comparisons on provided metadata
```python
def filters(self, ticker_data: dict[str, Any]) -> bool:
    return (
        ticker_data["market_cap"] > 1_000_000_000
        and ticker_data["avg_volume"] > 1_000_000
    )
```

❌ **Bad**: Complex calculations or external API calls
```python
def filters(self, ticker_data: dict[str, Any]) -> bool:
    # DON'T DO THIS - too expensive!
    historical_data = fetch_5_years_of_data(ticker_data["symbol"])
    ml_prediction = run_model(historical_data)
    return ml_prediction > 0.5
```

### 2. Make Features Reproducible
Features are versioned and stored. Ensure deterministic computation:

✅ **Good**: Deterministic calculations from provided data
```python
def features(self, ticker_data: dict[str, Any]) -> dict[str, Any]:
    bars = ticker_data["bars"]
    return {
        "drop_pct": self._calculate_drop(bars),
        "rsi": ticker_data["indicators"]["rsi"]
    }
```

❌ **Bad**: Non-deterministic or external dependencies
```python
def features(self, ticker_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": time.time(),  # Non-deterministic!
        "random_value": random.random(),  # Non-reproducible!
        "api_sentiment": fetch_sentiment(ticker)  # External dependency!
    }
```

### 3. Document Your Scoring Logic
Add clear comments explaining how scores are computed:

```python
def score(self, features: dict[str, Any]) -> float:
    """
    Scoring Logic:
    - Base score: 0.5
    - Drop 5-15%: +0.15 (ideal range)
    - RSI < 30: +0.20 (oversold)
    - Volume > 2x avg: +0.15 (spike)
    - Below SMA20: +0.10 (mean reversion opportunity)

    Max possible: 1.0
    Min possible: 0.0
    """
    score = 0.5
    # ... implementation
    return self.validate_score(score)
```

### 4. Test Edge Cases

```python
def test_edge_cases(strategy):
    """Test edge cases and boundary conditions."""

    # Test extreme drop
    features = {"drop_pct": -50.0, "rsi": 10}
    score = strategy.score(features)
    assert 0.0 <= score <= 1.0  # Should handle extreme values

    # Test missing data
    incomplete_features = {"drop_pct": -5.0}  # Missing RSI
    score = strategy.score(incomplete_features)
    # Should handle gracefully (not crash)

    # Test zero division
    features = {"drop_pct": 0.0, "rsi": 50}
    score = strategy.score(features)
    assert not math.isnan(score)
```

### 5. Use Structured Logging

```python
from src.ops.logging import get_logger

class MyStrategy(BaseStrategy):
    def __init__(self, config=None):
        super().__init__(config)
        self.logger = get_logger(f"strategy.{self.name}")

    def score(self, features: dict[str, Any]) -> float:
        """Compute score with logging."""
        score = self._compute_score(features)

        self.logger.info(
            "Score computed",
            strategy=self.name,
            score=score,
            features=features,
            version=self.version
        )

        return self.validate_score(score)
```

### 6. Version Your Strategy
Increment version when changing logic:

- **Patch** (1.0.0 → 1.0.1): Bug fixes, no logic changes
- **Minor** (1.0.0 → 1.1.0): New features, backward compatible
- **Major** (1.0.0 → 2.0.0): Breaking changes to scoring/features

---

## Example Strategy: Drop5

See `src/strategies/drop5/` for a complete reference implementation:

```python
"""Drop 5% Recovery Strategy.

Identifies stocks that:
- Drop 5-15% in a single day
- Show oversold RSI (< 30)
- Have volume spike (> 2x average)
- Are liquid (market cap > $1B, volume > 1M)

Recovery defined as: Price recovers 80% of drop within 5 days.
"""

from typing import Any

from src.strategies.base import BaseStrategy, StrategyConfig


class Drop5Config(StrategyConfig):
    """Extended config for Drop5 strategy."""

    class Parameters:
        min_drop_pct: float = 5.0
        max_drop_pct: float = 15.0
        rsi_threshold: float = 30.0
        volume_ratio: float = 2.0
        recovery_window: int = 5
        recovery_threshold: float = 0.8


class Drop5Strategy(BaseStrategy):
    """Drop 5% recovery detection strategy."""

    name = "drop5"
    version = "1.0.0"

    @property
    def config_schema(self):
        return Drop5Config

    def filters(self, ticker_data: dict[str, Any]) -> bool:
        """Pre-filter for liquid stocks with sufficient drop."""
        return (
            ticker_data["market_cap"] > 1_000_000_000  # $1B+
            and ticker_data["avg_volume"] > 1_000_000  # 1M+ volume
            and -15 <= ticker_data["price_change_pct"] <= -5  # 5-15% drop
        )

    # ... rest of implementation
```

---

## Testing Strategies

### Unit Tests (Required)
Test each method in isolation:

```bash
pytest tests/unit/test_my_strategy.py -v
```

### Integration Tests (Recommended)
Test full pipeline with mock data:

```python
def test_full_pipeline(strategy):
    """Test complete strategy workflow."""
    # 1. Filter
    assert strategy.filters(mock_ticker_data)

    # 2. Features
    features = strategy.features(mock_detailed_data)
    assert "drop_pct" in features

    # 3. Score
    score = strategy.score(features)
    assert 0.0 <= score <= 1.0

    # 4. Label
    label = strategy.label(mock_entry_data, mock_outcome_data)
    assert isinstance(label, bool)
```

### Backtesting (Advanced)
Run strategy on historical data:

```bash
python scripts/backtest.py --strategy my_strategy --start 2024-01-01 --end 2024-12-31
```

---

## Deployment Checklist

Before deploying a new strategy:

- [ ] All unit tests passing
- [ ] Integration tests passing
- [ ] Linting checks passing (ruff, mypy)
- [ ] Code coverage > 80%
- [ ] Documentation complete (docstrings, examples)
- [ ] Config validation working
- [ ] Backtesting results acceptable (hit-rate, returns)
- [ ] Strategy versioned correctly
- [ ] Logging structured and informative
- [ ] Edge cases handled (missing data, extreme values)
- [ ] Performance acceptable (<1s per ticker)

---

## Troubleshooting

### Strategy Not Discovered
- Check file location: `src/strategies/my_strategy/implementation.py`
- Check class name matches config: `class MyStrategy(BaseStrategy)`
- Check `config.yml` has `enabled: true`
- Check logs: `grep "strategy" logs/recover-bot.log`

### Type Errors
- Ensure all type hints match protocol
- Run `mypy src/strategies/my_strategy/`
- Check dict keys match expected names

### Score Out of Range
- Use `self.validate_score(score)` to auto-clamp
- Add bounds checking in scoring logic
- Test edge cases (very high/low feature values)

### Low Hit-Rate
- Review labeling logic (may be too strict/lenient)
- Analyze false positives/negatives
- Adjust score thresholds
- Review feature importance

---

## Additional Resources

- **Base Protocol**: `src/strategies/base.py`
- **Reference Strategy**: `src/strategies/drop5/`
- **Strategy Tests**: `tests/unit/test_strategies_base.py`
- **Architecture**: `PLAN.md` (Strategies section)
- **Data Adapters**: `docs/datasources.md`

---

**Questions?** Check `AGENTS.md` for AI agent guidelines or raise an issue on GitHub.
