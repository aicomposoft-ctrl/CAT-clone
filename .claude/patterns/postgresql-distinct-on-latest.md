# PostgreSQL DISTINCT ON: Latest-Per-Group Pagination

**Category:** Pattern
**Maturity:** 🔴 Alpha
**Used in:** CAT (Commerce Analytics Tool)
**Extracted:** 2026-04-05
**Version:** v1.0

---

## When to Use

When you need paginated results where each group (e.g. sku_platform pair) shows
only its **most recent** record, with optional filters applied *after* the deduplication.

Classic use cases:
- Latest sensor reading per device
- Most recent score per entity × dimension
- Current price per product × store
- Last event per user × session

## When NOT to Use

- MySQL/SQLite (no DISTINCT ON — use correlated subquery or window functions instead)
- When you need the Nth most recent (not just the latest) — use `RANK()` window function
- When grouping key is not indexed (DISTINCT ON requires ordered index scan)

## Prerequisites

- PostgreSQL (any recent version)
- Indexed column matching DISTINCT ON key
- SQLAlchemy async (or any parameterized query approach — never string interpolation)

## Implementation

```python
# Pattern: latest content score per (sku, platform) with pagination
# Generalizable to any "latest record per group" requirement

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio


async def fetch_latest_per_group_page(
    db: AsyncSession,
    tenant_id: str,          # {{TENANT_ID_COLUMN}} — your org/account isolation key
    *,
    filter_col: str | None = None,     # optional post-dedup filter column
    filter_val: str | None = None,
    page: int = 1,
    size: int = 50,
) -> tuple[list, int]:
    """
    Return paginated rows where each group shows only the latest record.

    Strategy:
    - DISTINCT ON (group_key) with ORDER BY group_key, created_at DESC
      resolves the latest row per group in a single index scan.
    - Wrap in CTE so outer query can apply additional filters after deduplication.
    - Use asyncio.gather() to fetch count and data in parallel — ~2x faster.
    """

    params: dict = {
        "tenant_id": tenant_id,
        "limit": size,
        "offset": (page - 1) * size,
    }

    outer_where = ""
    if filter_col and filter_val:
        # Build safe parameterized filter (never f-string with user input)
        outer_where = f"WHERE latest.{filter_col} = :filter_val"
        params["filter_val"] = filter_val

    # The key: DISTINCT ON + ORDER BY group_key, timestamp DESC
    cte = f"""
        WITH latest AS (
            SELECT DISTINCT ON (t.{{GROUP_KEY_COLUMN}})
                t.*,
                related.name AS {{RELATED_NAME}}
            FROM {{YOUR_TABLE}} t
            JOIN {{RELATED_TABLE}} rel ON rel.id = t.{{FK_COLUMN}}
            WHERE rel.{{TENANT_COLUMN}} = :tenant_id
              AND rel.is_active = TRUE
            ORDER BY t.{{GROUP_KEY_COLUMN}}, t.{{TIMESTAMP_COLUMN}} DESC
        )
        SELECT * FROM latest latest_row
        {outer_where}
    """

    count_q = text(f"SELECT COUNT(*) FROM ({cte}) counted")
    data_q = text(
        f"{cte} ORDER BY latest_row.{{SORT_COLUMN}} ASC NULLS LAST "
        f"LIMIT :limit OFFSET :offset"
    )

    count_result, data_result = await asyncio.gather(
        db.execute(count_q, params),
        db.execute(data_q, params),
    )

    total = count_result.scalar_one()
    rows = data_result.fetchall()
    return rows, total
```

## Template: Concrete Example (Content Scores)

```sql
WITH latest_scores AS (
    SELECT DISTINCT ON (cs.sku_platform_id)
        cs.id,
        cs.sku_platform_id,
        s.name  AS sku_name,
        p.name  AS platform_name,
        cs.content_total,
        cs.scored_at
    FROM content_scores cs
    JOIN sku_platforms sp ON sp.id = cs.sku_platform_id
    JOIN skus s           ON s.id  = sp.sku_id
    JOIN platforms p      ON p.id  = sp.platform_id
    WHERE s.org_id = :org_id       -- tenant isolation FIRST
      AND s.is_active = TRUE
    ORDER BY cs.sku_platform_id, cs.scored_at DESC   -- DISTINCT ON key must lead ORDER BY
)
SELECT * FROM latest_scores
WHERE content_total < :max_score   -- post-dedup filter
ORDER BY content_total ASC NULLS LAST
LIMIT :limit OFFSET :offset
```

## Performance Notes

- **Index required:** `CREATE INDEX ON {{table}} ({{group_key}}, {{timestamp}} DESC);`
  Without this, PostgreSQL does a full sequential scan.
- **Parallel count+data:** `asyncio.gather()` fires both queries simultaneously.
  On p50 saves ~30-50ms per request vs. sequential execution.
- **CTE vs. subquery:** CTE allows PostgreSQL to materialize once and reuse;
  for small result sets correlated subquery may be faster — benchmark both.

## Variants

### Variant B: MySQL / SQLite equivalent

```sql
-- MySQL: use window function
SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY group_key ORDER BY created_at DESC) AS rn
    FROM your_table WHERE tenant_id = ?
) ranked WHERE rn = 1
```

### Variant C: Specific date (no DISTINCT ON needed)

```sql
-- When an exact date is requested, drop DISTINCT ON:
SELECT ... FROM content_scores cs ... WHERE cs.scored_at = :date
ORDER BY cs.sku_platform_id
```

## Gotchas

- DISTINCT ON column **must be the leading key** in ORDER BY clause.
- Filtering on columns not in DISTINCT ON must happen in the outer query (after dedup),
  not in the inner WHERE — otherwise you may eliminate the latest record.
- `asyncio.gather()` reuses the same `AsyncSession` — safe because both are read-only SELECTs.
- Never use `f"WHERE {user_input}"` — always parameterize. Only static column names in f-strings.

## Related Artifacts

- `patterns/multi-tenant-saas-isolation.md`
- `snippets/pytest-async-db-rollback-fixture.py`

## Changelog

- v1.0 (2026-04-05): Initial extraction from CAT content scores pagination
