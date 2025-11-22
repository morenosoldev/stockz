"""Integration tests for research pipeline with real chatbot API calls.

These tests validate the end-to-end research pipeline with actual OpenAI API calls.
They require the LLM_OPENAI_API_KEY environment variable to be set.

Run with: pytest tests/integration/research/ -v -s
Skip with: pytest -m "not integration"
"""

from datetime import UTC, datetime

import pytest

from src.datasources.company import CompanyAdapter
from src.ops.config import get_config
from src.research.claim_extractor import (
    Claim,
    analyze_narrative,
    deduplicate_claims,
    extract_claims_batched,
)
from src.research.fact_checker import fact_check_claims, rank_claims_by_impact

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def config():
    """Load configuration for integration tests."""
    cfg = get_config()
    if not cfg.llm.openai_api_key:
        pytest.skip("LLM_OPENAI_API_KEY environment variable not set")
    return cfg


@pytest.fixture
def sample_reddit_comments():
    """Sample Reddit comments for testing claim extraction."""
    return [
        {
            "comment_id": "test1",
            "comment": "NVDA just crushed earnings with 50% revenue growth. Their data center business is booming and they're the clear AI leader.",
            "score": 150,
        },
        {
            "comment_id": "test2",
            "comment": "Nvidia's guidance was strong too. They're projecting another 45% growth next quarter. Stock is going to the moon! 🚀",
            "score": 120,
        },
        {
            "comment_id": "test3",
            "comment": "P/E ratio is over 60 though. Seems way overvalued even with the growth. Bubble territory.",
            "score": 80,
        },
        {
            "comment_id": "test4",
            "comment": "AMD is catching up fast. Competition is heating up in the GPU space. NVDA won't have a monopoly forever.",
            "score": 90,
        },
        {
            "comment_id": "test5",
            "comment": "Their gross margins are insane - over 70%. That's Apple-level profitability. Justifies the valuation IMO.",
            "score": 110,
        },
    ]


class TestClaimExtractionIntegration:
    """Integration tests for claim extraction with real LLM calls."""

    def test_extract_claims_from_comments(self, config, sample_reddit_comments):
        """Test extracting claims from real comments using GPT-4o-mini."""
        claims = extract_claims_batched(
            comments=sample_reddit_comments,
            ticker="NVDA",
            batch_size=3,  # Use smaller batch for faster test
            config=config,
        )

        # Validate we extracted claims
        assert len(claims) > 0, "Should extract at least one claim"

        # Validate claim structure
        for claim in claims:
            assert isinstance(claim, Claim)
            assert claim.ticker == "NVDA"
            assert claim.text  # Should have text
            assert claim.category in [
                "financial_performance",
                "product_launch",
                "market_position",
                "management_change",
                "regulatory_issue",
                "competitive_threat",
                "other",
            ]
            assert 0 <= claim.confidence <= 1.0
            assert claim.source_comment_id in [c["comment_id"] for c in sample_reddit_comments]
            assert claim.comment_score > 0
            assert claim.comment_index >= 0

        print(f"\n✅ Extracted {len(claims)} claims from {len(sample_reddit_comments)} comments")
        for claim in claims[:3]:  # Show first 3
            print(f"  - [{claim.category}] {claim.text} (confidence: {claim.confidence:.2f})")

    def test_deduplicate_claims(self, config, sample_reddit_comments):
        """Test deduplication with real claims."""
        # Extract claims
        claims = extract_claims_batched(
            comments=sample_reddit_comments,
            ticker="NVDA",
            batch_size=3,
            config=config,
        )

        original_count = len(claims)

        # Deduplicate
        deduplicated = deduplicate_claims(claims)

        # Should have <= original count
        assert len(deduplicated) <= original_count

        print(f"\n✅ Deduplicated {original_count} claims → {len(deduplicated)} unique claims")

    def test_analyze_narrative(self, config, sample_reddit_comments):
        """Test narrative analysis with real LLM call."""
        # Extract claims first
        claims = extract_claims_batched(
            comments=sample_reddit_comments,
            ticker="NVDA",
            batch_size=3,
            config=config,
        )

        # Analyze narrative
        narrative = analyze_narrative(claims=claims, ticker="NVDA", config=config)

        # Validate narrative
        assert narrative.primary_theme  # Should have a primary theme
        assert narrative.total_comments_analyzed == len(claims)
        assert 0 <= narrative.consensus_strength <= 1.0

        print("\n✅ Narrative Analysis for NVDA:")
        print(f"  - Primary Theme: {narrative.primary_theme}")
        print(f"  - Secondary Themes: {', '.join(narrative.secondary_themes)}")
        print(f"  - Consensus Strength: {narrative.consensus_strength:.2f}")
        print(f"  - Contradicting Views: {len(narrative.contradicting_views)}")


