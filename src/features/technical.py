"""
Technical indicator calculations for feature engineering.

This module provides common technical indicators used in trading strategies:
- ATR (Average True Range): Measures volatility
- RSI (Relative Strength Index): Measures momentum/overbought/oversold
- SMA/EMA (Moving Averages): Trend following indicators
- Bollinger Bands: Volatility bands around price

All functions accept pandas DataFrames with OHLCV (Open, High, Low, Close, Volume) data.
"""

import pandas as pd


class TechnicalIndicatorError(Exception):
    """Base exception for technical indicator calculation errors."""

    pass


class InsufficientDataError(TechnicalIndicatorError):
    """Raised when there is not enough data to calculate an indicator."""

    pass


def calculate_atr(
    data: pd.DataFrame,
    period: int = 14,
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
) -> pd.Series:
    """
    Calculate Average True Range (ATR).

    ATR measures volatility by decomposing the entire range of an asset price
    for that period. It's the moving average of the True Range.

    Formula:
        True Range = max[(high - low), abs(high - prev_close), abs(low - prev_close)]
        ATR = Moving Average of True Range over 'period' periods

    Args:
        data: DataFrame with OHLC data
        period: Number of periods for ATR calculation (default: 14)
        high_col: Name of the high price column (default: "high")
        low_col: Name of the low price column (default: "low")
        close_col: Name of the close price column (default: "close")

    Returns:
        Series with ATR values

    Raises:
        InsufficientDataError: If data has fewer rows than period + 1
        TechnicalIndicatorError: If required columns are missing

    Example:
        >>> df = pd.DataFrame({
        ...     "high": [100, 102, 101, 103],
        ...     "low": [98, 99, 98, 100],
        ...     "close": [99, 101, 99, 102]
        ... })
        >>> atr = calculate_atr(df, period=3)
        >>> assert atr.iloc[-1] > 0
    """
    # Validate inputs
    required_cols = {high_col, low_col, close_col}
    missing_cols = required_cols - set(data.columns)
    if missing_cols:
        raise TechnicalIndicatorError(f"Missing required columns for ATR: {missing_cols}")

    if len(data) < period + 1:
        raise InsufficientDataError(
            f"Need at least {period + 1} rows for ATR calculation, got {len(data)}"
        )

    # Calculate True Range
    high = data[high_col]
    low = data[low_col]
    close = data[close_col]

    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Calculate ATR as exponential moving average of True Range
    # Using Wilder's smoothing (similar to EMA)
    atr = true_range.ewm(span=period, adjust=False).mean()

    return atr


def calculate_rsi(
    data: pd.DataFrame,
    period: int = 14,
    close_col: str = "close",
) -> pd.Series:
    """
    Calculate Relative Strength Index (RSI).

    RSI measures momentum by comparing the magnitude of recent gains to recent losses.
    Values range from 0 to 100, with readings above 70 considered overbought
    and readings below 30 considered oversold.

    Formula:
        RS = Average Gain / Average Loss
        RSI = 100 - (100 / (1 + RS))

    Args:
        data: DataFrame with price data
        period: Number of periods for RSI calculation (default: 14)
        close_col: Name of the close price column (default: "close")

    Returns:
        Series with RSI values (0-100)

    Raises:
        InsufficientDataError: If data has fewer rows than period + 1
        TechnicalIndicatorError: If required columns are missing

    Example:
        >>> df = pd.DataFrame({"close": [100, 102, 101, 103, 105, 104, 106]})
        >>> rsi = calculate_rsi(df, period=5)
        >>> assert 0 <= rsi.iloc[-1] <= 100
    """
    # Validate inputs
    if close_col not in data.columns:
        raise TechnicalIndicatorError(f"Missing required column for RSI: {close_col}")

    if len(data) < period + 1:
        raise InsufficientDataError(
            f"Need at least {period + 1} rows for RSI calculation, got {len(data)}"
        )

    # Calculate price changes
    close = data[close_col]
    delta = close.diff()

    # Separate gains and losses
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    # Calculate average gain and loss using Wilder's smoothing
    avg_gain = gain.ewm(span=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, adjust=False).mean()

    # Calculate RS and RSI
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    # Handle division by zero (when avg_loss is 0, RSI = 100)
    rsi = rsi.fillna(100)

    return rsi


