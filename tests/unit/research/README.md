# Unit Tests for Research Module

This directory contains unit tests for the research module that use **mocked API responses** to avoid real OpenAI API calls.

## Overview

Unit tests validate the research module's logic without incurring API costs. All OpenAI API calls are mocked using `unittest.mock.patch`.

## Running Unit Tests

### Run All Research Unit Tests

```bash
pytest tests/unit/research/ -v
```

### Run Specific Test Files

```bash
# Claim extraction tests
pytest tests/unit/research/test_claim_extractor.py -v

# Fact-checking tests
pytest tests/unit/research/test_fact_checker.py -v

# Company adapter tests
pytest tests/unit/research/test_company_adapter.py -v
```

### Run Specific Test Classes

```bash
# Claim extraction
pytest tests/unit/research/test_claim_extractor.py::TestExtractClaimsFromBatch -v
pytest tests/unit/research/test_claim_extractor.py::TestDeduplicateClaims -v
pytest tests/unit/research/test_claim_extractor.py::TestAnalyzeNarrative -v

# Fact-checking
pytest tests/unit/research/test_fact_checker.py::TestFactCheckClaims -v
pytest tests/unit/research/test_fact_checker.py::TestResearchClaimWithChatbot -v

# Company adapter
pytest tests/unit/research/test_company_adapter.py::TestCompanyAdapter -v
pytest tests/unit/research/test_company_adapter.py::TestCompanyData -v
```

### Run with Coverage

```bash
# Coverage report for research module
pytest tests/unit/research/ --cov=src.research --cov-report=term-missing

# HTML coverage report
pytest tests/unit/research/ --cov=src.research --cov-report=html
# View: htmlcov/index.html
```

## Test Files

### `test_claim_extractor.py` (370 lines, 12 tests)

Tests for claim extraction from Reddit comments.

**Test Classes:**

1. **`TestExtractClaimsFromBatch`** (3 tests)

   - ✅ `test_extract_claims_from_batch_success` - Normal extraction with valid response
   - ✅ `test_extract_claims_from_batch_empty_response` - Handles empty LLM response
   - ✅ `test_extract_claims_from_batch_api_error` - Handles OpenAI API errors

2. **`TestExtractClaimsBatched`** (2 tests)

   - ✅ `test_extract_claims_batched_single_batch` - Single batch processing
   - ✅ `test_extract_claims_batched_multiple_batches` - Parallel batch processing

3. **`TestDeduplicateClaims`** (4 tests)

   - ✅ `test_deduplicate_identical_claims` - Merges exact duplicates
   - ✅ `test_deduplicate_boosts_confidence` - Confidence boost for 3+ mentions
   - ✅ `test_deduplicate_empty_list` - Handles empty input
   - ✅ `test_deduplicate_preserves_highest_score` - Keeps highest comment score

4. **`TestAnalyzeNarrative`** (3 tests)
   - ✅ `test_analyze_narrative_success` - LLM-based narrative analysis
   - ✅ `test_analyze_narrative_fallback_on_error` - Fallback to category-based
   - ✅ `test_analyze_narrative_empty_claims` - Handles no claims

**Key Validations:**

- OpenAI API called with correct parameters (model, temperature, JSON format)
- Proper error handling for API failures
- Deduplication logic (exact text match, confidence boost)
- Narrative consensus detection

### `test_fact_checker.py` (280 lines, 11 tests)

Tests for fact-checking claims with chatbot research.

**Test Classes:**

1. **`TestRankClaimsByImpact`** (2 tests)

   - ✅ `test_rank_claims_by_impact` - Sorts by comment_score × confidence
   - ✅ `test_rank_empty_list` - Handles empty input

2. **`TestResearchClaimWithChatbot`** (4 tests)

   - ✅ `test_research_claim_verified` - Verified claim with sources
   - ✅ `test_research_claim_debunked` - Debunked claim
   - ✅ `test_research_claim_api_error` - API error handling
   - ✅ `test_research_claim_invalid_json` - Invalid JSON response

3. **`TestFactCheckClaims`** (5 tests)
   - ✅ `test_fact_check_claims_all_verified` - All claims verified
   - ✅ `test_fact_check_claims_respects_max_claims` - Respects max_claims limit
   - ✅ `test_fact_check_claims_handles_errors` - Continues on individual errors
   - ✅ `test_fact_check_claims_empty_list` - Handles empty input
   - ✅ `test_fact_check_claims_ranks_by_impact` - Fact-checks highest impact first

