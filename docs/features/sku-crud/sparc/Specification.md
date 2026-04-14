# Specification — SKU CRUD + Bulk Upload

**SPARC Phase 3: Specification** | Feature: sku-crud

---

## 1. User Stories

### US-S01: Single SKU Creation

```gherkin
Feature: SKU CRUD

Scenario: Manager creates a new SKU
  Given I am authenticated as a manager
  When I POST /api/v1/skus with:
    | brand_id     | uuid of ИндиЛайт brand |
    | article      | 3927                   |
    | name         | Индейка Индилайт Духовая |
    | barcode      | 4600000123456          |
    | category     | Мясо птицы             |
    | sub_category | Индейка                |
  Then the response is 201
  And response contains "id" (UUID)
  And SKU is_active = true
  And SKU org_id matches my organisation

Scenario: Manager creates SKU without optional fields
  Given I am authenticated as a manager
  When I POST /api/v1/skus with only name and brand_id
  Then the response is 201
  And article, barcode, category are null

Scenario: Viewer cannot create SKU
  Given I am authenticated as a viewer
  When I POST /api/v1/skus
  Then the response is 403
  And detail is "INSUFFICIENT_PERMISSIONS"

Scenario: Duplicate article within org is rejected
  Given SKU with article "3927" exists in my org
  When I POST /api/v1/skus with article "3927"
  Then the response is 409
  And detail is "SKU_ARTICLE_DUPLICATE"

Scenario: Cross-org article collision is allowed
  Given org_B has SKU with article "3927"
  When org_A creates SKU with article "3927"
  Then the response is 201  # articles unique per org only
```

### US-S02: SKU Listing and Filtering

```gherkin
Scenario: Manager lists all SKUs
  Given my org has 150 SKUs
  When I GET /api/v1/skus?limit=50
  Then the response is 200
  And "items" contains 50 SKUs
  And "total" is 150
  And "next_cursor" is present

Scenario: Manager filters by brand
  When I GET /api/v1/skus?brand_id=<uuid>
  Then all returned SKUs belong to that brand
  And all returned SKUs have org_id = my org_id

Scenario: Inactive SKUs are excluded by default
  Given my org has 10 active and 5 inactive SKUs
  When I GET /api/v1/skus
  Then "total" is 10
  When I GET /api/v1/skus?include_inactive=true
  Then "total" is 15

Scenario: Cross-org SKU isolation
  Given org_B has 100 SKUs
  When I (org_A manager) GET /api/v1/skus
  Then I see only org_A SKUs
  And org_B SKUs are not visible
```

### US-S03: SKU Update and Soft Delete

```gherkin
Scenario: Manager updates SKU name
  Given I am authenticated as a manager
  And SKU with article "3927" exists in my org
  When I PATCH /api/v1/skus/{id} with name = "Updated Name"
  Then the response is 200
  And response body field "name" equals "Updated Name"
  And response body field "id" equals the original SKU id

Scenario: Manager deactivates a SKU (soft delete)
  Given I am authenticated as a manager
  And SKU with id X exists in my org and is_active = true
  When I DELETE /api/v1/skus/{X}
  Then the response is 200
  And response body field "is_active" is false
  And GET /api/v1/skus?include_inactive=true still returns SKU X  # record preserved, not hard-deleted
  And response body field "id" equals X

Scenario: Viewer cannot update a SKU
  Given I am authenticated as a viewer
  When I PATCH /api/v1/skus/{id} with name = "Updated Name"
  Then the response is 403
  And detail is "INSUFFICIENT_PERMISSIONS"

Scenario: Viewer cannot delete a SKU
  Given I am authenticated as a viewer
  When I DELETE /api/v1/skus/{id}
  Then the response is 403
  And detail is "INSUFFICIENT_PERMISSIONS"

Scenario: Manager cannot update another org's SKU
  Given SKU belongs to org_B
  When org_A manager sends PATCH /api/v1/skus/{id}
  Then the response is 404  # not 403 — don't reveal existence

Scenario: PATCH on soft-deleted SKU re-activates it
  Given SKU with id X exists and is_active = false
  When I PATCH /api/v1/skus/{X} with is_active = true
  Then the response is 200
  And response body field "is_active" is true
```

