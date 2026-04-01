/**
 * API client functions for the stock domain.
 */
import apiClient from './client'

export interface DistributionPlanRow {
  id: string
  sku_id: string
  platform_id: string
  platform_name: string
  sku_barcode: string | null
  group_name: string
  plan_tt_count: number
  week_number: number
  year: number
}

export interface DistributionPlanPage {
  items: DistributionPlanRow[]
  total: number
  page: number
  size: number
}

export interface RowError {
  row: number
  field: string
  message: string
}

export interface UploadResult {
  imported: number
  errors: RowError[]
}

export interface DistributionFilters {
  platform_id?: string
  week_number?: number
  year?: number
  page?: number
  size?: number
}

function normaliseFilters(filters: DistributionFilters): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(filters).filter(([, v]) => v !== undefined && v !== null)
  )
}

export const distributionApi = {
  list: (filters: DistributionFilters): Promise<DistributionPlanPage> =>
    apiClient
      .get('/stock/distribution-plan', { params: normaliseFilters(filters) })
      .then((r) => r.data),

  deletePlan: (id: string): Promise<void> =>
    apiClient.delete(`/stock/distribution-plan/${id}`),

  uploadCSV: (file: File): Promise<UploadResult> => {
    const form = new FormData()
    form.append('file', file)
    return apiClient
      .post('/stock/distribution-plan', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data)
  },
}
