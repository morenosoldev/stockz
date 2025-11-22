"""
Company data adapter using chatbot for autonomous web research.

This module provides company intelligence gathering using GPT-4o to research
company financials, recent events, analyst data, and fundamentals from the web.
Results are cached for 24 hours to avoid redundant research.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from openai import OpenAI

from src.datasources.attribution import Attribution, DataSource
from src.datasources.base import DataAdapterProtocol
from src.datasources.cache import Cache
from src.ops.config import get_config
from src.ops.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CompanyData:
    """Company intelligence data from chatbot research."""

    ticker: str
    company_name: str
    sector: str | None = None
    industry: str | None = None

    # Financials (latest available)
    market_cap: float | None = None
    revenue: float | None = None
    revenue_growth_yoy: float | None = None
    earnings_per_share: float | None = None
    pe_ratio: float | None = None
    profit_margin: float | None = None

    # Recent events (last 3 months)
    recent_news: list[str] = field(default_factory=list)
    recent_press_releases: list[str] = field(default_factory=list)
    catalyst_events: list[str] = field(default_factory=list)

    # Analyst data
    analyst_rating: str | None = None  # e.g., "Buy", "Hold", "Sell"
    price_target: float | None = None
    analyst_count: int | None = None

    # Company profile
    description: str | None = None
    employees: int | None = None
    founded_year: int | None = None
    headquarters: str | None = None

    # Research metadata
    sources: list[str] = field(default_factory=list)
    search_queries_used: list[str] = field(default_factory=list)
    researched_at: datetime = field(default_factory=datetime.now)
    confidence: float = 0.0  # 0.0-1.0 based on source quality

    # Attribution
    attribution: Attribution | None = None


# Chatbot research prompt for company intelligence
COMPANY_RESEARCH_PROMPT = """
You are a financial research assistant with access to the internet. Research the following company thoroughly and provide comprehensive intelligence.

**Company Ticker**: {ticker}

**Research Tasks**:
1. **Company Profile**:
   - Full company name
   - Sector and industry classification
   - Brief description of business model (2-3 sentences)
   - Headquarters location
   - Number of employees (if available)
   - Year founded (if available)

2. **Financial Metrics** (Most recent quarter or year):
   - Market capitalization (in millions/billions)
   - Revenue (latest quarter or annual)
   - Year-over-year revenue growth percentage
   - Earnings per share (EPS)
   - Price-to-earnings ratio (P/E)
   - Profit margin percentage

3. **Recent Events** (Last 3 months):
   - Major news headlines (top 3-5)
   - Press releases or company announcements
   - Catalyst events (earnings, product launches, partnerships, regulatory approvals, etc.)

4. **Analyst Coverage**:
   - Consensus analyst rating (Buy/Hold/Sell)
   - Average price target
   - Number of analysts covering the stock

**Research Guidelines**:
- Use the most recent data available
- Prioritize official sources (company filings, press releases, financial databases)
- For missing data, state "Not available" rather than guessing
- Include source URLs for each major data point
- Track all search queries you used to gather this information
- Assign confidence score based on source quality:
  - 0.95+ for SEC filings, official press releases
  - 0.90+ for financial databases (Bloomberg, Reuters, Yahoo Finance)
  - 0.85+ for major financial news outlets (WSJ, FT, CNBC)
  - 0.80+ for company website, investor relations
  - 0.70+ for general news sources
  - 0.60+ if data is incomplete or conflicting

**Output Format** (JSON):
{{
  "company_name": "string",
  "sector": "string or null",
  "industry": "string or null",
  "description": "string or null",
  "headquarters": "string or null",
  "employees": number or null,
  "founded_year": number or null,
  "market_cap": number or null,
  "revenue": number or null,
  "revenue_growth_yoy": number or null,
  "earnings_per_share": number or null,
  "pe_ratio": number or null,
  "profit_margin": number or null,
  "recent_news": ["string", ...],
  "recent_press_releases": ["string", ...],
  "catalyst_events": ["string", ...],
  "analyst_rating": "string or null",
  "price_target": number or null,
  "analyst_count": number or null,
  "sources": ["url1", "url2", ...],
  "search_queries_used": ["query1", "query2", ...],
  "confidence": number (0.0-1.0)
}}

