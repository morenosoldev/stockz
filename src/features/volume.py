"""
Volume analysis functions for feature engineering.

This module provides volume-based indicators and patterns:
- RVOL (Relative Volume): Volume compared to average
- Volume spikes: Unusual volume activity detection
- Volume confirmation: Volume-price relationship validation

All functions accept pandas DataFrames with OHLCV data.
"""

import numpy as np
import pandas as pd


class VolumeAnalysisError(Exception):
    """Base exception for volume analysis errors."""

    pass


class InsufficientDataError(VolumeAnalysisError):
    """Raised when there is not enough data for volume analysis."""

    pass


def calculate_rvol(
    data: pd.DataFrame,
    period: int = 20,
    volume_col: str = "volume",
) -> pd.Series:
    """
    Calculate Relative Volume (RVOL).

    RVOL compares current volume to the average volume over a period.
    Values > 1.0 indicate above-average volume, < 1.0 below-average.

    Formula:
        RVOL = Current Volume / Average Volume (period)

    Args:
        data: DataFrame with volume data
        period: Number of periods for average calculation (default: 20)
        volume_col: Name of the volume column (default: "volume")

    Returns:
        Series with RVOL values

    Raises:
        InsufficientDataError: If data has fewer rows than period
        VolumeAnalysisError: If required columns are missing

    Example:
        >>> df = pd.DataFrame({"volume": [1000, 1500, 2000, 1200, 5000]})
        >>> rvol = calculate_rvol(df, period=3)
        >>> assert rvol.iloc[-1] > 2.0  # 5000 vs avg(1500,2000,1200)
    """
    # Validate inputs
    if volume_col not in data.columns:
        raise VolumeAnalysisError(f"Missing required column: {volume_col}")

    if len(data) < period:
        raise InsufficientDataError(f"Need at least {period} rows for RVOL, got {len(data)}")

    # Calculate average volume
    avg_volume = data[volume_col].rolling(window=period).mean()

    # Calculate RVOL
    rvol = data[volume_col] / avg_volume

    # Handle division by zero (set to 1.0 when avg is zero)
    rvol = rvol.replace([np.inf, -np.inf], 1.0).fillna(1.0)

    return rvol


def detect_volume_spike(
    data: pd.DataFrame,
    threshold: float = 2.0,
    period: int = 20,
    volume_col: str = "volume",
) -> pd.Series:
    """
    Detect volume spikes (unusually high volume).

    A volume spike occurs when RVOL exceeds the threshold.

    Args:
        data: DataFrame with volume data
        threshold: RVOL threshold for spike detection (default: 2.0)
        period: Number of periods for average calculation (default: 20)
        volume_col: Name of the volume column (default: "volume")

    Returns:
        Boolean Series indicating volume spikes

    Raises:
        InsufficientDataError: If data has fewer rows than period
        VolumeAnalysisError: If required columns are missing

    Example:
        >>> df = pd.DataFrame({"volume": [1000, 1000, 1000, 5000]})
        >>> spikes = detect_volume_spike(df, threshold=3.0, period=3)
        >>> assert spikes.iloc[-1] is True
    """
    # Calculate RVOL
    rvol = calculate_rvol(data, period=period, volume_col=volume_col)

    # Detect spikes
    spikes = rvol > threshold

    return spikes


def calculate_volume_trend(
    data: pd.DataFrame,
    short_period: int = 10,
    long_period: int = 30,
    volume_col: str = "volume",
) -> pd.Series:
    """
    Calculate volume trend using short vs long moving averages.

    Positive values indicate increasing volume trend (short MA > long MA).
    Negative values indicate decreasing volume trend.

    Formula:
        Volume Trend = (Short MA - Long MA) / Long MA

    Args:
        data: DataFrame with volume data
        short_period: Short moving average period (default: 10)
        long_period: Long moving average period (default: 30)
        volume_col: Name of the volume column (default: "volume")

    Returns:
        Series with volume trend values (ratio)

    Raises:
        InsufficientDataError: If data has fewer rows than long_period
        VolumeAnalysisError: If required columns are missing

    Example:
        >>> df = pd.DataFrame({"volume": list(range(1000, 1100))})
        >>> trend = calculate_volume_trend(df, short_period=5, long_period=10)
        >>> assert trend.iloc[-1] > 0  # Increasing volume
    """
    # Validate inputs
    if volume_col not in data.columns:
        raise VolumeAnalysisError(f"Missing required column: {volume_col}")

    if len(data) < long_period:
        raise InsufficientDataError(
            f"Need at least {long_period} rows for volume trend, got {len(data)}"
        )

    # Calculate moving averages
    short_ma = data[volume_col].rolling(window=short_period).mean()
    long_ma = data[volume_col].rolling(window=long_period).mean()

    # Calculate trend ratio
    trend = (short_ma - long_ma) / long_ma

    # Handle division by zero
    trend = trend.replace([np.inf, -np.inf], 0.0).fillna(0.0)

    return trend


