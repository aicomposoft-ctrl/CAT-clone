# PRD — Reviews NLP

**Feature:** Reviews NLP Sentiment Analysis
**Sprint:** 7 | **Priority:** P1 | **Story Points:** 13
**Status:** Phase 1 — Planning

---

## Problem Statement

CAT collects reviews from 110+ platforms and stores raw text + rating. Currently `sentiment` and
`sentiment_score` columns exist in the Architecture doc schema but are **missing from migration 0003**
and are never populated. Brand managers have raw text but no structured insight into sentiment
distribution, trending topics, or platform-by-platform reputation dynamics.

Manual reading of hundreds of reviews per week per brand is impossible at scale.

---

## Solution

Add sentiment classification to the reviews pipeline using `rubert-base-cased-sentiment` (Russian
BERT fine-tuned for sentiment). Backfill existing reviews, score new reviews in background Celery
tasks, and expose 4 API endpoints for analytics.

---

## User Stories

### US-1: Sentiment Summary by SKU
```
As a brand manager,
I want to see the sentiment breakdown (% positive / neutral / negative) for a SKU across all
platforms over a configurable date range,
So that I can quickly identify which platforms have reputation problems.

Acceptance Criteria:
Given I provide a valid sku_id + optional date_from/date_to
When I call GET /api/v1/reviews/summary
Then I receive per-platform counts and percentages for each sentiment label,
  plus average rating, total review count, and the most-recent review date.
Given sku_id belongs to another org
When I call the endpoint
Then I receive HTTP 404 (not 403).
Given no reviews exist for the period
When I call the endpoint
Then I receive HTTP 200 with empty items list and total=0.
```

### US-2: Paginated Reviews with Sentiment
```
As a brand manager,
I want to browse individual reviews filtered by sentiment and/or platform,
So that I can read the most negative feedback without scrolling through all reviews.

Acceptance Criteria:
Given I provide sku_id + optional sentiment filter ("positive"|"neutral"|"negative") and platform_id
When I call GET /api/v1/reviews/history
Then I receive paginated reviews ordered by review_date DESC, each with: id, platform_name,
  review_text, rating, sentiment, sentiment_score, review_date.
Given sentiment_filter is an invalid value
When I call the endpoint
Then I receive HTTP 422.
Given limit > 500
When I call the endpoint
Then I receive HTTP 422.
```

### US-3: Rating + Sentiment Statistics
```
As a brand manager,
I want aggregated stats (avg rating, rating distribution, sentiment share, trend over time),
So that I can track reputation trends in weekly/monthly reviews.

Acceptance Criteria:
Given a valid sku_id + date range
When I call GET /api/v1/reviews/stats
Then I receive: avg_rating, rating_distribution (counts per 1-5), sentiment_share
  (positive/neutral/negative as fractions), review_count, and weekly_trend (list of
  {week_start, positive_share, avg_rating}).
Given no reviews in the range
When I call the endpoint
Then I receive HTTP 200 with review_count=0 and all aggregates null.
```

### US-4: Background Sentiment Scoring
```
As the system,
I want unscoredreviews (sentiment IS NULL) to be scored automatically in background Celery tasks,
So that new reviews collected by the scraper are always enriched without manual intervention.

Acceptance Criteria:
Given N reviews exist with sentiment IS NULL
When the score_pending_reviews Celery task runs
Then each review is scored using rubert-base-cased-sentiment (batch=32),
  sentiment and sentiment_score columns are updated,
  and the task completes with a count of scored reviews in its return value.
Given the ML model is unavailable
When the task runs
Then it raises an exception that Celery will retry (max 3 times, exponential backoff),
  and the failed reviews remain sentiment IS NULL.
Given a review_text is empty or NULL
When the task encounters it
Then that review is skipped (sentiment remains NULL), no error raised.
```

---

## Feature Scope

### In Scope (Sprint 7)
- Migration: ADD COLUMN sentiment + sentiment_score to reviews table
- Celery task: `score_pending_reviews` (batch=32, rubert-base-cased-sentiment)
- API endpoints: /summary, /history, /stats
- ORM model update: Review with sentiment fields
- Tests: e2e for all 3 endpoints + unit for scorer

### Out of Scope (future)
- Topic extraction / keyword trends
- Competitor review monitoring
- Review response recommendations
- ClickHouse analytics table for reviews time-series
- Frontend dashboard page (Sprint 8)

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Sentiment classification throughput | ≥ 1,000 reviews/min on 2 vCPU |
| API p99 response time | < 200ms |
| Sentiment accuracy (manual sample) | ≥ 85% agreement |
| Time to score all pending reviews | < 30 min for 100k reviews |
| Cross-tenant isolation | 100% — zero leaks in test suite |
