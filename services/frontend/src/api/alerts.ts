import apiClient from './client'

export interface AlertEvent {
  id: string
  config_id: string
  sku_platform_id: string
  scored_at: string
  triggered_at: string
  alert_type: 'content_drop' | 'oos' | 'price_change' | 'competitor_promo'
  value_before: number | null
  value_after: number | null
  is_sent: boolean
  sent_at: string | null
}

export interface AlertEventPage {
  items: AlertEvent[]
  total: number
  page: number
  size: number
}

export interface AlertFilters {
  alert_type?: string
  is_sent?: boolean
  page?: number
  size?: number
}

function cleanParams(obj: Record<string, unknown>) {
  return Object.fromEntries(Object.entries(obj).filter(([, v]) => v !== undefined && v !== null))
}

export const alertsApi = {
  list: (filters: AlertFilters = {}): Promise<AlertEventPage> =>
    apiClient.get('/alerts/events', { params: cleanParams(filters as Record<string, unknown>) }).then((r) => r.data),

  acknowledge: (id: string): Promise<AlertEvent> =>
    apiClient.patch(`/alerts/events/${id}/acknowledge`).then((r) => r.data),
}