def confirm_price_move_with_volume(
    price_change: float | pd.Series,
    rvol: float | pd.Series,
    min_rvol: float = 1.5,
) -> bool | pd.Series:
    """
    Check if a price move is confirmed by volume.

    A price move is considered confirmed if it's accompanied by
    above-average volume (RVOL > min_rvol).

    Args:
        price_change: Price change (positive or negative)
        rvol: Relative volume value(s)
        min_rvol: Minimum RVOL for confirmation (default: 1.5)

    Returns:
        Boolean or Series indicating volume confirmation

    Example:
        >>> assert confirm_price_move_with_volume(5.0, 2.0, min_rvol=1.5) is True
        >>> assert confirm_price_move_with_volume(-3.0, 1.2, min_rvol=1.5) is False
    """
    if isinstance(rvol, pd.Series):
        return rvol >= min_rvol
    else:
        return rvol >= min_rvol


def detect_accumulation_distribution(
    data: pd.DataFrame,
    period: int = 14,
    close_col: str = "close",
    high_col: str = "high",
    low_col: str = "low",
    volume_col: str = "volume",
) -> pd.Series:
    """
    Calculate Accumulation/Distribution Line (A/D Line).

    The A/D Line is a volume-based indicator that measures cumulative
    buying and selling pressure.

    Formula:
        Money Flow Multiplier = ((Close - Low) - (High - Close)) / (High - Low)
        Money Flow Volume = Money Flow Multiplier × Volume
        A/D Line = Cumulative Sum of Money Flow Volume

    Args:
        data: DataFrame with OHLCV data
        period: Not used, kept for API consistency
        close_col: Name of close column (default: "close")
        high_col: Name of high column (default: "high")
        low_col: Name of low column (default: "low")
        volume_col: Name of volume column (default: "volume")

    Returns:
        Series with A/D Line values

    Raises:
        VolumeAnalysisError: If required columns are missing

    Example:
        >>> df = pd.DataFrame({
        ...     "close": [100, 102, 101, 103],
        ...     "high": [101, 103, 102, 104],
        ...     "low": [99, 101, 100, 102],
        ...     "volume": [1000, 1200, 1100, 1300]
        ... })
        >>> ad = detect_accumulation_distribution(df)
        >>> assert len(ad) == len(df)
    """
    # Validate inputs
    required_cols = {close_col, high_col, low_col, volume_col}
    missing_cols = required_cols - set(data.columns)
    if missing_cols:
        raise VolumeAnalysisError(f"Missing required columns: {missing_cols}")

    # Get price data
    close = data[close_col]
    high = data[high_col]
    low = data[low_col]
    volume = data[volume_col]

    # Calculate Money Flow Multiplier
    # Handle division by zero (when high == low)
    range_hl = high - low
    range_hl = range_hl.replace(0, np.nan)  # Avoid division by zero

    mf_multiplier = ((close - low) - (high - close)) / range_hl
    mf_multiplier = mf_multiplier.fillna(0)  # Fill NaN with 0

    # Calculate Money Flow Volume
    mf_volume = mf_multiplier * volume

    # Calculate cumulative A/D Line
    ad_line = mf_volume.cumsum()

    return ad_line


def detect_on_balance_volume(
    data: pd.DataFrame,
    close_col: str = "close",
    volume_col: str = "volume",
) -> pd.Series:
    """
    Calculate On-Balance Volume (OBV).

    OBV measures buying and selling pressure as a cumulative indicator.
    It adds volume on up days and subtracts volume on down days.

    Formula:
        If Close > Previous Close: OBV = Previous OBV + Volume
        If Close < Previous Close: OBV = Previous OBV - Volume
        If Close = Previous Close: OBV = Previous OBV

    Args:
        data: DataFrame with price and volume data
        close_col: Name of close column (default: "close")
        volume_col: Name of volume column (default: "volume")

    Returns:
        Series with OBV values

    Raises:
        VolumeAnalysisError: If required columns are missing

    Example:
        >>> df = pd.DataFrame({
        ...     "close": [100, 102, 101, 103],
        ...     "volume": [1000, 1200, 1100, 1300]
        ... })
        >>> obv = detect_on_balance_volume(df)
        >>> assert len(obv) == len(df)
    """
    # Validate inputs
    required_cols = {close_col, volume_col}
    missing_cols = required_cols - set(data.columns)
    if missing_cols:
        raise VolumeAnalysisError(f"Missing required columns: {missing_cols}")

    # Calculate price change direction
    close = data[close_col]
    volume = data[volume_col]

    # Create signed volume (positive on up days, negative on down days)
    price_direction = np.sign(close.diff())
    signed_volume = price_direction * volume

    # First row has no previous close, so set to 0
    signed_volume.iloc[0] = 0

    # Calculate cumulative OBV
    obv = signed_volume.cumsum()

    return obv


