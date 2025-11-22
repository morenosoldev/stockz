"""Post classifier for categorizing Reddit posts by type and quality.

This module uses LLM to classify posts into categories (DD, YOLO, Loss Porn, etc.)
and assigns quality weights to filter noise from signals.
"""

from enum import Enum

from openai import OpenAI
from pydantic import BaseModel, Field

from src.ops.logging import get_logger

logger = get_logger(__name__)


class PostType(str, Enum):
    """Reddit post type categories."""

    DD_ANALYSIS = "DD_ANALYSIS"  # In-depth research, fundamental analysis
    NEWS = "NEWS"  # Breaking news, earnings reports, announcements
    YOLO_PLAY = "YOLO_PLAY"  # High-risk gambling bets
    LOSS_PORN = "LOSS_PORN"  # Posts about losses (negative sentiment)
    GAIN_PORN = "GAIN_PORN"  # Posts celebrating gains (positive sentiment)
    MEME = "MEME"  # Jokes, memes, shitposts
    DISCUSSION = "DISCUSSION"  # General discussion, questions
    OTHER = "OTHER"  # Uncategorized


class PostClassification(BaseModel):
    """Structured post classification output."""

    post_type: PostType = Field(description="Classified post type")
    confidence: float = Field(description="Confidence in classification 0.0-1.0", ge=0.0, le=1.0)
    reasoning: str = Field(description="Brief explanation of classification")
    quality_indicators: list[str] = Field(
        default_factory=list,
        description="Quality signals found (e.g., 'has data', 'cites sources', 'detailed analysis')",
    )
    noise_indicators: list[str] = Field(
        default_factory=list,
        description="Noise signals found (e.g., 'no evidence', 'pure speculation', 'meme language')",
    )


class PostClassifier:
    """Classify Reddit posts by type and quality using LLM.

    This classifier helps filter high-quality DD from noise (memes, loss porn, YOLOs).
    Results are used to apply quality weights during sentiment aggregation.

    Example:
        >>> classifier = PostClassifier()
        >>> classification = classifier.classify_post(
        ...     title="NVDA Q4 earnings analysis - PE ratio vs growth",
        ...     content="Detailed financial analysis...",
        ...     flair="DD"
        ... )
        >>> classification.post_type
        <PostType.DD_ANALYSIS: 'DD_ANALYSIS'>
        >>> get_quality_weight(classification.post_type)
        1.5
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.0,
    ):
        """Initialize post classifier.

        Args:
            model: OpenAI model name (default: gpt-4o-mini)
            temperature: LLM temperature 0.0-1.0 (0=deterministic)
        """
        self.model = model
        self.temperature = temperature
        self.client = OpenAI()  # Uses OPENAI_API_KEY env var

        logger.info(
            "PostClassifier initialized",
            extra={"model": self.model, "temperature": self.temperature},
        )

    def classify_post(
        self,
        title: str,
        content: str = "",
        flair: str = "",
    ) -> PostClassification:
        """Classify a Reddit post by type and quality.

        Args:
            title: Post title
            content: Post body/selftext
            flair: Post flair (e.g., "DD", "YOLO", "Loss")

        Returns:
            PostClassification with type, confidence, and quality indicators

        Raises:
            Exception: If LLM call fails
        """
        try:
            prompt = f"""Classify this Reddit post about stocks/trading.

Title: {title}

Flair: {flair or "None"}

Content: {content or "No body text"}

Classify the post type:
- DD_ANALYSIS: In-depth research, fundamental analysis, detailed DD
- NEWS: Breaking news, earnings reports, company announcements
- YOLO_PLAY: High-risk gambling bets, "calls/puts", no research
- LOSS_PORN: Posts describing losses, "lost $X on Y", negative outcomes
- GAIN_PORN: Posts celebrating gains, "made $X on Y", screenshots of profits
- MEME: Jokes, memes, shitposts, emojis, "to the moon"
- DISCUSSION: General discussion, questions, opinions
- OTHER: Uncategorized

Also identify:
- Quality indicators: Evidence of research, data, sources, detailed analysis
- Noise indicators: Pure speculation, no evidence, meme language, gambling language

Return your classification with confidence (0-1) and reasoning."""

            completion = self.client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a Reddit post classifier. Distinguish quality research from noise (memes, gambling, loss porn).",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format=PostClassification,
                temperature=self.temperature,
            )

            result: PostClassification | None = completion.choices[0].message.parsed

            if result is None:
                raise ValueError("LLM failed to return structured output")

            logger.debug(
                "Post classified",
                extra={
                    "title": title[:50],
                    "post_type": result.post_type,
                    "confidence": result.confidence,
                },
            )

            return result

        except Exception as e:
            logger.error(
                "Post classification failed",
                extra={"title": title[:50], "error": str(e)},
                exc_info=True,
            )
            # Return default classification on error
            return PostClassification(
                post_type=PostType.OTHER,
                confidence=0.0,
                reasoning=f"Classification failed: {e}",
                quality_indicators=[],
                noise_indicators=["classification_error"],
            )


def get_quality_weight(post_type: PostType) -> float:
    """Get quality weight multiplier for a post type.

    Higher-quality content (DD, News) gets boosted in aggregation.
    Noise (Memes, Loss Porn, YOLOs) gets penalized.

    Args:
        post_type: Classified post type

    Returns:
        Quality weight multiplier (0.3 to 1.5)

    Examples:
        >>> get_quality_weight(PostType.DD_ANALYSIS)
        1.5
        >>> get_quality_weight(PostType.MEME)
        0.3
        >>> get_quality_weight(PostType.LOSS_PORN)
        0.0
    """
    weights = {
        PostType.DD_ANALYSIS: 1.5,  # Boost quality research
        PostType.NEWS: 1.3,  # Boost news/announcements
        PostType.GAIN_PORN: 1.0,  # Neutral (real sentiment, but not research)
        PostType.DISCUSSION: 0.8,  # Slight penalty (often uninformed opinions)
        PostType.YOLO_PLAY: 0.5,  # Major penalty (gambling, not analysis)
        PostType.MEME: 0.3,  # Major penalty (noise)
        PostType.LOSS_PORN: 0.0,  # Filter out completely (negative sentiment)
        PostType.OTHER: 0.7,  # Slight penalty (uncertain quality)
    }
    return weights.get(post_type, 0.7)
