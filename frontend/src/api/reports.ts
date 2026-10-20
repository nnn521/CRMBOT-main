import { apiFetch } from '@/lib/api'

/* ── Dashboard 聚合数据 ── */

export interface DashboardSummary {
  total_sessions: number
  conversion_rate: number
  active_customers: number
  new_leads_this_month: number
}

export interface MonthlyTrend {
  month: string
  count: number
}

export interface FunnelData {
  total_leads: number
  contacted: number
  interested: number
  negotiating: number
  closed: number
}

export interface StatusBreakdown {
  new: number
  active: number
  negotiating: number
  closed: number
  lost: number
}

export interface DashboardData {
  summary: DashboardSummary
  monthly_trend: MonthlyTrend[]
  funnel: FunnelData
  status_breakdown: StatusBreakdown
}

export async function fetchDashboard(): Promise<DashboardData> {
  return apiFetch('/reports/dashboard')
}

/* ── 成交记录 ── */

export interface DealRecord {
  customer_name: string
  title: string
  updated_at: string | null
  status: string
}

export async function fetchDeals(limit = 10): Promise<DealRecord[]> {
  return apiFetch(`/reports/deals?limit=${limit}`)
}

/* ── AI 分析 ── */

export async function analyzeReport(data: string): Promise<string> {
  const result = await apiFetch<{ analysis: string }>('/reports/analyze', {
    method: 'POST',
    body: JSON.stringify({ data }),
  })
  return result.analysis
}
