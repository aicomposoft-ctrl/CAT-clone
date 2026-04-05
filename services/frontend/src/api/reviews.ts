import apiClient from './client'

export interface ReviewHistoryItem {
  id: string
  platform_id: string
  platform_name: string
  review_text: string
  rating: number
  sentiment: 'positive' | 'neutral' | 'negative' | null
  sentiment_score: string | null
  review_date: string
}

export interface ReviewHistoryResponse {
  sku_id: string
  total: number
  limit: number
  offset: number
  items: ReviewHistoryItem[]
}

export interface ReviewSummaryItem {
  platform_id: string
  platform_name: string
  review_count: number
  avg_rating: string | null
  positive_count: number
  neutral_count: number
  negative_count: number
  positive_pct: string
  neutral_pct: string
  negative_pct: string
  last_review_date: string | null
}

export interface ReviewSummaryResponse {
  sku_id: string
  date_from: string
  date_to: string
  total: number
  items: ReviewSummaryItem[]
}

export interface ReviewStats {
  sku_id: string
  review_count: number
  avg_rating: string | null
  rating_distribution: Record<string, number>
  sentiment_share: {
    positive: string
    neutral: string
    negative: string
  } | null
  weekly_trend: {
    week_start: string
    positive_share: string
    avg_rating: string | null
    review_count: number
  }[]
}

function cleanParams(obj: Record<string, unknown>) {
  return Object.fromEntries(Object.entries(obj).filter(([, v]) => v !== undefined && v !== null && v !== ''))
}

export const reviewsApi = {
  summary: (skuId: string, dateFrom?: string, dateTo?: string): Promise<ReviewSummaryResponse> =>
    apiClient
      .get('/reviews/summary', {
        params: cleanParams({ sku_id: skuId, date_from: dateFrom, date_to: dateTo }),
      })
      .then((r) => r.data),

  history: (
    skuId: string,
    options: {
      platformId?: string
      sentiment?: 'positive' | 'neutral' | 'negative'
      dateFrom?: string
      dateTo?: string
      limit?: number
      offset?: number
    } = {},
  ): Promise<ReviewHistoryResponse> =>
    apiClient
      .get('/reviews/history', {
        params: cleanParams({
          sku_id: skuId,
          platform_id: options.platformId,
          sentiment: options.sentiment,
          date_from: options.dateFrom,
          date_to: options.dateTo,
          limit: options.limit ?? 100,
          offset: options.offset ?? 0,
        }),
      })
      .then((r) => r.data),

  stats: (skuId: string, dateFrom?: string, dateTo?: string): Promise<ReviewStats> =>
    apiClient
      .get('/reviews/stats', {
        params: cleanParams({ sku_id: skuId, date_from: dateFrom, date_to: dateTo }),
      })
      .then((r) => r.data),
}
