# Task 6.2: Deep Research Pipeline - Fact Checking & Company Intelligence

**Status**: 🔴 Not Started  
**Priority**: P0 (Critical)  
**Estimated Effort**: 8 hours  
**Assignee**: AI Agent  
**Created**: 2025-11-01

---

## 📋 Description

Implement a multi-stage research pipeline that fact-checks claims made in Reddit comments and gathers comprehensive company intelligence. This ensures we're making decisions based on verified information, not hype, while also capturing company fundamentals and recent events.

**Research Flow**: Reddit Post → Extract Claims → Fact Check → Gather Company Data → Store in Rationale

---

## 🎯 Acceptance Criteria

### Phase 1: Claim Extraction & Fact Checking

- [ ] Create `src/research/claim_extractor.py`:

  - **Extract factual claims** from Reddit posts/comments using LLM
  - **Batch processing**: Analyze 20 comments per post to capture full narrative
  - **Smart batching strategy**:
    - **Option A** (Recommended): 2 LLM calls of 10 comments each
      - Better token efficiency (fewer system prompts)
      - Parallel processing for speed
      - Handles token limits safely (~4k tokens per batch)
    - **Option B**: 4 LLM calls of 5 comments each
      - Better for long comments (avoids token limits)
      - More granular error handling
    - **Option C**: Single call with all 20 comments
      - Only if comments are short (<100 words each)
      - Risk: May hit token limits (8k-16k context)
  - Identify claim types:
    - Product launches ("new iPhone", "FDA approval")
    - Financial events ("earnings beat", "revenue up 20%")
    - Partnerships ("deal with Microsoft", "acquired by Google")
    - Regulatory ("FDA approval", "SEC investigation")
    - Management changes ("new CEO", "insider buying")
  - Return structured claims:
    ```python
    @dataclass
    class Claim:
        text: str  # "FDA approval for drug XYZ expected Q1 2026"
        category: str  # "regulatory", "financial", "product", etc.
        ticker: str  # "NEM"
        confidence: float  # 0-1 (how confident extraction is)
        source_comment_id: str  # Reddit comment ID
        comment_score: int  # Reddit upvotes (higher = more credible)
        comment_index: int  # Position in thread (0-19)
    ```

- [ ] Create `src/research/fact_checker.py`:
  - **Verify claims** against reliable sources:
    - **Yahoo Finance News API**: Search for recent news mentioning claim keywords
    - **SEC Edgar API**: Check recent 8-K filings for material events
    - **Company Press Releases**: Scrape investor relations pages (optional)
  - Return fact-check results:
    ```python
    @dataclass
    class FactCheckResult:
        claim: Claim
        verified: bool  # True if found corroborating evidence
        confidence: float  # 0-1 (how confident we are in verification)
        sources: list[str]  # URLs to corroborating articles/filings
        evidence: str  # Short summary of what was found
        checked_at: datetime
    ```
  - **Verification logic**:
    - Search Yahoo Finance news for ticker + claim keywords
    - If found within 30 days → verified=True, confidence=0.8+
    - Check SEC filings (8-K) for matching events
    - If not found → verified=False, confidence based on search exhaustiveness
- [ ] Add LLM-based claim verification (fallback):
  - Use GPT-4 to assess claim plausibility
  - Prompt: "Is this claim about {ticker} plausible based on recent news? Provide confidence 0-1."
  - Only use if no hard evidence found in APIs

### Phase 2: Company Intelligence Gathering

- [ ] Create `src/datasources/company.py`:
  - **Financial Metrics** (Yahoo Finance):
    - Market cap, P/E ratio, revenue, earnings (TTM)
    - Revenue growth YoY, earnings growth YoY
    - Debt-to-equity ratio, current ratio
    - Profit margin, ROE
  - **Company Profile**:
    - Description, sector, industry
    - Number of employees, headquarters location
    - Website, founded year
  - **Analyst Data**:
    - Average analyst rating (buy/hold/sell)
    - Price target (consensus)
    - Number of analysts covering
  - **Recent Events** (last 30 days):
    - Earnings dates (past and upcoming)
    - Dividend announcements
    - Stock splits
    - Insider trades (large buys/sells)