**Key Validations:**

- GPT-4o called with temperature=0.2, timeout=15.0
- Web search enabled for fact-checking
- Impact ranking: comment_score × confidence (descending)
- Error resilience (continues on failures)

### `test_company_adapter.py` (330 lines, 11 tests)

Tests for company intelligence gathering.

**Test Classes:**

1. **`TestCompanyAdapter`** (9 tests)

   - ✅ `test_get_company_data_success` - Successful data retrieval
   - ✅ `test_get_company_data_uses_cache` - Cache hit (no API call)
   - ✅ `test_get_company_data_api_error` - Fallback on API error
   - ✅ `test_get_company_data_invalid_json` - Invalid JSON response
   - ✅ `test_fetch_method` - DataAdapterProtocol compatibility
   - ✅ `test_get_attribution` - Attribution metadata
   - ✅ `test_get_attribution_no_fetch_raises_error` - Error if no fetch
   - ✅ `test_ticker_normalization` - Lowercase to uppercase conversion

2. **`TestCompanyData`** (2 tests)
   - ✅ `test_company_data_creation` - Required fields only
   - ✅ `test_company_data_with_all_fields` - All fields populated

**Key Validations:**

- GPT-4o called with temperature=0.2, timeout=30.0
- 24-hour caching with FileCache
- Attribution source: CHATBOT_RESEARCH
- Ticker normalization (lowercase → uppercase)
- Fallback data on errors (ticker, company_name, fetched_at)

## Mocking Strategy

All tests use `unittest.mock.patch` to mock OpenAI API calls:

```python
from unittest.mock import MagicMock, Mock, patch

@patch("src.research.claim_extractor.OpenAI")
def test_extract_claims_from_batch_success(mock_openai):
    # Mock OpenAI client
    mock_client = MagicMock()
    mock_openai.return_value = mock_client

    # Mock API response
    mock_response = Mock()
    mock_response.choices = [...]
    mock_client.chat.completions.create.return_value = mock_response

    # Test
    result = extract_claims_from_batch(...)

    # Verify
    mock_client.chat.completions.create.assert_called_once_with(
        model="gpt-4o-mini",
        temperature=0.3,
        response_format={"type": "json_object"},
        messages=[...]
    )
```

### Benefits of Mocking

1. **No API costs**: Tests run without real OpenAI API calls
2. **Fast execution**: No network latency
3. **Deterministic**: Same inputs always produce same outputs
4. **Isolated**: Tests don't depend on external services
5. **Parameterizable**: Can test edge cases (errors, timeouts, invalid responses)

## Fixtures

Reusable test data defined in fixtures:

### Claim Extractor Fixtures

```python
@pytest.fixture
def sample_comments():
    """Sample Reddit comments for testing."""
    return [
        {"comment_id": "c1", "comment": "Great earnings!", "score": 100},
        {"comment_id": "c2", "comment": "Stock is overvalued", "score": 50},
    ]

@pytest.fixture
def sample_claims():
    """Sample claims for testing deduplication and ranking."""
    return [
        Claim(text="Revenue up 20%", category="financial_performance", ...),
        Claim(text="New product launch", category="product_launch", ...),
    ]
```

### Fact Checker Fixtures

```python
@pytest.fixture
def mock_fact_check_response():
    """Mock OpenAI response for fact-checking."""
    return {
        "verified": True,
        "confidence": 0.85,
        "sources": ["https://example.com/news"],
        "evidence": "Company reported...",
    }
```

### Company Adapter Fixtures

```python
@pytest.fixture
def mock_company_response():
    """Mock OpenAI response for company data."""
    return {
        "company_name": "Apple Inc.",
        "revenue_growth": 8.2,
        "earnings_surprise": 2.3,
        ...
    }
```

## Coverage Targets

Current coverage for research module:

- ✅ `claim_extractor.py`: ~95% (all major functions covered)
- ✅ `fact_checker.py`: ~90% (all major functions covered)
- ✅ `company.py`: ~92% (all methods covered)

**Uncovered areas** (by design):

- Exception handling for rare edge cases
- Logging statements
- Type checking branches

