# Refinement — Distribution Plan Upload (Stock Plan)

**Feature ID:** stock-plan-upload
**Sprint:** 3

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| CSV encoding mismatch (cp1251 vs UTF-8) | High | Medium | chardet auto-detection + UTF-8-sig explicit check first |
| Barcode not in org — silently treated as error | Medium | Low | Explicit `errors[]` entry with message; no silent drops |
| Concurrent uploads for same week overwrite each other | Low | Low | PostgreSQL UPSERT handles correctly; last-committed wins |
| File > 5 MB (large brands with 1000+ SKUs × 52 weeks) | Medium | Low | Return 422 with helpful message; suggest splitting by date range |
| Platform name misspelling by end users | High | Medium | Case-insensitive match; error message suggests checking spelling; fuzzy match in v2.0 |
| Memory spike on 10 000 row CSV | Low | Low | All rows parsed from StringIO in-memory; 10 000 rows ≈ < 10 MB strings |
| `distribution_plans` table scanned without index on sku_id | Medium | High | Covering index `(sku_id, platform_id, week_number, year)` in migration |

---

## Edge Cases

### CSV with mixed valid/invalid rows
- Valid rows are imported, invalid rows returned in `errors[]`.
- HTTP 200 always returned for file-level success, even if all rows fail.
- HTTP 422 only for file-level issues (wrong type, missing header, empty file).

### Duplicate rows within the same CSV
- Same `(sku_barcode, platform_name, week_number, year)` appearing twice in one file.
- DB UPSERT handles this safely — last row in the batch wins.
- No application-level dedup required.

### `plan_tt_count = 0`
- Valid (zero planned TT = distribution intentionally absent).
- Stored as-is. Distribution dashboard computes 0% achievement.

### Empty CSV (header only, no data rows)
- HTTP 422: `"CSV file contains no data rows"`.

### Week 53 (only exists in some years per ISO 8601)
- Validation accepts 1–53; business correctness (does ISO week 53 exist?) is not validated.
- User's responsibility to upload correct week numbers.

### Year boundary: week 1 of a new year vs week 53 of prior year
- ISO week numbering edge case. Application stores `week_number` and `year` as provided — no conversion to ISO dates.
- Distribution dashboard queries by `(week_number, year)` directly.

---

## Dependencies

| Dependency | Status | Notes |
|------------|--------|-------|
| `distribution_plans` table | ✅ Exists | Created in earlier migration |
| `skus` table with `barcode` column | ✅ Exists | Barcode lookup uses `skus.barcode` |
| `platforms` global catalog | ✅ Exists | Platform name resolution |
| `chardet` library | Must add to `requirements.txt` | Encoding detection |
| `idx_skus_org_barcode` index | Must add in migration | Without it, batch barcode lookup does full scan |

---

## Alternatives Considered

### Alternative 1: Accept sku_id directly in CSV (instead of barcode)
**Rejected:** Internal UUID not user-friendly; users don't have sku_ids. Barcode is natural identifier in operations planning.

### Alternative 2: Transaction per row instead of UPSERT
**Rejected:** 10 000 individual transactions is too slow. Bulk UPSERT in a single transaction is 100× faster.

### Alternative 3: Reject the entire file if any row has errors
**Rejected:** Users have large CSVs with occasional bad rows; rejecting all-or-nothing creates poor UX. Partial import with error report is standard for bulk tools.

### Alternative 4: Accept XLSX files
**Deferred to v2.0:** Requires `openpyxl` dependency in the API service (already added for Excel export). Can be added without schema changes.

---

## Implementation Notes

### Tenant isolation pattern
`distribution_plans` has no `org_id` column. All tenant scoping goes through:
```
distribution_plans.sku_id → skus.id → skus.org_id
```
Every read query MUST join through `skus`. Barcode lookup pre-validates `sku_id` ownership before UPSERT. DELETE uses a subquery `WHERE sku_id IN (SELECT id FROM skus WHERE org_id = :org_id)`.

### Alembic migration note
The `distribution_plans` table already exists (created before this sprint). The migration for this feature only adds a covering index. The migration file must check `if not op.get_bind().dialect.has_index(...)` before creating the index to be idempotent.

### PostgreSQL UPSERT vs SQLite
`pg_insert(...).on_conflict_do_update(...)` is PostgreSQL-specific (from `sqlalchemy.dialects.postgresql`). Tests using SQLite must mock the repository layer or use a PostgreSQL test database. The project's test fixture uses PostgreSQL via Docker — this is not an issue in CI.

---

## Acceptance Criteria Summary

| Story | Must Pass |
|-------|-----------|
| US-1 Upload valid CSV | ✅ 200, correct import count |
| US-1 Partial import | ✅ Valid rows in, invalid rows in errors[] |
| US-1 UPSERT idempotency | ✅ Same CSV twice = same state |
| US-1 Cross-tenant barcode | ✅ Foreign barcode → RowError, not imported |
| US-1 Encoding: cp1251 | ✅ Cyrillic text parsed correctly |
| US-2 List with filters | ✅ Only own org's data |
| US-3 Delete own row | ✅ 204, row gone |
| US-3 Delete other org's row | ✅ 404 (not 403) |
