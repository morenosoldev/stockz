"""Base interfaces and protocols for strategy plug-ins.

This module defines the StrategyProtocol that all strategies must implement,
providing a consistent interface for the scanner engine.

Example:
    Create a new strategy by implementing the protocol:

    >>> from src.strategies.base import StrategyProtocol
    >>> class MyStrategy:
    ...     name = "my_strategy"
    ...     version = "1.0.0"
    ...
    ...     def filters(self, ticker_data):
    ...         return ticker_data["volume"] > 1_000_000
    ...
    ...     def features(self, ticker_data):
    ...         return {"price_change": ticker_data["close"] - ticker_data["open"]}
    ...
    ...     def score(self, features):
    ...         return min(1.0, abs(features["price_change"]) / 10.0)
    ...
    ...     def label(self, entry_data, outcome_data):
    ...         return outcome_data["close"] > entry_data["close"]
"""

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class StrategyConfig(BaseModel):
    """Base configuration schema for strategies.

    All strategy config.yml files should map to this or a derived schema.

    Attributes:
        name: Unique strategy identifier (slug format: lowercase, hyphens)
        version: Semantic version (e.g., "1.0.0")
        description: Human-readable description
        enabled: Whether strategy is active
        parameters: Strategy-specific parameters
    """

    name: str = Field(..., pattern=r"^[a-z0-9_-]+$", description="Strategy identifier")
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$", description="Semantic version")
    description: str = Field(..., min_length=1, description="Strategy description")
    enabled: bool = Field(default=True, description="Whether strategy is active")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Strategy-specific parameters"
    )


@runtime_checkable
class StrategyProtocol(Protocol):
    """Protocol defining the interface all strategies must implement.

    This uses Python's Protocol (PEP 544) for structural subtyping, allowing
    type checkers to validate strategy implementations without inheritance.

    All strategies must implement these properties and methods to be compatible
    with the scanner engine.

    Example:
        >>> from src.strategies.base import StrategyProtocol
        >>> class MyStrategy:
        ...     name = "my_strategy"
        ...     version = "1.0.0"
        ...
        ...     def filters(self, ticker_data): ...
        ...     def features(self, ticker_data): ...
        ...     def score(self, features): ...
        ...     def label(self, entry_data, outcome_data): ...
        >>> isinstance(MyStrategy(), StrategyProtocol)  # True
    """

    config: StrategyConfig

    @property
    def name(self) -> str:
        """Unique strategy identifier (slug format: lowercase, hyphens).

        Returns:
            Strategy name (e.g., "drop5", "gap-reversal")
        """
        ...

    @property
    def version(self) -> str:
        """Strategy version for reproducibility (semantic versioning).

        Returns:
            Version string (e.g., "1.0.0")
        """
        ...

    @property
    def config_schema(self) -> type[StrategyConfig]:
        """Pydantic model for strategy configuration validation.

        Returns:
            Pydantic BaseModel subclass defining config schema
        """
        ...

    def filters(self, ticker_data: dict[str, Any]) -> bool:
        """Pre-filter to determine if ticker should be processed.

        This is called BEFORE fetching detailed data to reduce API calls.
        Should be fast and use only basic ticker metadata.

        Args:
            ticker_data: Basic ticker information:
                - symbol (str): Ticker symbol
                - name (str): Company name
                - sector (str): Sector classification
                - market_cap (float): Market capitalization
                - avg_volume (float): Average daily volume
                - current_price (float): Latest price
                - price_change_pct (float): % change from previous close

        Returns:
            True if ticker should be processed, False to skip

        Example:
            >>> def filters(self, ticker_data):
            ...     # Only process stocks with sufficient liquidity
            ...     return (
            ...         ticker_data["market_cap"] > 1_000_000_000  # $1B+ cap
            ...         and ticker_data["avg_volume"] > 1_000_000  # 1M+ volume
            ...     )
        """
        ...

    def features(self, ticker_data: dict[str, Any]) -> dict[str, Any]:
        """Extract strategy-specific features from ticker data.

        This is called AFTER filters() passes and detailed data is fetched.
        Compute all features needed for scoring and labeling.

        Args:
            ticker_data: Detailed ticker data:
                - symbol (str): Ticker symbol
                - asof (date): Analysis date
                - bars (list): OHLCV bars (last N days)
                  - date, open, high, low, close, volume
                - indicators (dict): Pre-computed technical indicators
                  - atr, rsi, sma_20, sma_50, ema_12, etc.
                - attribution (Attribution): Data source metadata

        Returns:
            Dictionary of computed features (JSON-serializable)

        Example:
            >>> def features(self, ticker_data):
            ...     close = ticker_data["bars"][-1]["close"]
            ...     prev_close = ticker_data["bars"][-2]["close"]
            ...     return {
            ...         "drop_pct": ((close - prev_close) / prev_close) * 100,
            ...         "rsi": ticker_data["indicators"]["rsi"],
            ...         "volume_ratio": ticker_data["bars"][-1]["volume"] / ticker_data["avg_volume"]
            ...     }
        """
        ...

    def score(self, features: dict[str, Any]) -> float:
        """Compute recovery probability score from features.

        This is the core strategy logic. Returns a score between 0.0 and 1.0
        representing the estimated probability of recovery.

        Args:
            features: Feature dictionary from features() method

        Returns:
            Score between 0.0 (no recovery expected) and 1.0 (high recovery probability)

        Raises:
            ValueError: If score is outside [0.0, 1.0] range

        Example:
            >>> def score(self, features):
            ...     # Simple rules-based scoring
            ...     base_score = 0.5
            ...     if features["drop_pct"] < -5:
            ...         base_score += 0.2  # Significant drop
            ...     if features["rsi"] < 30:
            ...         base_score += 0.2  # Oversold
            ...     if features["volume_ratio"] > 2:
            ...         base_score += 0.1  # Volume spike
            ...     return min(1.0, max(0.0, base_score))
        """
        ...

    def label(self, entry_data: dict[str, Any], outcome_data: dict[str, Any]) -> bool:
        """Label whether recovery occurred for evaluation.

        This is used for backtesting and strategy calibration. Determines if
        a candidate that met entry criteria actually recovered as expected.

        Args:
            entry_data: Data at candidate identification time:
                - symbol (str): Ticker symbol
                - entry_date (date): Candidate date
                - entry_price (float): Price at entry
                - features (dict): Feature values at entry
            outcome_data: Data after recovery window:
                - bars (list): OHLCV bars from entry_date to entry_date + window
                - max_price (float): Highest price in window
                - close_price (float): Final price in window
                - returns (dict): T+1, T+3, T+5 returns

        Returns:
            True if recovery occurred, False otherwise

        Example:
            >>> def label(self, entry_data, outcome_data):
            ...     # Recovery = price recovers 80% of drop within 5 days
            ...     entry_price = entry_data["entry_price"]
            ...     max_price = outcome_data["max_price"]
            ...     drop_pct = abs(entry_data["features"]["drop_pct"])
            ...     recovery_pct = ((max_price - entry_price) / entry_price) * 100
            ...     return recovery_pct >= (drop_pct * 0.8)
        """
        ...


