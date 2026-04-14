# Specification — Multi-Client Support

> **Feature:** multi-client-support | **Phase:** SPARC Specification | **Date:** 2026-04-04

---

## User Stories

### US-01: Create Client

```
As an agency admin,
I want to create a named client with contact info,
So that I can organize brands and data by the client they belong to.

Acceptance Criteria:

Given I am authenticated as admin
When I POST /api/v1/clients with { name: "Nestle RU", slug: "nestle-ru", contact_email: "nestle@agency.com" }
Then the response is 201 with { id, name, slug, contact_email, logo_url, is_active, created_at }
And the client belongs to my org_id

Given I am authenticated as viewer
When I POST /api/v1/clients
Then the response is 403 INSUFFICIENT_PERMISSIONS

Given slug already exists within my org
When I POST /api/v1/clients with the same slug
Then the response is 409 SLUG_CONFLICT

Given name exceeds 255 characters
When I POST /api/v1/clients
Then the response is 422 Unprocessable Entity
```

---

### US-02: List Clients

```
As an agency user,
I want to see all clients my organization manages,
So that I can select which client to work on.

Acceptance Criteria:

Given I am authenticated (any role)
When I GET /api/v1/clients
Then the response lists all active clients in my org
And each item includes: id, name, slug, contact_email, logo_url, brand_count, is_active

Given org_b has clients
When I GET /api/v1/clients as org_a user
Then I only see org_a's clients (cross-org isolation)

Given is_active=false filter
When I GET /api/v1/clients?include_inactive=true (admin only)
Then deactivated clients are included
```

---

### US-03: Switch Client Context

```
As an agency analyst,
I want to switch my active client without re-logging in,
So that I can quickly move between clients during the workday.

Acceptance Criteria:

Given I am authenticated
When I POST /api/v1/auth/switch-client { client_id: "<uuid>" }
Then the response is 200 with a new access token containing client_id claim
And the new token expires in the same remaining window as the original

Given client_id belongs to a different org
When I POST /api/v1/auth/switch-client { client_id: "<foreign-uuid>" }
Then the response is 403 CLIENT_NOT_IN_ORG

Given client_id is null
When I POST /api/v1/auth/switch-client { client_id: null }
Then the response is 200 with a token with no client_id claim (all-clients mode)

Given client is deactivated (is_active=false)
When I POST /api/v1/auth/switch-client { client_id: "<inactive-uuid>" }
Then the response is 404 CLIENT_NOT_FOUND
```

---

### US-04: Assign Brand to Client

```
As an agency admin,
I want to assign an existing brand to a client,
So that all SKUs of that brand are grouped under the client.

Acceptance Criteria:

Given I am authenticated as admin or manager
And brand_id belongs to my org
When I PATCH /api/v1/brands/{id} with { client_id: "<uuid>" }
Then the brand is updated and response includes client_id

Given client_id belongs to a different org
When I PATCH /api/v1/brands/{id} with foreign client_id
Then the response is 403 CLIENT_NOT_IN_ORG

Given client_id is null
When I PATCH /api/v1/brands/{id} with { client_id: null }
Then the brand is unassigned from any client (org-level brand)
```

---

### US-05: Client-Scoped Data Views

```
As an agency analyst with active client context,
I want all data views (SKUs, content scores, alerts, reports)
to automatically filter to my active client,
So that I don't accidentally see or modify another client's data.

Acceptance Criteria:

Given my JWT contains client_id = "client-a-uuid"
When I GET /api/v1/skus
Then I only see SKUs whose brand.client_id = "client-a-uuid"
And SKUs belonging to client B are not visible

Given my JWT has no client_id (all-clients mode)
When I GET /api/v1/skus
Then I see all org's SKUs, with a client_name field on each

Given a SKU belongs to a brand with client_id = null (unassigned brand)
When I am in client context
Then this SKU is NOT visible (only explicitly assigned brands show)
```

---

### US-06: Deactivate Client

```
As an agency admin,
I want to deactivate a client I no longer manage,
So that their data is hidden from views without being destroyed.

Acceptance Criteria:

Given I am authenticated as admin
When I DELETE /api/v1/clients/{id}
Then the response is 204
And the client.is_active = false
And all brands assigned to that client are NOT deleted
And GET /api/v1/clients no longer shows the client
And GET /api/v1/skus in all-clients mode excludes deactivated client's brands

Given the client has active alerts or scheduled reports
When I DELETE /api/v1/clients/{id}
Then deactivation succeeds (data retained, views hidden)
```

---

### US-07: Per-Client Report Branding

```
As an agency manager,
I want Excel reports to be branded with the client's name,
So that I can send them directly to the client without editing.

Acceptance Criteria:

Given my JWT contains client_id
When I POST /api/v1/reports/content (or stock/reviews)
Then the generated Excel includes the client name in the header row
And filename is prefixed with client slug: "nestle-ru_content_2026-04-04.xlsx"
And only SKUs belonging to that client are included in the report
```

---

## Non-Functional Requirements

| Category | Requirement |
|----------|-------------|
| Performance | Client switch (new JWT) < 200ms |
| Security | client_id in token validated against org_id on every request |
| Backward compat | All existing queries work when client_id claim is absent |
| Isolation | No cross-client data visible regardless of JWT manipulation |
| Pagination | Client list: page/page_size, default 50 |

---

## Feature Matrix

| Feature | MVP | v1.1 | v2.0 |
|---------|-----|------|------|
| Client CRUD | ✅ | | |
| Brand → Client assignment | ✅ | | |
| JWT client context switching | ✅ | | |
| Client-scoped SKU/content views | ✅ | | |
| Per-client report branding | ✅ | | |
| Client deactivation | ✅ | | |
| Per-client user permissions | | ✅ | |
| Cross-client analytics dashboard | | ✅ | |
| Client-specific white-label login | | | ✅ |
| Billing per client | | | ✅ |