class TestFactCheckingIntegration:
    """Integration tests for fact-checking with real chatbot research."""

    def test_fact_check_claims(self, config, sample_reddit_comments):
        """Test fact-checking with real chatbot web research."""
        # Extract claims first
        claims = extract_claims_batched(
            comments=sample_reddit_comments,
            ticker="NVDA",
            batch_size=3,
            config=config,
        )

        # Rank by impact
        ranked = rank_claims_by_impact(claims)

        # Fact-check top 3 claims (limit for faster test)
        fact_check_results = fact_check_claims(
            claims=ranked,
            ticker="NVDA",
            max_claims_to_verify=3,
            config=config,
        )

        # Validate results
        assert len(fact_check_results) <= 3, "Should respect max_claims limit"
        assert len(fact_check_results) > 0, "Should fact-check at least one claim"

        for result in fact_check_results:
            assert result.claim in [c.text for c in claims]
            assert isinstance(result.verified, bool)
            assert 0 <= result.confidence <= 1.0
            assert result.checked_at is not None

            # If verified, should have sources/evidence
            if result.verified:
                assert result.sources or result.evidence, (
                    "Verified claims should have sources/evidence"
                )

        print(f"\n✅ Fact-checked {len(fact_check_results)} claims:")
        for result in fact_check_results:
            status = "✓ VERIFIED" if result.verified else "✗ DEBUNKED"
            print(f"  {status} (confidence: {result.confidence:.2f})")
            print(f"    Claim: {result.claim}")
            if result.evidence:
                print(f"    Evidence: {result.evidence[:100]}...")

    def test_rank_claims_by_impact(self, config, sample_reddit_comments):
        """Test claim ranking by impact score."""
        # Extract claims
        claims = extract_claims_batched(
            comments=sample_reddit_comments,
            ticker="NVDA",
            batch_size=3,
            config=config,
        )

        # Rank
        ranked = rank_claims_by_impact(claims)

        # Validate ranking
        assert len(ranked) == len(claims)

        # Check descending order
        for i in range(len(ranked) - 1):
            impact_current = ranked[i].comment_score * ranked[i].confidence
            impact_next = ranked[i + 1].comment_score * ranked[i + 1].confidence
            assert impact_current >= impact_next, "Should be sorted by impact descending"

        print(f"\n✅ Ranked {len(ranked)} claims by impact")