### US-S04: Bulk CSV Upload

```gherkin
Scenario: Manager uploads valid CSV with 200 SKUs
  Given I have a CSV with headers: brand_name,article,name,barcode,category,sub_category
  And all 200 rows are valid
  When I POST /api/v1/skus/bulk-upload (multipart CSV file)
  Then the response is 200
  And "imported" = 200
  And "failed" = 0
  And "errors" is empty

Scenario: Manager uploads mixed CSV (some invalid)
  Given a CSV with 200 rows where rows 5, 47 have empty "name"
  When I POST /api/v1/skus/bulk-upload
  Then the response is 207 Multi-Status
  And "imported" = 198
  And "failed" = 2
  And "errors" contains:
    | row | field | reason         |
    | 5   | name  | REQUIRED_FIELD |
    | 47  | name  | REQUIRED_FIELD |

Scenario: File exceeds 1000 row limit
  Given a CSV with 1001 rows
  When I POST /api/v1/skus/bulk-upload
  Then the response is 422
  And detail is "CSV_TOO_LARGE"

Scenario: Bulk upload skips duplicate articles
  Given SKU with article "3927" already exists
  When CSV contains a row with article "3927"
  Then that row is reported as error: "SKU_ARTICLE_DUPLICATE"
  And other rows proceed normally

Scenario: Non-CSV file is rejected
  When I upload a .xlsx file
  Then the response is 422
  And detail is "INVALID_FILE_TYPE"
```

### US-S05: Brand Management

```gherkin
Scenario: Manager creates a brand
  Given I am authenticated as a manager
  When I POST /api/v1/brands with name="ИндиЛайт" type="client"
  Then the response is 201
  And response body contains "id" (UUID)
  And response body field "name" equals "ИндиЛайт"
  And response body field "type" equals "client"
  And response body field "org_id" equals the authenticated user's org_id

Scenario: Manager creates a competitor brand
  Given I am authenticated as a manager
  When I POST /api/v1/brands with name="Competitor Co" type="competitor"
  Then the response is 201
  And response body field "type" equals "competitor"

Scenario: Manager lists brands (org-scoped)
  Given org_B has 5 brands
  And my org has 3 brands
  When I GET /api/v1/brands
  Then the response is 200
  And response body field "items" contains exactly 3 brands
  And all returned brands have "org_id" equal to my org_id
  And org_B brands are not included in the response

Scenario: Viewer cannot create brand
  Given I am authenticated as a viewer
  When I POST /api/v1/brands with name="Test" type="client"
  Then the response is 403
  And detail is "INSUFFICIENT_PERMISSIONS"

Scenario: Brand type validation
  Given I am authenticated as a manager
  When I POST /api/v1/brands with type="unknown"
  Then the response is 422

Scenario: Duplicate brand name within same org is rejected
  Given brand "ИндиЛайт" already exists in my org
  When I POST /api/v1/brands with name="ИндиЛайт" type="competitor"
  Then the response is 409
  And detail is "BRAND_NAME_DUPLICATE"
```

### US-S06: Platform Catalog and SKU-Platform Linking

