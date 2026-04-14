# Refinement — SKU CRUD + Bulk Upload

**SPARC Phase 6: Refinement** | Feature: sku-crud

---

## 1. Edge Cases

| # | Scenario | Handling |
|---|----------|----------|
| EC-01 | CSV with BOM (Excel-exported UTF-8) | `decode("utf-8-sig")` strips BOM transparently |
| EC-02 | CSV with semicolons (European locale) | Auto-detect delimiter by counting `,` vs `;` in first line |
| EC-03 | CSV with Windows line endings (`\r\n`) | `splitlines()` handles both |
| EC-04 | brand_name not found during bulk upload | Auto-create brand with type="client" and cache per-upload |
| EC-05 | article is empty string in CSV | Treat empty string as NULL (no duplicate constraint) |
| EC-06 | article is NULL and two SKUs have NULL article | Allowed — partial unique index `WHERE article IS NOT NULL` |
| EC-07 | 1000-row CSV where all rows fail validation | Return 207, imported=0, failed=1000 — no DB writes |
| EC-08 | Concurrent bulk uploads from same org | Each upload runs in its own session; article duplicate detection may race. Accept: the second concurrent upload's duplicate rows will be caught by DB unique constraint and reported as errors |
| EC-09 | SKU soft-deleted then article reused | Soft-deleted SKU still has article; re-using the same article returns 409. Operator must hard-delete via admin CLI or archive old article. |
| EC-10 | PATCH on soft-deleted SKU | Return 200 and update fields (including allowing re-activation via is_active=true) |
| EC-11 | `DELETE /sku-platforms/{id}` where id belongs to another org | 404 (tenant isolation: look up by id + sku.org_id join) |
| EC-12 | Platform catalog empty (fresh deploy) | GET /platforms returns empty list — ops seeds via migration or admin tool |
| EC-13 | CSV row count 0 (header only) | Return 200 with imported=0, failed=0 |
| EC-14 | SKU name contains SQL metacharacters | SQLAlchemy ORM parameterizes all values — no injection risk |
| EC-15 | Content-Type not set on upload | Check file extension as fallback: `.csv` accepted |

---

## 2. Security

- **Org isolation:** Every query includes `WHERE org_id = current_user.org_id`. No query operates on SKU without verifying ownership.
- **RBAC:** Write endpoints (`POST`, `PATCH`, `DELETE`, `bulk-upload`) guarded by `require_role("admin", "manager")`.
- **Input validation:** All string fields validated for max length at Pydantic layer before hitting DB.
- **File upload:** CSV content never executed; processed as plain text via `csv.DictReader`.
- **No arbitrary file storage:** CSV is read in memory and discarded — not persisted to disk or S3.

---

## 3. Multi-Tenant Isolation Checklist

- [ ] `BrandRepository.get_by_id` — always add `WHERE org_id = org_id`
- [ ] `SKURepository.list` — always add `WHERE org_id = org_id`
- [ ] `SKURepository.get_by_id_and_org` — returns None if wrong org (→ 404, not 403)
- [ ] `SKUPlatformRepository.get_by_id` — JOIN to skus to verify org_id
- [ ] `bulk_upload_skus` — `org_id` injected server-side from JWT, never from request body
- [ ] Platform catalog — NOT filtered by org_id (global); sku_platforms IS filtered via sku.org_id

---

## 4. Testing Strategy

### Unit Tests (`tests/unit/test_bulk_upload.py`)
- `test_detect_delimiter_comma` — CSV with comma separator
- `test_detect_delimiter_semicolon` — CSV with semicolon
- `test_detect_delimiter_bom` — UTF-8 BOM file
- `test_validate_row_missing_name` — catches REQUIRED_FIELD
- `test_validate_row_name_too_long` — catches MAX_LENGTH_EXCEEDED
- `test_validate_row_valid` — passes without errors
- `test_bulk_report_empty_csv` — header-only file → imported=0

### E2E Tests (`tests/e2e/test_catalog_api.py`)
- `test_create_sku_success` — 201, fields correct, org_id correct
- `test_create_sku_viewer_forbidden` — 403
- `test_create_sku_duplicate_article` — 409
- `test_create_sku_cross_org_article_allowed` — 201 for org_B with same article as org_A
- `test_list_skus_returns_only_own_org` — cross-tenant isolation
- `test_list_skus_excludes_inactive_by_default`
- `test_list_skus_cursor_pagination`
- `test_update_sku_name`
- `test_delete_sku_soft_delete`
- `test_delete_sku_wrong_org_404`
- `test_bulk_upload_200_valid` — all imported
- `test_bulk_upload_mixed_errors_207`
- `test_bulk_upload_too_large_422`
- `test_bulk_upload_not_csv_422`
- `test_bulk_upload_missing_required_column_422`
- `test_create_brand_success`
- `test_list_brands_own_org_only`
- `test_list_platforms_shared_catalog`
- `test_link_sku_platform_success`
- `test_link_sku_platform_duplicate_409`
- `test_unlink_sku_platform`
- `test_unlink_sku_platform_wrong_org_404`

---

## 5. Performance Considerations

- **Bulk insert:** Use SQLAlchemy Core `insert()` with `execute_many` for 100-row chunks — faster than ORM loop
- **List query:** Cursor pagination avoids `OFFSET` scan; `idx_skus_active` covers the most common filter
- **Brand cache during bulk:** `brand_cache` dict per-upload avoids N×brand lookups for duplicate brand names
- **Count query:** Run `COUNT(*)` with same filters but without LIMIT/ORDER — let PostgreSQL use index scan

---

## 6. Tech Debt (deferred)

| Item | Reason | When |
|------|--------|------|
| Hard delete SKU (admin only) | Soft delete + is_active covers MVP | Sprint 4+ |
| Platform CRUD via API | Platforms seeded by ops for now | Sprint 6+ |
| CSV streaming for >1000 rows | Current limit is 1000; relaxation needs streaming parser | Sprint 3+ |
| SKU history/audit log | Useful for compliance | Sprint 5+ |
| Article uniqueness per brand (not just org) | Some orgs have multi-brand; articles may overlap per brand | Sprint 3 |
