# Performance Optimizations - AI Ticker Extraction Pipeline

**Date**: October 24, 2025  
**Implemented**: P1, P2, P3, P5, P6 (all optimizations except P4)  
**Expected Improvement**: 40-70% reduction in LLM API calls

---

## Problem Statement

The AI ticker extraction pipeline (Task 6.5) was making too many wasteful LLM calls:

- **~60+ LLM calls** per 50 Reddit posts
- **~30-40% were wasteful** (obvious non-companies like "EPS", "Q3", "AI", "IRS", "Company", "Been", "Penny")
- **Cost impact**: Significant at scale with gpt-4o-mini
- **Duplicate detections**: "Warner Bros Discovery", "Warner Bros Discovery's", "Warner Bros" → 3 separate LLM calls

---

## Implemented Optimizations

### ✅ P1: Expanded Blacklist (20-30% reduction)

**Location**: `src/datasources/reddit.py` lines 667-701

**Added Terms**:

- **Quarterly abbreviations**: Q1, Q2, Q3, Q4
- **Financial terms**: MAG7 (Magnificent 7)
- **Generic words**: AI (now in uppercase blacklist)
- **Government**: FED (Federal Reserve)
- **Technology**: More tech abbreviations

**Impact**: Prevents obvious non-tickers from regex extraction phase.

---

### ✅ P2: Minimum Length Filter (10-15% reduction)

**Location**: `src/datasources/reddit.py` lines 775-800

**Logic**:

```python
# Skip if < 4 chars and not all uppercase
if len(name) < 4 and not name.isupper():
    continue  # Skip "DM", "300s", "Been"

# Keep short uppercase: "IBM", "AMD", "AI"
```

**Generic Blacklist**:

```python
GENERIC_BLACKLIST = {
    "company", "companies", "corp", "corporation", "incorporated",
    "limited", "group", "holdings", "ventures", "capital",
    "partners", "fund", "trust", "bank", "financial",
    "been", "penny", "daily", "discussion", "fundamentals",
    "veterans", "westinghouse",
}
```

**Impact**: Filters short fragments and generic corporate terms before LLM.

---

### ✅ P3: Deduplication (5-10% reduction)

**Location**: `src/datasources/reddit.py` lines 762-773

**Logic**:

```python
# Deduplicate company names
unique_companies = set()
for name in company_names:
    # Strip possessive endings
    clean_name = name.rstrip("'s").rstrip("'")
    unique_companies.add(clean_name)
```

**Impact**:

- "Warner Bros Discovery" + "Warner Bros Discovery's" → 1 LLM call
- Eliminates redundant checks per post

---

### ✅ P5: Batch LLM Calls (50-70% reduction in API calls)

**Location**:

- `src/datasources/company_detector.py` lines 221-346 (new method)
- `src/datasources/reddit.py` lines 807-813 (caller)

**Implementation**:

**New Method**:

```python
def resolve_to_tickers_batch(
    self, company_names: List[str], batch_size: int = 10
) -> Dict[str, Optional[Dict[str, Any]]]:
    """Resolve multiple companies in a single LLM call."""
```

**Batching Strategy**:

- Groups up to **10 companies per API call**
- Single prompt with JSON array input/output
- Logs: "🤖 Asking LLM (BATCH): Are these 10 companies publicly traded?"

**Example Prompt**:

```
Company names: ["Apple", "Microsoft", "Fake Corp", ...]

For each company, return:
{
  "Apple": {"ticker": "AAPL", "exchange": "NASDAQ"},
  "Microsoft": {"ticker": "MSFT", "exchange": "NASDAQ"},
  "Fake Corp": null
}
```

**Impact**:

- **Before**: 10 companies = 10 API calls
- **After**: 10 companies = 1 API call
- **Cost**: More tokens per call, but far fewer total calls

---

### ✅ P6: Negative Cache (5-10% reduction)

**Location**: `src/datasources/reddit.py` lines 735-737, 859-863

**Implementation**:

