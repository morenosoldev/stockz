# Task 6.5: AI-Powered Ticker Validation & Global Company Detection

**Status**: 🔴 **NOT STARTED**  
**Priority**: P0 (Critical - affects data quality & global coverage)  
**Estimated Effort**: 6 hours  
**Assignee**: AI Agent  
**Created**: 2025-11-01  
**Dependencies**: None (can be done now)

---

## 📋 Description

Currently, the Reddit ticker extraction has **two critical issues**:

1. **Too Permissive**: Captures invalid symbols like "YOY" (Year-Over-Year), "API", "GDP" - common acronyms that aren't stocks
2. **Missing Company Names**: Fails to detect company names like "Apple", "Gubra" (Danish biotech), "Nintendo" that aren't explicitly marked with $ symbols

**The Challenge**: Manual ticker mappings can't scale to 70,000+ global stocks. We need **AI/NLP** to:

- Detect if "Gubra" is a company (vs a random word)
- Resolve "Gubra" → "GUBRA.CO" (Copenhagen exchange)
- Work for ANY publicly traded company worldwide

**Problem Examples**:

- ❌ Reddit post: "YOY growth" → Extracted as "$YOY" → Full analysis on non-existent ticker
- ❌ Reddit post: "Apple crushed earnings" → No ticker extracted → **Missed opportunity!**
- ❌ Reddit post: "Gubra trial results" → No ticker extracted → **Missed international stock!**

This task implements an **AI-powered** ticker validation + company detection system using:

**Multi-Stage AI Pipeline:**

1. **NER (Named Entity Recognition)**: spaCy detects potential company names in text
2. **LLM Validation**: GPT-4o-mini validates if entity is publicly traded + resolves to ticker
3. **API Validation**: yfinance confirms ticker exists
4. **Format Filtering**: Blacklist + regex filter invalid symbols

**Global Coverage**: Works for US, European, Asian, and other international markets

---

## 🎯 Acceptance Criteria

### Phase 1: Enhanced Common Words Blacklist

- [ ] **Expand `common_words` set in `RedditAdapter._extract_tickers()`**:

  ```python
  TICKER_BLACKLIST = {
      # Existing
      "A", "I", "THE", "WSB", "DD", "YOLO", "CEO", "CFO",
      "IPO", "ETF", "FD", "TA", "IV",

      # Financial/Economic Terms
      "YOY", "QOQ", "MOM", "GDP", "CPI", "API", "EPS", "PE",
      "EBITDA", "ROI", "ROE", "ATH", "ATL", "AH", "PM",

      # Market Terms
      "NYSE", "NASDAQ", "DOW", "SPX", "VIX", "DIA",

      # Common Reddit/Trading Slang
      "FOMO", "IMO", "IMHO", "TL;DR", "TLDR", "BTW", "FYI",
      "LOL", "WTF", "OMG", "IDK", "AFAIK", "AMA", "OTC",

      # Time/Date Abbreviations
      "AM", "PM", "EST", "PST", "UTC", "GMT",

      # Misc Common Words
      "USA", "US", "UK", "EU", "SEC", "FDA", "DOJ", "FBI",
      "IRS", "IT", "AI", "ML", "AR", "VR", "IoT", "SaaS",
  }
  ```

- [ ] **Add configurable blacklist in `config.yaml`**:
  ```yaml
  datasources:
    reddit:
      ticker_blacklist:
        - YOY
        - GDP
        - API
        # ... more
  ```

### Phase 2: Ticker Format Validation

- [ ] **Create `src/datasources/ticker_validator.py`** with validation rules:

  ```python
  class TickerValidator:
      """Validates ticker symbols before processing."""

      @staticmethod
      def is_valid_format(ticker: str) -> bool:
          """Check if ticker matches valid format."""
          # 1-5 uppercase letters
          # No numbers, special chars (except - for some tickers)
          # Not in blacklist

      @staticmethod
      def is_likely_stock(ticker: str) -> bool:
          """Quick heuristic checks (no API call)."""
          # Length check (1-5 chars)
          # Not all numbers
          # Not in blacklist
          # Not common abbreviation pattern
  ```