class BaseStrategy:
    """Abstract base class for strategies (convenience wrapper).

    Provides a concrete base class with common utilities for strategy development.
    Strategies can inherit from this instead of implementing StrategyProtocol directly.

    Attributes:
        name: Strategy identifier
        version: Strategy version
        config: Parsed configuration from config.yml
        logger: Structured logger instance
    """

    def __init__(self, config: StrategyConfig | None = None):
        """Initialize strategy with configuration.

        Args:
            config: Parsed strategy configuration (from config.yml)
        """
        from src.ops.logging import get_logger

        self.config = config or StrategyConfig(
            name=self.name,
            version=self.version,
            description=f"{self.name} strategy",
        )
        self.logger = get_logger(f"strategy.{self.name}")

    @property
    def name(self) -> str:
        """Strategy identifier (must be overridden)."""
        raise NotImplementedError("Subclass must define 'name' property")

    @property
    def version(self) -> str:
        """Strategy version (must be overridden)."""
        raise NotImplementedError("Subclass must define 'version' property")

    @property
    def config_schema(self) -> type[StrategyConfig]:
        """Configuration schema (can be overridden for custom config)."""
        return StrategyConfig

    def filters(self, ticker_data: dict[str, Any]) -> bool:
        """Pre-filter implementation (must be overridden)."""
        raise NotImplementedError("Subclass must implement 'filters' method")

    def features(self, ticker_data: dict[str, Any]) -> dict[str, Any]:
        """Feature extraction implementation (must be overridden)."""
        raise NotImplementedError("Subclass must implement 'features' method")

    def score(self, features: dict[str, Any]) -> float:
        """Scoring implementation (must be overridden)."""
        raise NotImplementedError("Subclass must implement 'score' method")

    def label(self, entry_data: dict[str, Any], outcome_data: dict[str, Any]) -> bool:
        """Labeling implementation (must be overridden)."""
        raise NotImplementedError("Subclass must implement 'label' method")

    def validate_score(self, score: float) -> float:
        """Validate and clamp score to [0.0, 1.0] range.

        Args:
            score: Raw score value

        Returns:
            Clamped score between 0.0 and 1.0

        Raises:
            ValueError: If score is NaN or infinite
        """
        import math

        if math.isnan(score) or math.isinf(score):
            raise ValueError(f"Invalid score: {score} (must be finite number)")

        if score < 0.0:
            self.logger.warning(
                "Score below 0.0, clamping to 0.0",
                raw_score=score,
                strategy=self.name,
            )
            return 0.0

        if score > 1.0:
            self.logger.warning(
                "Score above 1.0, clamping to 1.0",
                raw_score=score,
                strategy=self.name,
            )
            return 1.0

        return score


def validate_strategy(strategy: Any) -> bool:
    """Validate that an object implements StrategyProtocol.

    Args:
        strategy: Object to validate

    Returns:
        True if valid strategy implementation

    Raises:
        TypeError: If strategy doesn't implement required methods/properties

    Example:
        >>> from src.strategies.base import validate_strategy
        >>> class MyStrategy:
        ...     name = "test"
        ...     version = "1.0.0"
        ...     # ... implement other methods
        >>> validate_strategy(MyStrategy())  # True or raises TypeError
    """
    required_attrs = ["name", "version", "config_schema"]
    required_methods = ["filters", "features", "score", "label"]

    # Check properties
    for attr in required_attrs:
        if not hasattr(strategy, attr):
            raise TypeError(f"Strategy missing required property: {attr}")

    # Check methods
    for method in required_methods:
        if not hasattr(strategy, method) or not callable(getattr(strategy, method)):
            raise TypeError(f"Strategy missing required method: {method}")

    # Validate name format
    name = strategy.name
    if not isinstance(name, str) or not name.islower() or " " in name:
        raise TypeError(
            f"Strategy name must be lowercase slug (got: {name}). "
            "Use hyphens or underscores, no spaces."
        )

    # Validate version format
    version = strategy.version
    if not isinstance(version, str):
        raise TypeError(f"Strategy version must be string (got: {type(version).__name__})")

    parts = version.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise TypeError(f"Strategy version must be semantic version X.Y.Z (got: {version})")

    return True