def is_volume_confirmed_drop(
    data: pd.DataFrame,
    drop_pct: float,
    min_rvol: float = 1.5,
    close_col: str = "close",
    volume_col: str = "volume",
) -> bool:
    """
    Check if a price drop is confirmed by volume.

    A drop is volume-confirmed if the day(s) of the drop had above-average volume.

    Args:
        data: DataFrame with price and volume data (last row is current)
        drop_pct: Negative percentage drop (e.g., -5.0)
        min_rvol: Minimum RVOL for confirmation (default: 1.5)
        close_col: Name of close column (default: "close")
        volume_col: Name of volume column (default: "volume")

    Returns:
        True if drop is volume-confirmed, False otherwise

    Example:
        >>> df = pd.DataFrame({
        ...     "close": [100, 100, 100, 95],
        ...     "volume": [1000, 1000, 1000, 3000]
        ... })
        >>> confirmed = is_volume_confirmed_drop(df, -5.0, min_rvol=2.0)
        >>> assert confirmed is True
    """
    if len(data) < 2:
        return False

    # Calculate RVOL for the last row
    rvol = calculate_rvol(data, period=min(20, len(data) - 1), volume_col=volume_col)

    # Check if volume is high on the drop day
    result: bool = bool(rvol.iloc[-1] >= min_rvol)
    return result


def calculate_volume_profile(
    data: pd.DataFrame,
    num_bins: int = 20,
    price_col: str = "close",
    volume_col: str = "volume",
) -> pd.DataFrame:
    """
    Calculate Volume Profile (Volume by Price).

    Volume profile shows how much volume traded at each price level.

    Args:
        data: DataFrame with price and volume data
        num_bins: Number of price bins (default: 20)
        price_col: Name of price column (default: "close")
        volume_col: Name of volume column (default: "volume")

    Returns:
        DataFrame with columns: price_level, volume, pct_volume

    Raises:
        VolumeAnalysisError: If required columns are missing

    Example:
        >>> df = pd.DataFrame({
        ...     "close": [100, 102, 101, 103, 100],
        ...     "volume": [1000, 1200, 1100, 1300, 900]
        ... })
        >>> profile = calculate_volume_profile(df, num_bins=5)
        >>> assert "price_level" in profile.columns
    """
    # Validate inputs
    required_cols = {price_col, volume_col}
    missing_cols = required_cols - set(data.columns)
    if missing_cols:
        raise VolumeAnalysisError(f"Missing required columns: {missing_cols}")

    # Create price bins
    price_min = data[price_col].min()
    price_max = data[price_col].max()

    # Handle case where all prices are the same
    if price_min == price_max:
        return pd.DataFrame(
            {
                "price_level": [price_min],
                "volume": [data[volume_col].sum()],
                "pct_volume": [100.0],
            }
        )

    bins = np.linspace(price_min, price_max, num_bins + 1)
    labels = (bins[:-1] + bins[1:]) / 2  # Midpoint of each bin

    # Assign prices to bins
    price_bins = pd.cut(data[price_col], bins=bins, labels=labels, include_lowest=True)

    # Sum volume by price bin
    volume_by_price = data.groupby(price_bins, observed=False)[volume_col].sum()

    # Calculate percentage
    total_volume = volume_by_price.sum()
    pct_volume = (volume_by_price / total_volume * 100) if total_volume > 0 else volume_by_price

    # Create result DataFrame
    result = pd.DataFrame(
        {
            "price_level": volume_by_price.index.astype(float),
            "volume": volume_by_price.values,
            "pct_volume": pct_volume.values,
        }
    )

    # Sort by price level
    result = result.sort_values("price_level").reset_index(drop=True)

    return result