- [ ] Add caching with 24-hour TTL:
  - Company fundamentals change slowly
  - Cache key: `company_data:{ticker}:{date}`

### Phase 3: Integration with Reddit Strategy

- [ ] Update `RedditSentimentStrategy._refresh_sentiment_data()`:
  - After sentiment analysis, run deep research pipeline:
    1. Fetch **top 20 comments** per post (sorted by score/upvotes)
    2. Extract claims from all 20 comments using batched LLM calls
    3. Deduplicate similar claims (e.g., 3 people saying "FDA approval")
    4. Fact-check top 10 most impactful claims per ticker (sorted by comment_score × confidence)
    5. Gather company intelligence
    6. Store results in `candidate.rationale.research`
- [ ] **Batching Implementation**:

  ```python
  # Recommended: 2 batches of 10 comments
  def extract_claims_batched(comments: list[dict], ticker: str) -> list[Claim]:
      """Extract claims from 20 comments using 2 parallel LLM calls."""
      batch_size = 10
      batches = [comments[i:i+batch_size] for i in range(0, 20, batch_size)]

      # Parallel processing with asyncio or ThreadPoolExecutor
      with ThreadPoolExecutor(max_workers=2) as executor:
          futures = [
              executor.submit(extract_claims_from_batch, batch, ticker)
              for batch in batches
          ]
          results = [f.result() for f in futures]

      # Flatten and deduplicate
      all_claims = [claim for batch_claims in results for claim in batch_claims]
      return deduplicate_claims(all_claims)

  def deduplicate_claims(claims: list[Claim]) -> list[Claim]:
      """Merge similar claims (e.g., 5 people mentioning FDA approval)."""
      # Group by semantic similarity (use embedding or fuzzy matching)
      # Keep claim with highest comment_score
      # Increment confidence if multiple sources say same thing
      ...
  ```

- [ ] Add research results to `candidate.rationale`:

  ```json
  {
    "llm_analysis": { ... },  // Existing sentiment data
    "research": {
      "comments_analyzed": 20,
      "claims_extracted": 47,
      "claims_deduplicated": 18,
      "claims_verified": 8,
      "claims_debunked": 4,
      "verification_confidence_avg": 0.72,
      "narrative_consensus": {
        "primary_theme": "Upcoming FDA approval driving excitement",
        "secondary_themes": ["Strong fundamentals", "Insider buying"],
        "contradicting_views": ["Concerns about cash burn"],
        "consensus_strength": 0.78  // How aligned are comments?
      },
      "top_verified_claims": [
        {
          "claim": "FDA approval for lead drug expected Q1 2026",
          "verified": true,
          "confidence": 0.85,
          "sources": ["https://finance.yahoo.com/news/..."],
          "evidence": "Press release confirms FDA review on track",
          "mentioned_by": 7,  // 7 out of 20 comments mentioned this
          "avg_comment_score": 156  // Average upvotes on comments with this claim
        }
      ],
      "top_debunked_claims": [
        {
          "claim": "Company acquired by Apple",
          "verified": false,
          "confidence": 0.95,
          "evidence": "No SEC filings or news articles found",
          "mentioned_by": 2
        }
      ],
      "company_fundamentals": {
        "market_cap": 5.2e9,
        "pe_ratio": 15.3,
        "revenue_growth_yoy": 0.12,
        "debt_to_equity": 0.35,
        "analyst_rating": "buy",
        "price_target": 145.50
      },
      "recent_events": [
        {
          "date": "2025-11-05",
          "event": "Earnings call",
          "impact": "positive",
          "details": "Beat EPS by $0.15"
        }
      ],
      "research_quality_score": 0.78  // Overall confidence in research
    }
  }
  ```

