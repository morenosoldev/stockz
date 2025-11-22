# Integration Tests for Research Module

This directory contains integration tests for the research module that make **real API calls** to OpenAI.

## Prerequisites

1. **OpenAI API Key**: Set the `LLM_OPENAI_API_KEY` environment variable:

   ```bash
   export LLM_OPENAI_API_KEY="sk-..."
   ```

2. **Configuration**: Ensure `config/config.yaml` has the LLM section configured:
   ```yaml
   llm:
     openai_api_key: ${LLM_OPENAI_API_KEY}
     model_claim_extractor: gpt-4o-mini
     model_fact_checker: gpt-4o
     max_retries: 3
     timeout_seconds: 30
   ```

## Running Integration Tests

### Run All Integration Tests

```bash
pytest tests/integration/research/ -v -s
```

The `-s` flag shows print statements so you can see the pipeline progress.

### Run Specific Test Classes

```bash
# Claim extraction tests
pytest tests/integration/research/test_research_integration.py::TestClaimExtractionIntegration -v -s

# Fact-checking tests
pytest tests/integration/research/test_research_integration.py::TestFactCheckingIntegration -v -s

# Company adapter tests
pytest tests/integration/research/test_research_integration.py::TestCompanyAdapterIntegration -v -s

# End-to-end pipeline test
pytest tests/integration/research/test_research_integration.py::TestEndToEndResearchPipeline -v -s
```

### Run Specific Tests

```bash
# Test full pipeline
pytest tests/integration/research/test_research_integration.py::TestEndToEndResearchPipeline::test_full_research_pipeline -v -s

# Test claim extraction
pytest tests/integration/research/test_research_integration.py::TestClaimExtractionIntegration::test_extract_claims_from_comments -v -s

# Test fact-checking
pytest tests/integration/research/test_research_integration.py::TestFactCheckingIntegration::test_fact_check_claims -v -s

# Test company data
pytest tests/integration/research/test_research_integration.py::TestCompanyAdapterIntegration::test_get_company_data_real_api -v -s
```

### Skip Integration Tests

When running the full test suite, you can skip integration tests to avoid API costs:

```bash
# Run all tests EXCEPT integration tests
pytest -m "not integration"

# Run only unit tests
pytest tests/unit/
```

## What Gets Tested

### 1. Claim Extraction (`TestClaimExtractionIntegration`)

- ✅ Extract claims from Reddit comments using GPT-4o-mini
- ✅ Deduplicate similar claims
- ✅ Analyze narrative consensus with LLM

**Example Output:**

```
✅ Extracted 8 claims from 5 comments
  - [financial_performance] NVDA crushed earnings with 50% revenue growth (confidence: 0.85)
  - [market_position] Nvidia is the clear AI leader (confidence: 0.75)
  - [competitive_threat] AMD is catching up fast (confidence: 0.60)
```

### 2. Fact-Checking (`TestFactCheckingIntegration`)

- ✅ Fact-check claims using GPT-4o with web research
- ✅ Rank claims by impact (comment_score × confidence)
- ✅ Verify sources and evidence

**Example Output:**

```
✅ Fact-checked 3 claims:
  ✓ VERIFIED (confidence: 0.80)
    Claim: NVDA crushed earnings with 50% revenue growth
    Evidence: Nvidia reported Q3 revenue growth of 94% year-over-year...
  ✗ DEBUNKED (confidence: 0.65)
    Claim: P/E ratio is over 60
    Evidence: Current P/E ratio is 54.3...
```

### 3. Company Data (`TestCompanyAdapterIntegration`)

- ✅ Gather company intelligence using chatbot research
- ✅ Validate caching (24-hour TTL)
- ✅ Check attribution metadata

**Example Output:**

```
✅ Fetched company data for AAPL:
  - Company: Apple Inc.
  - Revenue Growth: 8.2%
  - Earnings Surprise: 2.3%
  - Recent Events: 3
  - Analyst Ratings: {'buy': 25, 'hold': 10, 'sell': 2}
```

### 4. End-to-End Pipeline (`TestEndToEndResearchPipeline`)

Tests the complete research workflow:

