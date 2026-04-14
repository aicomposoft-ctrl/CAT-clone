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

export interface AlertConfig {
  id: string
  org_id: string
  sku_id: string | null
  platform_id: string | null
  alert_type: 'content_drop' | 'oos'
  threshold: number | null
  email_recipients: string[]
  is_active: boolean
  created_at: string
}

export interface AlertConfigPage {
  items: AlertConfig[]
  total: number
  page: number
  size: number
}

export interface AlertConfigCreateRequest {
  alert_type: 'content_drop' | 'oos'
  sku_id?: string | null
  platform_id?: string | null
  threshold?: number | null
  email_recipients: string[]
  is_active?: boolean
}

export interface AlertConfigUpdateRequest {
  threshold?: number | null
  email_recipients?: string[]
  is_active?: boolean
}

export interface AlertCheckResult {
  events_created: number
  emails_sent: number
  errors: string[]
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

export const alertConfigsApi = {
  list: (params?: { page?: number; size?: number }): Promise<AlertConfigPage> =>
    apiClient.get('/alerts/configs', { params }).then((r) => r.data),

  create: (data: AlertConfigCreateRequest): Promise<AlertConfig> =>
    apiClient.post('/alerts/configs', data).then((r) => r.data),

  update: (id: string, data: AlertConfigUpdateRequest): Promise<AlertConfig> =>
    apiClient.patch(`/alerts/configs/${id}`, data).then((r) => r.data),

  remove: (id: string): Promise<void> =>
    apiClient.delete(`/alerts/configs/${id}`).then(() => undefined),

  check: (): Promise<AlertCheckResult> =>
    apiClient.post('/alerts/check').then((r) => r.data),
}