- [ ] Add research-based score adjustments:
  - **Verified positive claims**: +0.05 per claim (max +0.15)
  - **Debunked hype claims**: -0.10 per claim (max -0.30)
  - **Strong fundamentals**: +0.10 if revenue_growth > 15% and profitable
  - **Upcoming catalysts**: +0.05 per verified upcoming event
  - **Consensus bonus**: +0.05 if mentioned_by ≥ 5 (strong community agreement)
  - **Contradicting penalty**: -0.05 if consensus_strength < 0.5 (community split)

### Phase 4: Frontend Display

- [ ] Update `CandidateDetailModal.tsx` with new "Research" tab:

  - **Narrative Summary Section** (NEW):

    - Display `narrative_consensus.primary_theme` prominently
    - Show secondary themes as badges
    - If contradicting_views exist, show warning badge: "⚠️ Community Split"
    - Consensus strength meter: 🟢 High (>0.7) | 🟡 Medium (0.5-0.7) | 🔴 Low (<0.5)

  - **Fact Check Section**:

    - List of verified claims with ✅ icon
    - Show "Mentioned by X/20 comments" badge
    - Show average upvotes on comments with this claim
    - List of debunked claims with ❌ icon
    - Each claim shows: text, confidence, sources (clickable links)

  - **Company Fundamentals Section**:

    - Grid of key metrics (market cap, P/E, growth rates)
    - Color-coded: green for good, yellow for neutral, red for concerns
    - Comparison to industry averages (optional)

  - **Recent Events Section**:

    - Timeline of events in last 30 days
    - Icons for event types (📊 earnings, 💰 dividend, 👤 insider trade)

  - **Research Quality Indicator**:
    - Badge showing research confidence (0-100%)
    - Tooltip: "Analyzed 20 comments, verified 8 claims"

- [ ] Add research summary to candidate cards:
  - Small badge: "✅ 3 verified claims" (green)
  - Or: "⚠️ Research pending" (yellow)
  - Or: "❌ 2 debunked claims" (red)

### Testing

- [ ] Unit tests for claim extraction:

  - Test extraction from various comment formats
  - Test claim categorization
  - Test edge cases (no claims, multiple claims)

- [ ] Unit tests for fact checking:

  - Mock Yahoo Finance API responses
  - Test verification logic
  - Test confidence scoring

- [ ] Integration tests for company data:

  - Real API calls to Yahoo Finance (like price adapter)
  - Test caching behavior
  - Test error handling (delisted stocks, etc.)

- [ ] End-to-end test with real Reddit data:
  - Find real Reddit post with verifiable claims
  - Run full pipeline
  - Verify results match reality

---

## 🔗 Dependencies

- Task 2.5 (News Adapter) ✅ - Uses similar Yahoo Finance APIs
- Task 5.4 (Candidate Detail Modal) ✅ - Display research results
- Reddit Sentiment Strategy (completed) - Integration point

---

## ✅ Validation Steps

### Manual Testing

```bash
# Terminal 1: Start backend
make dev

# Terminal 2: Python interactive test
python
>>> from src.research.claim_extractor import extract_claims
>>> from src.research.fact_checker import fact_check_claims
>>>
>>> # Test claim extraction
>>> comment = "NEM just got FDA approval for their new drug! Earnings also beat by 20%"
>>> claims = extract_claims(comment, ticker="NEM")
>>> print(claims)
# Should extract 2 claims: FDA approval + earnings beat
>>>
>>> # Test fact checking
>>> results = fact_check_claims(claims)
>>> for r in results:
...     print(f"{r.claim.text}: verified={r.verified}, confidence={r.confidence}")
>>>
>>> # Test company data
>>> from src.datasources.company import CompanyAdapter
>>> adapter = CompanyAdapter()
>>> data = adapter.get_company_data("NEM")
>>> print(data.keys())
# Should have: financials, profile, analyst_data, recent_events
```

### Automated Testing

```bash
# Backend tests
pytest tests/unit/test_research_claim_extractor.py -v
pytest tests/unit/test_research_fact_checker.py -v
pytest tests/unit/test_datasources_company.py -v
pytest tests/integration/test_research_pipeline.py -v

# Full scan with research
python scripts/one_shot_scan.py --strategy reddit_sentiment --research-enabled
# Check database for research results in candidate.rationale
```