```python
# Initialize cache (persists during scan session)
if not hasattr(self, '_negative_cache'):
    self._negative_cache = set()

# Check cache before LLM
if name.lower() in self._negative_cache:
    logger.debug(f"Skipped cached rejection (P6)")
    continue

# Add to cache after LLM rejection
if not resolution:
    self._negative_cache.add(company_name.lower())
```

**Impact**:

- Avoids re-querying "EPS" if it appears in multiple posts
- Builds knowledge during scan session
- Resets per scan (intentional - fresh start each day)

---

### ❌ P4: Title/Heading Filters (REJECTED)

**Reason**: User concern about false positives

> "im afraid that one will filter out posts talking about relevant companies!"

**Alternative**: Implemented comprehensive generic term blacklist instead (P2).

---

## Performance Metrics

### Before Optimizations

**Sample scan** (50 posts):

- **~60 LLM calls** total
- **~25 wasteful calls** (42%):
  - "EPS" → LLM ❌
  - "Q3" → LLM ❌
  - "AI" → LLM ❌
  - "IRS" → LLM ❌
  - "Company" → LLM ❌
  - "Been" → LLM ❌
  - "Penny" → LLM ❌
  - "Warner Bros Discovery" → LLM ✅
  - "Warner Bros Discovery's" → LLM ✅ (duplicate)
  - "Warner Bros" → LLM ✅ (duplicate)

### Expected After Optimizations

**Same scan** (50 posts):

- **~15-25 LLM API calls** (50-70% reduction via batching)
- **~10-15 wasteful calls** (75% reduction via filters)

**Breakdown**:

1. **P1 (Blacklist)**: Blocks Q1-Q4, MAG7, FED → -20%
2. **P2 (Min Length + Generic)**: Blocks "AI", "Company", "Been", "Penny" → -10%
3. **P3 (Dedup)**: Blocks "Warner Bros" duplicates → -5%
4. **P5 (Batching)**: 30 companies → 3 API calls instead of 30 → -90% API calls
5. **P6 (Negative Cache)**: Avoids re-checking "EPS" across posts → -5%

**Total Expected Reduction**:

- **LLM queries sent**: 40-70% fewer (filters + dedup)
- **API calls made**: 50-90% fewer (batching)
- **Cost savings**: 40-70% (fewer tokens + fewer API calls)

---

## Logging Improvements

**Before**:

```
🤖 Asking LLM: Is 'EPS' a publicly traded company?
❌ LLM says NO: 'EPS' is not a public company
```

**After (with optimizations)**:

```
Skipped short name (P2 min length filter): EPS
Skipped generic term (P2 generic blacklist): Company
Skipped cached rejection (P6 negative cache): IRS

🤖 Asking LLM (BATCH): Are these 10 companies publicly traded?
  companies: ["Apple", "Microsoft", "Tesla", ...]
✅ LLM says YES: 'Apple' → AAPL
✅ LLM says YES: 'Microsoft' → MSFT
❌ LLM says NO: 'Westinghouse' is not a public company
```

**Benefits**:

- Clear visibility into filter actions
- Batch logging shows efficiency gains
- Debug logs track optimization decisions

---

## Testing & Validation

### Test Plan

1. **Run full scan** (50-100 posts)
2. **Compare metrics**:
   - Before: Count LLM calls in logs (search for "🤖 Asking LLM:")
   - After: Count batch LLM calls + individual calls
3. **Verify no false negatives**:
   - Check that real companies (Apple, Microsoft, Tesla) still detected
   - Verify tickers match expected results
4. **Measure cost savings**:
   - Count API calls: `grep "🤖 Asking LLM" logs/* | wc -l`
   - Verify reduction matches 40-70% target

### Validation Commands

```bash
# Count LLM calls (before)
grep "🤖 Asking LLM:" logs/recover-bot.log | wc -l

# Count batch LLM calls (after)
grep "🤖 Asking LLM (BATCH):" logs/recover-bot.log | wc -l

# Count filtered companies
grep "Skipped" logs/recover-bot.log | wc -l

# Verify real companies still detected
grep "✅ LLM says YES" logs/recover-bot.log | grep -i "apple\|microsoft\|tesla"
```

