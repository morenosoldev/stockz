"""
Price Action Feature Engineering.

Provides functions for detecting gaps, drops, reversals, and other
price action patterns commonly used in technical analysis.

All functions work with pandas DataFrames containing OHLCV data.
"""

import pandas as pd


class PriceActionError(Exception):
    """Base exception for price action errors."""

    pass


class InsufficientDataError(PriceActionError):
    """Raised when there's not enough data for analysis."""

    pass


def detect_gap(
    data: pd.DataFrame,
    gap_threshold: float = 1.0,
    open_col: str = "open",
    close_col: str = "close",
) -> pd.Series:
    """
    Detect price gaps (gap up or gap down).

    A gap occurs when today's open is significantly different from
    yesterday's close. Positive values indicate gap up, negative gap down.

    Args:
        data: DataFrame with OHLC data
        gap_threshold: Minimum gap size (%) to detect (default: 1.0)
        open_col: Name of the open column (default: "open")
        close_col: Name of the close column (default: "close")

    Returns:
        Series with gap percentage (positive = gap up, negative = gap down)

    Raises:
        PriceActionError: If required columns are missing
        InsufficientDataError: If less than 2 rows

    Example:
        >>> df = pd.DataFrame({
        ...     "open": [100, 105, 102],
        ...     "close": [102, 104, 101]
        ... })
        >>> gaps = detect_gap(df, gap_threshold=1.0)
        >>> assert gaps.iloc[1] > 1.0  # Gap up from 102 to 105
    """
    # Validate inputs
    required_cols = {open_col, close_col}
    missing_cols = required_cols - set(data.columns)
    if missing_cols:
        raise PriceActionError(f"Missing required columns: {missing_cols}")

    if len(data) < 2:
        raise InsufficientDataError(f"Need at least 2 rows for gap detection, got {len(data)}")

    # Calculate gap percentage
    prev_close = data[close_col].shift(1)
    today_open = data[open_col]

    gap_pct = ((today_open - prev_close) / prev_close) * 100

    # Set first row to 0 (no previous close)
    gap_pct.iloc[0] = 0.0

    return gap_pct


def detect_drop(
    data: pd.DataFrame,
    drop_threshold: float = 5.0,
    close_col: str = "close",
    lookback: int = 1,
) -> pd.Series:
    """
    Detect price drops (% decline from N periods ago).

    Args:
        data: DataFrame with price data
        drop_threshold: Minimum drop size (%) to detect (default: 5.0)
        close_col: Name of the close column (default: "close")
        lookback: Number of periods to look back (default: 1)

    Returns:
        Series with drop percentage (negative values = drop)

    Raises:
        PriceActionError: If required columns are missing
        InsufficientDataError: If less than lookback+1 rows

    Example:
        >>> df = pd.DataFrame({"close": [100, 95, 90]})
        >>> drops = detect_drop(df, drop_threshold=5.0, lookback=1)
        >>> assert drops.iloc[-1] < -5.0  # 10% drop from 95 to 90
    """
    # Validate inputs
    if close_col not in data.columns:
        raise PriceActionError(f"Missing required column: {close_col}")

    if len(data) < lookback + 1:
        raise InsufficientDataError(
            f"Need at least {lookback + 1} rows for drop detection, got {len(data)}"
        )

    # Calculate drop percentage
    prev_close = data[close_col].shift(lookback)
    current_close = data[close_col]

    drop_pct = ((current_close - prev_close) / prev_close) * 100

    return drop_pct


def detect_intraday_drop(
    data: pd.DataFrame,
    drop_threshold: float = 5.0,
    open_col: str = "open",
    low_col: str = "low",
    close_col: str = "close",
) -> pd.Series:
    """
    Detect intraday price drops (% decline from open to low or close).

    Measures the maximum intraday decline, useful for identifying
    selling pressure within a single period.

    Args:
        data: DataFrame with OHLC data
        drop_threshold: Minimum drop size (%) to detect (default: 5.0)
        open_col: Name of the open column (default: "open")
        low_col: Name of the low column (default: "low")
        close_col: Name of the close column (default: "close")

    Returns:
        Series with intraday drop percentage (negative values = drop)

    Raises:
        PriceActionError: If required columns are missing

    Example:
        >>> df = pd.DataFrame({
        ...     "open": [100, 100],
        ...     "low": [95, 92],
        ...     "close": [98, 94]
        ... })
        >>> drops = detect_intraday_drop(df)
        >>> assert drops.iloc[-1] < -5.0  # 8% intraday drop
    """
    # Validate inputs
    required_cols = {open_col, low_col, close_col}
    missing_cols = required_cols - set(data.columns)
    if missing_cols:
        raise PriceActionError(f"Missing required columns: {missing_cols}")

    # Calculate maximum intraday decline
    open_price = data[open_col]
    low_price = data[low_col]
    close_price = data[close_col]

    # Drop from open to low
    drop_to_low = ((low_price - open_price) / open_price) * 100

    # Drop from open to close
    drop_to_close = ((close_price - open_price) / open_price) * 100

    # Return the most negative (maximum drop)
    intraday_drop = pd.DataFrame({"to_low": drop_to_low, "to_close": drop_to_close}).min(axis=1)

    return intraday_drop


