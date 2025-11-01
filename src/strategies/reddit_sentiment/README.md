# Reddit Sentiment Strategy

**Version**: 1.0.0  
**Type**: Sentiment-based candidate discovery  
**Data Sources**: Reddit (r/wallstreetbets), OpenAI (sentiment analysis)

## Overview

The Reddit Sentiment Strategy identifies stock candidates by analyzing Reddit discussions and sentiment. It follows the standard strategy protocol while leveraging Reddit data and AI-powered sentiment analysis.

## How It Works

1. **Data Collection** (RedditAdapter):

   - Fetches posts from r/wallstreetbets
   - Extracts ticker mentions using regex
   - Caches results with TTL

2. **Sentiment Analysis** (SentimentAnalyzer):

   - Analyzes post titles + content using OpenAI
   - Returns sentiment score (-1 to +1) and rationale
   - Caches analysis results

3. **Aggregation**:

   - Counts ticker mentions across posts
   - Averages sentiment scores
   - Filters by minimum mentions and sentiment threshold

4. **Scoring**:
   - Normalized sentiment score (0 to 1)
   - Higher sentiment = higher score
   - Filters out low sentiment tickers

## Configuration

Edit `config.yml` to adjust parameters:

```yaml
name: reddit_sentiment
version: 1.0.0
description: "Reddit sentiment-based candidate selection"
parameters:
  sentiment_threshold: 0.5 # Minimum sentiment to consider (0-1)
  top_n: 20 # Number of top tickers to process
enabled: true
```

## Strategy Interface

### `filters(ticker_data)`

Returns `True` if ticker sentiment >= `sentiment_threshold`.

**Input**:

```python
{
    "ticker": "AAPL",
    "sentiment": 0.75,
    "mentions": 15,
    "attribution": {...}
}
```

**Output**: `True` (sentiment 0.75 >= 0.5)

### `features(ticker_data)`

Extracts sentiment and mention count.

**Output**:

```python
{
    "sentiment": 0.75,
    "mentions": 15
}
```

### `score(features)`

Returns normalized sentiment score (0-1).

**Output**: `0.75`

### `label(entry_data, outcome_data)`

Placeholder for evaluation. Currently returns `False`.

## Usage

### As a Strategy Module

```python
from src.strategies.reddit_sentiment.implementation import RedditSentimentStrategy

strategy = RedditSentimentStrategy(sentiment_threshold=0.5, top_n=20)

# Filter tickers
ticker_data = {"ticker": "AAPL", "sentiment": 0.8, "mentions": 10}
if strategy.filters(ticker_data):
    features = strategy.features(ticker_data)
    score = strategy.score(features)
    print(f"{ticker_data['ticker']}: {score}")
```

### Get Candidates

```python
from src.strategies.reddit_sentiment.implementation import get_candidates

result = get_candidates(
    date=None,              # Use today
    top_n=10,               # Top 10 tickers
    sentiment_threshold=0.5 # Min sentiment 0.5
)

for candidate in result["candidates"]:
    print(f"{candidate['ticker']}: {candidate['score']}")
```

### Run Demo

```bash
python scripts/demo_reddit_strategy.py
```

## Environment Variables

Required in `.env`:

```bash
# Reddit API
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
REDDIT_USER_AGENT=RecoverBot/1.0

# OpenAI API
OPENAI_API_KEY=your_openai_key
OPENAI_MODEL=gpt-4o-mini
```

## Data Attribution

All data includes attribution metadata:

```python
{
    "ticker": "AAPL",
    "sentiment": 0.75,
    "mentions": 15,
    "attribution": {
        "reddit": {
            "source": "reddit",
            "subreddit": "wallstreetbets",
            "timestamp": "2025-10-31T12:00:00",
            "url": "https://reddit.com/r/wallstreetbets/hot"
        },
        "sentiment": {
            "source": "openai",
            "model": "gpt-4o-mini",
            "timestamp": "2025-10-31T12:01:00"
        }
    }
}
```

## Testing

Run tests:

```bash
pytest src/strategies/reddit_sentiment/tests/ -v
```

## Limitations

- **Rate Limits**: Reddit API has 60 requests/minute limit
- **Sentiment Accuracy**: AI sentiment analysis is not perfect
- **Mention Spam**: Popular tickers may have inflated mention counts
- **Subreddit Focus**: Currently only r/wallstreetbets
- **No Price Data**: Strategy does not consider price action yet

## Future Improvements

1. **Multi-subreddit support**: r/stocks, r/investing, etc.
2. **Time-weighted mentions**: Recent mentions count more
3. **Sentiment confidence**: Filter low-confidence analyses
4. **Price integration**: Combine sentiment with technical indicators
5. **Evaluation**: Backtest hit-rate and PnL proxy

## Phase 4 Status

✅ **Completed**:

- Strategy implementation following StrategyProtocol
- Integration with Reddit, sentiment, and aggregation modules
- Configuration file
- Demo script
- Tests stub
- Documentation

⏳ **Pending**:

- Full integration with scanner engine
- Database persistence of candidates
- API endpoints for Reddit strategy
- Evaluation and backtesting (Phase 5)