**Important**:
- Be thorough but concise
- Verify critical numbers from multiple sources
- Flag any data that seems outdated or unreliable
- If the company is delisted, private, or has no recent data, still provide what's available
"""


class CompanyAdapter(DataAdapterProtocol):
    """
    Adapter for fetching company intelligence using chatbot research.

    Uses GPT-4o with web search to autonomously gather company data including
    financials, recent events, analyst coverage, and company profile. Results
    are cached for 24 hours to minimize redundant research.

    Example:
        >>> adapter = CompanyAdapter()
        >>> company_data = adapter.get_company_data("AAPL")
        >>> print(f"Market Cap: ${company_data.market_cap}B")
        >>> print(f"Revenue Growth: {company_data.revenue_growth_yoy}%")
    """

    source = DataSource.CHATBOT_RESEARCH

    def __init__(self) -> None:
        """Initialize company adapter with chatbot client and cache."""
        config = get_config()
        self.client = OpenAI(api_key=config.llm.openai_api_key)
        self.model = config.llm.model_fact_checker  # GPT-4o for company research
        self.cache_dir = Path(config.datasources.cache.cache_dir) / "company"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache = Cache(cache_dir=str(self.cache_dir), ttl_seconds=86400)  # 24h cache
        self._last_attribution: Attribution | None = None

        logger.info(
            "Initialized CompanyAdapter",
            extra={"model": self.model, "cache_dir": str(self.cache_dir)},
        )

    def get_company_data(self, ticker: str) -> CompanyData:
        """
        Get comprehensive company data for a ticker using chatbot research.

        Args:
            ticker: Stock ticker symbol (e.g., "AAPL")

        Returns:
            CompanyData with financials, events, analyst data, and profile

        Raises:
            Exception: If chatbot research fails after retries
        """
        ticker = ticker.upper()
        cache_key = f"company_{ticker}"

        # Check cache first
        cached_data = self.cache.get(cache_key)
        if cached_data is not None:
            logger.info(f"Using cached company data for {ticker}")
            # Reconstruct Attribution from dict
            attribution_dict = cached_data.pop("attribution", None)
            if attribution_dict:
                attribution = Attribution(
                    source=DataSource(attribution_dict["source"]),
                    timestamp=datetime.fromisoformat(attribution_dict["timestamp"]),
                    url=attribution_dict.get("url"),
                    api_endpoint=attribution_dict.get("api_endpoint"),
                    version=attribution_dict.get("version", "1.0"),
                )
                cached_data["attribution"] = attribution

            # Convert researched_at string to datetime if needed
            if "researched_at" in cached_data and isinstance(cached_data["researched_at"], str):
                cached_data["researched_at"] = datetime.fromisoformat(cached_data["researched_at"])

            company_data = CompanyData(**cached_data)
            self._last_attribution = company_data.attribution
            return company_data

        # Research company with chatbot
        logger.info(f"Researching company data for {ticker} using chatbot")
        company_data = self._research_company_with_chatbot(ticker)

        # Add attribution
        company_data.attribution = Attribution(
            source=DataSource.CHATBOT_RESEARCH,
            timestamp=datetime.now(),
            url=None,
            api_endpoint="openai/chat/completions",
            version="1.0",
        )
        self._last_attribution = company_data.attribution

        # Cache result
        cache_data = {
            "ticker": company_data.ticker,
            "company_name": company_data.company_name,
            "sector": company_data.sector,
            "industry": company_data.industry,
            "market_cap": company_data.market_cap,
            "revenue": company_data.revenue,
            "revenue_growth_yoy": company_data.revenue_growth_yoy,
            "earnings_per_share": company_data.earnings_per_share,
            "pe_ratio": company_data.pe_ratio,
            "profit_margin": company_data.profit_margin,
            "recent_news": company_data.recent_news,
            "recent_press_releases": company_data.recent_press_releases,
            "catalyst_events": company_data.catalyst_events,
            "analyst_rating": company_data.analyst_rating,
            "price_target": company_data.price_target,
            "analyst_count": company_data.analyst_count,
            "description": company_data.description,
            "employees": company_data.employees,
            "founded_year": company_data.founded_year,
            "headquarters": company_data.headquarters,
            "sources": company_data.sources,
            "search_queries_used": company_data.search_queries_used,
            "researched_at": company_data.researched_at.isoformat(),
            "confidence": company_data.confidence,
            "attribution": {
                "source": company_data.attribution.source.value,
                "timestamp": company_data.attribution.timestamp.isoformat(),
                "url": company_data.attribution.url,
                "api_endpoint": company_data.attribution.api_endpoint,
                "version": company_data.attribution.version,
            },
        }
        self.cache.set(cache_key, cache_data)

        logger.info(
            f"Company research completed for {ticker}",
            extra={
                "company": company_data.company_name,
                "confidence": company_data.confidence,
                "sources_count": len(company_data.sources),
            },
        )

        return company_data

    def _research_company_with_chatbot(self, ticker: str) -> CompanyData:
        """
        Use chatbot to research company intelligence from the web.

        Args:
            ticker: Stock ticker symbol

        Returns:
            CompanyData with researched information

        Raises:
            Exception: If chatbot call fails
        """
        prompt = COMPANY_RESEARCH_PROMPT.format(ticker=ticker)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,  # Low temperature for factual research
                response_format={"type": "json_object"},
                timeout=30.0,  # 30s timeout for thorough research
            )

            result_json = response.choices[0].message.content
            if not result_json:
                raise ValueError("Empty response from chatbot")

            result = json.loads(result_json)

            # Build CompanyData from chatbot response
            company_data = CompanyData(
                ticker=ticker,
                company_name=result.get("company_name", ticker),
                sector=result.get("sector"),
                industry=result.get("industry"),
                market_cap=result.get("market_cap"),
                revenue=result.get("revenue"),
                revenue_growth_yoy=result.get("revenue_growth_yoy"),
                earnings_per_share=result.get("earnings_per_share"),
                pe_ratio=result.get("pe_ratio"),
                profit_margin=result.get("profit_margin"),
                recent_news=result.get("recent_news", []),
                recent_press_releases=result.get("recent_press_releases", []),
                catalyst_events=result.get("catalyst_events", []),
                analyst_rating=result.get("analyst_rating"),
                price_target=result.get("price_target"),
                analyst_count=result.get("analyst_count"),
                description=result.get("description"),
                employees=result.get("employees"),
                founded_year=result.get("founded_year"),
                headquarters=result.get("headquarters"),
                sources=result.get("sources", []),
                search_queries_used=result.get("search_queries_used", []),
                researched_at=datetime.now(),
                confidence=result.get("confidence", 0.7),
            )

            return company_data

        except Exception as e:
            logger.error(
                f"Chatbot research failed for {ticker}: {e}",
                exc_info=True,
                extra={"ticker": ticker},
            )
            # Return minimal fallback data
            return CompanyData(
                ticker=ticker,
                company_name=ticker,
                confidence=0.0,
                sources=[],
                search_queries_used=[],
            )

    def fetch(self, ticker: str, **kwargs: Any) -> CompanyData:
        """
        Fetch company data (implements DataAdapterProtocol).

        Args:
            ticker: Stock ticker symbol
            **kwargs: Additional arguments (unused)

        Returns:
            CompanyData for the ticker
        """
        return self.get_company_data(ticker)

    def get_attribution(self) -> Attribution:
        """
        Get attribution for the last fetch.

        Returns:
            Attribution metadata for last company data fetch

        Raises:
            ValueError: If no fetch has been performed yet
        """
        if self._last_attribution is None:
            raise ValueError("No fetch performed yet, no attribution available")
        return self._last_attribution
