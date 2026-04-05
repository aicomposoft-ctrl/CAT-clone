import apiClient from './client'
import { cleanParams } from './utils'

// Prices are Decimal on the backend — serialized as strings in JSON
export interface PriceLatestItem {
  platform_id: string
  platform_name: string
  price: string
  original_price: string
  discount_pct: string
  promo_label: string | null
  collected_at: string
}

export interface PriceLatestResponse {
  sku_id: string
  cheapest_platform_id: string | null
  items: PriceLatestItem[]
}

export interface PriceAnomaly {
  platform_id: string
  platform_name: string
  date: string
  price_before: string
  price_after: string
  change_abs: string
  change_pct: string
  direction: 'up' | 'down'
}

export interface PriceAnomaliesResponse {
  sku_id: string
  threshold: number
  items: PriceAnomaly[]
}

export interface PriceHistoryItem {
  id: string
  platform_id: string
  platform_name: string
  price: string
  original_price: string
  discount_pct: string
  promo_label: string | null
  collected_at: string
}

export interface PriceHistoryResponse {
  sku_id: string
  items: PriceHistoryItem[]
  total: number
}

export interface PriceStats {
  sku_id: string
  platform_id: string | null
  date_from: string
  date_to: string
  snapshot_count: number
  price_min: string | null
  price_max: string | null
  price_avg: string | null
  price_median: string | null
  change_abs: string | null
  change_pct: string | null
  discount_avg: string | null
}


export const pricesApi = {
  latest: (skuId: string): Promise<PriceLatestResponse> =>
    apiClient.get('/prices/latest', { params: { sku_id: skuId } }).then((r) => r.data),

  anomalies: (
    skuId: string,
    dateFrom?: string,
    dateTo?: string,
    threshold?: number,
  ): Promise<PriceAnomaliesResponse> =>
    apiClient
      .get('/prices/anomalies', {
        params: cleanParams({ sku_id: skuId, date_from: dateFrom, date_to: dateTo, threshold }),
      })
      .then((r) => r.data),

  history: (
    skuId: string,
    platformId?: string,
    dateFrom?: string,
    dateTo?: string,
  ): Promise<PriceHistoryResponse> =>
    apiClient
      .get('/prices/history', {
        params: cleanParams({ sku_id: skuId, platform_id: platformId, date_from: dateFrom, date_to: dateTo }),
      })
      .then((r) => r.data),

  stats: (
    skuId: string,
    platformId?: string,
    dateFrom?: string,
    dateTo?: string,
  ): Promise<PriceStats> =>
    apiClient
      .get('/prices/stats', {
        params: cleanParams({ sku_id: skuId, platform_id: platformId, date_from: dateFrom, date_to: dateTo }),
      })
      .then((r) => r.data),
}