---

## 📦 Deliverables

### Backend - Research Module

- [ ] `src/research/__init__.py`
- [ ] `src/research/claim_extractor.py` (250 lines) - Increased for batching logic
  - `extract_claims_batched(comments, ticker) -> list[Claim]`
  - `extract_claims_from_batch(batch, ticker) -> list[Claim]` (single LLM call)
  - `deduplicate_claims(claims) -> list[Claim]` (merge similar claims)
  - `analyze_narrative(claims, comments) -> NarrativeConsensus` (extract themes)
  - Uses OpenAI GPT-4o-mini with structured output
  - Parallel processing with ThreadPoolExecutor
- [ ] `src/research/fact_checker.py` (250 lines) - Increased for more claims
  - `fact_check_claims(claims) -> list[FactCheckResult]`
  - `rank_claims_by_impact(claims) -> list[Claim]` (sort by score × confidence)
  - Yahoo Finance news search
  - SEC Edgar API integration (optional)
- [ ] `src/datasources/company.py` (300 lines)
  - `CompanyAdapter` class (inherits from `BaseDataAdapter`)
  - `get_company_data(ticker) -> CompanyData`
  - Caching with 24h TTL

### Backend - Integration

- [ ] `src/strategies/reddit_sentiment/implementation.py` - Updated with research pipeline
- [ ] `src/strategies/reddit_sentiment/config.yml` - Add research settings:
  ```yaml
  research:
    enabled: true
    comments_per_post: 20 # Increased from 5
    batch_size: 10 # 2 LLM calls of 10 comments each
    max_claims_to_verify: 10 # Verify top 10 claims (sorted by impact)
    fact_check_timeout_seconds: 15 # Increased for more claims
    min_verification_confidence: 0.5
    consensus_threshold: 5 # Claim needs 5+ mentions for consensus bonus
    enable_deduplication: true
    enable_narrative_analysis: true
  ```

### Backend - Tests

- [ ] `tests/unit/test_research_claim_extractor.py` (100 lines, 10+ tests)
- [ ] `tests/unit/test_research_fact_checker.py` (120 lines, 12+ tests)
- [ ] `tests/unit/test_datasources_company.py` (150 lines, 15+ tests)
- [ ] `tests/integration/test_research_pipeline.py` (80 lines, 5+ tests)

### Frontend

- [ ] `frontend/src/components/ResearchTab.tsx` (250 lines) - Expanded for narrative
  - Narrative summary section
  - Fact check section
  - Company fundamentals section
  - Recent events timeline
- [ ] `frontend/src/components/NarrativeConsensus.tsx` (80 lines) - NEW
  - Display primary/secondary themes
  - Consensus strength meter
  - Contradicting views warning
- [ ] `frontend/src/components/ClaimCard.tsx` (70 lines) - Enhanced
  - Display claim with verification status
  - Show "Mentioned by X/20" badge
  - Show average comment score
- [ ] `frontend/src/components/CompanyMetrics.tsx` (80 lines)
  - Grid of financial metrics with color coding

### Documentation

- [ ] `docs/research-pipeline.md` - Architecture and usage guide
- [ ] Update `AGENTS.md` - Add research module conventions
- [ ] Update `docs/api.md` - Document company data structures

---

## 📝 Implementation Notes

### Claim Extraction Prompt (LLM)

