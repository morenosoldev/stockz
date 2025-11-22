"""Research module for fact-checking and company intelligence gathering.

This module provides tools to extract claims from Reddit discussions,
verify them using AI-powered web research, and gather comprehensive
company intelligence to support investment decisions.

Key components:
- ClaimExtractor: Extract factual claims from Reddit comments
- FactChecker: Verify claims using chatbot web research
- CompanyAdapter: Gather company intelligence via chatbot research
- NarrativeAnalyzer: Analyze consensus and themes in discussions
"""

from src.datasources.company import CompanyAdapter, CompanyData
from src.research.claim_extractor import (
    Claim,
    NarrativeConsensus,
    analyze_narrative,
    deduplicate_claims,
    extract_claims_batched,
)
from src.research.fact_checker import (
    FactCheckResult,
    fact_check_claims,
    rank_claims_by_impact,
)

__all__ = [
    # Claim extraction
    "Claim",
    "NarrativeConsensus",
    "extract_claims_batched",
    "deduplicate_claims",
    "analyze_narrative",
    # Fact checking
    "FactCheckResult",
    "fact_check_claims",
    "rank_claims_by_impact",
    # Company intelligence
    "CompanyAdapter",
    "CompanyData",
]
