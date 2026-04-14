import type { DistributionFilters, DistributionPlanRow } from '../../api/stock'

export type { DistributionPlanRow, DistributionFilters }

export interface DistributionTableProps {
  data: DistributionPlanRow[]
  total: number
  page: number
  loading: boolean
  canDelete: boolean
  onDelete: (id: string) => void
  onPageChange: (page: number) => void
}

export interface DistributionFiltersProps {
  value: DistributionFilters
  onChange: (filters: DistributionFilters) => void
}
