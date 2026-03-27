# Pattern: Multi-Tenant SaaS Data Isolation

## Maturity: 🔴 Alpha
## Used in: CAT (Commerce Analytics Tool)
## Extracted: 2026-03-27
## Last updated: 2026-03-27
## Version: v1.0

## When to Use

Any SaaS application where multiple organizations share a single database instance.
Applies whenever data from different tenants (orgs, companies, workspaces) must be
strictly separated at the application and database level.

## When NOT to Use

- Single-tenant applications (only one org in the system)
- Separate database per tenant strategy (no shared tables)
- Read-only public datasets (no tenant ownership)

## Prerequisites

- PostgreSQL (for RLS) or equivalent DB with row-level policy support
- ORM with filter composition (SQLAlchemy, Django ORM, Prisma, etc.)
- `org_id` (or equivalent tenant identifier) column on every tenant-owned table
- Authenticated request context that provides `current_user.org_id`

## Implementation

### Layer 1: Application-Level Filtering (Mandatory)

Every query in the repository layer MUST include `org_id` filter. No exceptions.

```python
# Python / SQLAlchemy
class SKURepository:
    async def list(self, db: AsyncSession, org_id: UUID) -> list[SKU]:
        result = await db.execute(
            select(SKU).where(SKU.org_id == org_id)
        )
        return result.scalars().all()

    async def get(self, db: AsyncSession, id: UUID, org_id: UUID) -> SKU | None:
        result = await db.execute(
            select(SKU).where(SKU.org_id == org_id, SKU.id == id)
        )
        return result.scalar_one_or_none()
```

### Layer 2: PostgreSQL Row-Level Security (Defense-in-Depth)

```sql
-- Enable RLS on every tenant-scoped table
ALTER TABLE skus ENABLE ROW LEVEL SECURITY;

-- Policy: app user can only see their org's rows
CREATE POLICY org_isolation ON skus
    FOR ALL
    TO app_user
    USING (org_id = current_setting('app.current_org_id')::uuid);

-- Set org context in each request (in DB session setup)
SET LOCAL app.current_org_id = '{{ORG_UUID}}';
```

### Layer 3: Schema Convention

Every tenant-owned table must have:

```sql
CREATE TABLE {{table_name}} (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    -- ... domain columns
);

-- Mandatory index for performance
CREATE INDEX idx_{{table_name}}_org_id ON {{table_name}}(org_id);
CREATE INDEX idx_{{table_name}}_org_created ON {{table_name}}(org_id, created_at DESC);
```

## Variants

### Variant A: Django ORM

```python
class TenantScopedManager(models.Manager):
    def for_org(self, org_id):
        return self.get_queryset().filter(org_id=org_id)

class SKU(models.Model):
    objects = TenantScopedManager()
    org = models.ForeignKey(Organization, on_delete=models.CASCADE)
```

### Variant B: Prisma (TypeScript)

```typescript
// Middleware that enforces org_id on all queries
prisma.$use(async (params, next) => {
  const tenantModels = ['Sku', 'ContentScore', 'PriceSnapshot']
  if (tenantModels.includes(params.model) && params.action !== 'create') {
    params.args.where = { ...params.args.where, orgId: currentOrgId }
  }
  return next(params)
})
```

## Gotchas

- **RLS bypassed by superuser**: PostgreSQL superuser connections bypass RLS. Always test with the application database user, never with `postgres` superuser.
- **Missing index degrades performance**: Without `(org_id, created_at)` index, queries become full table scans as data grows.
- **Cross-tenant admin queries**: If your admin panel needs cross-tenant queries, use a separate connection/user that bypasses RLS intentionally and explicitly.
- **Soft deletes**: If using soft deletes, include `deleted_at IS NULL` filter alongside `org_id` — both are required.

## Related Artifacts

- `snippets/cross-tenant-isolation-test.py` — pytest pattern to verify isolation
- `rules/security.md` — OWASP checklist with multi-tenancy requirements

## Changelog
- v1.0: Initial extraction from CAT project (2026-03-27)