## Best Practices

### 1. Test Isolation

Each test should be independent:

```python
# ✅ Good - uses fresh mock for each test
@patch("src.research.claim_extractor.OpenAI")
def test_something(mock_openai):
    mock_client = MagicMock()
    mock_openai.return_value = mock_client
    # Test...

# ❌ Bad - shares state between tests
mock_client = MagicMock()  # Global state
def test_something():
    # Test...
```

### 2. Verify API Parameters

Always verify that OpenAI is called with correct parameters:

```python
mock_client.chat.completions.create.assert_called_once_with(
    model="gpt-4o",  # Correct model
    temperature=0.2,  # Correct temperature
    timeout=15.0,  # Correct timeout
    messages=[...],  # Correct prompt
)
```

### 3. Test Error Paths

Don't just test happy paths:

```python
# Test API errors
mock_client.chat.completions.create.side_effect = Exception("API Error")
result = fact_check_claims(...)
assert result == []  # Should handle gracefully

# Test invalid responses
mock_response.choices[0].message.content = "Invalid JSON"
result = extract_claims(...)
assert result == []  # Should handle gracefully
```

### 4. Use Descriptive Names

Test names should describe what they validate:

```python
# ✅ Good
def test_deduplicate_boosts_confidence_for_three_or_more_mentions():
    ...

# ❌ Bad
def test_deduplicate():
    ...
```

## Comparison with Integration Tests

| Aspect            | Unit Tests                        | Integration Tests                  |
| ----------------- | --------------------------------- | ---------------------------------- |
| **API Calls**     | Mocked (no real calls)            | Real OpenAI API calls              |
| **Cost**          | Free                              | ~$0.50-$1.00 per run               |
| **Speed**         | Fast (<1s per test)               | Slow (10-30s per test)             |
| **Deterministic** | Yes (same inputs = same outputs)  | No (LLM responses vary)            |
| **Coverage**      | Logic, error handling, edge cases | Real API integration, end-to-end   |
| **When to Run**   | Every commit, pre-commit hook     | Before releases, manual validation |
| **Purpose**       | Validate logic correctness        | Validate real-world behavior       |

**Recommendation**:

- Run unit tests frequently (every commit, pre-commit hook)
- Run integration tests sparingly (before releases, major changes)

## Adding New Tests

When adding new research functionality:

1. **Write unit test first** (TDD):

   ```bash
   # Create test file
   touch tests/unit/research/test_new_feature.py

   # Write failing test
   def test_new_feature():
       result = new_feature()
       assert result == expected
   ```

2. **Mock OpenAI API**:

   ```python
   @patch("src.research.new_feature.OpenAI")
   def test_new_feature(mock_openai):
       # Mock setup
       mock_client = MagicMock()
       mock_openai.return_value = mock_client

       # Mock response
       mock_response = Mock()
       mock_response.choices = [...]
       mock_client.chat.completions.create.return_value = mock_response

       # Test
       result = new_feature()

       # Verify
       assert result == expected
   ```

3. **Run test to ensure it fails**:

   ```bash
   pytest tests/unit/research/test_new_feature.py -v
   ```

4. **Implement feature** until test passes

5. **Add integration test** (optional, for end-to-end validation)

## Troubleshooting

### `ModuleNotFoundError: No module named 'src'`

**Solution**: Run pytest from project root:

```bash
cd /workspaces/stockz
pytest tests/unit/research/ -v
```

### `AttributeError: Mock object has no attribute 'choices'`

**Cause**: Incomplete mock setup.

**Solution**: Ensure mock response has all required attributes:

```python
mock_response = Mock()
mock_response.choices = [Mock()]
mock_response.choices[0].message = Mock()
mock_response.choices[0].message.content = json.dumps({...})
```

### `AssertionError: Expected call not found`

**Cause**: API not called with expected parameters.

**Solution**: Use `mock_client.chat.completions.create.call_args` to inspect actual call:

```python
print(mock_client.chat.completions.create.call_args)
```

## Related Documentation

- [Integration Tests README](../../integration/research/README.md) - Real API tests
- [AGENTS.md](../../../AGENTS.md) - Testing guidelines for AI agents
- [Research Module](../../../src/research/) - Implementation code
- [pytest Documentation](https://docs.pytest.org/) - pytest framework