```python
CLAIM_EXTRACTION_BATCH_PROMPT = """
You are analyzing Reddit comments about stock ${TICKER} to extract verifiable claims.

You will receive a batch of 10 comments. Extract all factual claims from ALL comments.

Focus on:
- Product announcements or launches
- Financial metrics (earnings, revenue, growth)
- Partnerships or acquisitions
- Regulatory events (FDA approvals, SEC filings)
- Management changes or insider activity

Comments:
${COMMENTS_JSON}

For each claim found, return:
{
  "text": "FDA approval expected Q1 2026",
  "category": "regulatory",
  "confidence": 0.85,
  "comment_index": 3,  // Which comment (0-9) this came from
  "comment_score": 245  // Reddit upvotes on that comment
}

If a claim appears in multiple comments, return it ONCE with the highest comment_score.

Return JSON array of claims (empty array if no claims found):
[...]
"""

# Example batch processing
def extract_claims_from_batch(comments: list[dict], ticker: str) -> list[Claim]:
    """Process 10 comments in single LLM call."""
    comments_json = json.dumps([
        {
            "index": i,
            "text": c["body"],
            "score": c["score"],
            "id": c["id"]
        }
        for i, c in enumerate(comments)
    ])

    # Call LLM with batch prompt
    # Returns ~5-15 claims from 10 comments
    ...
```

### Fact Checking Strategy

1. **Yahoo Finance News Search**:

   ```python
   # Search for news matching claim keywords
   url = f"https://query2.finance.yahoo.com/v1/finance/search"
   params = {
       "q": f"{ticker} {claim_keywords}",
       "newsCount": 10
   }
   # Check if any results published within 30 days
   # Extract matching articles as evidence
   ```

2. **SEC Edgar API** (optional, for material events):

   ```python
   # Check recent 8-K filings
   url = f"https://data.sec.gov/submissions/CIK{cik}.json"
   # Parse recent filings for matching events
   ```

3. **Confidence Scoring**:
   - Found in Yahoo Finance news (within 7 days): confidence = 0.9
   - Found in Yahoo Finance news (within 30 days): confidence = 0.7
   - Found in SEC filing: confidence = 0.95
   - Found via LLM plausibility check only: confidence = 0.3-0.6
   - Not found anywhere: confidence = 0.8-0.95 (high confidence it's false)

### Company Data Caching

```python
# Cache key includes date to auto-expire daily
cache_key = f"company_data:{ticker}:{date.today()}"
ttl_seconds = 86400  # 24 hours

# If cached, return immediately
# Otherwise fetch from Yahoo Finance and cache
```

---

## 🐛 Edge Cases

1. **Ticker has no recent news**

   - Fact checker returns verified=False with low confidence
   - Don't penalize score (absence of evidence ≠ evidence of absence)

2. **Claim is about future event**

   - Can't verify future claims definitively
   - Use LLM plausibility check + check for press releases announcing future plans
   - Lower confidence (0.3-0.6)

3. **Company is private/delisted**

   - Yahoo Finance API returns no data
   - Gracefully handle with fallback to null values
   - Flag in research results: "Limited data available"

4. **Reddit comment mentions multiple tickers**

   - Extract claims per ticker separately
   - Associate each claim with correct ticker

5. **API rate limits hit during research**

   - Implement exponential backoff retry
   - Cache aggressively to reduce API calls
   - Fall back to partial research if timeout exceeded

6. **Many similar claims from multiple comments**

   - Deduplicate: "FDA approval Q1" + "FDA approval coming" → single claim
   - Increase confidence if 5+ people say same thing
   - Track `mentioned_by` count for consensus scoring

7. **Token limits with 20 long comments**
   - Use 4 batches of 5 instead of 2 batches of 10
   - Truncate extremely long comments (>500 words) with warning
   - Monitor token usage and auto-adjust batch size

---

## ✨ Success Metrics

- [ ] 80%+ of claims successfully categorized
- [ ] 70%+ of verifiable claims get fact-checked within 15 seconds (increased from 10s)
- [ ] <5% false positives (hype claims marked as verified)
- [ ] Company data fetched for 95%+ of tickers
- [ ] Research pipeline adds <45 seconds to total scan time (increased from 30s)
- [ ] Users can clearly see verified vs debunked claims in UI
- [ ] Deduplication reduces 20-30 raw claims to 10-15 unique claims
- [ ] Consensus detection works: claims with 5+ mentions get bonus
- [ ] Narrative summary accurately captures primary theme in 90%+ of cases