def detect_reversal_candle(
    data: pd.DataFrame,
    min_body_pct: float = 60.0,
    open_col: str = "open",
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
) -> pd.Series:
    """
    Detect bullish reversal candles (hammer, bullish engulfing).

    A reversal candle has:
    - Long lower shadow (at least 2x body size)
    - Small upper shadow
    - Body in upper 60% of total range
    - Close > Open (bullish)

    Args:
        data: DataFrame with OHLC data
        min_body_pct: Minimum % of range that body occupies (default: 60.0)
        open_col: Name of the open column (default: "open")
        high_col: Name of the high column (default: "high")
        low_col: Name of the low column (default: "low")
        close_col: Name of the close column (default: "close")

    Returns:
        Boolean Series indicating reversal candles

    Raises:
        PriceActionError: If required columns are missing

    Example:
        >>> df = pd.DataFrame({
        ...     "open": [100, 95],
        ...     "high": [101, 98],
        ...     "low": [99, 90],
        ...     "close": [100.5, 97]
        ... })
        >>> reversals = detect_reversal_candle(df)
        >>> assert reversals.iloc[-1] == True  # Hammer pattern
    """
    # Validate inputs
    required_cols = {open_col, high_col, low_col, close_col}
    missing_cols = required_cols - set(data.columns)
    if missing_cols:
        raise PriceActionError(f"Missing required columns: {missing_cols}")

    # Get price components
    open_price = data[open_col]
    high_price = data[high_col]
    low_price = data[low_col]
    close_price = data[close_col]

    # Calculate components
    total_range = high_price - low_price
    body_size = abs(close_price - open_price)
    lower_shadow = pd.DataFrame({"open": open_price, "close": close_price}).min(axis=1) - low_price
    upper_shadow = high_price - pd.DataFrame({"open": open_price, "close": close_price}).max(axis=1)

    # Reversal conditions
    is_bullish = close_price > open_price
    has_long_lower_shadow = lower_shadow >= (2 * body_size)
    has_small_upper_shadow = upper_shadow <= (0.5 * body_size)
    body_in_upper_range = (high_price - close_price) <= (total_range * (100 - min_body_pct) / 100)

    # Combine conditions
    is_reversal = is_bullish & has_long_lower_shadow & has_small_upper_shadow & body_in_upper_range

    # Handle division by zero (when high == low)
    is_reversal = is_reversal.fillna(False)

    return is_reversal


def calculate_price_momentum(
    data: pd.DataFrame,
    period: int = 5,
    close_col: str = "close",
) -> pd.Series:
    """
    Calculate price momentum (rate of change).

    Momentum measures the speed of price movement over N periods.
    Positive values indicate upward momentum, negative downward.

    Args:
        data: DataFrame with price data
        period: Number of periods for momentum calculation (default: 5)
        close_col: Name of the close column (default: "close")

    Returns:
        Series with momentum percentage

    Raises:
        PriceActionError: If required columns are missing
        InsufficientDataError: If less than period+1 rows

    Example:
        >>> df = pd.DataFrame({"close": [100, 105, 110, 115, 120, 125]})
        >>> momentum = calculate_price_momentum(df, period=5)
        >>> assert momentum.iloc[-1] > 20.0  # 25% gain over 5 periods
    """
    # Validate inputs
    if close_col not in data.columns:
        raise PriceActionError(f"Missing required column: {close_col}")

    if len(data) < period + 1:
        raise InsufficientDataError(
            f"Need at least {period + 1} rows for momentum, got {len(data)}"
        )

    # Calculate momentum
    prev_close = data[close_col].shift(period)
    current_close = data[close_col]

    momentum_pct = ((current_close - prev_close) / prev_close) * 100

    return momentum_pct


