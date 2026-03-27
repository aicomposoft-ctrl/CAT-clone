# PRD — SKU CRUD + Bulk Upload

**Feature:** SKU CRUD + Bulk Upload
**Priority:** P0 | **Sprint:** 1 | **Story Points:** 8
**Status:** Planning

---

## 1. Problem Statement

FMCG brand managers need to configure which SKUs are monitored across which platforms. Without a structured SKU catalog, the scraping, content scoring, and distribution modules have no data to operate on. This is the foundational data layer — nothing else in CAT works without it.

Currently there is no way to:
- Register a SKU for monitoring
- Bulk-upload hundreds of SKUs from an existing internal catalog (Excel/CSV)
- Assign SKUs to specific platforms for monitoring
- Organise SKUs by brand (own vs competitor)

## 2. Target Users

| Persona | Role | Need |
|---------|------|------|
| Brand Manager | Configures catalog | Add/edit/deactivate SKUs, upload reference materials |
| Trade Marketing Manager | Views reports | Needs SKUs to have correct brand, category, article metadata |
| System Admin | Manages org | Bulk-import SKUs from internal ERP/spreadsheet |

## 3. Core Requirements

### Must Have (Sprint 1)
- Create a single SKU with brand, article, name, barcode, category
- List own-org SKUs with filtering (brand, platform, active status)
- Update SKU metadata
- Soft-delete SKU (set is_active=false, preserve history)
- Bulk import SKUs via CSV (up to 1000 rows per upload)
- Link/unlink SKU ↔ Platform (sku_platforms table)
- Brand CRUD (client vs competitor brands)
- Platform catalog (read-only, pre-seeded by ops team)

### Out of Scope (Sprint 1)
- Reference image/text upload → Sprint 1 feature #3 "Reference upload (S3)"
- Content scoring from SKU — Sprint 3
- Distribution plan per SKU — Sprint 3

## 4. Success Metrics

| Metric | Target |
|--------|--------|
| Single SKU creation time | < 2 sec (API response) |
| Bulk upload (200 SKUs) | < 10 sec end-to-end |
| CSV error reporting | Line number + field + reason for every invalid row |
| Valid rows imported despite errors | Yes — partial import on mixed files |
| Multi-tenant isolation | Zero cross-org SKU leakage |

## 5. Non-Functional Requirements

- **Security:** Every endpoint requires JWT auth. Admin/Manager can write; Viewer is read-only.
- **Multi-tenancy:** All DB queries MUST filter by `org_id`. No cross-org access.
- **Idempotency:** Bulk upload with duplicate articles within the same org returns error per row, does not crash.
- **Limits:** Max 1000 rows per CSV upload. Max 10 000 SKUs per org.
- **Performance:** GET /skus list with 10 000 SKUs must respond < 200ms with cursor pagination.

## 6. Constraints

- Backend: FastAPI + SQLAlchemy async + PostgreSQL (existing stack)
- No new Python packages beyond `python-multipart` (already in requirements.txt)
- CSV parsing: Python stdlib `csv` module — no pandas
- No frontend in this sprint (API-only)