- [ ] **Validation rules to implement**:
  - ✅ Length: 1-5 characters (existing regex)
  - ✅ No numbers-only tickers (e.g., "2024", "401K")
  - ✅ Allow hyphen for class shares (e.g., "BRK-B")
  - ✅ No special characters except hyphen
  - ✅ Not in TICKER_BLACKLIST
  - ✅ Not matching common abbreviation patterns (e.g., all vowels removed)

### Phase 2.5: AI-Powered Company Name Detection 🆕 🤖

**CRITICAL**: Use NLP/AI to detect **ANY** company mention worldwide (not just pre-mapped ones)

**Goal**: Extract tickers from natural language mentions like:

- "Apple crushed earnings" → AAPL
- "Gubra showed promising results" → GUBRA.CO (Danish company)
- "Nintendo Switch sales" → NTDOY (Japanese ADR)
- "My local bakery" → ❌ (not publicly traded)

**Why AI/NLP?** Manual mappings can't scale to 70,000+ global tickers. We need intelligent detection.

---

#### Stage 1: Named Entity Recognition (NER) for Company Detection

Use **spaCy** to identify potential company names in text:

- [ ] **Install spaCy and download NER model**:

  ```bash
  pip install spacy
  python -m spacy download en_core_web_sm
  # Or for better accuracy: python -m spacy download en_core_web_trf
  ```

- [ ] **Create `src/datasources/company_detector.py`**:

  ```python
  import spacy
  from typing import List, Dict, Optional
  from functools import lru_cache
  import logging

  logger = logging.getLogger(__name__)

  class CompanyDetector:
      """AI-powered company name detection and ticker resolution."""

      def __init__(self):
          """Load spaCy model with NER capabilities."""
          try:
              self.nlp = spacy.load("en_core_web_sm")
          except OSError:
              # Fallback if model not downloaded
              logger.warning("spaCy model not found. Run: python -m spacy download en_core_web_sm")
              self.nlp = None

      def extract_company_names(self, text: str) -> List[str]:
          """Extract potential company names using NER.

          Args:
              text: Reddit post or comment text

          Returns:
              List of detected company/organization names

          Example:
              >>> detector.extract_company_names("Apple crushed earnings! Gubra promising.")
              ['Apple', 'Gubra']
          """
          if not self.nlp:
              return []

          doc = self.nlp(text)

          # Extract entities labeled as ORG (organizations) or PRODUCT
          companies = []
          for ent in doc.ents:
              if ent.label_ in ["ORG", "PRODUCT"]:
                  companies.append(ent.text)

          logger.debug(f"NER detected {len(companies)} potential companies: {companies}")
          return companies
  ```

---

#### Stage 2: LLM-Based Company Validation & Ticker Resolution

Use **GPT-4o-mini** to validate if NER entity is a publicly traded company and get ticker:

- [ ] **Add ticker resolution to `CompanyDetector`**:
  ```python
  @lru_cache(maxsize=5000)  # Cache to avoid repeated API calls
  def resolve_to_ticker(self, company_name: str) -> Optional[Dict[str, str]]:
      """Use LLM to determine if company name is publicly traded and get ticker.

      Args:
          company_name: Potential company name from NER

      Returns:
          {"ticker": "AAPL", "exchange": "NASDAQ"} or None if not public

      Example:
          >>> detector.resolve_to_ticker("Apple")
          {'ticker': 'AAPL', 'exchange': 'NASDAQ'}

          >>> detector.resolve_to_ticker("Gubra")
          {'ticker': 'GUBRA.CO', 'exchange': 'Copenhagen'}

          >>> detector.resolve_to_ticker("My Local Bakery")
          None
      """
      from src.ops.config import get_config
      import openai
      import json

      config = get_config()
      client = openai.OpenAI(api_key=config.openai.api_key)

      prompt = f"""You are a stock market expert. Analyze if the following name is a publicly traded company.
  ```

Company name: "{company_name}"

If it IS a publicly traded company:

