"""
Technical data adapter using Twelve Data and ta library.

Fetches historical OHLCV data and calculates technical indicators for stock analysis.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import MACD, ADXIndicator, EMAIndicator, SMAIndicator
from ta.volatility import AverageTrueRange, BollingerBands

from src.datasources import get_market_data_adapter
from src.datasources.base import Attribution, BaseDataAdapter, DataSource
from src.datasources.cache import Cache

logger = logging.getLogger(__name__)


@dataclass
class TechnicalData:
    """Technical analysis data for a stock."""

    ticker: str
    as_of_date: date
    current_price: float
    price_change_pct: float  # From lookback start to current

    # Trend Indicators
    sma_20: float | None
    sma_50: float | None
    sma_200: float | None
    ema_20: float | None
    ema_50: float | None

    # Momentum Indicators
    rsi: float | None  # 0-100
    macd: float | None
    macd_signal: float | None
    macd_histogram: float | None
    stochastic_k: float | None
    stochastic_d: float | None

    # Volatility Indicators
    bb_upper: float | None
    bb_middle: float | None
    bb_lower: float | None
    bb_width: float | None  # Squeeze indicator
    atr: float | None

    # Trend Strength
    adx: float | None  # 0-100

    # Volume Analysis
    volume: int
    avg_volume_20d: int | None
    volume_ratio: float | None  # Current vs 20d average

    # Price Levels
    support_level: float | None  # Recent low
    resistance_level: float | None  # Recent high

    # Attribution
    attribution: Attribution


class TechnicalDataAdapter(BaseDataAdapter):
    """Adapter for fetching and calculating technical analysis data."""

    def __init__(self, cache_ttl_seconds: int = 3600):
        """
        Initialize the technical data adapter.

        Args:
            cache_ttl_seconds: Cache TTL in seconds (default: 1 hour)
        """
        self.cache = Cache(ttl_seconds=cache_ttl_seconds)
        self.cache_ttl = cache_ttl_seconds
        self._attribution: Attribution | None = None

    def get_technical_data(
        self, ticker: str, lookback_days: int = 90, as_of_date: date | None = None
    ) -> TechnicalData:
        """
        Fetch OHLCV data and calculate technical indicators.

        Args:
            ticker: Stock ticker symbol (e.g., "AAPL")
            lookback_days: Number of days of historical data (default: 90)
            as_of_date: Analysis date (default: today)

        Returns:
            TechnicalData object with all indicators

        Raises:
            ValueError: If ticker is invalid or data unavailable
            RuntimeError: If technical indicators cannot be calculated
        """
        if not ticker or not isinstance(ticker, str):
            raise ValueError(f"Invalid ticker: {ticker}")

        if as_of_date is None:
            as_of_date = date.today()

        # Check cache
        cache_key = f"technical:{ticker}:{as_of_date}"
        cached_data = self.cache.get(cache_key)
        if cached_data:
            logger.debug(f"Cache hit for {cache_key}")
            return self._deserialize_technical_data(cached_data)

        logger.info(
            f"Fetching technical data for {ticker}",
            extra={"ticker": ticker, "lookback_days": lookback_days, "as_of_date": as_of_date},
        )

        # Fetch historical data from yfinance
        try:
            df = self._fetch_ohlcv_data(ticker, lookback_days, as_of_date)
        except Exception as e:
            logger.error(
                f"Failed to fetch OHLCV data for {ticker}",
                extra={"ticker": ticker, "error": str(e)},
                exc_info=True,
            )
            raise ValueError(f"Cannot fetch data for {ticker}: {e}") from e

        # Calculate technical indicators
        try:
            technical_data = self._calculate_indicators(df, ticker, as_of_date)
        except Exception as e:
            logger.error(
                f"Failed to calculate indicators for {ticker}",
                extra={"ticker": ticker, "error": str(e)},
                exc_info=True,
            )
            raise RuntimeError(f"Cannot calculate indicators for {ticker}: {e}") from e

        # Cache the result
        serialized = self._serialize_technical_data(technical_data)
        self.cache.set(cache_key, serialized)

        return technical_data

    def _fetch_ohlcv_data(self, ticker: str, lookback_days: int, as_of_date: date) -> pd.DataFrame:
        """
        Fetch OHLCV data from yfinance.

        Args:
            ticker: Stock ticker symbol
            lookback_days: Number of days to look back
            as_of_date: End date for data

        Returns:
            DataFrame with OHLCV data

        Raises:
            ValueError: If no data is available
        """
        # Calculate date range
        # Add extra days to account for weekends/holidays
        start_date = as_of_date - timedelta(days=lookback_days + 30)
        end_date = as_of_date

        # Get market data adapter
        adapter = get_market_data_adapter()

        # Fetch OHLCV data
        bars = adapter.get_ohlcv(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            interval="1d",
        )

        if not bars:
            raise ValueError(f"No data available for {ticker}")

        # Convert to DataFrame
        data = {
            "Open": [bar.open for bar in bars],
            "High": [bar.high for bar in bars],
            "Low": [bar.low for bar in bars],
            "Close": [bar.close for bar in bars],
            "Volume": [bar.volume for bar in bars],
        }
        df = pd.DataFrame(data, index=[bar.timestamp for bar in bars])

        # Ensure we have enough data points for indicators
        if len(df) < 30:
            raise ValueError(f"Insufficient data for {ticker}: only {len(df)} days available")

        # Store attribution
        self._attribution = adapter.get_attribution()

        logger.debug(f"Fetched {len(df)} days of data for {ticker}")
        return df

    def _calculate_indicators(
        self, df: pd.DataFrame, ticker: str, as_of_date: date
    ) -> TechnicalData:
        """
        Calculate all technical indicators from OHLCV data.

        Args:
            df: DataFrame with OHLCV data (columns: Open, High, Low, Close, Volume)
            ticker: Stock ticker symbol
            as_of_date: Analysis date

        Returns:
            TechnicalData object with all calculated indicators
        """
        # Get the most recent row (as_of_date or closest available)
        latest_row = df.iloc[-1]
        current_price = float(latest_row["Close"])

        # Calculate price change from start to current
        first_price = float(df.iloc[0]["Close"])
        price_change_pct = ((current_price - first_price) / first_price) * 100

        # Extract OHLCV columns
        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]

        # --- Trend Indicators ---
        sma_20_ind = SMAIndicator(close=close, window=20)
        sma_50_ind = SMAIndicator(close=close, window=50)
        sma_200_ind = SMAIndicator(close=close, window=200)
        ema_20_ind = EMAIndicator(close=close, window=20)
        ema_50_ind = EMAIndicator(close=close, window=50)

        # --- Momentum Indicators ---
        rsi_ind = RSIIndicator(close=close, window=14)
        macd_ind = MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
        stoch_ind = StochasticOscillator(
            high=high, low=low, close=close, window=14, smooth_window=3
        )

        # --- Volatility Indicators ---
        bb_ind = BollingerBands(close=close, window=20, window_dev=2)
        atr_ind = AverageTrueRange(high=high, low=low, close=close, window=14)

        # --- Trend Strength ---
        adx_ind = ADXIndicator(high=high, low=low, close=close, window=14)

        # --- Volume Analysis ---
        avg_volume_20d = int(volume.tail(20).mean()) if len(volume) >= 20 else None
        current_volume = int(latest_row["Volume"])
        volume_ratio = (
            current_volume / avg_volume_20d if avg_volume_20d and avg_volume_20d > 0 else None
        )

        # --- Support/Resistance Levels ---
        # Use recent 20-day high/low as resistance/support
        recent_20d = df.tail(20)
        support_level = float(recent_20d["Low"].min()) if len(recent_20d) >= 20 else None
        resistance_level = float(recent_20d["High"].max()) if len(recent_20d) >= 20 else None

        # Extract latest values (handle NaN gracefully)
        def safe_float(series: pd.Series) -> float | None:
            """Extract latest value from pandas Series, return None if NaN."""
            val = series.iloc[-1]
            return float(val) if pd.notna(val) else None

        # Bollinger Band Width (squeeze indicator)
        bb_upper_val = safe_float(bb_ind.bollinger_hband())
        bb_lower_val = safe_float(bb_ind.bollinger_lband())
        bb_width = None
        if bb_upper_val is not None and bb_lower_val is not None and current_price > 0:
            bb_width = (bb_upper_val - bb_lower_val) / current_price

        # Build TechnicalData object
        technical_data = TechnicalData(
            ticker=ticker,
            as_of_date=as_of_date,
            current_price=current_price,
            price_change_pct=price_change_pct,
            # Trend
            sma_20=safe_float(sma_20_ind.sma_indicator()),
            sma_50=safe_float(sma_50_ind.sma_indicator()),
            sma_200=safe_float(sma_200_ind.sma_indicator()),
            ema_20=safe_float(ema_20_ind.ema_indicator()),
            ema_50=safe_float(ema_50_ind.ema_indicator()),
            # Momentum
            rsi=safe_float(rsi_ind.rsi()),
            macd=safe_float(macd_ind.macd()),
            macd_signal=safe_float(macd_ind.macd_signal()),
            macd_histogram=safe_float(macd_ind.macd_diff()),
            stochastic_k=safe_float(stoch_ind.stoch()),
            stochastic_d=safe_float(stoch_ind.stoch_signal()),
            # Volatility
            bb_upper=bb_upper_val,
            bb_middle=safe_float(bb_ind.bollinger_mavg()),
            bb_lower=bb_lower_val,
            bb_width=bb_width,
            atr=safe_float(atr_ind.average_true_range()),
            # Trend Strength
            adx=safe_float(adx_ind.adx()),
            # Volume
            volume=current_volume,
            avg_volume_20d=avg_volume_20d,
            volume_ratio=volume_ratio,
            # Price Levels
            support_level=support_level,
            resistance_level=resistance_level,
            # Attribution
            attribution=self._attribution,  # type: ignore
        )

        logger.debug(
            f"Calculated indicators for {ticker}",
            extra={
                "ticker": ticker,
                "rsi": technical_data.rsi,
                "macd_histogram": technical_data.macd_histogram,
                "bb_width": technical_data.bb_width,
                "adx": technical_data.adx,
            },
        )

        return technical_data

    def _serialize_technical_data(self, data: TechnicalData) -> dict[str, Any]:
        """Serialize TechnicalData to dict for caching."""
        return {
            "ticker": data.ticker,
            "as_of_date": data.as_of_date.isoformat(),
            "current_price": data.current_price,
            "price_change_pct": data.price_change_pct,
            "sma_20": data.sma_20,
            "sma_50": data.sma_50,
            "sma_200": data.sma_200,
            "ema_20": data.ema_20,
            "ema_50": data.ema_50,
            "rsi": data.rsi,
            "macd": data.macd,
            "macd_signal": data.macd_signal,
            "macd_histogram": data.macd_histogram,
            "stochastic_k": data.stochastic_k,
            "stochastic_d": data.stochastic_d,
            "bb_upper": data.bb_upper,
            "bb_middle": data.bb_middle,
            "bb_lower": data.bb_lower,
            "bb_width": data.bb_width,
            "atr": data.atr,
            "adx": data.adx,
            "volume": data.volume,
            "avg_volume_20d": data.avg_volume_20d,
            "volume_ratio": data.volume_ratio,
            "support_level": data.support_level,
            "resistance_level": data.resistance_level,
            "attribution": {
                "source": data.attribution.source.value,
                "timestamp": data.attribution.timestamp.isoformat(),
                "url": data.attribution.url,
                "version": data.attribution.version,
            },
        }

    def _deserialize_technical_data(self, data: dict[str, Any]) -> TechnicalData:
        """Deserialize dict to TechnicalData."""
        attribution = Attribution(
            source=DataSource(data["attribution"]["source"]),
            timestamp=datetime.fromisoformat(data["attribution"]["timestamp"]),
            url=data["attribution"]["url"],
            version=data["attribution"]["version"],
        )

        return TechnicalData(
            ticker=data["ticker"],
            as_of_date=date.fromisoformat(data["as_of_date"]),
            current_price=data["current_price"],
            price_change_pct=data["price_change_pct"],
            sma_20=data.get("sma_20"),
            sma_50=data.get("sma_50"),
            sma_200=data.get("sma_200"),
            ema_20=data.get("ema_20"),
            ema_50=data.get("ema_50"),
            rsi=data.get("rsi"),
            macd=data.get("macd"),
            macd_signal=data.get("macd_signal"),
            macd_histogram=data.get("macd_histogram"),
            stochastic_k=data.get("stochastic_k"),
            stochastic_d=data.get("stochastic_d"),
            bb_upper=data.get("bb_upper"),
            bb_middle=data.get("bb_middle"),
            bb_lower=data.get("bb_lower"),
            bb_width=data.get("bb_width"),
            atr=data.get("atr"),
            adx=data.get("adx"),
            volume=data["volume"],
            avg_volume_20d=data.get("avg_volume_20d"),
            volume_ratio=data.get("volume_ratio"),
            support_level=data.get("support_level"),
            resistance_level=data.get("resistance_level"),
            attribution=attribution,
        )

    def get_attribution(self) -> Attribution:
        """Return attribution for last fetch operation."""
        if self._attribution is None:
            raise RuntimeError("No attribution available - call get_technical_data() first")
        return self._attribution

    def fetch(self, *args: Any, **kwargs: Any) -> Any:
        """
        Fetch data (implements BaseDataAdapter abstract method).

        This method delegates to get_technical_data() for backward compatibility.
        """
        ticker = kwargs.get("ticker") or (args[0] if args else None)
        lookback_days = kwargs.get("lookback_days", 90)
        as_of_date = kwargs.get("as_of_date")

        if not ticker:
            raise ValueError("ticker parameter is required")

        return self.get_technical_data(
            ticker=ticker, lookback_days=lookback_days, as_of_date=as_of_date
        )

    def _build_attribution(self, **kwargs: Any) -> Attribution:
        """
        Build attribution metadata (implements BaseDataAdapter abstract method).

        Returns the last attribution from get_technical_data() call.
        """
        return self.get_attribution()
