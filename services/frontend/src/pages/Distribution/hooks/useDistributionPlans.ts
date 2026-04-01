import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { distributionApi } from '../../../api/stock'
import type { DistributionFilters } from '../../../api/stock'

function normaliseFilters(filters: DistributionFilters): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(filters).filter(([, v]) => v !== undefined && v !== null)
  )
}

export function useDistributionPlans(filters: DistributionFilters) {
  const normalisedFilters = normaliseFilters(filters)
  return useQuery({
    queryKey: ['distribution-plans', normalisedFilters],
    queryFn: () => distributionApi.list(filters),
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  })
}
