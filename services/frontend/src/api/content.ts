import apiClient from './client'

export interface ContentScoreItem {
  id: string
  sku_platform_id: string
  sku_id: string
  sku_name: string
  article: string | null
  brand_id: string
  brand_name: string
  platform_id: string
  platform_name: string
  platform_url: string | null
  scored_at: string
  content_total: number | null
  image_score: number | null
  description_score: number | null
  composition_score: number | null
  collected_image_url: string | null
  created_at: string
}

export interface ContentScorePage {
  items: ContentScoreItem[]
  total: number
  page: number
  size: number
}

export interface ContentScoreDrilldown extends ContentScoreItem {
  collected_description: string | null
  collected_composition: string | null
  collected_title: string | null
  reference_image_url: string | null
  reference_description: string | null
  reference_composition: string | null
  history: { scored_at: string; content_total: number | null }[]
}

export interface ContentScoreFilters {
  platform_id?: string
  brand_id?: string
  score_max?: number
  score_min?: number
  scored_at?: string
  page?: number
  size?: number
}

function cleanParams(obj: Record<string, unknown>) {
  return Object.fromEntries(Object.entries(obj).filter(([, v]) => v !== undefined && v !== null))
}

export const contentApi = {
  list: (filters: ContentScoreFilters = {}): Promise<ContentScorePage> =>
    apiClient.get('/content/scores', { params: cleanParams(filters as Record<string, unknown>) }).then((r) => r.data),

  drilldown: (skuPlatformId: string): Promise<ContentScoreDrilldown> =>
    apiClient.get(`/content/scores/${skuPlatformId}/drilldown`).then((r) => r.data),
}
