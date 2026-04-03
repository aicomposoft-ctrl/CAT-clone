# Specification — Distribution Plan Upload (Stock Plan)

**Feature ID:** stock-plan-upload
**Sprint:** 3

---

## User Stories

### US-1: Upload distribution plan via CSV

```gherkin
Feature: Stock Plan Upload

Scenario: Manager uploads a valid CSV plan
  Given I am authenticated as a manager
  When I POST /api/v1/stock/distribution-plan
       with Content-Type: multipart/form-data
       and file=plan.csv containing:
         sku_barcode,platform_name,group_name,plan_tt_count,week_number,year
         4600000123456,Wildberries,Moscow,150,14,2026
         4600000789012,Ozon,SPb,80,14,2026
  Then the response is 200
  And response body is { "imported": 2, "errors": [] }
  And distribution_plans table contains 2 new rows
  And each row has correct sku_id, platform_id, plan_tt_count

Scenario: Viewer cannot upload
  Given I am authenticated as a viewer
  When I POST /api/v1/stock/distribution-plan
  Then the response is 403

Scenario: File exceeds 5 MB limit
  Given I am authenticated as a manager
  When I POST with a CSV file of 6 MB
  Then the response is 422
  And detail contains "FILE_TOO_LARGE"

Scenario: Wrong file type
  Given I am authenticated as a manager
  When I POST with Content-Type: application/json
  Then the response is 422
  And detail contains "INVALID_CONTENT_TYPE"

Scenario: Missing required CSV columns
  Given CSV is missing the "plan_tt_count" column
  When I POST the file
  Then the response is 422
  And detail contains "Missing columns: {'plan_tt_count'}"

Scenario: Partial import — some rows invalid
  Given CSV has 5 rows, rows 2 and 4 have invalid plan_tt_count ("-1" and "abc")
  When I POST the file
  Then the response is 200
  And response body has "imported": 3
  And "errors" contains 2 entries
  And errors[0].row == 3 and errors[0].field == "plan_tt_count"
  And errors[1].row == 5 and errors[1].field == "plan_tt_count"

Scenario: Unknown SKU barcode (cross-tenant protection)
  Given org_B has SKU with barcode "4600000111111"
  And I am authenticated as org_A manager
  When I POST a CSV with barcode "4600000111111"
  Then the response is 200
  And "errors" contains 1 entry with field "sku_barcode"
  And message contains "not found in your organisation"
  And distribution_plans table has 0 new rows for org_A

Scenario: Unknown platform name
  Given platform "UnknownStore" does not exist
  When I POST a CSV with platform_name "UnknownStore"
  Then the response is 200
  And "errors" contains 1 entry with field "platform_name"
  And message contains "not found"

Scenario: Case-insensitive platform matching
  Given platform "Wildberries" exists in the catalog
  When CSV contains platform_name "wildberries"
  Then the response is 200 with "imported": 1
  And the row is linked to the correct platform_id

Scenario: Repeat upload is idempotent (UPSERT)
  Given week 14 plan for SKU × Wildberries already exists with plan_tt_count=150
  When I upload the same CSV again with plan_tt_count=150
  Then the response is 200 with "imported": 1
  And distribution_plans row count does not increase
  And plan_tt_count remains 150

Scenario: Repeat upload updates plan_tt_count (UPSERT overwrites)
  Given week 14 plan exists with plan_tt_count=150
  When I upload CSV with same sku × platform × week × year but plan_tt_count=200
  Then the response is 200 with "imported": 1
  And the existing row now has plan_tt_count=200

Scenario: CSV with cp1251 encoding (Russian Windows export)
  Given CSV file is encoded in Windows-1251
  When I POST the file
  Then the response is 200 with "imported": N (correct parsing of Cyrillic platform names)
```

---

### US-2: List distribution plans

```gherkin
Scenario: Manager lists plans — default pagination
  Given my org has 120 distribution plan rows
  When I GET /api/v1/stock/distribution-plan
  Then the response is 200
  And "items" contains 50 rows (default page size)
  And "total" is 120

Scenario: Filter by week and year
  When I GET /api/v1/stock/distribution-plan?week_number=14&year=2026
  Then "items" contains only rows where week_number=14 AND year=2026

Scenario: Cross-tenant isolation
  Given org_A and org_B both have plans for week 14
  When org_A manager calls GET /api/v1/stock/distribution-plan
  Then "items" contains only org_A plans
  And org_B plans are not visible
```

---

### US-3: Delete a plan row

```gherkin
Scenario: Manager deletes own plan row
  Given a distribution plan row with id=PLAN-UUID belonging to my org
  When I DELETE /api/v1/stock/distribution-plan/PLAN-UUID
  Then the response is 204
  And the row no longer exists in distribution_plans

Scenario: Delete non-existent plan
  When I DELETE /api/v1/stock/distribution-plan/00000000-0000-0000-0000-000000000000
  Then the response is 404
  And detail is "PLAN_NOT_FOUND"

Scenario: Delete plan belonging to other org (cross-tenant)
  Given org_B owns PLAN-UUID-B
  When org_A manager calls DELETE /api/v1/stock/distribution-plan/PLAN-UUID-B
  Then the response is 404  # not 403 — do not reveal existence of other org's data
```

---

## API Contract

### POST /api/v1/stock/distribution-plan

**Request:**
- `Content-Type: multipart/form-data`
- Body: `file` field — CSV file, max 5 MB

**Response 200:**
```json
{
  "imported": 95,
  "errors": [
    { "row": 3, "field": "plan_tt_count", "message": "Must be a non-negative integer" },
    { "row": 7, "field": "sku_barcode", "message": "SKU with barcode '...' not found in your organisation" }
  ]
}
```

**Response 422:** File-level validation failures (size, type, missing columns).

### GET /api/v1/stock/distribution-plan

**Query params:**
- `platform_id?: UUID`
- `week_number?: int (1–53)`
- `year?: int (2000–2100)`
- `page?: int = 1`
- `size?: int = 50 (max 200)`

**Response 200:**
```json
{
  "items": [
    {
      "id": "uuid",
      "sku_id": "uuid",
      "platform_id": "uuid",
      "group_name": "Moscow",
      "plan_tt_count": 150,
      "week_number": 14,
      "year": 2026
    }
  ],
  "total": 120,
  "page": 1,
  "size": 50
}
```

### DELETE /api/v1/stock/distribution-plan/{id}

**Response 204:** No content.
**Response 404:** Plan not found or not owned by requesting org.

---

## Data Contract — CSV

| Column | Type | Constraints |
|--------|------|-------------|
| sku_barcode | string | non-empty; must match an active SKU in org |
| platform_name | string | non-empty; case-insensitive match against platforms |
| group_name | string | non-empty; max 100 chars |
| plan_tt_count | integer | ≥ 0 |
| week_number | integer | 1–53 |
| year | integer | 2000–2100 |

Row limit: 10 000 rows per upload.
