import type { FeedbackFormData, HistorySession, LeadFormData } from '@/types'

const API_BASE = '/api/v1'

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('crmbot_token')
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

export async function submitLead(data: LeadFormData): Promise<{ id: number; coupon_code: string }> {
  const response = await fetch(`${API_BASE}/leads`, {
    method: 'POST', headers: authHeaders(), body: JSON.stringify(data),
  })
  if (!response.ok) throw new Error(`Lead API error: ${response.status}`)
  return response.json()
}

export async function submitFeedback(data: FeedbackFormData): Promise<void> {
  const response = await fetch(`${API_BASE}/feedback`, {
    method: 'POST', headers: authHeaders(), body: JSON.stringify(data),
  })
  if (!response.ok) throw new Error(`Feedback API error: ${response.status}`)
}

export async function fetchHistory(): Promise<HistorySession[]> {
  const response = await fetch(`${API_BASE}/chat/history`, { headers: authHeaders() })
  if (!response.ok) throw new Error(`History API error: ${response.status}`)
  const data = await response.json()
  return data.sessions || []
}

export async function deleteHistory(sessionId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/chat/history/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE', headers: authHeaders(),
  })
  if (!response.ok) throw new Error(`Delete history error: ${response.status}`)
}
