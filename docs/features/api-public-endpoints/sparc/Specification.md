# Specification — API Public Endpoints

> **Feature:** api-public-endpoints | **Phase:** SPARC Specification | **Date:** 2026-04-04

---

## User Stories

### US-01: Create API Key

```
As a brand admin,
I want to create a named API key with an optional expiry date,
So that I can authorize an integration to access CAT data on behalf of my organization.

Acceptance Criteria:

Given I am authenticated as admin or manager
When I POST /api/v1/api-keys with { name: "Power BI", expires_at: "2027-01-01" }
Then the response includes the full API key exactly once
And the response includes key_id, name, key_prefix, expires_at, created_at
And the full key is never stored in the database (only SHA-256 hash)
And the key format matches: cat_live_[40 random url-safe chars]

Given I am authenticated as viewer
When I POST /api/v1/api-keys
Then the response is 403 INSUFFICIENT_PERMISSIONS

Given I am authenticated as admin
When I POST /api/v1/api-keys with name exceeding 255 characters
Then the response is 422 Unprocessable Entity
```

---

### US-02: List API Keys

```
As a brand admin,
I want to see all active and revoked API keys for my organization,
So that I can audit which integrations have access.

Acceptance Criteria:

Given I am authenticated as admin or manager
When I GET /api/v1/api-keys
Then the response lists all org's API keys
And each entry shows: id, name, key_prefix, expires_at, last_used_at, revoked, created_at
And the full key value is never included in any response

Given I have keys from two different organizations
When I GET /api/v1/api-keys as org_a
Then I only see keys belonging to org_a
```

---

### US-03: Revoke API Key

```
As a brand admin,
I want to revoke an API key immediately,
So that a compromised or decommissioned integration cannot access data.

Acceptance Criteria:

Given I am authenticated as admin or manager
And a key with key_id exists in my org
When I DELETE /api/v1/api-keys/{key_id}
Then the response is 204 No Content
And subsequent requests using that key return 401

Given the key_id belongs to a different org
When I DELETE /api/v1/api-keys/{key_id}
Then the response is 404 (not 403, to avoid enumeration)
```

---

### US-04: Authenticate via API Key

```
As an external integration,
I want to authenticate using X-API-Key header,
So that I can query CAT data without managing JWT tokens.

Acceptance Criteria:

Given a valid, non-expired, non-revoked API key
When I GET /api/v1/public/skus with header X-API-Key: cat_live_...
Then the response is 200 with org-scoped data

Given an expired API key
When I send a request with X-API-Key header
Then the response is 401 with detail: "API_KEY_EXPIRED"

Given a revoked API key
When I send a request with X-API-Key header
Then the response is 401 with detail: "API_KEY_REVOKED"

Given a malformed key (wrong prefix or length)
When I send a request with X-API-Key header
Then the response is 401 with detail: "INVALID_API_KEY"

Given no X-API-Key header
When I GET /api/v1/public/skus
Then the response is 401 with detail: "MISSING_API_KEY"
```

---

### US-05: Rate Limiting

```
As the CAT platform,
I want to rate-limit API key requests to 60/minute,
So that one noisy integration cannot degrade service for other users.

Acceptance Criteria:

Given an API key making 60 requests in 60 seconds
When the 61st request arrives within that window
Then the response is 429 Too Many Requests
And the response includes header: Retry-After: <seconds>
And the response includes header: X-RateLimit-Limit: 60
And the response includes header: X-RateLimit-Remaining: 0

Given the same key making requests after the window resets
When a new request arrives
Then the response is 200 (counter has reset)
```

---

### US-06: Query SKUs with Content Scores

```
As a BI analyst,
I want to retrieve all SKUs with their latest content scores,
So that I can build a content quality dashboard in Power BI.

Acceptance Criteria:

Given a valid API key for org_a
When I GET /api/v1/public/skus?page=1&page_size=50
Then the response includes paginated SKUs with fields:
  sku_id, sku_name, brand_name, content_total, image_score,
  description_score, completeness_score, scored_at, platform_count
And only SKUs belonging to org_a are returned
And content_total is null if no score has been computed yet

Given filter ?brand_id=<uuid>
When I GET /api/v1/public/skus?brand_id=<uuid>
Then only SKUs of that brand are returned (still org-scoped)
```

---

### US-07: Query Stock Distribution

```
As a BI analyst,
I want to retrieve current stock distribution across platforms,
So that I can identify distribution gaps.

Acceptance Criteria:

Given a valid API key
When I GET /api/v1/public/stock?sku_id=<uuid>
Then the response lists platforms where the SKU is listed
With fields: platform_name, in_stock, stock_status, last_checked_at

Given no sku_id filter
When I GET /api/v1/public/stock
Then the response returns all org's SKU-platform combinations (paginated)
```

---

### US-08: Query Price Snapshots

```
As a BI analyst,
I want to retrieve the latest price for each SKU per platform,
So that I can monitor price compliance.

Acceptance Criteria:

Given a valid API key
When I GET /api/v1/public/prices?sku_id=<uuid>
Then the response lists latest prices per platform
With fields: platform_name, price, currency, discount_pct, snapshot_at

Given filter ?platform_id=<uuid>
When I GET /api/v1/public/prices?platform_id=<uuid>
Then only prices from that platform are returned
```

---

### US-09: Query Reviews Summary

```
As a brand analyst,
I want to retrieve sentiment summary for my brand's reviews,
So that I can track review health without reading individual reviews.

Acceptance Criteria:

Given a valid API key
When I GET /api/v1/public/reviews/summary
Then the response returns:
  total_reviews, avg_rating, positive_pct, negative_pct, neutral_pct
  grouped by: brand (required), platform (optional filter)
```

---

### US-10: Query Triggered Alerts

```
As an agency developer,
I want to retrieve alerts that fired in the last 30 days,
So that I can build a notification pipeline in our system.

Acceptance Criteria:

Given a valid API key
When I GET /api/v1/public/alerts?days=30
Then the response lists triggered alerts
With fields: alert_id, alert_type, sku_id, sku_name, platform_name,
             severity, message, triggered_at
And only alerts for the key's org are returned
```

---

## Non-Functional Requirements

| Category | Requirement |
|----------|-------------|
| Performance | p99 < 300ms for all public endpoints under 100 concurrent requests |
| Security | API key never logged in plaintext; masked as `cat_live_****` in logs |
| Availability | Public API endpoints share the same SLA as the web dashboard API |
| Compatibility | `X-API-Key` header only; no query-param key passing |
| Pagination | All list endpoints: page/page_size (max 500), default page_size 50 |
| Filtering | All list endpoints support date range via `from_date` / `to_date` (ISO 8601) |

---

## Feature Matrix

| Feature | MVP | v1.1 | v2.0 |
|---------|-----|------|------|
| API key CRUD (admin/manager) | ✅ | | |
| API key auth middleware | ✅ | | |
| Rate limiting (60/min per key) | ✅ | | |
| GET /public/skus | ✅ | | |
| GET /public/skus/{id}/content-score | ✅ | | |
| GET /public/stock | ✅ | | |
| GET /public/prices | ✅ | | |
| GET /public/reviews/summary | ✅ | | |
| GET /public/alerts | ✅ | | |
| Per-endpoint rate limits | | ✅ | |
| Key scopes/permissions | | ✅ | |
| IP allowlisting | | | ✅ |
| Write API | | | ✅ |
| Webhook registration | | | ✅ |