- Return ONLY a JSON object: {{"ticker": "SYMBOL", "exchange": "EXCHANGE_NAME"}}
- Use the primary ticker (e.g., AAPL for Apple, GUBRA.CO for Gubra, NTDOY for Nintendo ADR)
- Include exchange suffix if not US (e.g., ".CO" for Copenhagen, ".TO" for Toronto)

If it is NOT a publicly traded company or you're uncertain:

- Return ONLY: {{"ticker": null}}

Examples:

- "Apple" → {{"ticker": "AAPL", "exchange": "NASDAQ"}}
- "Gubra" → {{"ticker": "GUBRA.CO", "exchange": "Copenhagen"}}
- "Nintendo" → {{"ticker": "NTDOY", "exchange": "OTC"}}
- "My Local Bakery" → {{"ticker": null}}
- "Goldman Sachs" → {{"ticker": "GS", "exchange": "NYSE"}}

Respond with ONLY the JSON, no explanation."""

      try:
          response = client.chat.completions.create(
              model="gpt-4o-mini",
              messages=[{"role": "user", "content": prompt}],
              max_tokens=50,
              temperature=0
          )

          result = json.loads(response.choices[0].message.content.strip())

          if result.get("ticker"):
              logger.info(
                  f"LLM resolved company to ticker",
                  extra={
                      "company_name": company_name,
                      "ticker": result["ticker"],
                      "exchange": result.get("exchange")
                  }
              )
              return result

      except (json.JSONDecodeError, Exception) as e:
          logger.warning(f"Failed to parse LLM response for '{company_name}': {e}")

      return None

````

---

#### Stage 3: yfinance Validation (Existence Check)

Verify the LLM-provided ticker actually exists:

- [ ] **Add ticker validation to `CompanyDetector`**:
```python
@lru_cache(maxsize=10000)  # Cache for 24 hours
def validate_ticker(self, ticker: str) -> bool:
    """Verify ticker exists via yfinance API.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL", "GUBRA.CO")

    Returns:
        True if ticker exists and has valid data
    """
    import yfinance as yf

    try:
        info = yf.Ticker(ticker).info
        # Check if we got valid data (not empty or error)
        return info.get('symbol') == ticker or len(info) > 5
    except Exception as e:
        logger.debug(f"Ticker validation failed for {ticker}: {e}")
        return False
````

---

#### Complete Integration in RedditAdapter

- [ ] **Update `RedditAdapter._extract_tickers()` to use AI detection**:
  ```python
  class RedditAdapter:
      def __init__(self):
          self.company_detector = CompanyDetector()
          self.ticker_validator = TickerValidator()

      def _extract_tickers(self, text: str) -> list[str]:
          """Extract tickers using regex + AI company detection."""

          # Stage 1: Regex-based extraction (fast path for explicit tickers)
          dollar_tickers = re.findall(r"\$([A-Z]{1,5})\b", text)
          word_tickers = [
              w for w in re.findall(r"\b[A-Z]{1,5}\b", text)
              if w not in self.TICKER_BLACKLIST
          ]

          # Stage 2: AI-powered company name detection (slow path)
          company_tickers = []
          company_names = self.company_detector.extract_company_names(text)

          for company_name in company_names:
              # Skip if already extracted as ticker
              if company_name.upper() in dollar_tickers + word_tickers:
                  continue

              # Resolve company name to ticker via LLM
              result = self.company_detector.resolve_to_ticker(company_name)
              if result and result.get("ticker"):
                  ticker = result["ticker"]

                  # Validate ticker exists
                  if self.company_detector.validate_ticker(ticker):
                      company_tickers.append(ticker)
                      logger.info(
                          f"✅ Resolved company name to ticker",
                          extra={
                              "company_name": company_name,
                              "ticker": ticker,
                              "exchange": result.get("exchange"),
                          }
                      )
                  else:
                      logger.warning(
                          f"❌ LLM suggested invalid ticker",
                          extra={
                              "company_name": company_name,
                              "ticker": ticker
                          }
                      )

          # Combine all sources
          all_tickers = set(dollar_tickers + word_tickers + company_tickers)

          # Final validation with format rules
          valid_tickers = [
              t for t in all_tickers
              if self.ticker_validator.is_likely_stock(t)
          ]

          logger.info(
              f"Ticker extraction complete",
              extra={
                  "total_extracted": len(all_tickers),
                  "regex_tickers": len(dollar_tickers) + len(word_tickers),
                  "ai_detected": len(company_tickers),
                  "final_valid": len(valid_tickers)
              }
          )

          return sorted(valid_tickers)
  ```

### Phase 3: API-Based Validation (Optional Quick Check)

- [ ] **Add lightweight ticker existence check**:

  ```python
  class TickerValidator:

      @staticmethod
      @lru_cache(maxsize=10000)
      def exists(ticker: str) -> bool:
          """Check if ticker exists via yfinance (cached).

          Fast validation using yfinance.Ticker().info with timeout.
          Results cached to avoid repeated API calls.

          Returns:
              True if ticker exists and has basic info
          """
          try:
              stock = yf.Ticker(ticker)
              info = stock.info

              # Check if ticker returned valid data
              return (
                  info is not None
                  and "symbol" in info
                  and info.get("regularMarketPrice") is not None
              )
          except Exception:
              return False
  ```

- [ ] **Validation timing**:
  - Call `exists()` AFTER sentiment analysis but BEFORE expensive operations
  - Only validate tickers that pass sentiment filters (min_mentions, min_confidence)
  - Cache results for 24 hours to avoid repeated validation

### Phase 4: Integration Points

- [ ] **Update `RedditAdapter._extract_tickers()`**:

  ```python
  def _extract_tickers(self, text: str) -> list[str]:
      """Extract and validate ticker symbols."""
      # Existing extraction logic...
      all_tickers = list(set(dollar_tickers + word_tickers))

      # NEW: Filter out invalid tickers
      validator = TickerValidator()
      valid_tickers = [
          t for t in all_tickers
          if validator.is_likely_stock(t)  # No API call
      ]

      return sorted(valid_tickers)
  ```

- [ ] **Update `RedditSentimentStrategy._refresh_sentiment_data()`**:

  ```python
  # After aggregation but before processing each ticker
  valid_candidates = []
  for candidate in candidates:
      ticker = candidate["ticker"]

      # Quick existence check (cached)
      if not TickerValidator.exists(ticker):
          logger.info(
              f"❌ ${ticker} filtered out: ticker does not exist or is invalid",
              ticker=ticker
          )
          continue

      valid_candidates.append(candidate)
  ```

- [ ] **Add validation metrics to logs**:
  - Total tickers extracted from Reddit
  - Tickers filtered by blacklist
  - Tickers filtered by format validation
  - Tickers filtered by existence check
  - Final valid tickers for processing

### Phase 5: Configuration & Monitoring

- [ ] **Add config section in `config.yaml`**:

  ```yaml
  ticker_validation:
    enabled: true
    use_api_validation: true # Enable yfinance existence check
    api_validation_cache_ttl: 86400 # 24 hours
    log_filtered_tickers: true
    blacklist_from_config: true
  ```

- [ ] **Add validation stats to scan metadata**:
  - `tickers_extracted`: Total from Reddit
  - `tickers_blacklisted`: Filtered by blacklist
  - `tickers_invalid_format`: Filtered by format rules
  - `tickers_not_found`: Filtered by API check
  - `tickers_validated`: Final count for processing

### Testing

- [ ] **Unit tests for `TickerValidator`**:

  - `test_valid_tickers()` - AAPL, MSFT, GOOGL, BRK-B
  - `test_invalid_format()` - "123", "A#BC", "TOOLONG"
  - `test_blacklisted()` - YOY, API, GDP, CEO
  - `test_common_abbreviations()` - USA, FBI, SEC
  - `test_exists_check()` - Mock yfinance responses

- [ ] **Integration test**:
  - Create Reddit post with mixed tickers: "$AAPL $YOY $MSFT GDP growth"
  - Verify only AAPL and MSFT extracted
  - Verify YOY and GDP filtered out
  - Check logs show filter reasons

---

## 🔗 Dependencies

- None (can be implemented immediately)

---

## ✅ Validation Steps

### Manual Testing

```python
# Test AI-powered company detection

from src.datasources.reddit import RedditAdapter
from src.datasources.company_detector import CompanyDetector

adapter = RedditAdapter()
detector = CompanyDetector()

# Test Case 1: Common abbreviation (should be filtered)
text = "The stock dropped 20% YOY"
tickers = adapter._extract_tickers(text)
assert "YOY" not in tickers  # Blacklist filter
print("✅ Test 1 passed: YOY filtered out")

# Test Case 2: Invalid format (should be filtered)
text = "Check out stock 123ABC"
tickers = adapter._extract_tickers(text)
assert "123ABC" not in tickers  # Format validation
print("✅ Test 2 passed: 123ABC filtered out")

# Test Case 3: Valid ticker (should pass)
text = "I bought $AAPL today"
tickers = adapter._extract_tickers(text)
assert "AAPL" in tickers
print("✅ Test 3 passed: $AAPL detected")

# Test Case 4: AI company detection - US company (should pass)
text = "Apple crushed earnings!"
tickers = adapter._extract_tickers(text)
assert "AAPL" in tickers  # NER detects "Apple" → LLM resolves to "AAPL"
print("✅ Test 4 passed: 'Apple' → AAPL")

# Test Case 5: AI company detection - European company (should pass)
text = "Gubra announced positive trial results"
tickers = adapter._extract_tickers(text)
assert "GUBRA.CO" in tickers  # NER detects "Gubra" → LLM resolves to "GUBRA.CO"
print("✅ Test 5 passed: 'Gubra' → GUBRA.CO")

# Test Case 6: AI company detection - Asian company (should pass)
text = "Nintendo Switch sales are booming"
tickers = adapter._extract_tickers(text)
assert "NTDOY" in tickers  # NER detects "Nintendo" → LLM resolves to ADR ticker
print("✅ Test 6 passed: 'Nintendo' → NTDOY")

# Test Case 7: Not a company (should be filtered)
text = "I went to my local bakery this morning"
tickers = adapter._extract_tickers(text)
assert len(tickers) == 0  # NER detects "bakery" but LLM rejects (not public)
print("✅ Test 7 passed: Non-public company filtered")

# Test Case 8: Invalid LLM-suggested ticker (should be filtered)
text = "Made-up Company Inc showed results"
tickers = adapter._extract_tickers(text)
assert len(tickers) == 0  # LLM suggests ticker but yfinance validation fails
print("✅ Test 8 passed: Invalid ticker filtered")

# Test Case 9: Mixed US + international companies
text = "Apple, Gubra, and Nintendo all beat expectations. YOY growth is 50%."
tickers = adapter._extract_tickers(text)
assert set(tickers) == {"AAPL", "GUBRA.CO", "NTDOY"}  # YOY filtered out
print("✅ Test 9 passed: Mixed companies detected, YOY filtered")

# Test Case 10: NER component
companies = detector.extract_company_names("Apple and Tesla announced earnings")
assert "Apple" in companies
assert "Tesla" in companies
print("✅ Test 10 passed: NER detected companies")

# Test Case 11: LLM resolution
result = detector.resolve_to_ticker("Gubra")
assert result["ticker"] == "GUBRA.CO"
assert result["exchange"] == "Copenhagen"
print("✅ Test 11 passed: LLM resolved Gubra to GUBRA.CO")

# Test Case 12: yfinance validation
assert detector.validate_ticker("AAPL") == True
assert detector.validate_ticker("FAKESYMBOL123") == False
print("✅ Test 12 passed: yfinance validation working")

print("\n🎉 All tests passed!")
```

```bash
# Run full Reddit strategy scan
python scripts/one_shot_scan.py --strategy reddit --date 2025-11-01

# Check logs for AI detection metrics
grep "NER detected\|LLM resolved\|Resolved company" logs/recover-bot.log | tail -20
```

### Automated Testing

```bash
# Run ticker validator tests
pytest tests/unit/datasources/test_ticker_validator.py -v

# Run Reddit adapter tests
pytest tests/unit/datasources/test_reddit.py::test_extract_tickers -v

# Run integration test
pytest tests/integration/test_ticker_validation.py -v
```

---

## 📦 Deliverables

- [ ] `src/datasources/company_detector.py` - NEW CompanyDetector class with NER + LLM resolution
- [ ] `src/datasources/ticker_validator.py` - TickerValidator class with validation logic
- [ ] Updated `src/datasources/reddit.py` - Integration of AI detection + validation
- [ ] Updated `config/config.yaml` - company_detection & ticker_validation config
- [ ] Updated `pyproject.toml` - Add spaCy dependencies
- [ ] `tests/unit/datasources/test_company_detector.py` - Unit tests for NER + LLM
- [ ] `tests/unit/datasources/test_ticker_validator.py` - Unit tests for validation
- [ ] `tests/integration/test_ticker_validation.py` - End-to-end tests (US + international)
- [ ] Updated scan logs with AI detection metrics (NER entities, LLM resolutions, cache hits)

---

## 📝 Implementation Notes

### Recommended Approach

1. **Phase 1** (30 min): Expand blacklist, test with current code
2. **Phase 2** (45 min): Create `TickerValidator` with format rules
3. **Phase 2.5** (2.5 hours): **AI-powered company detection** (CRITICAL)
   - Install spaCy and download en_core_web_sm model (30 min)
   - Implement CompanyDetector with NER (60 min)
   - Add LLM ticker resolution with prompt engineering (45 min)
   - Integrate with caching (15 min)
4. **Phase 3** (45 min): Add yfinance validation (optional but recommended)
5. **Phase 4** (45 min): Integrate into RedditAdapter with logging
6. **Phase 5** (45 min): Add config, tests, monitoring

**Total time**: ~6 hours (was 3 hours before AI company detection)

### Performance Considerations

- **Blacklist check**: O(1) set lookup - no performance impact
- **Format validation**: Regex - negligible overhead
- **NER detection**:
  - 50-200ms per post (spaCy processing)
  - Only runs if no explicit tickers found
  - Parallelizable across posts
- **LLM resolution**:
  - 100-300ms per unique company name (first call)
  - 0ms for cached results (LRU cache 5000 entries)
  - Only called for NER-detected entities
  - Typical: 0-3 LLM calls per Reddit post
- **yfinance validation**:
  - 100-200ms per unique ticker (first check)
  - 0ms for cached results (24h TTL, 10000 entries)
  - Only called AFTER sentiment filtering
  - Total overhead: ~2-10 seconds per scan

**Expected overhead per scan**:

- NER processing: ~5-15 seconds (500 posts × 10-30ms each)
- LLM calls: ~3-10 seconds (10-30 unique companies × 300ms)
- yfinance validation: ~2-5 seconds (10-25 unique tickers × 200ms)
- **Total: ~10-30 seconds added to scan time** (acceptable trade-off for 90%+ coverage)

### Dependencies

- **spaCy**: `pip install spacy`
- **spaCy model**: `python -m spacy download en_core_web_sm` (or en_core_web_trf for better accuracy)
- **yfinance**: Already installed
- **OpenAI API**: Already available in project

---

## 🐛 Edge Cases

1. **Legitimate 1-2 char tickers** (e.g., "F" for Ford, "T" for AT&T)

   - Keep in extraction if prefixed with $ (clear intent)
   - Filter standalone 1-2 char words unless high confidence context

2. **Tickers that are also common words** (e.g., "CAT", "ON", "IT")

   - Rely on $ prefix for disambiguation
   - Standalone words require sentiment score threshold

3. **Class shares with hyphens** (e.g., "BRK-B", "GOOG-A")

   - Allow single hyphen in ticker format
   - Validate both parts are letters

4. **Cryptocurrency mentions** (e.g., "BTC", "ETH")

   - Add to blacklist if crypto not supported
   - Or create separate crypto validation path (future)

5. **Index symbols** (e.g., "SPY", "QQQ", "DIA")
   - Strategy-dependent: blacklist for individual stock strategies
   - Allow for index/ETF strategies

---

## 💡 Future Enhancements

- [ ] **Ticker metadata enrichment**:

  - Cache exchange, asset_type, country during validation
  - Use for further filtering (e.g., US stocks only)

- [ ] **Machine learning classifier**:

  - Train model on valid vs invalid ticker patterns
  - Use context around mention for classification

- [ ] **Ticker normalization**:

  - Map common misspellings (e.g., "TSLA" vs "TESLA")
  - Handle exchange prefixes (e.g., "NASDAQ:AAPL")

- [ ] **Smart blacklist updates**:
  - Auto-detect frequently filtered non-stocks
  - Suggest additions to blacklist

---

## ✨ Success Metrics

- [ ] False positive rate: <5% (invalid tickers passing validation)
- [ ] False negative rate: <5% (valid tickers being filtered)
- [ ] NER detection rate: >85% (companies correctly identified in text)
- [ ] LLM resolution accuracy: >90% (correct ticker for detected companies)
- [ ] yfinance validation cache hit rate: >95%
- [ ] LLM resolution cache hit rate: >80% (same companies mentioned repeatedly)
- [ ] Global coverage: Successfully detects US, European, Asian companies
- [ ] Scan logs show AI metrics (NER entities, LLM calls, cache hits, resolutions)
- [ ] No invalid tickers (YOY, GDP, etc.) reaching sentiment analysis
- [ ] Company name resolution working globally (not just top 200)

**Example Success Case**:

```
Input: "Apple and Gubra announced earnings. YOY up 50%. Nintendo crushed it!"
Output: ['AAPL', 'GUBRA.CO', 'NTDOY']  ✅ (not ['YOY'])
Coverage: 100% of companies detected (US + European + Asian)
```

---

## 📊 Expected Impact

**Before Task 6.5**:

- Extraction Rate: ~70% of valid tickers captured (only explicit tickers)
- Noise Rate: ~40% of extracted "tickers" are invalid (YOY, GDP, CEO, etc.)
- API Waste: 40% of price lookups fail or return garbage
- Coverage: Misses 30%+ of Reddit mentions (company names without tickers)
- Global Markets: Misses 90%+ of non-US companies (Gubra, Nintendo, etc.)

**After Task 6.5**:

- Extraction Rate: ~95% of valid tickers captured (tickers + AI-detected companies)
- Noise Rate: ~5% invalid (filtered by blacklist + format + AI + API validation)
- API Waste: <5% of price lookups fail
- Coverage: 90%+ of Reddit stock mentions captured (any language, any market)
- Global Markets: Captures international companies via NER + LLM resolution
- Resource Savings: -40% wasted API calls, -40% wasted LLM tokens

**Example Improvement**:

```
Reddit Post: "YOY growth slowing. I'm bullish on Apple and Gubra but QOQ numbers worry me. Nintendo also looks good."

BEFORE:
- Extracted: ["YOY", "QOQ", "I"]
- Valid: 0/3 (0% accuracy)
- Missed: Apple, Gubra, Nintendo (no tickers in text)
- Coverage: 0%

AFTER:
- NER Detected: ["Apple", "Gubra", "Nintendo"]
- LLM Resolved: Apple→AAPL, Gubra→GUBRA.CO, Nintendo→NTDOY
- yfinance Validated: AAPL ✓, GUBRA.CO ✓, NTDOY ✓
- Final: ["AAPL", "GUBRA.CO", "NTDOY"]
- Accuracy: 3/3 (100%)
- Coverage: 100% (all companies captured)
- Filtered: YOY (blacklist), QOQ (blacklist), I (blacklist)
```

**Cost Savings per Scan**:

- **API calls saved**: ~50 invalid tickers filtered (yfinance, news, company data)
- **LLM tokens saved**: ~50 tickers × 2000 tokens = 100k tokens
- **API calls added**: ~15-30 LLM calls for company resolution (~$0.01 each)
- **Processing time saved**: ~50 tickers × 3 seconds = 2.5 minutes
- **Processing time added**: ~10-30 seconds for NER + LLM
- **Net savings**: ~$0.15 per scan (100k tokens - 30 LLM calls)

Over 100 scans/month: **$15/month savings** + 90%+ coverage + cleaner data! 💰