def detect_higher_low(
    data: pd.DataFrame,
    lookback: int = 5,
    low_col: str = "low",
) -> pd.Series:
    """
    Detect higher lows (bullish pattern).

    A higher low occurs when the current low is higher than the
    previous low over the lookback period.

    Args:
        data: DataFrame with price data
        lookback: Number of periods to look back (default: 5)
        low_col: Name of the low column (default: "low")

    Returns:
        Boolean Series indicating higher lows

    Raises:
        PriceActionError: If required columns are missing
        InsufficientDataError: If less than lookback+1 rows

    Example:
        >>> df = pd.DataFrame({"low": [95, 90, 92, 94, 96]})
        >>> higher_lows = detect_higher_low(df, lookback=2)
        >>> assert higher_lows.iloc[-1] == True  # 96 > 94
    """
    # Validate inputs
    if low_col not in data.columns:
        raise PriceActionError(f"Missing required column: {low_col}")

    if len(data) < lookback + 1:
        raise InsufficientDataError(
            f"Need at least {lookback + 1} rows for higher low detection, got {len(data)}"
        )

    # Get current and previous lows
    current_low = data[low_col]
    prev_low = data[low_col].shift(lookback)

    # Detect higher lows
    higher_lows = current_low > prev_low

    return higher_lows


def calculate_true_range(
    data: pd.DataFrame,
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
) -> pd.Series:
    """
    Calculate True Range for each period.

    True Range is the greatest of:
    - Current High - Current Low
    - abs(Current High - Previous Close)
    - abs(Current Low - Previous Close)

    Args:
        data: DataFrame with OHLC data
        high_col: Name of the high column (default: "high")
        low_col: Name of the low column (default: "low")
        close_col: Name of the close column (default: "close")

    Returns:
        Series with True Range values

    Raises:
        PriceActionError: If required columns are missing

    Example:
        >>> df = pd.DataFrame({
        ...     "high": [105, 110],
        ...     "low": [100, 105],
        ...     "close": [102, 108]
        ... })
        >>> tr = calculate_true_range(df)
        >>> assert tr.iloc[-1] == 5  # max(110-105, 110-102, 105-102)
    """
    # Validate inputs
    required_cols = {high_col, low_col, close_col}
    missing_cols = required_cols - set(data.columns)
    if missing_cols:
        raise PriceActionError(f"Missing required columns: {missing_cols}")

    # Get price data
    high = data[high_col]
    low = data[low_col]
    close = data[close_col]
    prev_close = close.shift(1)

    # Calculate three ranges
    range_hl = high - low
    range_hc = abs(high - prev_close)
    range_lc = abs(low - prev_close)

    # True Range is the maximum of the three
    true_range = pd.DataFrame({"hl": range_hl, "hc": range_hc, "lc": range_lc}).max(axis=1)

    # First row has no previous close, so use H-L
    true_range.iloc[0] = range_hl.iloc[0]

    return true_range


def calculate_avg_directional_change(
    data: pd.DataFrame,
    period: int = 5,
    close_col: str = "close",
) -> tuple[float, str]:
    """
    Calculate average directional change over N periods.

    Returns both the average absolute change and the predominant direction.

    Args:
        data: DataFrame with price data
        period: Number of periods to average (default: 5)
        close_col: Name of the close column (default: "close")

    Returns:
        Tuple of (avg_change_pct, direction) where direction is "up", "down", or "sideways"

    Raises:
        PriceActionError: If required columns are missing
        InsufficientDataError: If less than period+1 rows

    Example:
        >>> df = pd.DataFrame({"close": [100, 102, 104, 106, 108, 110]})
        >>> avg_change, direction = calculate_avg_directional_change(df, period=5)
        >>> assert direction == "up"
        >>> assert avg_change > 0
    """
    # Validate inputs
    if close_col not in data.columns:
        raise PriceActionError(f"Missing required column: {close_col}")

    if len(data) < period + 1:
        raise InsufficientDataError(
            f"Need at least {period + 1} rows for directional change, got {len(data)}"
        )

    # Calculate daily changes
    close_prices = data[close_col]
    daily_changes = close_prices.pct_change() * 100

    # Get last N periods (excluding NaN)
    recent_changes = daily_changes.iloc[-period:]

    # Calculate average change
    avg_change = recent_changes.mean()

    # Determine direction
    if abs(avg_change) < 0.5:
        direction = "sideways"
    elif avg_change > 0:
        direction = "up"
    else:
        direction = "down"

    return avg_change, direction