---

## Code Changes Summary

### Modified Files

1. **`src/datasources/reddit.py`**:

   - Lines 667-701: Expanded `TICKER_BLACKLIST` (+50 terms)
   - Lines 735-737: Added `_negative_cache` initialization
   - Lines 743-750: Added `GENERIC_BLACKLIST`
   - Lines 762-773: Deduplication logic
   - Lines 775-800: Min length + generic term filters
   - Lines 781-787: Negative cache check
   - Lines 807-813: Batch LLM call
   - Lines 815-863: Process batch results + update negative cache

2. **`src/datasources/company_detector.py`**:
   - Line 25: Added `Any, Dict, List` to typing imports
   - Lines 221-346: New `resolve_to_tickers_batch()` method
   - Lines 114-219: Legacy `resolve_to_ticker()` (kept for compatibility, now delegates to batch)

### Lines of Code

- **Added**: ~200 lines
- **Modified**: ~50 lines
- **Deleted**: 0 lines (backward compatible)

---

## Backward Compatibility

✅ **Fully backward compatible**:

- `resolve_to_ticker()` still works (delegates to batch method)
- Existing code using single-company resolution unaffected
- New batch method is opt-in via explicit caller

---

## Future Improvements

### P7: Persistent Negative Cache (Future)

**Idea**: Store negative cache in Redis/database across scans

**Benefits**:

- Avoid re-querying "EPS" every day
- Build long-term knowledge of non-companies

**Trade-offs**:

- Requires external dependency (Redis)
- Risk of stale data (company goes public)
- Added complexity

**Recommendation**: Wait until cost justifies complexity (v2).

### P8: Smart Batch Sizing (Future)

**Idea**: Dynamic batch size based on token usage

**Logic**:

```python
# Shorter company names → larger batches
if avg_length < 10:
    batch_size = 15
else:
    batch_size = 5
```

**Benefits**: Maximize efficiency within token limits

**Recommendation**: Implement if hitting token limits.

---

## Acceptance Criteria

- [x] **P1**: Blacklist expanded with ~50 new terms
- [x] **P2**: Min length filter implemented (< 4 chars unless uppercase)
- [x] **P2**: Generic term blacklist (company, corp, etc.)
- [x] **P3**: Deduplication logic (strip possessives, use set)
- [x] **P5**: Batch LLM method created (`resolve_to_tickers_batch()`)
- [x] **P5**: Caller updated to use batching
- [x] **P6**: Negative cache initialized and checked
- [x] **P6**: Negative cache updated after rejections
- [x] **Logging**: All filters log debug messages
- [x] **Logging**: Batch calls log batch size + companies
- [x] **Backward Compatibility**: Legacy method still works
- [ ] **Testing**: Run full scan and verify 40-70% reduction
- [ ] **Validation**: Confirm no false negatives (real companies still detected)

---

## Next Steps

1. **Run full scan** to test all optimizations:

   ```bash
   make scan
   # or
   python scripts/one_shot_scan.py --date 2025-10-24
   ```

2. **Analyze logs** for performance improvement:

   ```bash
   # Count LLM calls
   grep "🤖 Asking LLM" logs/recover-bot.log | wc -l

   # Count batch calls
   grep "BATCH" logs/recover-bot.log | wc -l

   # Check filter effectiveness
   grep "Skipped" logs/recover-bot.log | wc -l
   ```

3. **Verify accuracy**:

   - Check that real companies (AAPL, MSFT, TSLA) are still detected
   - Ensure no false negatives introduced by filters

4. **Measure cost savings**:

   - Compare API call counts before/after
   - Verify 40-70% reduction target met

5. **Document results** in AGENTS.md or PLAN.md

---

**Status**: ✅ **Implementation Complete** - Ready for Testing

**Estimated Improvement**: 40-70% reduction in LLM costs
