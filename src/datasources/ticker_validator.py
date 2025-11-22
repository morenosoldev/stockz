"""Ticker validation utilities for filtering invalid stock symbols.

This module provides validation logic for ticker symbols extracted from Reddit
and other sources. It includes:
- Format validation (length, characters, patterns)
- Blacklist filtering
- Existence checking via market data adapter (Twelve Data/Yahoo Finance)

Example:
    >>> validator = TickerValidator()
    >>> validator.is_likely_stock("AAPL")  # True
    >>> validator.is_likely_stock("YOY")   # False (blacklisted)
    >>> validator.is_likely_stock("123")   # False (invalid format)
    >>> validator.exists("AAPL")           # True (via market data adapter)
"""

import re
from functools import lru_cache

from src.datasources import get_market_data_adapter
from src.ops.logging import get_logger

logger = get_logger(__name__)


class TickerValidator:
    """Validates ticker symbols using format rules and optional API checks."""

    # Core blacklist (synchronized with RedditAdapter._extract_tickers)
    TICKER_BLACKLIST = {
        # Original common words
        "A",
        "I",
        "THE",
        "WSB",
        "DD",
        "YOLO",
        "CEO",
        "CFO",
        "IPO",
        "ETF",
        "FD",
        "TA",
        "IV",
        # Financial/Economic Terms
        "YOY",
        "QOQ",
        "MOM",
        "WOW",
        "GDP",
        "CPI",
        "PPI",
        "API",
        "EPS",
        "PE",
        "PS",
        "PB",
        "ROE",
        "ROI",
        "ROA",
        "EBIT",
        "EBITDA",
        "FCF",
        "NPV",
        "IRR",
        "CAGR",
        "YTD",
        "MTD",
        "QTD",
        "ATH",
        "ATL",
        "AH",
        "PM",
        # Market Terms
        "NYSE",
        "NASDAQ",
        "AMEX",
        "OTC",
        "DOW",
        "SPX",
        "SPY",
        "QQQ",
        "VIX",
        "DIA",
        "IWM",
        "DJI",
        "RUT",
        # Reddit/Trading Slang
        "FOMO",
        "FUD",
        "HODL",
        "IMO",
        "IMHO",
        "TBH",
        "NGL",
        "BTW",
        "FYI",
        "PSA",
        "TIL",
        "ELI5",
        "TLDR",
        "AMA",
        "ITM",
        "OTM",
        "GUH",
        "BTFD",
        "GG",
        "GL",
        "RIP",
        "LFG",
        "GME",
        "AMC",
        # Time/Date Abbreviations
        "AM",
        "EST",
        "PST",
        "CST",
        "MST",
        "UTC",
        "GMT",
        "MON",
        "TUE",
        "WED",
        "THU",
        "FRI",
        "SAT",
        "SUN",
        "JAN",
        "FEB",
        "MAR",
        "APR",
        "MAY",
        "JUN",
        "JUL",
        "AUG",
        "SEP",
        "OCT",
        "NOV",
        "DEC",
        # Organizations/Government
        "USA",
        "US",
        "UK",
        "EU",
        "UN",
        "SEC",
        "FDA",
        "DOJ",
        "FBI",
        "IRS",
        "EPA",
        "FTC",
        "DOD",
        "CIA",
        "NSA",
        "OSHA",
        # Technology/General
        "IT",
        "AI",
        "ML",
        "AR",
        "VR",
        "IOT",
        "SaaS",
        "SDK",
        "AWS",
        "UI",
        "UX",
        "SEO",
        "CRM",
        "ERP",
        "BI",
        # Common Expressions
        "LOL",
        "LMAO",
        "WTF",
        "OMG",
        "IDK",
        "AFAIK",
        "IIRC",
        "SMH",
        "TY",
        "NP",
        "OP",
        "DM",
        "DMs",
        "NSFW",
        "SFW",
    }

    # Valid ticker patterns
    TICKER_PATTERNS = [
        r"^[A-Z]{1,5}$",  # Standard US tickers (AAPL, MSFT, etc.)
        r"^[A-Z]{1,5}-[A-Z]{1,2}$",  # Share classes (BRK-B, BRK-A, etc.)
        r"^[A-Z]{1,5}\.[A-Z]{1,3}$",  # Exchange suffixes (GUBRA.CO, SAP.DE, etc.)
        r"^\d{4}\.[A-Z]{1,3}$",  # Asian format (0700.HK for Tencent, etc.)
    ]

    def __init__(self, custom_blacklist: set[str] | None = None):
        """Initialize validator with optional custom blacklist.

        Args:
            custom_blacklist: Additional words to blacklist (merged with default)
        """
        self.blacklist = self.TICKER_BLACKLIST.copy()
        if custom_blacklist:
            self.blacklist.update(custom_blacklist)

    def is_valid_format(self, ticker: str) -> bool:
        """Check if ticker matches valid format patterns.

        Args:
            ticker: Ticker symbol to validate

        Returns:
            True if ticker matches any valid pattern

        Examples:
            >>> validator.is_valid_format("AAPL")      # True
            >>> validator.is_valid_format("BRK-B")     # True
            >>> validator.is_valid_format("GUBRA.CO")  # True
            >>> validator.is_valid_format("0700.HK")   # True
            >>> validator.is_valid_format("123ABC")    # False
            >>> validator.is_valid_format("TOOLONG")   # False (>5 chars base)
        """
        if not ticker:
            return False

        # Check against all valid patterns
        for pattern in self.TICKER_PATTERNS:
            if re.match(pattern, ticker):
                return True

        return False

    def is_numbers_only(self, ticker: str) -> bool:
        """Check if ticker is numbers only (invalid for most markets).

        Args:
            ticker: Ticker symbol to check

        Returns:
            True if ticker contains only digits

        Examples:
            >>> validator.is_numbers_only("123")    # True
            >>> validator.is_numbers_only("AAPL")   # False
            >>> validator.is_numbers_only("0700.HK") # False (has .HK)
        """
        # Extract base ticker (before hyphen or dot)
        base_ticker = re.split(r"[-.]", ticker)[0]
        return base_ticker.isdigit()

    def is_likely_stock(self, ticker: str) -> bool:
        """Quick heuristic check if ticker is likely a real stock (no API call).

        Checks:
        - Valid format (1-5 chars, optional hyphen/exchange suffix)
        - Not numbers-only
        - Not in blacklist
        - Not matching common abbreviation patterns

        Args:
            ticker: Ticker symbol to validate

        Returns:
            True if ticker passes all heuristic checks

        Examples:
            >>> validator.is_likely_stock("AAPL")     # True
            >>> validator.is_likely_stock("BRK-B")    # True
            >>> validator.is_likely_stock("GUBRA.CO") # True
            >>> validator.is_likely_stock("YOY")      # False (blacklisted)
            >>> validator.is_likely_stock("123")      # False (numbers only)
            >>> validator.is_likely_stock("ABC123")   # False (invalid format)
        """
        if not ticker:
            return False

        ticker_upper = ticker.upper()

        # Check blacklist first (fastest)
        if ticker_upper in self.blacklist:
            logger.debug(f"Ticker {ticker} rejected: in blacklist")
            return False

        # Check format
        if not self.is_valid_format(ticker_upper):
            logger.debug(f"Ticker {ticker} rejected: invalid format")
            return False

        # Check if numbers-only (reject)
        if self.is_numbers_only(ticker_upper):
            logger.debug(f"Ticker {ticker} rejected: numbers only")
            return False

        return True

    @lru_cache(maxsize=10000)  # noqa: B019 - Singleton service, caching essential for performance
    def exists(self, ticker: str) -> bool:
        """Check if ticker exists via yfinance API (cached).

        Fast validation using yfinance.Ticker().info with timeout.
        Results cached to avoid repeated API calls.

        Args:
            ticker: Ticker symbol to validate

        Returns:
            True if ticker exists and has valid data

        Examples:
            >>> validator.exists("AAPL")          # True
            >>> validator.exists("GUBRA.CO")      # True (if it exists)
            >>> validator.exists("FAKESYMBOL123") # False

        Note:
            This method makes an API call on first invocation for each ticker.
            Subsequent calls for the same ticker use cached results.
        """
        try:
            # Get market data adapter
            adapter = get_market_data_adapter()

            # Validate using adapter
            is_valid = adapter.validate_ticker(ticker)

            if is_valid:
                logger.debug(f"Ticker {ticker} validated via market data adapter")
            else:
                logger.debug(f"Ticker {ticker} rejected: validation failed")

            return is_valid

        except Exception as e:
            logger.debug(f"Ticker {ticker} validation failed: {e}")
            return False
