import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { distributionApi } from '../../../api/stock'
import type { DistributionFilters } from '../../../api/stock'

function normaliseFilters(filters: DistributionFilters): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(filters).filter(([, v]) => v !== undefined && v !== null)
  )
}

export function useDistributionPlans(filters: DistributionFilters) {
  // Normalise once — both queryKey and queryFn use the same object
  // so the cache key always matches the actual fetch arguments.
  const normalisedFilters = normaliseFilters(filters) as DistributionFilters
  return useQuery({
    queryKey: ['distribution-plans', normalisedFilters],
    queryFn: () => distributionApi.list(normalisedFilters),
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  })
}
