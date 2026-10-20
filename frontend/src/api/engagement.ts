import { apiFetch } from '@/lib/api'
import type { FeedbackFormData, HistorySession, LeadFormData } from '@/types'

export async function submitLead(
  data: LeadFormData,
): Promise<{ id: number; coupon_code: string }> {
  return apiFetch('/leads', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function submitFeedback(data: FeedbackFormData): Promise<void> {
  await apiFetch('/feedback', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function fetchHistory(): Promise<HistorySession[]> {
  const data = await apiFetch<{ sessions: HistorySession[] }>('/chat/history')
  return data.sessions || []
}

export async function deleteHistory(sessionId: string): Promise<void> {
  await apiFetch(`/chat/history/${encodeURIComponent(sessionId)}`, { method: 'DELETE' })
}
