"""Unit tests for claim extraction module."""

import json
from unittest.mock import Mock, patch

import pytest

from src.research.claim_extractor import (
    Claim,
    analyze_narrative,
    deduplicate_claims,
    extract_claims_batched,
    extract_claims_from_batch,
)


@pytest.fixture
def sample_comments():
    """Sample Reddit comments for testing."""
    return [
        {
            "id": "abc123",
            "body": "AAPL got FDA approval for their new medical device. Huge catalyst!",
            "score": 150,
        },
        {
            "id": "def456",
            "body": "Apple's revenue grew 25% YoY according to latest earnings.",
            "score": 200,
        },
        {
            "id": "ghi789",
            "body": "FDA approval coming Q1 2026 for AAPL medical device.",
            "score": 100,
        },
        {
            "id": "jkl012",
            "body": "This stock is going to the moon! 🚀",
            "score": 50,
        },
    ]


@pytest.fixture
def sample_claims():
    """Sample claims for testing."""
    return [
        Claim(
            text="FDA approval for medical device expected Q1 2026",
            category="regulatory",
            ticker="AAPL",
            confidence=0.9,
            source_comment_id="abc123",
            comment_score=150,
            comment_index=0,
        ),
        Claim(
            text="Revenue grew 25% year-over-year",
            category="financial",
            ticker="AAPL",
            confidence=0.95,
            source_comment_id="def456",
            comment_score=200,
            comment_index=1,
        ),
        Claim(
            text="FDA approval for medical device expected Q1 2026",
            category="regulatory",
            ticker="AAPL",
            confidence=0.85,
            source_comment_id="ghi789",
            comment_score=100,
            comment_index=2,
        ),
    ]


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response for claim extraction."""
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "claims": [
                                {
                                    "text": "FDA approval for medical device expected Q1 2026",
                                    "category": "regulatory",
                                    "confidence": 0.9,
                                    "comment_index": 0,
                                    "comment_score": 150,
                                },
                                {
                                    "text": "Revenue grew 25% year-over-year",
                                    "category": "financial",
                                    "confidence": 0.95,
                                    "comment_index": 1,
                                    "comment_score": 200,
                                },
                            ]
                        }
                    )
                }
            }
        ]
    }


class TestExtractClaimsFromBatch:
    """Tests for extract_claims_from_batch function."""

    @patch("src.research.claim_extractor.get_config")
    @patch("src.research.claim_extractor.OpenAI")
    def test_extract_claims_from_batch_success(
        self, mock_openai_class, mock_config, sample_comments, mock_openai_response
    ):
        """Test successful claim extraction from a batch."""
        # Setup config mock
        config_instance = Mock()
        config_instance.llm.openai_api_key = "test-key"
        config_instance.llm.model_claim_extractor = "gpt-4o-mini"
        mock_config.return_value = config_instance

        # Setup OpenAI mock
        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        # Create properly nested mock response
        # The content is already JSON-encoded in the fixture
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = mock_openai_response["choices"][0]["message"][
            "content"
        ]
        mock_client.chat.completions.create.return_value = mock_response

        # Execute
        claims = extract_claims_from_batch(sample_comments[:2], "AAPL", start_index=0)

        # Assert
        assert len(claims) == 2
        assert claims[0].text == "FDA approval for medical device expected Q1 2026"
        assert claims[0].category == "regulatory"
        assert claims[0].ticker == "AAPL"
        assert claims[0].confidence == 0.9
        assert claims[0].comment_score == 150

        assert claims[1].text == "Revenue grew 25% year-over-year"
        assert claims[1].category == "financial"

        # Verify OpenAI was called with correct parameters
        mock_client.chat.completions.create.assert_called_once()
        call_args = mock_client.chat.completions.create.call_args
        assert call_args.kwargs["model"] == "gpt-4o-mini"
        assert call_args.kwargs["temperature"] == 0.3
        assert call_args.kwargs["response_format"] == {"type": "json_object"}

    @patch("src.research.claim_extractor.OpenAI")
    @patch("src.research.claim_extractor.get_config")
    def test_extract_claims_from_batch_empty_response(
        self, mock_config, mock_openai_class, sample_comments
    ):
        """Test handling of empty response from LLM."""
        # Setup
        mock_config.return_value.llm.openai_api_key = "test-key"
        mock_config.return_value.llm.model_claim_extractor = "gpt-4o-mini"

        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value = Mock(
            choices=[Mock(message=Mock(content=json.dumps({"claims": []})))]
        )

        # Execute
        claims = extract_claims_from_batch(sample_comments, "AAPL")

        # Assert
        assert len(claims) == 0

    @patch("src.research.claim_extractor.OpenAI")
    @patch("src.research.claim_extractor.get_config")
    def test_extract_claims_from_batch_api_error(
        self, mock_config, mock_openai_class, sample_comments
    ):
        """Test handling of API errors."""
        # Setup
        mock_config.return_value.llm.openai_api_key = "test-key"
        mock_config.return_value.llm.model_claim_extractor = "gpt-4o-mini"

        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API Error")

        # Execute
        claims = extract_claims_from_batch(sample_comments, "AAPL")

        # Assert - should return empty list on error
        assert len(claims) == 0


class TestExtractClaimsBatched:
    """Tests for extract_claims_batched function."""

    @patch("src.research.claim_extractor.extract_claims_from_batch")
    def test_extract_claims_batched_single_batch(self, mock_extract, sample_comments):
        """Test extraction with comments that fit in one batch."""
        # Setup
        mock_extract.return_value = [
            Claim(
                text="Test claim",
                category="financial",
                ticker="AAPL",
                confidence=0.9,
                source_comment_id="abc",
                comment_score=100,
                comment_index=0,
            )
        ]

        # Execute - 5 comments with batch_size=10 = 1 batch
        claims = extract_claims_batched(sample_comments[:5], "AAPL", batch_size=10)

        # Assert
        assert mock_extract.call_count == 1
        assert len(claims) == 1

    @patch("src.research.claim_extractor.extract_claims_from_batch")
    def test_extract_claims_batched_multiple_batches(self, mock_extract, sample_comments):
        """Test extraction with comments requiring multiple batches."""
        # Setup - return different claims for each batch call
        mock_extract.side_effect = [
            [
                Claim(
                    text="Batch 1 claim",
                    category="financial",
                    ticker="AAPL",
                    confidence=0.9,
                    source_comment_id="abc1",
                    comment_score=100,
                    comment_index=0,
                )
            ],
            [
                Claim(
                    text="Batch 2 claim",
                    category="market_position",
                    ticker="AAPL",
                    confidence=0.8,
                    source_comment_id="abc2",
                    comment_score=80,
                    comment_index=10,
                )
            ],
        ]

        # Create 20 comments to trigger 2 batches (batch_size=10)
        many_comments = sample_comments * 5  # 20 comments

        # Execute
        claims = extract_claims_batched(many_comments, "AAPL", batch_size=10)

        # Assert - should call extract twice (2 batches)
        assert mock_extract.call_count == 2
        assert len(claims) == 2  # 1 claim per batch
        assert claims[0].text == "Batch 1 claim"
        assert claims[1].text == "Batch 2 claim"


class TestDeduplicateClaims:
    """Tests for deduplicate_claims function."""

    def test_deduplicate_identical_claims(self, sample_claims):
        """Test deduplication of identical claims."""
        # Execute
        deduplicated = deduplicate_claims(sample_claims)

        # Assert - first and third claims are duplicates
        assert len(deduplicated) == 2
        assert deduplicated[0].text == "FDA approval for medical device expected Q1 2026"
        assert deduplicated[1].text == "Revenue grew 25% year-over-year"

    def test_deduplicate_boosts_confidence(self):
        """Test that duplicate claims boost confidence."""
        # Setup - 4 identical claims
        claims = [
            Claim(
                text="FDA approval expected",
                category="regulatory",
                ticker="AAPL",
                confidence=0.8,
                source_comment_id=f"id{i}",
                comment_score=100,
                comment_index=i,
            )
            for i in range(4)
        ]

        # Execute
        deduplicated = deduplicate_claims(claims)

        # Assert - 4 mentions should boost confidence
        assert len(deduplicated) == 1
        assert deduplicated[0].confidence > 0.8  # Boosted from 0.8

    def test_deduplicate_empty_list(self):
        """Test deduplication with empty list."""
        # Execute
        deduplicated = deduplicate_claims([])

        # Assert
        assert len(deduplicated) == 0

    def test_deduplicate_preserves_highest_score(self):
        """Test that deduplication keeps claim with highest comment score."""
        # Setup
        claims = [
            Claim(
                text="FDA approval",
                category="regulatory",
                ticker="AAPL",
                confidence=0.8,
                source_comment_id="low",
                comment_score=50,
                comment_index=0,
            ),
            Claim(
                text="FDA approval",
                category="regulatory",
                ticker="AAPL",
                confidence=0.9,
                source_comment_id="high",
                comment_score=200,
                comment_index=1,
            ),
        ]

        # Execute
        deduplicated = deduplicate_claims(claims)

        # Assert - should keep the one with higher score
        assert len(deduplicated) == 1
        assert deduplicated[0].comment_score == 200


class TestAnalyzeNarrative:
    """Tests for analyze_narrative function."""

    @patch("src.research.claim_extractor.OpenAI")
    @patch("src.research.claim_extractor.get_config")
    def test_analyze_narrative_success(
        self, mock_config, mock_openai_class, sample_claims, sample_comments
    ):
        """Test successful narrative analysis."""
        # Setup
        mock_config.return_value.llm.openai_api_key = "test-key"
        mock_config.return_value.llm.model_fact_checker = "gpt-4o"

        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value = Mock(
            choices=[
                Mock(
                    message=Mock(
                        content=json.dumps(
                            {
                                "primary_theme": "FDA approval catalyst for medical device",
                                "secondary_themes": ["Strong revenue growth"],
                                "contradicting_views": [],
                                "consensus_strength": 0.9,
                            }
                        )
                    )
                )
            ]
        )

        # Execute
        narrative = analyze_narrative(sample_claims, sample_comments, "AAPL")

        # Assert
        assert narrative.primary_theme == "FDA approval catalyst for medical device"
        assert narrative.secondary_themes == ["Strong revenue growth"]
        assert narrative.consensus_strength == 0.9
        assert narrative.total_comments_analyzed == len(sample_comments)

    @patch("src.research.claim_extractor.OpenAI")
    @patch("src.research.claim_extractor.get_config")
    def test_analyze_narrative_fallback_on_error(
        self, mock_config, mock_openai_class, sample_claims, sample_comments
    ):
        """Test fallback to category-based analysis on API error."""
        # Setup
        mock_config.return_value.llm.openai_api_key = "test-key"
        mock_config.return_value.llm.model_fact_checker = "gpt-4o"

        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API Error")

        # Execute
        narrative = analyze_narrative(sample_claims, sample_comments, "AAPL")

        # Assert - should fall back to category-based analysis
        assert "regulatory" in narrative.primary_theme.lower()
        assert narrative.consensus_strength > 0  # Should calculate from categories

    def test_analyze_narrative_empty_claims(self, sample_comments):
        """Test narrative analysis with no claims."""
        # Execute
        narrative = analyze_narrative([], sample_comments, "AAPL")

        # Assert
        assert "no clear narrative" in narrative.primary_theme.lower()
        assert narrative.consensus_strength == 0.0
        assert len(narrative.secondary_themes) == 0
