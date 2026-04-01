import { Alert, Button, Typography } from 'antd'
import { useSearchParams } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'
import { DistributionFilters } from './components/DistributionFilters'
import { DistributionTable } from './components/DistributionTable'
import { UploadPlanButton } from './components/UploadPlanButton'
import { useDeletePlan } from './hooks/useDeletePlan'
import { useDistributionPlans } from './hooks/useDistributionPlans'
import type { DistributionFilters as Filters } from './types'

const currentYear = new Date().getFullYear()
const currentWeek = getISOWeek(new Date())

function getISOWeek(date: Date): number {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()))
  d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7))
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1))
  return Math.ceil(((d.getTime() - yearStart.getTime()) / 86_400_000 + 1) / 7)
}

function parseFilters(params: URLSearchParams): Filters {
  return {
    week_number: params.get('week') ? Number(params.get('week')) : currentWeek,
    year: params.get('year') ? Number(params.get('year')) : currentYear,
    platform_id: params.get('platform_id') ?? undefined,
    page: params.get('page') ? Number(params.get('page')) : 1,
    size: 50,
  }
}

function filtersToParams(filters: Filters): Record<string, string> {
  const p: Record<string, string> = {}
  if (filters.week_number != null) p.week = String(filters.week_number)
  if (filters.year != null) p.year = String(filters.year)
  if (filters.platform_id) p.platform_id = filters.platform_id
  if (filters.page && filters.page > 1) p.page = String(filters.page)
  return p
}

export default function DistributionPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = parseFilters(searchParams)
  const { data, isLoading, isError, refetch } = useDistributionPlans(filters)
  const deleteMutation = useDeletePlan()
  const { role } = useAuth()
  const canEdit = role === 'manager' || role === 'admin'

  const handleFilterChange = useCallback(
    (next: Filters) => {
      setSearchParams(filtersToParams({ ...next, page: 1 }), { replace: true })
    },
    [setSearchParams]
  )

  const handlePageChange = useCallback(
    (page: number) => {
      setSearchParams(filtersToParams({ ...filters, page }), { replace: true })
    },
    [filters, setSearchParams]
  )

  return (
    <div style={{ padding: '24px' }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16,
        }}
      >
        <Typography.Title level={4} style={{ margin: 0 }}>
          Distribution Plans
        </Typography.Title>
        {canEdit && <UploadPlanButton onSuccess={() => refetch()} />}
      </div>

      <DistributionFilters value={filters} onChange={handleFilterChange} />

      {isError ? (
        <Alert
          type="error"
          message="Failed to load plans"
          action={
            <Button size="small" onClick={() => refetch()}>
              Retry
            </Button>
          }
        />
      ) : (
        <DistributionTable
          data={data?.items ?? []}
          total={data?.total ?? 0}
          page={filters.page ?? 1}
          loading={isLoading}
          canDelete={canEdit}
          onDelete={(id) => deleteMutation.mutate(id)}
          onPageChange={handlePageChange}
        />
      )}
    </div>
  )
}
