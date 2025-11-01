# Task 6.3: Enhanced LLM Prompts - Balanced Fundamentals & Potential

**Status**: ✅ **COMPLETED**  
**Priority**: P1 (High)  
**Estimated Effort**: 3 hours  
**Actual Effort**: ~2 hours  
**Assignee**: AI Agent  
**Created**: 2025-11-01  
**Completed**: 2025-11-01

---

## 📋 Description

Upgrade the LLM prompts used for Reddit sentiment analysis to use a **Balanced Expert Persona** approach. This strategy focuses on both solid fundamentals AND exciting future potential, catching established value plays and high-growth opportunities equally well.

**Key Philosophy**: "Don't just look at what IS, look at what COULD BE. A struggling company with a breakthrough product is more exciting than a stable company with no growth."

---

## 🎯 Acceptance Criteria

### Prompt Design

- [ ] Create new prompt template in `src/datasources/sentiment.py`:

  - **Persona**: Growth-focused investor (mix of Peter Thiel + Cathie Wood)
  - **Evaluation Criteria**:
    1. **Fundamentals** (30% weight): Current financial health
    2. **Potential/Catalysts** (40% weight): Future opportunities
    3. **Market Sentiment** (30% weight): Community conviction
  - **Scoring Philosophy**:
    - Strong fundamentals + no growth = 0.6 (neutral-positive)
    - Weak fundamentals + breakthrough potential = 0.8 (bullish)
    - Strong fundamentals + exciting catalysts = 0.9+ (very bullish)
    - Weak fundamentals + no catalysts = 0.2 (bearish)

- [ ] Replace existing `SENTIMENT_ANALYSIS_PROMPT` with new balanced prompt
- [ ] Update `SentimentScore` Pydantic model to include:

  ```python
  class SentimentScore(BaseModel):
      ticker: str
      sentiment: Literal["bullish", "bearish", "neutral"]
      confidence: float  # 0-1
      score: float  # -1 to +1

      # NEW FIELDS
      fundamentals_score: float  # 0-1 (current business health)
      potential_score: float  # 0-1 (future opportunity)
      conviction_score: float  # 0-1 (how certain is the author)

      reasoning: str
      catalysts: list[str]
      risk_factors: list[str]

      # NEW FIELD
      growth_drivers: list[str]  # Why this could 10x
  ```

### Prompt Template

- [ ] Implement the following prompt structure:

```python
BALANCED_SENTIMENT_PROMPT = """
You are a growth-focused investment analyst who evaluates stocks based on BOTH current fundamentals AND future potential.

Your philosophy:
- A struggling company with a revolutionary product is MORE exciting than a stable company with no growth
- Past performance matters, but future catalysts matter MORE
- Be open-minded to contrarian opportunities
- High risk + high reward = bullish if the upside is 10x+

Analyze this Reddit post/comment about ${TICKER}:

"${POST_TEXT}"

Evaluate in 3 dimensions:

1. FUNDAMENTALS (Current State):
   - Is the business profitable or on path to profitability?
   - Does it have revenue? Growing or declining?
   - Is it well-managed? Any red flags (debt, lawsuits)?
   - Score 0-1: 0=bankrupt, 0.5=break-even, 1.0=highly profitable

2. POTENTIAL (Future Catalysts):
   - What could make this 10x in 2-5 years?
   - Product launches, FDA approvals, market expansion?
   - Does the author cite specific upcoming events?
   - Is this a paradigm shift (AI, biotech, clean energy)?
   - Score 0-1: 0=no catalysts, 0.5=moderate potential, 1.0=revolutionary

3. CONVICTION (Community Belief):
   - How confident is the author?
   - Do they provide evidence or just hype?
   - Is this based on research or memes?
   - Score 0-1: 0=pure speculation, 0.5=reasonable thesis, 1.0=deep research

Return JSON:
{
  "ticker": "NEM",
  "sentiment": "bullish|bearish|neutral",
  "confidence": 0.85,  // Your confidence in this analysis
  "score": 0.75,  // Overall -1 to +1

  "fundamentals_score": 0.6,  // Current business health
  "potential_score": 0.9,  // Future opportunity
  "conviction_score": 0.7,  // Author's research quality

  "reasoning": "Despite current losses, the upcoming FDA approval could transform the company...",
  "catalysts": ["FDA approval Q1 2026", "Partnership with big pharma", "Market size $50B"],
  "risk_factors": ["Regulatory risk", "Cash burn rate high", "Competition from Pfizer"],
  "growth_drivers": ["First-to-market advantage", "Massive TAM", "Proven efficacy in trials"]
}

IMPORTANT:
- Don't dismiss a stock just because it's unprofitable today
- DO dismiss if there are NO growth drivers (stagnant business)
- Weight POTENTIAL higher than FUNDAMENTALS for high-growth plays
- Be skeptical of pure hype, but open to contrarian opportunities
- If fundamentals are weak BUT potential is high, score can still be 0.8+
"""
```

