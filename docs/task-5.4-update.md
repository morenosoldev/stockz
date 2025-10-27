# Task 5.4 Update - Aligned with Database Schema

## Summary

Updated Task 5.4 (Candidates Grid & Detail Modal) to accurately reflect the actual data model and available fields from the database schema and API endpoints.

## Changes Made

### 1. CandidateCard Component - Added All Available Fields

**Before**: Only showed ticker, score, drop %, strategy, and date

**After**: Now includes all available fields from the API:
- Ticker symbol (large, bold)
- Score badge (color-coded)
- Drop percentage (`drop_pct` field - may be null)
- **Price at identification** (`price` field - may be null)
- **Volume ratio** (`volume_rvol` field - may be null)
- Strategy name (badge)
- Date (relative)

### 2. Overview Tab - Realistic Field Expectations

**Before**: Listed RSI and other features not in Candidate table

**After**: Focuses on fields actually available in Candidate and Ticker tables:
- Score (recovery probability)
- Price at identification (`price`)
- Drop percentage (`drop_pct`)
- Volume ratio (`volume_rvol`)
- Company name (`ticker.name`)
- Sector (`ticker.sector`)

**Note**: All optional fields marked as "if available" since they may be null.

### 3. Features Tab - Clarified Data Source

**Before**: Assumed features were in candidate detail

**After**: Documented that features are in a separate table:
- Features stored in `Feature` table linked by `run_id`
- May need additional API endpoint or inclusion in detail response
- Display as key-value table (e.g., "atr_14": 2.5, "rsi_14": 35.2)
- Show feature version for reproducibility

### 4. Reasoning Tab - Strategy-Specific Format

**Before**: Generic "rationale text"

**After**: Documented expected structure from drop5 strategy:
- Rules triggered (checkmarks/badges)
- Confidence factors (progress bars)
- Drop analysis details
- Volume analysis details
- Convert JSON keys to human-readable labels

### 5. Attribution Tab - Data Transparency

**Before**: Generic "data sources"

**After**: Specific attribution fields:
- Data source name (e.g., "yahoo_finance")
- Timestamp of data fetch
- API endpoint used
- Data version/snapshot info
- Emphasizes transparency and reproducibility

### 6. Added API Documentation Section

Added comprehensive documentation of actual API contracts:

```typescript
// List candidates endpoint
GET /v1/candidates
- All available query parameters
- Complete response structure
- Notes on nullable fields

// Detail endpoint
GET /v1/candidate/{ticker}/{asof}
- Complete response structure
- Ticker table join fields (name, sector)
- Rationale and attribution JSON objects

// Note about Features
- Separate table requires additional endpoint or inclusion
```

## Database Schema Reference

### Candidate Table Fields
```sql
- id (UUID)
- ticker_symbol (FK to Ticker)
- run_id (FK to Run)
- asof (Date)
- strategy (String)
- score (Numeric 5,4) -- 0.0000 to 1.0000
- price (Numeric 12,2) -- NULLABLE
- drop_pct (Numeric 6,3) -- NULLABLE
- volume_rvol (Numeric 6,2) -- NULLABLE
- rationale (JSONB)
- attribution (JSONB)
- created_at (DateTime)
```

### Ticker Table Fields (via JOIN)
```sql
- symbol (PK)
- name (String 255)
- sector (String 100) -- NULLABLE
- industry (String 100) -- NULLABLE
- market_cap (BigInt) -- NULLABLE
- is_active (Boolean)
```

### Feature Table (Separate)
```sql
- id (UUID)
- ticker_symbol (FK)
- run_id (FK)
- asof (Date)
- strategy (String)
- feature_version (String 20)
- features (JSONB) -- {"atr_14": 2.5, "rsi_14": 35.2, ...}
- attribution (JSONB)
```

## Why These Changes Matter

### 1. Prevents Runtime Errors
- No assumptions about fields that don't exist
- Handles nullable fields gracefully
- UI won't crash when data is missing

### 2. Type Safety
- OpenAPI-generated types will match expectations
- TypeScript will catch mismatches at compile time
- Autocomplete will show correct fields

### 3. Better UX
- Users see real data that exists
- No "undefined" or empty fields
- Graceful handling of missing optional data

### 4. Implementation Clarity
- Developer knows exactly what's available
- No need to guess at data structure
- Clear what comes from which table/endpoint

### 5. Reproducibility
- Feature version tracking documented
- Attribution fields for data lineage
- Aligns with project CONSTITUTION.md principles

## Implementation Notes for Developer

### Handle Nullable Fields
```typescript
// Example: Display price or fallback
{candidate.price ? (
  <div>Price: ${candidate.price.toFixed(2)}</div>
) : (
  <div className="text-gray-400">Price: N/A</div>
)}
```

### Display JSONB Fields
```typescript
// rationale and attribution are objects
// Display them nicely:
<pre className="text-sm">
  {JSON.stringify(candidate.rationale, null, 2)}
</pre>

// Or parse and display specific fields:
{candidate.rationale.rules_triggered?.map(rule => (
  <Badge key={rule}>{rule}</Badge>
))}
```

### Features Tab Decision Points
**Option 1**: Add features to detail response (backend change)
```python
# In candidates.py detail endpoint
response = CandidateDetailResponse(
    ...,
    features=features_dict,  # Add this field
    feature_version=feature.feature_version
)
```

**Option 2**: Create separate endpoint (frontend makes 2 calls)
```typescript
// In modal, fetch features separately
const { data: features } = useQuery({
  queryKey: ['features', ticker, asof],
  queryFn: () => api.GET('/v1/candidate/{ticker}/{asof}/features', {...})
});
```

**Recommendation**: Option 1 (add to detail response) is simpler for MVP.

## Testing Checklist

When implementing Task 5.4, verify:

- [ ] CandidateCard displays all non-null fields correctly
- [ ] CandidateCard gracefully handles null fields (shows "N/A" or hides)
- [ ] Detail modal Overview tab shows all available candidate fields
- [ ] Detail modal handles missing ticker.name or ticker.sector
- [ ] Rationale JSON is displayed in readable format
- [ ] Attribution JSON is displayed in readable format
- [ ] Features tab shows data from Feature table (or clear message)
- [ ] All TypeScript types match OpenAPI schema
- [ ] No console errors for undefined properties
- [ ] Empty states work when data is missing

---

**Updated**: October 25, 2025
**Next**: Implement Task 5.4 with accurate expectations