1. Extract claims from comments (batched)
2. Deduplicate claims
3. Analyze narrative consensus
4. Fact-check top claims
5. Gather company data

**Example Output:**

```
🔬 Running full research pipeline for NVDA...

1️⃣ Extracting claims...
   Extracted 8 raw claims

2️⃣ Deduplicating claims...
   Deduplicated to 6 unique claims

3️⃣ Analyzing narrative...
   Primary theme: Strong financial performance and AI leadership
   Consensus strength: 0.75

4️⃣ Fact-checking top claims...
   Verified: 2, Debunked: 1

5️⃣ Gathering company data...
   Company: NVIDIA Corporation

✅ Full pipeline completed successfully!
```

## Cost Considerations

⚠️ **These tests make real API calls to OpenAI and will incur costs:**

- **Claim Extraction**: ~$0.02 per test (GPT-4o-mini)
- **Fact-Checking**: ~$0.10 per test (GPT-4o with web search)
- **Company Data**: ~$0.05 per test (GPT-4o)
- **Full Pipeline**: ~$0.15-$0.20 per test

**Estimated total cost for full integration test suite**: ~$0.50-$1.00

### Cost Optimization Tips

1. **Run selectively**: Only run integration tests when validating changes to research module
2. **Use test limits**: Tests are configured with smaller batch sizes and claim limits
3. **Cache usage**: Company data uses 24h cache, so repeated tests within 24h are cheaper
4. **Skip when unnecessary**: Use `pytest -m "not integration"` for regular development

## Debugging Integration Tests

### Enable Verbose Logging

```bash
# Set log level to DEBUG
export LOG_LEVEL=DEBUG

# Run tests with full output
pytest tests/integration/research/ -v -s --log-cli-level=DEBUG
```

### Inspect API Responses

The tests print detailed output when run with `-s`. You can see:

- Claims extracted
- Fact-check results with sources
- Company data retrieved
- Pipeline progress

### Check Cache

Integration tests use the same cache as production:

```bash
# View cached files
ls -la data/cache/

# Clear cache to force fresh API calls
rm -rf data/cache/*
```

### API Rate Limits

If you hit rate limits:

1. **Reduce concurrency**: Tests are sequential, but batching may hit limits
2. **Add delays**: Modify tests to add `time.sleep(1)` between API calls
3. **Use smaller batches**: Reduce `batch_size` and `max_claims_to_verify` parameters

## CI/CD Integration

For CI/CD pipelines, integration tests should be **optional** or run in a separate job:

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run unit tests
        run: pytest tests/unit/ -v

  integration-tests:
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3
      - name: Run integration tests
        env:
          LLM_OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: pytest tests/integration/research/ -v
```

This ensures:

- Unit tests run on every PR
- Integration tests only run on `main` branch pushes
- API key is stored as a GitHub secret

## Troubleshooting

### `LLM_OPENAI_API_KEY environment variable not set`

**Solution**: Set the environment variable before running tests:

```bash
export LLM_OPENAI_API_KEY="sk-..."
pytest tests/integration/research/ -v -s
```

### `OpenAI API error: Rate limit exceeded`

**Solution**: Wait a few minutes and try again, or reduce test concurrency.

### `Timeout waiting for API response`

**Solution**: Increase timeout in `config/config.yaml`:

```yaml
llm:
  timeout_seconds: 60 # Increase from 30
```

### `No claims extracted from comments`

**Cause**: LLM may not have identified factual claims in the sample comments.

**Solution**: This is expected behavior if comments are too vague. Check the test output to see if any claims were extracted.

## Test Maintenance

When adding new research features:

1. **Add unit tests first**: Mock API responses in `tests/unit/research/`
2. **Add integration test**: Validate with real API in `tests/integration/research/`
3. **Update this README**: Document what the new test validates
4. **Check costs**: Estimate API costs for the new test

## Related Documentation

- [Unit Tests README](../../unit/research/README.md) - Mock-based tests (no API costs)
- [AGENTS.md](../../../AGENTS.md) - Testing guidelines for AI agents
- [Research Module](../../../src/research/) - Implementation code