def calculate_sma(
    data: pd.DataFrame,
    period: int,
    price_col: str = "close",
) -> pd.Series:
    """
    Calculate Simple Moving Average (SMA).

    SMA is the arithmetic mean of prices over a specified period.

    Formula:
        SMA = (P1 + P2 + ... + Pn) / n

    Args:
        data: DataFrame with price data
        period: Number of periods for SMA calculation
        price_col: Name of the price column (default: "close")

    Returns:
        Series with SMA values

    Raises:
        InsufficientDataError: If data has fewer rows than period
        TechnicalIndicatorError: If required columns are missing

    Example:
        >>> df = pd.DataFrame({"close": [100, 102, 104, 106, 108]})
        >>> sma = calculate_sma(df, period=3)
        >>> assert sma.iloc[-1] == (104 + 106 + 108) / 3
    """
    # Validate inputs
    if price_col not in data.columns:
        raise TechnicalIndicatorError(f"Missing required column for SMA: {price_col}")

    if len(data) < period:
        raise InsufficientDataError(
            f"Need at least {period} rows for SMA calculation, got {len(data)}"
        )

    # Calculate simple moving average
    sma = data[price_col].rolling(window=period).mean()

    return sma


def calculate_ema(
    data: pd.DataFrame,
    period: int,
    price_col: str = "close",
) -> pd.Series:
    """
    Calculate Exponential Moving Average (EMA).

    EMA gives more weight to recent prices, making it more responsive to new information.

    Formula:
        Multiplier = 2 / (period + 1)
        EMA = (Close - Previous EMA) × Multiplier + Previous EMA

    Args:
        data: DataFrame with price data
        period: Number of periods for EMA calculation
        price_col: Name of the price column (default: "close")

    Returns:
        Series with EMA values

    Raises:
        InsufficientDataError: If data has fewer rows than period
        TechnicalIndicatorError: If required columns are missing

    Example:
        >>> df = pd.DataFrame({"close": [100, 102, 104, 106, 108]})
        >>> ema = calculate_ema(df, period=3)
        >>> assert ema.iloc[-1] > 0
    """
    # Validate inputs
    if price_col not in data.columns:
        raise TechnicalIndicatorError(f"Missing required column for EMA: {price_col}")

    if len(data) < period:
        raise InsufficientDataError(
            f"Need at least {period} rows for EMA calculation, got {len(data)}"
        )

    # Calculate exponential moving average
    ema = data[price_col].ewm(span=period, adjust=False).mean()

    return ema


def calculate_bollinger_bands(
    data: pd.DataFrame,
    period: int = 20,
    num_std: float = 2.0,
    price_col: str = "close",
) -> pd.DataFrame:
    """
    Calculate Bollinger Bands.

    Bollinger Bands consist of a middle band (SMA) and upper/lower bands
    that are 'num_std' standard deviations away from the middle band.

    Formula:
        Middle Band = SMA(period)
        Upper Band = Middle Band + (num_std × std_dev)
        Lower Band = Middle Band - (num_std × std_dev)
        %B = (Price - Lower Band) / (Upper Band - Lower Band)
        Bandwidth = (Upper Band - Lower Band) / Middle Band

    Args:
        data: DataFrame with price data
        period: Number of periods for SMA and std dev (default: 20)
        num_std: Number of standard deviations for bands (default: 2.0)
        price_col: Name of the price column (default: "close")

    Returns:
        DataFrame with columns: middle, upper, lower, percent_b, bandwidth

    Raises:
        InsufficientDataError: If data has fewer rows than period
        TechnicalIndicatorError: If required columns are missing

    Example:
        >>> df = pd.DataFrame({"close": [100, 102, 104, 106, 108] * 5})
        >>> bb = calculate_bollinger_bands(df, period=10)
        >>> assert "upper" in bb.columns
        >>> assert (bb["upper"] > bb["middle"]).all()
    """
    # Validate inputs
    if price_col not in data.columns:
        raise TechnicalIndicatorError(f"Missing required column for Bollinger Bands: {price_col}")

    if len(data) < period:
        raise InsufficientDataError(
            f"Need at least {period} rows for Bollinger Bands, got {len(data)}"
        )

    # Calculate middle band (SMA)
    middle = calculate_sma(data, period=period, price_col=price_col)

    # Calculate standard deviation
    std_dev = data[price_col].rolling(window=period).std()

    # Calculate upper and lower bands
    upper = middle + (num_std * std_dev)
    lower = middle - (num_std * std_dev)

    # Calculate %B (position within bands)
    # %B = 1 when price is at upper band, 0 when at lower band
    band_width = upper - lower
    percent_b = (data[price_col] - lower) / band_width

    # Calculate bandwidth (measure of band width)
    bandwidth = band_width / middle

    # Return DataFrame with all bands
    result = pd.DataFrame(
        {
            "middle": middle,
            "upper": upper,
            "lower": lower,
            "percent_b": percent_b,
            "bandwidth": bandwidth,
        },
        index=data.index,
    )

    return result