```gherkin
Scenario: Manager views platform catalog
  When I GET /api/v1/platforms
  Then the response is 200
  And response body field "items" is a list
  And each item contains "id", "name", "type", "is_active"
  And all returned platforms have "is_active" equal to true
  And platforms are shared across all orgs (same list regardless of org)

Scenario: Platform catalog is empty on fresh deploy
  Given no platforms are seeded
  When I GET /api/v1/platforms
  Then the response is 200
  And response body field "items" is an empty list

Scenario: Manager links SKU to platform
  Given I am authenticated as a manager
  And SKU exists in my org
  And the platform exists and is active
  When I POST /api/v1/sku-platforms with sku_id and platform_id
  Then the response is 201
  And response body contains "id" (UUID)
  And response body field "is_monitored" is true
  And response body field "sku_id" equals the provided sku_id

Scenario: Manager cannot link SKU from another org
  Given sku_id belongs to org_B
  When I POST /api/v1/sku-platforms with that sku_id
  Then the response is 404

Scenario: Viewer cannot link SKU to platform
  Given I am authenticated as a viewer
  When I POST /api/v1/sku-platforms with sku_id and platform_id
  Then the response is 403
  And detail is "INSUFFICIENT_PERMISSIONS"

Scenario: Duplicate link is rejected
  Given SKU X is already linked to Platform Y
  When I POST /api/v1/sku-platforms again with same sku_id + platform_id
  Then the response is 409
  And detail is "SKU_PLATFORM_DUPLICATE"

Scenario: Manager unlinks SKU from platform
  Given SKU X is linked to Platform Y via sku_platform record with id Z
  When I DELETE /api/v1/sku-platforms/{Z}
  Then the response is 200
  And GET /api/v1/sku-platforms/{Z} returns 404  # record is hard-deleted

Scenario: Manager cannot unlink another org's sku_platform
  Given sku_platform id belongs to org_B
  When I DELETE /api/v1/sku-platforms/{id}
  Then the response is 404
```

---

## 2. CSV Format Specification

```
Required columns (order-insensitive, case-insensitive headers):
  brand_name  - string, must match existing brand name in org or be created
  name        - string, required, max 500 chars

Optional columns:
  article     - string, unique per org, max 100 chars
  rpc         - string, max 100 chars
  barcode     - string, max 50 chars
  category    - string, max 255 chars
  sub_category - string, max 255 chars

Encoding: UTF-8 with BOM allowed
Delimiter: comma (,) or semicolon (;) — auto-detected
Max rows: 1000 (excluding header)
Max file size: 5 MB
```

---

## 3. API Contracts

### SKU endpoints
```
GET    /api/v1/skus                     list (paginated, filtered)
POST   /api/v1/skus                     create single
PATCH  /api/v1/skus/{id}               update fields
DELETE /api/v1/skus/{id}               soft-delete (is_active=false)
POST   /api/v1/skus/bulk-upload        CSV upload

GET    /api/v1/brands                   list brands (org-scoped)
POST   /api/v1/brands                   create brand

GET    /api/v1/platforms               list all active platforms (shared catalog)

POST   /api/v1/sku-platforms           link SKU ↔ Platform
DELETE /api/v1/sku-platforms/{id}      unlink
```

### RBAC
| Endpoint | admin | manager | viewer |
|----------|-------|---------|--------|
| GET (any) | ✅ | ✅ | ✅ |
| POST/PATCH/DELETE SKU | ✅ | ✅ | ❌ |
| POST/DELETE sku-platforms | ✅ | ✅ | ❌ |
| POST brands | ✅ | ✅ | ❌ |
| bulk-upload | ✅ | ✅ | ❌ |

### Rate Limits
| Endpoint | Limit | Scope |
|----------|-------|-------|
| POST /api/v1/skus/bulk-upload | 5 req/min | per org |
| POST /api/v1/skus | 60 req/min | per user |
| GET (any) | 100 req/min | per user |

---

## 4. Feature Matrix

| Capability | Sprint 1 (this) | Sprint 1 #3 | Later |
|------------|-----------------|-------------|-------|
| SKU CRUD | ✅ | | |
| Bulk CSV upload | ✅ | | |
| Brand CRUD | ✅ | | |
| Platform catalog | ✅ (read-only) | | |
| SKU-Platform linking | ✅ | | |
| Reference image upload | | ✅ | |
| Reference text upload | | ✅ | |
| Content scoring | | | Sprint 3 |