class TestCompanyAdapterIntegration:
    """Integration tests for company data gathering with real chatbot calls."""

    def test_get_company_data_real_api(self, config):
        """Test company data retrieval with real chatbot research."""
        adapter = CompanyAdapter(config=config)

        # Fetch company data for a real ticker
        company_data = adapter.get_company_data(ticker="AAPL")

        # Validate structure
        assert company_data.ticker == "AAPL"
        assert company_data.company_name  # Should have a name
        assert company_data.fetched_at is not None

        # At least some fields should be populated
        assert (
            company_data.revenue_growth is not None
            or company_data.earnings_surprise is not None
            or company_data.recent_events
            or company_data.analyst_ratings
        ), "Should have at least some data populated"

        print(f"\n✅ Fetched company data for {company_data.ticker}:")
        print(f"  - Company: {company_data.company_name}")
        if company_data.revenue_growth is not None:
            print(f"  - Revenue Growth: {company_data.revenue_growth:.1f}%")
        if company_data.earnings_surprise is not None:
            print(f"  - Earnings Surprise: {company_data.earnings_surprise:.1f}%")
        if company_data.recent_events:
            print(f"  - Recent Events: {len(company_data.recent_events)}")
        if company_data.analyst_ratings:
            print(f"  - Analyst Ratings: {company_data.analyst_ratings}")

    def test_company_data_caching(self, config):
        """Test that company data is cached between calls."""
        adapter = CompanyAdapter(config=config)

        # First call - should hit API
        start1 = datetime.now(UTC)
        data1 = adapter.get_company_data(ticker="MSFT")
        duration1 = (datetime.now(UTC) - start1).total_seconds()

        # Second call - should use cache (much faster)
        start2 = datetime.now(UTC)
        data2 = adapter.get_company_data(ticker="MSFT")
        duration2 = (datetime.now(UTC) - start2).total_seconds()

        # Validate
        assert data1.ticker == data2.ticker == "MSFT"
        assert duration2 < duration1, "Cached call should be faster than API call"

        print("\n✅ Caching validation:")
        print(f"  - First call (API): {duration1:.2f}s")
        print(f"  - Second call (cache): {duration2:.2f}s")
        print(f"  - Speedup: {duration1 / duration2:.1f}x")

    def test_attribution(self, config):
        """Test that attribution is properly set."""
        adapter = CompanyAdapter(config=config)

        # Fetch data
        adapter.get_company_data(ticker="GOOGL")

        # Get attribution
        attribution = adapter.get_attribution()

        # Validate
        assert attribution.source.value == "chatbot_research"
        assert attribution.timestamp is not None

        print("\n✅ Attribution validated:")
        print(f"  - Source: {attribution.source.value}")
        print(f"  - Timestamp: {attribution.timestamp}")


class TestEndToEndResearchPipeline:
    """Integration test for the complete research pipeline."""

    def test_full_research_pipeline(self, config, sample_reddit_comments):
        """Test the complete pipeline: extract → deduplicate → fact-check → company data."""
        ticker = "NVDA"

        print(f"\n🔬 Running full research pipeline for {ticker}...")

        # Step 1: Extract claims
        print("\n1️⃣ Extracting claims...")
        raw_claims = extract_claims_batched(
            comments=sample_reddit_comments,
            ticker=ticker,
            batch_size=3,
            config=config,
        )
        print(f"   Extracted {len(raw_claims)} raw claims")

        # Step 2: Deduplicate
        print("\n2️⃣ Deduplicating claims...")
        unique_claims = deduplicate_claims(raw_claims)
        print(f"   Deduplicated to {len(unique_claims)} unique claims")

        # Step 3: Analyze narrative
        print("\n3️⃣ Analyzing narrative...")
        narrative = analyze_narrative(claims=unique_claims, ticker=ticker, config=config)
        print(f"   Primary theme: {narrative.primary_theme}")
        print(f"   Consensus strength: {narrative.consensus_strength:.2f}")

        # Step 4: Fact-check top claims
        print("\n4️⃣ Fact-checking top claims...")
        ranked_claims = rank_claims_by_impact(unique_claims)
        fact_check_results = fact_check_claims(
            claims=ranked_claims,
            ticker=ticker,
            max_claims_to_verify=2,  # Limit for faster test
            config=config,
        )
        verified_count = sum(1 for r in fact_check_results if r.verified)
        debunked_count = len(fact_check_results) - verified_count
        print(f"   Verified: {verified_count}, Debunked: {debunked_count}")

        # Step 5: Gather company data
        print("\n5️⃣ Gathering company data...")
        company_adapter = CompanyAdapter(config=config)
        company_data = company_adapter.get_company_data(ticker=ticker)
        print(f"   Company: {company_data.company_name}")

        # Final validation
        assert len(raw_claims) > 0, "Should extract claims"
        assert len(unique_claims) <= len(raw_claims), (
            "Deduplication should reduce or maintain count"
        )
        assert narrative.primary_theme, "Should have narrative"
        assert len(fact_check_results) > 0, "Should fact-check claims"
        assert company_data.ticker == ticker, "Should fetch company data"

        print("\n✅ Full pipeline completed successfully!")
        print("\nPipeline Summary:")
        print(f"  - Raw claims: {len(raw_claims)}")
        print(f"  - Unique claims: {len(unique_claims)}")
        print(f"  - Narrative consensus: {narrative.consensus_strength:.2f}")
        print(
            f"  - Fact-checks: {len(fact_check_results)} ({verified_count} verified, {debunked_count} debunked)"
        )
        print(f"  - Company: {company_data.company_name}")
