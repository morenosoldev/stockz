"""Unit tests for fact checker module."""

import json
from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from src.research.claim_extractor import Claim
from src.research.fact_checker import (
    FactCheckResult,
    fact_check_claims,
    rank_claims_by_impact,
    research_claim_with_chatbot,
)


@pytest.fixture
def sample_claims():
    """Sample claims for testing."""
    return [
        Claim(
            text="FDA approval for drug XYZ expected Q1 2026",
            category="regulatory",
            ticker="AAPL",
            confidence=0.9,
            source_comment_id="abc123",
            comment_score=200,
            comment_index=0,
        ),
        Claim(
            text="Revenue grew 25% year-over-year",
            category="financial",
            ticker="AAPL",
            confidence=0.95,
            source_comment_id="def456",
            comment_score=150,
            comment_index=1,
        ),
        Claim(
            text="New CEO appointed last week",
            category="management",
            ticker="AAPL",
            confidence=0.8,
            source_comment_id="ghi789",
            comment_score=50,
            comment_index=2,
        ),
    ]


@pytest.fixture
def mock_fact_check_response():
    """Mock OpenAI response for fact-checking."""
    return {
        "verified": True,
        "confidence": 0.9,
        "sources": [
            "https://www.sec.gov/filing/...",
            "https://finance.yahoo.com/...",
        ],
        "evidence": "SEC filing shows FDA approval timeline for Q1 2026.",
        "search_queries_used": ["AAPL FDA approval 2026", "drug XYZ approval status"],
    }


class TestRankClaimsByImpact:
    """Tests for rank_claims_by_impact function."""

    def test_rank_claims_by_impact(self, sample_claims):
        """Test that claims are ranked by comment_score × confidence."""
        # Execute
        ranked = rank_claims_by_impact(sample_claims)

        # Assert - First claim has highest impact (200 * 0.9 = 180)
        assert ranked[0].text == "FDA approval for drug XYZ expected Q1 2026"
        assert ranked[0].comment_score == 200

        # Second claim (150 * 0.95 = 142.5)
        assert ranked[1].text == "Revenue grew 25% year-over-year"

        # Third claim (50 * 0.8 = 40)
        assert ranked[2].text == "New CEO appointed last week"

    def test_rank_empty_list(self):
        """Test ranking empty list."""
        # Execute
        ranked = rank_claims_by_impact([])

        # Assert
        assert len(ranked) == 0


class TestResearchClaimWithChatbot:
    """Tests for research_claim_with_chatbot function."""

    @patch("src.research.fact_checker.OpenAI")
    @patch("src.research.fact_checker.get_config")
    def test_research_claim_verified(
        self, mock_config, mock_openai_class, sample_claims, mock_fact_check_response
    ):
        """Test successful claim verification."""
        # Setup
        mock_config.return_value.llm.openai_api_key = "test-key"

        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value = Mock(
            choices=[Mock(message=Mock(content=json.dumps(mock_fact_check_response)))]
        )

        # Execute
        result = research_claim_with_chatbot(sample_claims[0])

        # Assert
        assert result.verified is True
        assert result.confidence == 0.9
        assert len(result.sources) == 2
        assert "SEC filing" in result.evidence
        assert len(result.search_queries_used) == 2

        # Verify API call
        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["temperature"] == 0.2
        assert call_kwargs["response_format"] == {"type": "json_object"}
        assert call_kwargs["timeout"] == 15.0

    @patch("src.research.fact_checker.OpenAI")
    @patch("src.research.fact_checker.get_config")
    def test_research_claim_debunked(self, mock_config, mock_openai_class, sample_claims):
        """Test claim debunking."""
        # Setup
        mock_config.return_value.llm.openai_api_key = "test-key"

        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value = Mock(
            choices=[
                Mock(
                    message=Mock(
                        content=json.dumps(
                            {
                                "verified": False,
                                "confidence": 0.95,
                                "sources": ["https://reuters.com/..."],
                                "evidence": "No evidence of FDA approval timeline. Company has not filed for approval.",
                                "search_queries_used": ["AAPL FDA approval"],
                            }
                        )
                    )
                )
            ]
        )

        # Execute
        result = research_claim_with_chatbot(sample_claims[0])

        # Assert
        assert result.verified is False
        assert result.confidence == 0.95
        assert "No evidence" in result.evidence

    @patch("src.research.fact_checker.OpenAI")
    @patch("src.research.fact_checker.get_config")
    def test_research_claim_api_error(self, mock_config, mock_openai_class, sample_claims):
        """Test handling of API errors."""
        # Setup
        mock_config.return_value.llm.openai_api_key = "test-key"

        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API timeout")

        # Execute - should raise exception
        with pytest.raises(Exception, match="API timeout"):
            research_claim_with_chatbot(sample_claims[0])

    @patch("src.research.fact_checker.OpenAI")
    @patch("src.research.fact_checker.get_config")
    def test_research_claim_invalid_json(self, mock_config, mock_openai_class, sample_claims):
        """Test handling of invalid JSON response."""
        # Setup
        mock_config.return_value.llm.openai_api_key = "test-key"

        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        # Create properly nested mock response with invalid JSON
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "invalid json {}"
        mock_client.chat.completions.create.return_value = mock_response

        # Execute - should raise ValueError for invalid JSON
        with pytest.raises(ValueError, match="Invalid JSON response"):
            research_claim_with_chatbot(sample_claims[0])


