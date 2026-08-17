const API_BASE = '/api/v1'

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('crmbot_token')
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}

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
  const res = await fetch(`${API_BASE}/reports/dashboard`, { headers: authHeaders() })
  if (!res.ok) throw new Error(`Dashboard API error: ${res.status}`)
  return res.json()
}

/* ── 成交记录 ── */

export interface DealRecord {
  customer_name: string
  title: string
  updated_at: string | null
  status: string
}

export async function fetchDeals(limit = 10): Promise<DealRecord[]> {
  const res = await fetch(`${API_BASE}/reports/deals?limit=${limit}`, { headers: authHeaders() })
  if (!res.ok) throw new Error(`Deals API error: ${res.status}`)
  return res.json()
}

/* ── AI 分析 ── */

export async function analyzeReport(data: string): Promise<string> {
  const res = await fetch(`${API_BASE}/reports/analyze`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ data }),
  })
  if (!res.ok) throw new Error(`Analyze API error: ${res.status}`)
  const result = await res.json()
  return result.analysis
}
