# Pseudocode: Distribution Dashboard

**Feature:** `distribution-dashboard`
**Date:** 2026-04-01

---

## Backend: repository.list_plans (updated)

```python
async def list_plans(
    db: AsyncSession,
    org_id: UUID,
    platform_id: UUID | None,
    week_number: int | None,
    year: int | None,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:

    # Build base SELECT with JOINs for display fields
    stmt = (
        select(
            DistributionPlan.id,
            DistributionPlan.sku_id,
            DistributionPlan.platform_id,
            Platform.name.label("platform_name"),
            SKU.barcode.label("sku_barcode"),
            DistributionPlan.group_name,
            DistributionPlan.plan_tt_count,
            DistributionPlan.week_number,
            DistributionPlan.year,
        )
        .join(SKU, DistributionPlan.sku_id == SKU.id)
        .join(Platform, DistributionPlan.platform_id == Platform.id)
        .where(SKU.org_id == org_id)           # tenant isolation via JOIN
    )

    # Apply optional filters
    if platform_id is not None:
        stmt = stmt.where(DistributionPlan.platform_id == platform_id)
    if week_number is not None:
        stmt = stmt.where(DistributionPlan.week_number == week_number)
    if year is not None:
        stmt = stmt.where(DistributionPlan.year == year)

    # Count query (same filters, no pagination)
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # Paginated data query
    data_stmt = stmt.order_by(
        DistributionPlan.year.desc(),
        DistributionPlan.week_number.desc(),
        SKU.barcode.asc(),
    ).limit(limit).offset(offset)

    rows = (await db.execute(data_stmt)).mappings().all()
    return [dict(r) for r in rows], total
```

---

## Backend: service.list_distribution_plans (updated)

```python
async def list_distribution_plans(...) -> tuple[list[DistributionPlanRow], int]:
    items, total = await repository.list_plans(...)

    # items is list[dict] (not ORM objects) — use dict unpacking
    rows = [DistributionPlanRow(**item) for item in items]
    return rows, total
```

---

## Frontend: Filter Normalisation Utility

```typescript
// Normalise filters before use in queryKey — omit undefined values to prevent
// React Query cache misses when keys contain undefined fields.
function normaliseFilters(f: DistributionFilters): Record<string, unknown> {
    return Object.fromEntries(
        Object.entries(f).filter(([, v]) => v !== undefined && v !== null)
    )
}
```

---

## Frontend: useDistributionPlans hook

```typescript
function useDistributionPlans(filters: DistributionFilters) {
    const normalisedFilters = normaliseFilters(filters)
    return useQuery({
        queryKey: ['distribution-plans', normalisedFilters],
        queryFn: () => distributionApi.list(filters),
        staleTime: 30_000,
        placeholderData: keepPreviousData,  // no flash on filter change
    })
}
```

---

## Frontend: useDeletePlan hook

```typescript
// RQ v5 convention: call useQueryClient() inside the hook, not as a parameter.
function useDeletePlan() {
    const queryClient = useQueryClient()
    return useMutation({
        mutationFn: (id: string) => distributionApi.deletePlan(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['distribution-plans'] })
            message.success('Plan row deleted')
        },
        onError: () => {
            message.error('Failed to delete — try again')
        },
    })
}
```

---

## Frontend: DistributionPage (index.tsx)

```typescript
function DistributionPage() {
    // Read initial filters from URL
    const [searchParams, setSearchParams] = useSearchParams()
    const filters = parseFilters(searchParams)   // extract week/year/platform_id/page

    const { data, isLoading, isError, refetch } = useDistributionPlans(filters)
    const deleteMutation = useDeletePlan(queryClient)
    const { role } = useAuth()
    const canEdit = role === 'manager' || role === 'admin'

    function handleFilterChange(next: DistributionFilters) {
        // Merge with current, reset page to 1 when filters change
        setSearchParams({ ...next, page: '1' })
    }

    function handlePageChange(page: number) {
        setSearchParams(prev => ({ ...parseFilters(prev), page: String(page) }))
    }

    return (
        <PageLayout
            title="Distribution Plans"
            extra={canEdit && <UploadPlanButton onSuccess={refetch} />}
        >
            <DistributionFilters value={filters} onChange={handleFilterChange} />
            
            IF isError:
                <Alert type="error" message="Failed to load plans" action={<Retry />} />
            ELSE:
                <DistributionTable
                    data={data?.items ?? []}
                    total={data?.total ?? 0}
                    page={filters.page ?? 1}
                    loading={isLoading}
                    canDelete={canEdit}
                    onDelete={deleteMutation.mutate}
                    onPageChange={handlePageChange}
                />
        </PageLayout>
    )
}
```

---

## Frontend: UploadPlanButton

```typescript
function UploadPlanButton({ onSuccess }: { onSuccess: () => void }) {
    const [open, setOpen] = useState(false)
    const [result, setResult] = useState<UploadResult | null>(null)
    const [uploading, setUploading] = useState(false)

    async function handleUpload(file: File) {
        IF file.size > 5 * 1024 * 1024:
            message.error('File too large (max 5 MB)')
            RETURN

        setUploading(true)
        TRY:
            result = await distributionApi.uploadCSV(file)
            setResult(result)
            IF result.imported > 0:
                onSuccess()   // trigger table refresh
        CATCH error:
            IF error.status == 422:
                show error.detail in modal
            ELSE:
                message.error('Server error — contact support')
        FINALLY:
            setUploading(false)
    }

    return (
        <Button onClick={() => setOpen(true)}>Upload Plan</Button>
        <Modal open={open} onClose={() => { setOpen(false); setResult(null) }}>
            IF result is null:
                <Dragger
                    accept=".csv"
                    beforeUpload={(file) => { handleUpload(file); return false }}
                    showUploadList={false}
                >
                    Drag CSV here or click to select
                </Dragger>
            ELSE:
                <UploadResultCard result={result} />
                <Button onClick={closeAndReset}>Done</Button>
        </Modal>
    )
}
```

---

## Frontend: DistributionTable

```typescript
function DistributionTable({ data, total, page, loading, canDelete, onDelete, onPageChange }) {
    const columns = [
        { title: 'SKU Barcode', dataIndex: 'sku_barcode', width: 160 },
        { title: 'Platform', dataIndex: 'platform_name', width: 140 },
        { title: 'Group', dataIndex: 'group_name', width: 180 },
        { title: 'Plan Qty', dataIndex: 'plan_tt_count', width: 100, align: 'right' },
        { title: 'Week', dataIndex: 'week_number', width: 70, align: 'center' },
        { title: 'Year', dataIndex: 'year', width: 70, align: 'center' },
        IF canDelete: {
            title: '',
            width: 60,
            render: (row) =>
                <Popconfirm
                    title="Delete this plan row?"
                    onConfirm={() => onDelete(row.id)}
                >
                    <DeleteOutlined className="delete-icon" />
                </Popconfirm>
        }
    ]

    return (
        <Table
            rowKey="id"
            dataSource={data}
            columns={columns}
            loading={loading}
            pagination={{ current: page, total, pageSize: 50, onChange: onPageChange,
                         showTotal: (t) => `${t} rows` }}
            locale={{ emptyText: <EmptyDistribution /> }}
        />
    )
}
```
