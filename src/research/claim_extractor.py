"""Claim extraction from Reddit comments using LLM.

This module extracts factual claims from Reddit posts and comments,
categorizes them, and analyzes narrative consensus across discussions.
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from src.ops.config import get_config
from src.ops.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Claim:
    """A factual claim extracted from a Reddit comment."""

    text: str  # "FDA approval for drug XYZ expected Q1 2026"
    category: str  # "regulatory", "financial", "product", "partnership", "management"
    ticker: str  # Stock ticker this claim is about
    confidence: float  # 0-1, how confident extraction is
    source_comment_id: str  # Reddit comment ID
    comment_score: int  # Reddit upvotes (higher = more credible)
    comment_index: int  # Position in thread (0-19)


@dataclass
class NarrativeConsensus:
    """Analysis of narrative consensus across comments."""

    primary_theme: str  # Main discussion theme
    secondary_themes: list[str]  # Other notable themes
    contradicting_views: list[str]  # Opposing viewpoints
    consensus_strength: float  # 0-1, how aligned are comments
    total_comments_analyzed: int


# Claim extraction prompt for batched processing
CLAIM_EXTRACTION_BATCH_PROMPT = """
You are analyzing Reddit comments about stock ticker ${TICKER} to extract verifiable factual claims.

You will receive a batch of comments. Extract ALL factual claims from ALL comments.

Focus on these claim types:
1. **Product**: Product announcements, launches, releases ("new iPhone launching")
2. **Financial**: Earnings, revenue, growth metrics ("earnings beat by 20%")
3. **Partnership**: Deals, acquisitions, collaborations ("acquired by Google")
4. **Regulatory**: FDA approvals, SEC filings, legal events ("FDA approval expected")
5. **Management**: Leadership changes, insider activity ("new CEO appointed")

Comments (JSON array):
${COMMENTS_JSON}

For each claim found, return:
{
  "text": "FDA approval expected Q1 2026",
  "category": "regulatory",
  "confidence": 0.85,
  "comment_index": 3,
  "comment_score": 245
}

**Important**:
- Only extract FACTUAL claims (not opinions like "stock will moon")
- If same claim appears in multiple comments, return it ONCE with the highest comment_score
- Confidence = how certain you are this is a factual claim (not speculation)
- Return empty array [] if no factual claims found

Return JSON array of claims:
"""


# Narrative analysis prompt for LLM-based consensus detection
NARRATIVE_ANALYSIS_PROMPT = """
You are analyzing the narrative consensus in Reddit discussions about stock ticker {ticker}.

You will receive:
1. A list of extracted claims with their categories and confidence scores
2. Excerpts from the original comments

Your task is to identify:
- **Primary theme**: The main discussion topic/catalyst
- **Secondary themes**: Other notable topics (up to 3)
- **Contradicting views**: Any opposing viewpoints or skepticism
- **Consensus strength**: How aligned are the comments (0.0-1.0)

**Extracted Claims** ({total_claims} total from {unique_commenters} unique commenters):
{claims_summary}

**Comment Excerpts**:
{comments_summary}

**Guidelines for consensus_strength**:
- 0.9-1.0: Strong consensus, all comments agree on same catalyst/theme
- 0.7-0.9: Moderate consensus, most agree with some dissenting views
- 0.5-0.7: Mixed opinions, multiple competing narratives
- 0.3-0.5: Fragmented discussion, no clear consensus
- 0.0-0.3: Highly contradictory, opposing views dominate

**Output Format** (JSON):
{{
  "primary_theme": "Brief description of main discussion topic (1 sentence)",
  "secondary_themes": ["theme1", "theme2", "theme3"],
  "contradicting_views": ["description of opposing view 1", "description of opposing view 2"],
  "consensus_strength": number (0.0-1.0)
}}

