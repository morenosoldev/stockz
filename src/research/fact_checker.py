"""Fact-checking claims using AI-powered web research.

This module uses chatbot (GPT-4 with web search) to verify claims
by autonomously searching the web and synthesizing evidence.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from openai import OpenAI

from src.ops.config import get_config
from src.ops.logging import get_logger
from src.research.claim_extractor import Claim

logger = get_logger(__name__)


@dataclass
class FactCheckResult:
    """Result of fact-checking a claim."""

    claim: Claim
    verified: bool  # True if found corroborating evidence
    confidence: float  # 0-1, how confident we are in verification
    sources: list[str]  # URLs to corroborating articles/filings
    evidence: str  # Short summary of what was found
    checked_at: datetime
    search_queries_used: list[str] | None = None  # Queries chatbot used


# Fact-checking prompt for chatbot web research
FACT_CHECK_RESEARCH_PROMPT = """
You are a financial fact-checker verifying claims about stock ticker ${TICKER}.

**Claim to verify**: "${CLAIM_TEXT}"
**Category**: ${CATEGORY}
**Date context**: This claim was made recently. Focus on events from the last 30 days.

**Your task**:
1. Search the web for evidence (news articles, press releases, SEC filings, analyst reports)
2. Determine if the claim is TRUE, FALSE, or UNVERIFIABLE
3. Provide confidence level (0-1) based on source quality and evidence strength

**Confidence scoring guidelines**:
- Official press release or SEC filing: 0.95
- Multiple reputable news sources (within 7 days): 0.9
- Single reputable news source (within 30 days): 0.7-0.8
- Analyst reports or industry publications: 0.6-0.7
- No evidence found after thorough search: 0.85-0.95 (high confidence it's FALSE)
- Found contradicting evidence: 0.9-0.95 (claim is DEBUNKED)

**Return JSON**:
{
  "verified": true/false,
  "confidence": 0.0-1.0,
  "evidence": "Brief summary of what you found (2-3 sentences)",
  "sources": ["url1", "url2", ...],
  "search_queries_used": ["query1", "query2"]
}

Be thorough but concise. Prioritize recent, authoritative sources.
"""


def fact_check_claims(
    claims: list[Claim], max_claims: int = 10, timeout_seconds: int = 15
) -> list[FactCheckResult]:
    """Fact-check claims using chatbot web research.

    Args:
        claims: List of claims to verify
        max_claims: Maximum number of claims to verify (verify top N by impact)
        timeout_seconds: Timeout per claim verification

    Returns:
        List of fact-check results
    """
    if not claims:
        logger.info("No claims to fact-check")
        return []

    # Rank claims by impact and take top N
    ranked_claims = rank_claims_by_impact(claims)[:max_claims]

    logger.info(
        f"Fact-checking top {len(ranked_claims)} claims (out of {len(claims)} total)",
        total_claims=len(claims),
        checking_count=len(ranked_claims),
    )

    results = []
    for i, claim in enumerate(ranked_claims, 1):
        logger.info(
            f"Fact-checking claim {i}/{len(ranked_claims)}: {claim.text[:60]}...",
            claim_number=i,
            total=len(ranked_claims),
            category=claim.category,
        )

        try:
            result = research_claim_with_chatbot(claim, timeout_seconds)
            results.append(result)

            status = "✅ VERIFIED" if result.verified else "❌ DEBUNKED"
            logger.info(
                f"{status}: {claim.text[:60]}... (confidence: {result.confidence:.2f})",
                verified=result.verified,
                confidence=result.confidence,
                sources_count=len(result.sources),
            )

        except Exception as e:
            logger.error(
                f"Failed to fact-check claim: {claim.text[:60]}...",
                claim_text=claim.text,
                error=str(e),
                exc_info=True,
            )
            # Create failed result
            results.append(
                FactCheckResult(
                    claim=claim,
                    verified=False,
                    confidence=0.0,
                    sources=[],
                    evidence=f"Fact-check failed: {str(e)}",
                    checked_at=datetime.now(UTC),
                    search_queries_used=[],
                )
            )

    verified_count = sum(1 for r in results if r.verified)
    logger.info(
        f"Fact-checking complete: {verified_count}/{len(results)} verified",
        verified_count=verified_count,
        total_checked=len(results),
    )

    return results


def research_claim_with_chatbot(claim: Claim, timeout_seconds: int = 15) -> FactCheckResult:
    """Research a single claim using chatbot with web search.

    Args:
        claim: Claim to verify
        timeout_seconds: Timeout for research

    Returns:
        Fact-check result with evidence and sources
    """
    config = get_config()
    client = OpenAI(api_key=config.llm.openai_api_key)

    # Build research prompt
    prompt = (
        FACT_CHECK_RESEARCH_PROMPT.replace("${TICKER}", claim.ticker)
        .replace("${CLAIM_TEXT}", claim.text)
        .replace("${CATEGORY}", claim.category)
    )

    try:
        # Call OpenAI GPT-4 with function calling for web search
        # NOTE: This requires GPT-4 with browsing/function calling enabled
        # or integration with Perplexity API / Tavily / SerpAPI
        response = client.chat.completions.create(
            model="gpt-4o",  # Use GPT-4 for better reasoning
            messages=[
                {
                    "role": "system",
                    "content": "You are a financial fact-checker with access to web search. Research claims thoroughly and provide evidence-based verdicts.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,  # Low temperature for factual accuracy
            response_format={"type": "json_object"},
            timeout=timeout_seconds,
        )

        # Parse response
        result_text = response.choices[0].message.content
        if not result_text:
            raise ValueError("Empty response from chatbot")

        result_json = json.loads(result_text)

        # Extract fields
        verified = bool(result_json.get("verified", False))
        confidence = float(result_json.get("confidence", 0.5))
        evidence = result_json.get("evidence", "No evidence summary provided")
        sources = result_json.get("sources", [])
        search_queries = result_json.get("search_queries_used", [])

        # Validate confidence is in range
        confidence = max(0.0, min(1.0, confidence))

        return FactCheckResult(
            claim=claim,
            verified=verified,
            confidence=confidence,
            sources=sources if isinstance(sources, list) else [],
            evidence=evidence,
            checked_at=datetime.now(UTC),
            search_queries_used=search_queries if isinstance(search_queries, list) else [],
        )

    except json.JSONDecodeError as e:
        logger.error(
            "Failed to parse chatbot response as JSON",
            claim_text=claim.text,
            error=str(e),
        )
        raise ValueError(f"Invalid JSON response from chatbot: {e}") from e

    except Exception as e:
        logger.error(
            "Chatbot research failed",
            claim_text=claim.text,
            error=str(e),
            exc_info=True,
        )
        raise


def rank_claims_by_impact(claims: list[Claim]) -> list[Claim]:
    """Rank claims by impact score (comment_score × confidence).

    Claims with high upvotes and high confidence are more impactful.

    Args:
        claims: List of claims to rank

    Returns:
        Sorted list of claims (highest impact first)
    """

    def impact_score(claim: Claim) -> float:
        """Calculate impact score for a claim."""
        # Impact = comment_score × confidence
        # Higher upvotes + higher confidence = higher impact
        return claim.comment_score * claim.confidence

    return sorted(claims, key=impact_score, reverse=True)