### Scoring Algorithm

- [ ] Update score calculation in `analyze_batch()`:

  ```python
  def calculate_final_score(
      fundamentals: float,
      potential: float,
      conviction: float,
      sentiment: str
  ) -> float:
      """
      Weighted combination emphasizing potential over fundamentals.

      Formula:
      - Base = (fundamentals × 0.3) + (potential × 0.4) + (conviction × 0.3)
      - If sentiment == "bullish": final = base × 2 - 1  (scale to 0-1)
      - If sentiment == "bearish": final = -(base × 2 - 1)
      - If sentiment == "neutral": final = 0

      Examples:
      - fundamentals=0.3, potential=0.9, conviction=0.7, bullish
        → base = 0.09 + 0.36 + 0.21 = 0.66
        → final = 0.66 × 2 - 1 = 0.32 (moderately bullish)

      - fundamentals=0.8, potential=0.9, conviction=0.9, bullish
        → base = 0.24 + 0.36 + 0.27 = 0.87
        → final = 0.87 × 2 - 1 = 0.74 (strongly bullish)

      - fundamentals=0.2, potential=0.3, conviction=0.4, bearish
        → base = 0.06 + 0.12 + 0.12 = 0.30
        → final = -(0.30 × 2 - 1) = 0.40 (weak bearish, close to neutral)
      """
      base_score = (
          fundamentals * 0.3 +
          potential * 0.4 +
          conviction * 0.3
      )

      if sentiment == "bullish":
          return base_score * 2 - 1  # Maps 0.5-1.0 → 0 to +1
      elif sentiment == "bearish":
          return -(base_score * 2 - 1)  # Maps 0.5-1.0 → 0 to -1
      else:  # neutral
          return 0.0
  ```

### Testing & Validation

- [ ] Create test cases in `tests/unit/test_datasources_sentiment.py`:

  ```python
  TEST_CASES = [
      # Case 1: Strong fundamentals, weak potential → moderate bullish
      {
          "input": "NEM is a solid dividend stock, stable cash flow, no debt",
          "expected": {
              "fundamentals_score": 0.8,
              "potential_score": 0.3,
              "sentiment": "bullish",
              "score_range": (0.3, 0.5)
          }
      },

      # Case 2: Weak fundamentals, high potential → strong bullish
      {
          "input": "NEM burning cash but FDA approval in 3 months could be huge, $50B market",
          "expected": {
              "fundamentals_score": 0.2,
              "potential_score": 0.9,
              "sentiment": "bullish",
              "score_range": (0.6, 0.9)
          }
      },

      # Case 3: Strong fundamentals + strong potential → very bullish
      {
          "input": "NEM profitable + growing 40% YoY + new AI product launching Q1",
          "expected": {
              "fundamentals_score": 0.8,
              "potential_score": 0.9,
              "sentiment": "bullish",
              "score_range": (0.8, 1.0)
          }
      },

      # Case 4: Weak fundamentals + no potential → bearish
      {
          "input": "NEM losing money, market shrinking, no new products",
          "expected": {
              "fundamentals_score": 0.2,
              "potential_score": 0.2,
              "sentiment": "bearish",
              "score_range": (-0.6, -0.3)
          }
      },

      # Case 5: Pure hype, no substance → low conviction
      {
          "input": "NEM TO THE MOON 🚀🚀🚀 BUY NOW!!!",
          "expected": {
              "conviction_score": 0.1,
              "sentiment": "neutral",  # Low conviction → neutral
              "score_range": (-0.2, 0.2)
          }
      }
  ]
  ```

- [ ] Add integration test with real Reddit data:
  - Find 5 real posts with known outcomes
  - Run new prompt on historical data
  - Validate scores align with actual stock performance