class TestFactCheckClaims:
    """Tests for fact_check_claims function."""

    @patch("src.research.fact_checker.research_claim_with_chatbot")
    def test_fact_check_claims_all_verified(self, mock_research, sample_claims):
        """Test fact-checking with all claims verified."""
        # Setup
        mock_research.return_value = FactCheckResult(
            claim=sample_claims[0],
            verified=True,
            confidence=0.9,
            sources=["https://example.com"],
            evidence="Verified",
            checked_at=datetime.now(),
            search_queries_used=["test query"],
        )

        # Execute
        results = fact_check_claims(sample_claims, max_claims=3)

        # Assert
        assert len(results) == 3
        assert all(r.verified for r in results)
        assert mock_research.call_count == 3

    @patch("src.research.fact_checker.research_claim_with_chatbot")
    def test_fact_check_claims_respects_max_claims(self, mock_research, sample_claims):
        """Test that max_claims parameter is respected."""
        # Setup
        mock_research.return_value = FactCheckResult(
            claim=sample_claims[0],
            verified=True,
            confidence=0.9,
            sources=[],
            evidence="",
            checked_at=datetime.now(),
            search_queries_used=[],
        )

        # Execute - only check top 2 claims
        results = fact_check_claims(sample_claims, max_claims=2)

        # Assert
        assert len(results) == 2
        assert mock_research.call_count == 2

    @patch("src.research.fact_checker.research_claim_with_chatbot")
    def test_fact_check_claims_handles_errors(self, mock_research, sample_claims):
        """Test that errors in individual checks don't stop the process."""

        # Setup - first call succeeds, second fails, third succeeds
        def side_effect(claim, timeout_seconds=15.0):
            if claim == sample_claims[1]:
                raise Exception("API error")
            return FactCheckResult(
                claim=claim,
                verified=True,
                confidence=0.9,
                sources=[],
                evidence="",
                checked_at=datetime.now(),
                search_queries_used=[],
            )

        mock_research.side_effect = side_effect

        # Execute
        results = fact_check_claims(sample_claims, max_claims=3)

        # Assert - should create fallback results for failed claims
        assert len(results) == 3  # All claims get results (success or fallback)
        assert mock_research.call_count == 3  # All 3 attempted

        # Check that failed claim has fallback result (verified=False, confidence=0.0)
        failed_result = next(r for r in results if r.claim == sample_claims[1])
        assert failed_result.verified is False
        assert failed_result.confidence == 0.0

    def test_fact_check_claims_empty_list(self):
        """Test fact-checking with empty claim list."""
        # Execute
        results = fact_check_claims([])

        # Assert
        assert len(results) == 0

    @patch("src.research.fact_checker.rank_claims_by_impact")
    @patch("src.research.fact_checker.research_claim_with_chatbot")
    def test_fact_check_claims_ranks_by_impact(self, mock_research, mock_rank, sample_claims):
        """Test that claims are ranked by impact before checking."""
        # Setup
        mock_rank.return_value = list(reversed(sample_claims))  # Reverse order
        mock_research.return_value = FactCheckResult(
            claim=sample_claims[0],
            verified=True,
            confidence=0.9,
            sources=[],
            evidence="",
            checked_at=datetime.now(),
            search_queries_used=[],
        )

        # Execute
        fact_check_claims(sample_claims, max_claims=2)

        # Assert - rank_claims_by_impact was called
        mock_rank.assert_called_once_with(sample_claims)
