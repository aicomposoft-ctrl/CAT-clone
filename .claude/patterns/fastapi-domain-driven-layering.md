# Pattern: FastAPI Domain-Driven Layering (Router / Service / Repository)

## Maturity: 🔴 Alpha
## Used in: CAT (Commerce Analytics Tool)
## Extracted: 2026-03-27
## Last updated: 2026-03-27
## Version: v1.0

## When to Use

FastAPI applications with 3+ domain areas, where business logic must be tested
independently of HTTP and database layers. Use when:
- You want to unit-test service logic without mocking HTTP
- Multiple routes share the same business logic
- Celery workers and API routes share domain operations

## When NOT to Use

- Tiny CRUD apps with <3 endpoints (over-engineering)
- Serverless functions with single responsibility
- Prototypes where velocity > maintainability

## Prerequisites

- FastAPI + SQLAlchemy (async)
- Pydantic v2 for schema validation
- Each domain has clearly bounded responsibility

## Implementation

### Directory Structure per Domain

```
app/
├── core/
│   ├── config.py      # pydantic-settings, env var loading
│   ├── database.py    # engine, AsyncSession factory
│   ├── deps.py        # FastAPI dependencies (get_db, get_current_user)
│   └── security.py    # JWT, hashing
└── {{domain}}/        # e.g. content, orders, users, billing
    ├── models.py      # SQLAlchemy ORM models
    ├── schemas.py     # Pydantic request/response schemas
    ├── service.py     # Business logic (no HTTP, no raw DB)
    ├── repository.py  # DB queries (always filters tenant_id)
    └── router.py      # FastAPI routes (thin — delegates to service)
```

### Layer Responsibilities

```python
# --- router.py (thin HTTP layer) ---
@router.get("/{id}", response_model=ItemResponse)
async def get_item(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return await item_service.get(db, id=id, org_id=user.org_id)
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Not found")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Forbidden")


# --- service.py (business logic, no HTTP imports) ---
async def get(db: AsyncSession, id: UUID, org_id: UUID) -> Item:
    item = await item_repo.get(db, id=id, org_id=org_id)
    if not item:
        raise ResourceNotFoundError(f"Item {id} not found")
    return item


# --- repository.py (DB queries, always scoped to tenant) ---
async def get(db: AsyncSession, id: UUID, org_id: UUID) -> Item | None:
    result = await db.execute(
        select(Item).where(Item.id == id, Item.org_id == org_id)
    )
    return result.scalar_one_or_none()
```

### Error Propagation Convention

```python
# service raises domain exceptions (not HTTP-aware)
class ResourceNotFoundError(Exception): pass
class PermissionError(Exception): pass
class ValidationError(Exception): pass

# router converts to HTTP exceptions
# This lets services be called from Celery workers, CLI, etc.
```

## Variants

### Variant A: With Celery task reuse

```python
# Celery task reuses service layer directly (no HTTP involved)
@celery_app.task
async def process_item_task(item_id: str, org_id: str):
    async with get_db_session() as db:
        await item_service.process(db, id=UUID(item_id), org_id=UUID(org_id))
```

### Variant B: With dependency injection testing

```python
# In tests: override get_db dependency with test session
app.dependency_overrides[get_db] = lambda: test_db_session
```

## Gotchas

- **Service must not import router modules**: Creates circular imports. Service → Repository → Models only.
- **Repository must not call other repositories**: If you need cross-domain data, do it in the service layer or create a dedicated orchestration service.
- **Async session expire_on_commit**: Set `expire_on_commit=False` in session factory, or explicitly refresh objects after commit. Default behavior silently returns stale data.
- **Router must not contain logic**: If you find yourself writing `if`/`for` in a router, extract to service.

## Related Artifacts

- `patterns/multi-tenant-saas-isolation.md` — repository always filters by org_id
- `snippets/async-db-session-dependency.py` — FastAPI dependency for AsyncSession

## Changelog
- v1.0: Initial extraction from CAT project (2026-03-27)
