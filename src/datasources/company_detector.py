"""AI-powered company name detection and ticker resolution.

This module uses a multi-stage pipeline to detect company names in text
and resolve them to stock ticker symbols:

Stage 1: Named Entity Recognition (NER) - Detect potential company names
Stage 2: LLM Validation & Resolution - Validate and resolve to ticker + exchange
Stage 3: Market Data Validation - Confirm ticker exists

Example:
    >>> detector = CompanyDetector()
    >>> companies = detector.extract_company_names("Apple crushed earnings!")
    >>> companies
    ['Apple']

    >>> result = detector.resolve_to_ticker("Apple")
    >>> result
    {'ticker': 'AAPL', 'exchange': 'NASDAQ'}

    >>> detector.validate_ticker("AAPL")
    True
"""

import json
import logging
from functools import lru_cache
from typing import Any

from src.datasources import get_market_data_adapter
from src.ops.config import get_config
from src.ops.logging import get_logger

logger = get_logger(__name__)

# Suppress OpenAI's httpx client logs (the "HTTP Request: POST" spam)
logging.getLogger("httpx").setLevel(logging.WARNING)


class CompanyDetector:
    """AI-powered company name detection and ticker resolution."""

    def __init__(self) -> None:
        """Initialize CompanyDetector with spaCy NER model."""
        self.nlp: Any = None
        self._initialize_nlp()

    def _initialize_nlp(self) -> None:
        """Lazy-load spaCy model with NER capabilities."""
        try:
            import spacy

            self.nlp = spacy.load("en_core_web_sm")
            logger.info("spaCy NER model loaded successfully")
        except OSError:
            logger.warning(
                "spaCy model 'en_core_web_sm' not found. "
                "Run: python -m spacy download en_core_web_sm"
            )
            self.nlp = None
        except Exception as e:
            logger.error(f"Failed to load spaCy model: {e}", exc_info=True)
            self.nlp = None

    def extract_company_names(self, text: str) -> list[str]:
        """Extract potential company names using Named Entity Recognition.

        Uses spaCy's pre-trained NER model to identify entities labeled as
        organizations (ORG) or products (PRODUCT).

        Args:
            text: Reddit post or comment text

        Returns:
            List of detected company/organization names

        Examples:
            >>> detector.extract_company_names("Apple crushed earnings! Gubra promising.")
            ['Apple', 'Gubra']

            >>> detector.extract_company_names("I love my local bakery")
            ['local bakery']  # Will be filtered by LLM later
        """
        if not self.nlp:
            logger.warning("spaCy NER model not available")
            return []

        try:
            doc = self.nlp(text)

            # Extract entities labeled as ORG (organizations) or PRODUCT
            companies = []
            for ent in doc.ents:
                if ent.label_ in ["ORG", "PRODUCT"]:
                    companies.append(ent.text)

            if companies:
                logger.debug(
                    f"NER detected {len(companies)} potential companies: {companies}",
                    extra={"companies": companies, "text_length": len(text)},
                )

            return companies

        except Exception as e:
            logger.error(f"NER extraction failed: {e}", exc_info=True)
            return []

    @lru_cache(maxsize=5000)  # noqa: B019 - Singleton service, caching essential for performance
    def resolve_to_ticker(self, company_name: str) -> dict[str, str] | None:
        """Use LLM to determine if company name is publicly traded and get ticker.

        Uses GPT-4o-mini to validate whether the detected entity is a publicly
        traded company and resolve it to the correct ticker symbol + exchange.

        Args:
            company_name: Potential company name from NER

        Returns:
            {"ticker": "AAPL", "exchange": "NASDAQ"} or None if not public

        Examples:
            >>> detector.resolve_to_ticker("Apple")
            {'ticker': 'AAPL', 'exchange': 'NASDAQ'}

            >>> detector.resolve_to_ticker("Gubra")
            {'ticker': 'GUBRA.CO', 'exchange': 'Copenhagen'}

            >>> detector.resolve_to_ticker("Nintendo")
            {'ticker': 'NTDOY', 'exchange': 'OTC'}

            >>> detector.resolve_to_ticker("My Local Bakery")
            None

        Note:
            Results are cached (LRU cache, 5000 entries) to avoid repeated
            LLM calls for the same company names.
        """
        try:
            import openai

            config = get_config()
            client = openai.OpenAI(api_key=config.llm.openai_api_key)

            prompt = f"""You are a stock market expert. Analyze if the following name is a publicly traded company.

Company name: "{company_name}"

If it IS a publicly traded company:
- Return ONLY a JSON object: {{"ticker": "SYMBOL", "exchange": "EXCHANGE_NAME"}}
- Use the primary ticker (e.g., AAPL for Apple, GUBRA.CO for Gubra, NTDOY for Nintendo ADR)
- Include exchange suffix if not US (e.g., ".CO" for Copenhagen, ".TO" for Toronto, ".HK" for Hong Kong)

If it is NOT a publicly traded company or you're uncertain:
- Return ONLY: {{"ticker": null}}

Examples:
- "Apple" → {{"ticker": "AAPL", "exchange": "NASDAQ"}}
- "Gubra" → {{"ticker": "GUBRA.CO", "exchange": "Copenhagen"}}
- "Nintendo" → {{"ticker": "NTDOY", "exchange": "OTC"}}
- "My Local Bakery" → {{"ticker": null}}
- "Goldman Sachs" → {{"ticker": "GS", "exchange": "NYSE"}}
- "SAP" → {{"ticker": "SAP.DE", "exchange": "Frankfurt"}}

Respond with ONLY the JSON, no explanation."""

            logger.info(
                f"🤖 Asking LLM: Is '{company_name}' a publicly traded company?",
                extra={
                    "company_name": company_name,
                    "model": "gpt-4o-mini",
                    "purpose": "ticker_resolution",
                },
            )

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50,
                temperature=0,
            )

            result_text = (
                response.choices[0].message.content.strip()
                if response.choices[0].message.content
                else ""
            )
            result = json.loads(result_text)

            if result.get("ticker"):
                logger.info(
                    f"✅ LLM says YES: '{company_name}' → {result['ticker']}",
                    extra={
                        "company_name": company_name,
                        "ticker": result["ticker"],
                        "exchange": result.get("exchange"),
                        "model": "gpt-4o-mini",
                    },
                )
                return result  # type: ignore[no-any-return]

            logger.debug(
                f"❌ LLM says NO: '{company_name}' is not a public company",
                extra={"company_name": company_name},
            )
            return None

        except json.JSONDecodeError as e:
            logger.warning(
                f"Failed to parse LLM response for '{company_name}': {e}",
                extra={"company_name": company_name, "error": str(e)},
            )
            return None
        except Exception as e:
            logger.error(
                f"LLM resolution failed for '{company_name}': {e}",
                extra={"company_name": company_name, "error": str(e)},
                exc_info=True,
            )
            return None

    def resolve_to_tickers_batch(
        self, company_names: list[str], batch_size: int = 10
    ) -> dict[str, dict[str, Any] | None]:
        """Resolve multiple company names to tickers using batched LLM calls (P5 optimization).

        This is ~10x more efficient than calling resolve_to_ticker() in a loop,
        as it batches multiple companies into a single LLM API call.

        Args:
            company_names: List of company names to resolve
            batch_size: Number of companies per LLM call (default: 10)

        Returns:
            Dictionary mapping company_name → {"ticker": "...", "exchange": "..."}
            or None if not a public company

        Examples:
            >>> detector.resolve_to_tickers_batch(["Apple", "Microsoft", "Fake Corp"])
            {
                "Apple": {"ticker": "AAPL", "exchange": "NASDAQ"},
                "Microsoft": {"ticker": "MSFT", "exchange": "NASDAQ"},
                "Fake Corp": None
            }
        """
        results: dict[str, dict[str, Any] | None] = {}

        try:
            import openai

            config = get_config()
            client = openai.OpenAI(api_key=config.llm.openai_api_key)

            # Process in batches to avoid token limits
            for i in range(0, len(company_names), batch_size):
                batch = company_names[i : i + batch_size]

                # Build JSON array of company names
                companies_json = json.dumps(batch)

                prompt = f"""You are a stock market expert. Analyze if each company name is a publicly traded company.

Company names: {companies_json}

For each company, return a JSON object in this format:
{{
  "CompanyName": {{"ticker": "SYMBOL", "exchange": "EXCHANGE"}} OR null
}}

Rules:
- If the company IS publicly traded: return {{"ticker": "SYMBOL", "exchange": "EXCHANGE_NAME"}}
- Use primary ticker (e.g., AAPL for Apple, GUBRA.CO for Gubra, NTDOY for Nintendo ADR)
- Include exchange suffix if not US (.CO for Copenhagen, .TO for Toronto, .HK for Hong Kong)
- If NOT publicly traded or uncertain: return null

Examples:
{{
  "Apple": {{"ticker": "AAPL", "exchange": "NASDAQ"}},
  "Gubra": {{"ticker": "GUBRA.CO", "exchange": "Copenhagen"}},
  "My Local Bakery": null,
  "Goldman Sachs": {{"ticker": "GS", "exchange": "NYSE"}}
}}

Respond with ONLY the JSON object, no explanation."""

                logger.info(
                    f"🤖 Asking LLM (BATCH): Are these {len(batch)} companies publicly traded?",
                    extra={
                        "batch_size": len(batch),
                        "companies": batch,
                        "model": "gpt-4o-mini",
                        "purpose": "batch_ticker_resolution",
                    },
                )

                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=500,  # More tokens for batch responses
                    temperature=0,
                )

                result_text = (
                    response.choices[0].message.content.strip()
                    if response.choices[0].message.content
                    else ""
                )
                batch_results = json.loads(result_text)

                # Parse results and log each company
                for company_name in batch:
                    company_result = batch_results.get(company_name)

                    if company_result and company_result.get("ticker"):
                        logger.info(
                            f"✅ LLM says YES: '{company_name}' → {company_result['ticker']}",
                            extra={
                                "company_name": company_name,
                                "ticker": company_result["ticker"],
                                "exchange": company_result.get("exchange"),
                                "model": "gpt-4o-mini",
                                "batch_mode": True,
                            },
                        )
                        results[company_name] = company_result
                    else:
                        logger.debug(
                            f"❌ LLM says NO: '{company_name}' is not a public company",
                            extra={"company_name": company_name, "batch_mode": True},
                        )
                        results[company_name] = None

        except json.JSONDecodeError as e:
            logger.warning(
                f"Failed to parse batched LLM response: {e}",
                extra={"error": str(e), "batch_size": len(company_names)},
            )
            # Fallback: Mark all as None
            for company_name in company_names:
                results[company_name] = None

        except Exception as e:
            logger.error(
                f"Batched LLM resolution failed: {e}",
                extra={"error": str(e), "batch_size": len(company_names)},
                exc_info=True,
            )
            # Fallback: Mark all as None
            for company_name in company_names:
                results[company_name] = None

        return results

    @lru_cache(maxsize=10000)  # noqa: B019 - Singleton service, caching essential for performance
    def validate_ticker(self, ticker: str) -> bool:
        """Verify ticker exists via yfinance API.

        Validates that the LLM-suggested ticker actually exists and has
        valid market data. This catches LLM hallucinations or errors.

        Args:
            ticker: Stock ticker symbol (e.g., "AAPL", "GUBRA.CO")

        Returns:
            True if ticker exists and has valid data

        Examples:
            >>> detector.validate_ticker("AAPL")
            True

            >>> detector.validate_ticker("GUBRA.CO")
            True  # If it exists

            >>> detector.validate_ticker("FAKESYMBOL123")
            False

        Note:
            Results are cached (LRU cache, 10,000 entries) to avoid repeated
            API calls. Cache persists for the lifetime of the process.
        """
        try:
            logger.debug(
                "📊 Validating ticker via market data adapter",
                extra={"ticker": ticker, "purpose": "existence_check"},
            )

            # Get market data adapter
            adapter = get_market_data_adapter()

            # Validate ticker
            is_valid = adapter.validate_ticker(ticker)

            if is_valid:
                logger.info(
                    "✅ Ticker validated successfully",
                    extra={
                        "ticker": ticker,
                        "method": "market_data_adapter",
                    },
                )
            else:
                logger.warning(
                    "❌ Ticker validation failed (no price data)",
                    extra={
                        "ticker": ticker,
                        "method": "price_history",
                    },
                )

            return is_valid

        except Exception as e:
            error_msg = str(e)

            # If rate limited, log appropriately
            if "429" in error_msg or "Too Many Requests" in error_msg:
                logger.error(
                    "⚠️  Rate limited by yfinance - ticker validation skipped",
                    extra={
                        "ticker": ticker,
                        "error": "429_too_many_requests",
                        "suggestion": "Increase _YFINANCE_MIN_INTERVAL or wait before retrying",
                    },
                )
            else:
                logger.warning(
                    f"❌ Ticker validation failed with error: {e}",
                    extra={"ticker": ticker, "error": str(e), "error_type": type(e).__name__},
                )

            # Don't retry on errors - cache the failure to prevent hammering API
            return False