def calculate_macd(
    data: pd.DataFrame,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
    price_col: str = "close",
) -> pd.DataFrame:
    """
    Calculate MACD (Moving Average Convergence Divergence).

    MACD shows the relationship between two moving averages of a price.

    Formula:
        MACD Line = EMA(fast) - EMA(slow)
        Signal Line = EMA(MACD Line, signal_period)
        Histogram = MACD Line - Signal Line

    Args:
        data: DataFrame with price data
        fast_period: Period for fast EMA (default: 12)
        slow_period: Period for slow EMA (default: 26)
        signal_period: Period for signal line EMA (default: 9)
        price_col: Name of the price column (default: "close")

    Returns:
        DataFrame with columns: macd, signal, histogram

    Raises:
        InsufficientDataError: If data has fewer rows than slow_period
        TechnicalIndicatorError: If required columns are missing

    Example:
        >>> df = pd.DataFrame({"close": list(range(100, 140))})
        >>> macd = calculate_macd(df)
        >>> assert "macd" in macd.columns
        >>> assert "signal" in macd.columns
    """
    # Validate inputs
    if price_col not in data.columns:
        raise TechnicalIndicatorError(f"Missing required column for MACD: {price_col}")

    if len(data) < slow_period + signal_period:
        raise InsufficientDataError(
            f"Need at least {slow_period + signal_period} rows for MACD, got {len(data)}"
        )

    # Calculate fast and slow EMAs
    fast_ema = calculate_ema(data, period=fast_period, price_col=price_col)
    slow_ema = calculate_ema(data, period=slow_period, price_col=price_col)

    # Calculate MACD line
    macd_line = fast_ema - slow_ema

    # Calculate signal line (EMA of MACD line)
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()

    # Calculate histogram
    histogram = macd_line - signal_line

    # Return DataFrame with all components
    result = pd.DataFrame(
        {
            "macd": macd_line,
            "signal": signal_line,
            "histogram": histogram,
        },
        index=data.index,
    )

    return result


def is_oversold(rsi: float | pd.Series, threshold: float = 30.0) -> bool | pd.Series:
    """
    Check if RSI indicates oversold condition.

    Args:
        rsi: RSI value(s)
        threshold: Threshold for oversold (default: 30)

    Returns:
        Boolean or Series indicating oversold condition

    Example:
        >>> assert is_oversold(25.0) is True
        >>> assert is_oversold(50.0) is False
    """
    return rsi < threshold


def is_overbought(rsi: float | pd.Series, threshold: float = 70.0) -> bool | pd.Series:
    """
    Check if RSI indicates overbought condition.

    Args:
        rsi: RSI value(s)
        threshold: Threshold for overbought (default: 70)

    Returns:
        Boolean or Series indicating overbought condition

    Example:
        >>> assert is_overbought(75.0) is True
        >>> assert is_overbought(50.0) is False
    """
    return rsi > threshold


def detect_bollinger_squeeze(
    bb: pd.DataFrame,
    threshold: float = 0.02,
) -> bool | pd.Series:
    """
    Detect Bollinger Band squeeze (low volatility period).

    A squeeze occurs when bandwidth is below the threshold, indicating
    low volatility that may precede a significant price move.

    Args:
        bb: DataFrame from calculate_bollinger_bands()
        threshold: Bandwidth threshold for squeeze (default: 0.02 = 2%)

    Returns:
        Boolean or Series indicating squeeze condition

    Example:
        >>> df = pd.DataFrame({"close": [100] * 25})
        >>> bb = calculate_bollinger_bands(df, period=20)
        >>> squeeze = detect_bollinger_squeeze(bb)
        >>> assert squeeze.iloc[-1] is True  # No volatility
    """
    if "bandwidth" not in bb.columns:
        raise TechnicalIndicatorError("Input must have 'bandwidth' column")

    return bb["bandwidth"] < threshold


def price_vs_bands(
    price: float | pd.Series,
    bb: pd.DataFrame,
) -> str | pd.Series:
    """
    Determine price position relative to Bollinger Bands.

    Args:
        price: Current price(s)
        bb: DataFrame from calculate_bollinger_bands()

    Returns:
        String or Series with values: "above_upper", "in_bands", "below_lower"

    Example:
        >>> df = pd.DataFrame({"close": [100, 102, 104, 106, 108] * 5})
        >>> bb = calculate_bollinger_bands(df, period=10)
        >>> position = price_vs_bands(df["close"].iloc[-1], bb.iloc[-1:])
    """
    if isinstance(price, pd.Series):
        result = pd.Series("in_bands", index=price.index)
        result[price > bb["upper"]] = "above_upper"
        result[price < bb["lower"]] = "below_lower"
        return result
    else:
        if price > bb["upper"].iloc[-1]:
            return "above_upper"
        elif price < bb["lower"].iloc[-1]:
            return "below_lower"
        else:
            return "in_bands"
