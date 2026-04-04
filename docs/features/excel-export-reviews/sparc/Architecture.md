# Architecture: Excel Export — Reviews

**Feature:** `excel-export-reviews`
**Date:** 2026-04-04

---

## 1. Component Placement

The Reviews export extends the **existing `reports` domain** — no new service, no new router. Changes are additive only:

```
services/api/app/reports/
├── repository.py   ← add ReviewRow dataclass + get_reviews_for_export()
├── service.py      ← add build_reviews_export()
└── router.py       ← add GET /reviews-export endpoint
```

No DB migration required — all data is in the existing `reviews` table (with `sentiment` and `sentiment_score` from migration 0009).

---

## 2. Tenant Isolation

Reviews have no direct `org_id` column. Isolation follows the same JOIN chain used by the `reviews` domain API:

```
reviews r
  JOIN sku_platforms sp ON sp.id = r.sku_platform_id
  JOIN skus s           ON s.id  = sp.sku_id AND s.org_id = :org_id  ← gate
  JOIN brands b         ON b.id  = s.brand_id
  JOIN platforms p      ON p.id  = sp.platform_id
```

Defence-in-depth: `s.org_id = org_id` is applied in the repository query. The router also validates `sku_id` ownership via `SKURepository.get_by_id_and_org()` when the optional `sku_id` filter is provided.

---

## 3. Repository Layer

### ReviewRow (dataclass)

```python
@dataclass(slots=True)
class ReviewRow:
    brand_name: str
    sku_article: Optional[str]
    sku_name: str
    platform_name: str
    review_date: date
    rating: Optional[int]
    sentiment: Optional[str]
    sentiment_score: Optional[Decimal]
    review_text: Optional[str]
```

### get_reviews_for_export()

SQLAlchemy ORM query (same pattern as `get_content_scores_for_export`):

```python
stmt = (
    select(
        Brand.name.label("brand_name"),
        SKU.article.label("sku_article"),
        SKU.name.label("sku_name"),
        Platform.name.label("platform_name"),
        Review.review_date,
        Review.rating,
        Review.sentiment,
        Review.sentiment_score,
        Review.review_text,
    )
    .join(SKUPlatform, Review.sku_platform_id == SKUPlatform.id)
    .join(SKU, SKUPlatform.sku_id == SKU.id)
    .join(Brand, SKU.brand_id == Brand.id)
    .join(Platform, SKUPlatform.platform_id == Platform.id)
    .where(SKU.org_id == org_id)
    .where(Review.review_date >= date_from)
    .where(Review.review_date <= date_to)
    .order_by(Brand.name, SKU.article.nulls_last(), Platform.name, Review.review_date.desc())
    .limit(_ROW_LIMIT + 1)   # fetch +1 to detect overflow
)
```

Optional filters appended conditionally:
```python
if platform_id: stmt = stmt.where(SKUPlatform.platform_id == platform_id)
if sentiment:   stmt = stmt.where(Review.sentiment == sentiment)
if sku_id:      stmt = stmt.where(SKU.id == sku_id)
```

Returns `(rows[:_ROW_LIMIT], truncated: bool)` where `truncated = len(rows) > _ROW_LIMIT`.

---

## 4. Service Layer

### build_reviews_export()

```python
async def build_reviews_export(
    db: AsyncSession,
    org_id: UUID,
    date_from: date,
    date_to: date,
    platform_id: Optional[UUID] = None,
    sentiment: Optional[str] = None,
    sku_id: Optional[UUID] = None,
) -> bytes:
    rows, truncated = await get_reviews_for_export(...)
    wb = _build_reviews_workbook(rows, date_from, date_to, truncated)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()
```

### _build_reviews_workbook()

openpyxl pattern (consistent with content + stock):
1. Create `Workbook()`; `ws.title = "Reviews"`
2. Row 1: merged A1:I1 — period header
3. Row 2: 9 column headers (blue fill, bold white font, height=30)
4. `ws.freeze_panes = "A3"`
5. For each row (starting row 3):
   - Write 9 cells
   - Apply sentiment fill to columns 7–8 only
   - Wrap text on column 9 (review text)
6. If `truncated`, append warning row at `len(rows) + 3`
7. `ws.auto_filter.ref = "A2:I2"`

### Sentiment Fill Map

```python
_SENTIMENT_FILLS = {
    "positive": PatternFill("solid", fgColor="C6EFCE"),
    "neutral":  PatternFill("solid", fgColor="FFEB9C"),
    "negative": PatternFill("solid", fgColor="FFC7CE"),
}
```

---

## 5. Router Layer

```
GET /api/v1/reports/reviews-export
```

Reuses the existing `_validate_date_range()` helper in `reports/router.py`.

New logic vs existing endpoints:
- Optional `sentiment: Literal["positive", "neutral", "negative"] | None`
- Optional `sku_id: UUID | None` — validated via `SKURepository.get_by_id_and_org()` (404 if not found)

Response: `Response(content=xlsx_bytes, media_type=_EXCEL_CONTENT_TYPE, headers={...})`

Filename: `reviews_{date_from}_{date_to}.xlsx`

---

## 6. Review ORM Model Import

The repository uses the `Review` ORM model from `app.reviews.models`. Import:
```python
from app.reviews.models import Review
```

The `Review` model was added by the reviews-nlp feature and uses `extend_existing=True` to allow shared table mapping.

---

## 7. Rate Limiting

The `reviews-export` endpoint is an export endpoint. Applies the existing reports domain rate limit: **5 requests/minute per user** (same as content-export and stock-export — enforced at the Nginx level via `limit_req_zone`).

No Redis-based rate limiting at the application layer for this endpoint (consistent with the existing export endpoints).

---

## 8. No DB Migration

All required columns (`sentiment`, `sentiment_score`) were added to `reviews` by migration `0009_add_reviews_sentiment`. No new migration is needed for this feature.

---

## 9. Index Usage

The query accesses `reviews.review_date` for the date range filter. The composite index from migration 0009:
```sql
idx_reviews_sp_sentiment ON reviews (sku_platform_id, review_date DESC, sentiment)
```
covers the date range scan for all platform × date queries. When `sku_id` is additionally specified, the `s.id = :sku_id` JOIN condition narrows the scan to just that SKU's platforms.