**Important**:
- Be concise in theme descriptions
- Identify real contradictions, not just different topics
- Base consensus_strength on claim alignment and comment sentiment
- Return empty arrays if no secondary themes or contradictions found
"""


def extract_claims_batched(
    comments: list[dict[str, Any]], ticker: str, batch_size: int = 10
) -> list[Claim]:
    """Extract claims from comments using batched LLM processing.

    Args:
        comments: List of Reddit comment dicts (up to 20)
        ticker: Stock ticker symbol
        batch_size: Number of comments per LLM call (default: 10 for 2 batches)

    Returns:
        List of extracted and deduplicated claims
    """
    if not comments:
        logger.warning("No comments provided for claim extraction", ticker=ticker)
        return []

    # Split comments into batches
    batches = [comments[i : i + batch_size] for i in range(0, len(comments), batch_size)]

    logger.info(
        f"Extracting claims from {len(comments)} comments using {len(batches)} batches",
        ticker=ticker,
        batch_count=len(batches),
        batch_size=batch_size,
    )

    # Process batches in parallel
    all_claims: list[Claim] = []
    with ThreadPoolExecutor(max_workers=min(len(batches), 4)) as executor:
        futures = {
            executor.submit(extract_claims_from_batch, batch, ticker, i * batch_size): i
            for i, batch in enumerate(batches)
        }

        for future in as_completed(futures):
            batch_idx = futures[future]
            try:
                batch_claims = future.result()
                all_claims.extend(batch_claims)
                logger.info(
                    f"Batch {batch_idx + 1}/{len(batches)}: Extracted {len(batch_claims)} claims",
                    ticker=ticker,
                    batch=batch_idx + 1,
                    claims_count=len(batch_claims),
                )
            except Exception as e:
                logger.error(
                    f"Failed to extract claims from batch {batch_idx + 1}",
                    ticker=ticker,
                    batch=batch_idx + 1,
                    error=str(e),
                    exc_info=True,
                )

    # Deduplicate across batches
    deduplicated = deduplicate_claims(all_claims)

    logger.info(
        f"Claim extraction complete: {len(all_claims)} raw → {len(deduplicated)} deduplicated",
        ticker=ticker,
        raw_count=len(all_claims),
        deduplicated_count=len(deduplicated),
    )

    return deduplicated


def extract_claims_from_batch(
    batch: list[dict[str, Any]], ticker: str, start_index: int = 0
) -> list[Claim]:
    """Extract claims from a single batch of comments using LLM.

    Args:
        batch: List of comment dicts (typically 10 comments)
        ticker: Stock ticker symbol
        start_index: Starting index for comment numbering

    Returns:
        List of extracted claims
    """
    config = get_config()
    client = OpenAI(api_key=config.llm.openai_api_key)

    # Format comments for LLM
    comments_json = json.dumps(
        [
            {
                "index": start_index + i,
                "text": comment.get("body", ""),
                "score": comment.get("score", 0),
                "id": comment.get("id", ""),
            }
            for i, comment in enumerate(batch)
        ],
        indent=2,
    )

    # Build prompt
    prompt = CLAIM_EXTRACTION_BATCH_PROMPT.replace("${TICKER}", ticker).replace(
        "${COMMENTS_JSON}", comments_json
    )

    try:
        # Call OpenAI with structured output
        response = client.chat.completions.create(
            model=config.llm.model_claim_extractor,  # GPT-4o-mini for extraction
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert financial analyst extracting factual claims from Reddit discussions.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,  # Low temperature for consistent extraction
            response_format={"type": "json_object"},
        )

        # Parse response
        result_text = response.choices[0].message.content
        if not result_text:
            logger.warning("Empty response from LLM", ticker=ticker)
            return []

        result_json = json.loads(result_text)

        # Handle different response formats
        claims_data = result_json.get("claims", [])
        if not isinstance(claims_data, list):
            logger.warning("Unexpected response format from LLM", ticker=ticker, result=result_json)
            return []

        # Convert to Claim objects
        claims = []
        for claim_dict in claims_data:
            try:
                comment_idx = claim_dict.get("comment_index", 0)
                comment_id = batch[comment_idx - start_index].get("id", "unknown")

                claims.append(
                    Claim(
                        text=claim_dict["text"],
                        category=claim_dict.get("category", "unknown"),
                        ticker=ticker,
                        confidence=float(claim_dict.get("confidence", 0.5)),
                        source_comment_id=comment_id,
                        comment_score=int(claim_dict.get("comment_score", 0)),
                        comment_index=comment_idx,
                    )
                )
            except (KeyError, ValueError, IndexError) as e:
                logger.warning(
                    "Failed to parse claim from LLM response",
                    ticker=ticker,
                    claim=claim_dict,
                    error=str(e),
                )
                continue

        return claims

    except Exception as e:
        logger.error(
            "LLM call failed during claim extraction",
            ticker=ticker,
            error=str(e),
            exc_info=True,
        )
        return []


def deduplicate_claims(claims: list[Claim]) -> list[Claim]:
    """Deduplicate similar claims, keeping the one with highest comment score.

    Args:
        claims: List of claims to deduplicate

    Returns:
        Deduplicated list of claims
    """
    if not claims:
        return []

    # Simple deduplication by exact text match
    # TODO: Use embeddings or fuzzy matching for semantic similarity
    claim_groups: dict[str, list[Claim]] = {}

    for claim in claims:
        # Normalize text for comparison
        normalized_text = claim.text.lower().strip()

        if normalized_text not in claim_groups:
            claim_groups[normalized_text] = []

        claim_groups[normalized_text].append(claim)

    # Keep claim with highest comment score from each group
    deduplicated = []
    for group in claim_groups.values():
        if len(group) == 1:
            deduplicated.append(group[0])
        else:
            # Sort by comment score (descending) and take first
            best_claim = sorted(group, key=lambda c: c.comment_score, reverse=True)[0]

            # Update confidence if multiple people say same thing
            mention_count = len(group)
            if mention_count >= 3:
                # Boost confidence if 3+ people mention same claim
                best_claim.confidence = min(best_claim.confidence + 0.1, 1.0)

            deduplicated.append(best_claim)

            logger.debug(
                f"Deduplicated claim mentioned by {mention_count} comments",
                claim_text=best_claim.text[:50],
                mention_count=mention_count,
                best_score=best_claim.comment_score,
            )

    return deduplicated


def analyze_narrative(
    claims: list[Claim], comments: list[dict[str, Any]], ticker: str
) -> NarrativeConsensus:
    """Analyze narrative consensus from claims and comments using LLM.

    Uses GPT-4o to identify primary themes, detect contradicting views,
    and calculate consensus strength from Reddit discussion patterns.

    Args:
        claims: Extracted claims
        comments: Original comments
        ticker: Stock ticker for context

    Returns:
        Narrative consensus analysis with themes, contradictions, and strength
    """
    if not claims:
        return NarrativeConsensus(
            primary_theme="No clear narrative",
            secondary_themes=[],
            contradicting_views=[],
            consensus_strength=0.0,
            total_comments_analyzed=len(comments),
        )

    # Count unique commenters
    unique_commenters = len({claim.source_comment_id for claim in claims})

    # Use LLM for narrative analysis
    config = get_config()
    client = OpenAI(api_key=config.llm.openai_api_key)

    # Prepare claims summary for LLM
    claims_summary = "\n".join(
        [
            f"- [{claim.category}] {claim.text} (confidence: {claim.confidence:.2f}, "
            f"score: {claim.comment_score}, comment #{claim.comment_index})"
            for claim in claims[:20]  # Limit to top 20 claims to avoid token overflow
        ]
    )

    # Prepare comments summary (first 100 chars of each)
    comments_summary = "\n".join(
        [
            f"Comment #{i}: {comment.get('body', '')[:100]}..."
            for i, comment in enumerate(comments[:10])  # Top 10 comments
        ]
    )

    prompt = NARRATIVE_ANALYSIS_PROMPT.format(
        ticker=ticker,
        claims_summary=claims_summary,
        comments_summary=comments_summary,
        total_claims=len(claims),
        unique_commenters=unique_commenters,
    )

    try:
        response = client.chat.completions.create(
            model=config.llm.model_fact_checker,  # GPT-4o for analysis
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"},
            timeout=15.0,
        )

        result_json = response.choices[0].message.content
        if not result_json:
            raise ValueError("Empty response from LLM")

        result = json.loads(result_json)

        logger.info(
            f"Narrative analysis complete for {ticker}",
            extra={
                "ticker": ticker,
                "primary_theme": result.get("primary_theme", "Unknown")[:50],
                "consensus_strength": result.get("consensus_strength", 0.0),
                "contradictions": len(result.get("contradicting_views", [])),
            },
        )

        return NarrativeConsensus(
            primary_theme=result.get("primary_theme", "Unknown"),
            secondary_themes=result.get("secondary_themes", []),
            contradicting_views=result.get("contradicting_views", []),
            consensus_strength=result.get("consensus_strength", 0.0),
            total_comments_analyzed=len(comments),
        )

    except Exception as e:
        logger.error(
            f"Narrative analysis failed for {ticker}: {e}",
            exc_info=True,
            extra={"ticker": ticker, "claims_count": len(claims)},
        )
        # Fallback to category-based analysis
        category_counts: dict[str, int] = {}
        for claim in claims:
            category_counts[claim.category] = category_counts.get(claim.category, 0) + 1

        primary_category = (
            max(category_counts.items(), key=lambda x: x[1])[0] if category_counts else "general"
        )

        # Map category to human-readable theme
        theme_map = {
            "regulatory": "Regulatory catalysts (FDA, SEC, etc.)",
            "financial": "Strong financial performance",
            "product": "New product launches/innovations",
            "partnership": "Strategic partnerships and deals",
            "management": "Management changes and insider activity",
        }

        primary_theme = theme_map.get(primary_category, "General market interest")

        # Secondary themes
        secondary_categories = sorted(
            [(cat, count) for cat, count in category_counts.items() if cat != primary_category],
            key=lambda x: x[1],
            reverse=True,
        )[:2]
        secondary_themes = [theme_map.get(cat, cat) for cat, _ in secondary_categories]

        # Consensus strength: ratio of claims agreeing with primary theme
        primary_count = category_counts.get(primary_category, 0)
        consensus_strength = primary_count / len(claims) if claims else 0.0

        return NarrativeConsensus(
            primary_theme=primary_theme,
            secondary_themes=secondary_themes,
            contradicting_views=[],
            consensus_strength=consensus_strength,
            total_comments_analyzed=len(comments),
        )
