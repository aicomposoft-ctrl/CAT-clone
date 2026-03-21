# Coding Style — CAT

## Python / FastAPI (Backend)

### File Organization

```
services/api/app/
├── main.py              # FastAPI app, startup validation, middleware
├── core/
│   ├── config.py        # Settings (pydantic-settings), secret validation
│   ├── database.py      # SQLAlchemy engine, session factory, Base
│   ├── deps.py          # FastAPI dependencies (get_db, get_current_user)
│   └── security.py      # JWT encode/decode, password hashing
├── {domain}/            # content, stock, reviews, prices, reports, alerts, auth
│   ├── models.py        # SQLAlchemy ORM models
│   ├── schemas.py       # Pydantic request/response schemas
│   ├── service.py       # Business logic (no HTTP, no DB sessions directly)
│   ├── repository.py    # DB queries (takes db: Session, always filters org_id)
│   └── router.py        # FastAPI routes (thin — delegates to service)
```

### Naming Conventions

```python
# Files: snake_case
content_scorer.py, sku_repository.py

# Classes: PascalCase
class ContentScore, class SKURepository

# Functions/methods: snake_case
def get_content_scores(org_id: UUID, sku_id: UUID) -> list[ContentScore]

# Constants: UPPER_SNAKE_CASE
MAX_SKU_PER_REQUEST = 1000
DEFAULT_CONTENT_THRESHOLD = 70.0

# Pydantic models: PascalCase with Request/Response suffix
class ContentScoreResponse(BaseModel), class SKUCreateRequest(BaseModel)

# DB table names: snake_case plural
content_scores, distribution_plans, price_snapshots

# Route paths: kebab-case
/api/v1/content-scores, /api/v1/sku-platforms
```

### Async Patterns

```python
# Database queries: use async session
async def get_scores(db: AsyncSession, org_id: UUID):
    result = await db.execute(
        select(ContentScore).where(ContentScore.org_id == org_id)
    )
    return result.scalars().all()

# Scraping: always async with rate limiting
async def collect_content(self, sku: SKU) -> ContentData:
    async with self.semaphore:  # concurrency control
        await asyncio.sleep(1 / self.rate_limit)
        ...
```

### Error Handling

```python
# Domain errors: raise HTTPException in router, not in service
# Service raises: ValueError, PermissionError, ResourceNotFoundError
# Router catches and converts to HTTPException

# Never expose internal errors to client
@router.get("/skus/{id}")
async def get_sku(id: UUID, db: AsyncSession = Depends(get_db)):
    try:
        return await sku_service.get(id, db)
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="SKU not found")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Forbidden")
```

## TypeScript / React (Frontend)

### File Organization

```
services/frontend/src/
├── pages/{Domain}/           # One directory per page/feature
│   ├── index.tsx             # Page component (route entry point)
│   ├── components/           # Page-specific components
│   └── hooks/                # Page-specific hooks
├── components/               # Shared UI components
├── api/                      # API client (axios instances, typed endpoints)
│   ├── client.ts             # Axios instance with JWT interceptor
│   └── {domain}.ts           # Typed API functions per domain
├── hooks/                    # Global hooks (useAuth, useOrg)
├── store/                    # Zustand or React Query stores
└── types/                    # Global TypeScript types
```

### Naming Conventions

```typescript
// Components: PascalCase
const ContentScoreTable: React.FC<Props> = ...
const SKUDetailDrawer: React.FC<Props> = ...

// Hooks: camelCase with 'use' prefix
const useContentScores = (filters: ScoreFilters) => ...

// API functions: camelCase with HTTP verb
const getContentScores = (filters: ScoreFilters): Promise<ContentScore[]> => ...
const createSKU = (data: SKUCreateRequest): Promise<SKU> => ...

// Types/Interfaces: PascalCase
interface ContentScore { ... }
type SKUStatus = 'active' | 'inactive'

// Constants: UPPER_SNAKE_CASE
const DEFAULT_PAGE_SIZE = 50
const CONTENT_SCORE_THRESHOLDS = { green: 80, yellow: 50 }
```

### React Patterns

```typescript
// Prefer React Query for server state
const { data: scores, isLoading } = useQuery({
  queryKey: ['content-scores', filters],
  queryFn: () => getContentScores(filters),
})

// Use Ant Design Table with server-side pagination
<Table
  dataSource={scores}
  pagination={{ pageSize: 50, total, onChange: setPage }}
  loading={isLoading}
  rowKey="id"
/>
```

## Known Gotchas

### Python

- **Alembic env.py**: `target_metadata` must include all SQLAlchemy Base subclasses. Missing a model = silent migration gaps.
- **Celery task retries**: `max_retries=3` with `countdown=2**self.request.retries` for exponential backoff. Never `retry()` without `max_retries`.
- **SQLAlchemy async**: `AsyncSession` does NOT auto-expire on commit by default. Set `expire_on_commit=False` in session factory or refresh explicitly.
- **ClickHouse driver**: Use `clickhouse-driver` for sync or `asynch` for async. They have different connection string formats.
- **openpyxl column widths**: Must be set explicitly after writing data — Worksheet.column_dimensions[col].width. Auto-size not supported.
- **CLIP / HuggingFace**: Models download on first use to `~/.cache/huggingface/`. In Docker, pre-download to a mounted volume or the container will re-download on every restart.

### TypeScript / React

- **Ant Design Table `rowKey`**: Must be unique. Using array index causes re-render bugs with pagination. Always use `id` field.
- **ECharts resize**: Call `chart.resize()` on window resize AND on panel/drawer show. Missing this causes chart squishing.
- **React Query cache**: `queryKey` must be fully specified — include all filters in the key array, not just the function name.
- **Axios interceptor**: JWT refresh must handle concurrent requests (401 race condition). Use a single refresh promise with a queue.

### Infrastructure

- **Celery Beat + replicas**: Beat scheduler must have exactly 1 replica. Multiple replicas = duplicate tasks.
- **PostgreSQL RLS**: RLS policies are NOT inherited by superuser connections. Test with application user, not postgres superuser.
- **MinIO bucket policy**: Default policy is private. Explicitly create buckets in startup script — don't assume they exist.
- **Playwright in Docker**: Requires `--ipc=host` and Chromium dependencies. Use `mcr.microsoft.com/playwright/python` base image.