### Configuration

- [ ] Add prompt configuration to `src/strategies/reddit_sentiment/config.yml`:

  ```yaml
  sentiment_analysis:
    model: "gpt-4o-mini"
    temperature: 0.3 # Lower for more consistent scoring
    max_tokens: 500

    scoring_weights:
      fundamentals: 0.3
      potential: 0.4
      conviction: 0.3

    min_conviction_threshold: 0.3 # Ignore pure hype (conviction < 0.3)
    potential_boost_threshold: 0.7 # High-potential plays get extra boost
  ```

---

## 🔗 Dependencies

- Task 2.5 (Sentiment Analyzer) ✅
- Reddit Sentiment Strategy (completed) ✅

---

## ✅ Validation Steps

### Manual Testing

```bash
# Test new prompt with sample comments
python
>>> from src.datasources.sentiment import SentimentAnalyzer
>>> analyzer = SentimentAnalyzer()
>>>
>>> # Test Case 1: High potential, weak fundamentals
>>> comment = "NEM is pre-revenue but their AI chip beats Nvidia by 10x. Launch in Q2."
>>> result = analyzer.analyze_batch([("NEM", comment, False)])
>>> print(result["NEM"][0].model_dump_json(indent=2))
# Should show: fundamentals_score ~ 0.2, potential_score ~ 0.9, overall bullish
>>>
>>> # Test Case 2: Strong fundamentals, no catalysts
>>> comment = "NEM is profitable with steady growth but nothing exciting happening"
>>> result = analyzer.analyze_batch([("NEM", comment, False)])
>>> print(result["NEM"][0].model_dump_json(indent=2))
# Should show: fundamentals_score ~ 0.7, potential_score ~ 0.3, moderate bullish
```

### Automated Testing

```bash
# Run all sentiment tests with new prompt
pytest tests/unit/test_datasources_sentiment.py -v

# Full scan to validate in production
python scripts/one_shot_scan.py --strategy reddit_sentiment
# Check database: SELECT reasoning, catalysts, growth_drivers FROM candidate WHERE strategy='reddit_sentiment'
```

### A/B Testing (Optional)

- [ ] Run same Reddit scan with old prompt vs new prompt
- [ ] Compare:
  - Number of candidates found
  - Score distribution
  - Diversity of opportunities (value vs growth)
  - False positives (hype stocks that crash)

---

## 📦 Deliverables

### Backend

- [ ] `src/datasources/sentiment.py` - Updated with new prompt and scoring
  - Replace `SENTIMENT_ANALYSIS_PROMPT`
  - Update `SentimentScore` model
  - Update `calculate_final_score()` function
- [ ] `tests/unit/test_datasources_sentiment.py` - New test cases
  - 5 test cases covering different scenarios
  - Integration test with real data
- [ ] `src/strategies/reddit_sentiment/config.yml` - Updated configuration

### Documentation

- [ ] `docs/prompts.md` - Document prompt design philosophy
- [ ] Update `AGENTS.md` - Add prompt engineering guidelines
- [ ] Create `docs/examples/` with sample analyses:
  - `high-potential-low-fundamentals.json`
  - `strong-fundamentals-weak-potential.json`
  - `pure-hype-low-conviction.json`

---

## 📝 Implementation Notes

### Why This Approach Works

**Traditional Value Investing Bias**:

- Focuses only on current metrics (P/E, revenue, profit)
- Misses early-stage disruptors (Tesla in 2012, Nvidia in 2016)
- Penalizes companies investing heavily in R&D

**Growth-Focused Approach**:

