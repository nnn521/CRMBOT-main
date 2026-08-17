import type { ChatRequest, ChatResponse } from '@/types'

const API_BASE = '/api/v1'

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('crmbot_token')
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}

export interface ChatSessionSummary {
  session_id: string
  last_message_preview: string
  last_updated: string | null
  message_count: number
}

/** Fetch chat sessions from conversations table (for admin B端 real-time list) */
export async function fetchChatSessions(): Promise<ChatSessionSummary[]> {
  const res = await fetch(`${API_BASE}/chat/sessions`, { headers: authHeaders() })
  if (!res.ok) throw new Error(`Chat sessions API error: ${res.status}`)
  return res.json()
}

export async function sendChatMessage(
  sessionId: string,
  message: string,
  history?: { role: string; content: string }[]
): Promise<ChatResponse> {
  const body: ChatRequest = {
    session_id: sessionId,
    message,
    history,
  }

  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(body),
  })

  if (!res.ok) {
    throw new Error(`Chat API error: ${res.status}`)
  }

  return res.json()
}
