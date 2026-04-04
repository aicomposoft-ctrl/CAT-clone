import apiClient from './client'

export interface DashboardRedZoneItem {
  sku_platform_id: string
  sku_name: string
  article: string | null
  platform_name: string
  content_total: number | null
  scored_at: string
}

export interface DashboardAlert {
  id: string
  alert_type: string
  sku_name: string
  platform_name: string
  value_before: number | null
  value_after: number | null
  triggered_at: string
  is_sent: boolean
}

export interface DashboardSummary {
  avg_content_score: number
  active_alerts_count: number
  distribution_coverage_pct: number
  monitored_sku_count: number
  red_zone: DashboardRedZoneItem[]
  recent_alerts: DashboardAlert[]
}

export const dashboardApi = {
  getSummary: (): Promise<DashboardSummary> =>
    apiClient.get('/dashboard/summary').then((r) => r.data),
}