- Weighs potential (40%) > fundamentals (30%)
- Captures paradigm shifts early
- Still respects fundamentals (won't chase pure scams)
- Requires conviction (filters out lazy hype)

**Example Applications**:

| Company State                      | Old Prompt Score        | New Prompt Score     | Why Different              |
| ---------------------------------- | ----------------------- | -------------------- | -------------------------- |
| Profitable but stagnant            | 0.7 (good fundamentals) | 0.4 (no growth)      | Neutral-positive → neutral |
| Unprofitable but breakthrough tech | 0.3 (poor fundamentals) | 0.8 (high potential) | Bearish → bullish          |
| Profitable + launching new product | 0.7                     | 0.9                  | Good → excellent           |
| Unprofitable + no catalysts        | 0.2                     | 0.2                  | Both bearish (correct)     |

### Conviction Filtering

- **High Conviction (0.7+)**: "Here's the 10-K showing 40% revenue growth..."
  - Trust the analysis, weight it heavily
- **Medium Conviction (0.4-0.7)**: "I think their new product will do well"
  - Useful signal, but temper expectations
- **Low Conviction (<0.4)**: "🚀🚀🚀 TO THE MOON"
  - Ignore or heavily discount

### Prompt Engineering Best Practices

1. **Clear Persona**: "Growth-focused investor" sets the tone
2. **Explicit Weights**: Tell LLM exactly how to prioritize (30/40/30)
3. **Concrete Examples**: "0=bankrupt, 0.5=break-even, 1.0=highly profitable"
4. **Anti-Pattern Warnings**: "Don't dismiss just because unprofitable today"
5. **Structured Output**: JSON schema forces consistency

---

## 🐛 Edge Cases

1. **Post mentions multiple catalysts but weak fundamentals**

   - High potential_score (0.8+)
   - Low fundamentals_score (0.3)
   - Overall: Bullish (potential wins)

2. **Post is purely technical analysis (no fundamentals or catalysts)**

   - Moderate fundamentals_score (0.5, unknown)
   - Low potential_score (0.3, no catalysts mentioned)
   - Low conviction_score (0.4, not research-based)
   - Overall: Neutral

3. **Post mentions negative catalysts (FDA rejection, lawsuit)**

   - These go in risk_factors, not catalysts
   - Low potential_score
   - Bearish sentiment

4. **Post is sarcastic or ironic**
   - LLM should detect tone
   - Neutral sentiment or opposite of stated sentiment
   - Low conviction_score

---

## ✨ Success Metrics

- [ ] New prompt identifies 30%+ more growth opportunities than old prompt
- [ ] False positive rate (hype stocks) remains <10%
- [ ] Average potential_score for successful candidates: 0.7+
- [ ] Conviction_score correlates with actual stock performance (r > 0.3)
- [ ] Users report more diverse candidate types (not just value plays)
- [ ] Prompts consistently return valid JSON (99%+ parse success rate)

---

## 🎨 Example Output

**Input Comment**:

> "NEM is burning cash but their AI drug discovery platform just found a breakthrough cancer treatment. Phase 2 trials starting Q1 2026. If successful, this could disrupt a $200B market. Current market cap only $3B."

**Expected Output**:

```json
{
  "ticker": "NEM",
  "sentiment": "bullish",
  "confidence": 0.82,
  "score": 0.76,

  "fundamentals_score": 0.25,
  "potential_score": 0.95,
  "conviction_score": 0.75,

  "reasoning": "Despite cash burn and lack of profitability, the breakthrough cancer treatment represents massive potential. Phase 2 trials in Q1 provide a near-term catalyst. The $200B market size vs $3B valuation suggests 50x+ upside if successful. Author cites specific timelines and market data, indicating research-based conviction.",

  "catalysts": [
    "Phase 2 clinical trials Q1 2026",
    "Breakthrough cancer treatment discovery",
    "$200B addressable market",
    "AI drug discovery platform (competitive advantage)"
  ],

  "risk_factors": [
    "Cash burn with no revenue",
    "Clinical trial risk (Phase 2 failure)",
    "Highly speculative biotech play",
    "Regulatory approval uncertainty"
  ],

  "growth_drivers": [
    "First-mover in AI drug discovery for cancer",
    "200B TAM vs 3B market cap = 66x potential",
    "Platform approach (multiple drugs, not just one)",
    "De-risks with successful Phase 2"
  ]
}
```

**Score Breakdown**:

- Fundamentals: 0.25 (cash burn, pre-revenue)
- Potential: 0.95 (breakthrough tech, huge TAM, near-term catalyst)
- Conviction: 0.75 (specific data, timeline, market size cited)
- **Weighted**: 0.25×0.3 + 0.95×0.4 + 0.75×0.3 = 0.075 + 0.38 + 0.225 = **0.68**
- **Final Score**: Bullish → 0.68×2 - 1 = **+0.36** (moderately bullish)

_(Note: In actual implementation, you may adjust the formula to get 0.76 as shown, e.g., by using a sigmoid or different scaling)_
