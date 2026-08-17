import type { Session, ChatMessage } from '@/types'

const API_BASE = '/api/v1'

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('crmbot_token')
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}

export async function fetchSessions(): Promise<{ sessions: Session[]; total: number }> {
  const res = await fetch(`${API_BASE}/chat/sessions`, { headers: authHeaders() })
  if (!res.ok) throw new Error(`Sessions API error: ${res.status}`)
  const data = await res.json()
  const sessions: Session[] = (data.sessions || data).map((item: any) => ({
    id: item.session_id || item.id,
    title: item.last_message_preview || item.title || '新会话',
    status: item.status || 'active',  // Issue #2: 使用后端返回的状态
    handover_mode: item.handover_mode || 'ai',
    customer_name: item.customer_name,
    last_message: item.last_message_preview,
    updated_at: item.last_updated || new Date().toISOString(),
    created_at: item.last_updated || new Date().toISOString(),
  }))
  return { sessions, total: sessions.length }
}

export async function createSession(
  title: string,
  customerName?: string,
): Promise<{ session: Session }> {
  const body: Record<string, string> = { title }
  if (customerName) body.customer_name = customerName
  const res = await fetch(`${API_BASE}/sessions`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`Create session error: ${res.status}`)
  return res.json()
}

export async function getSession(id: string): Promise<{ session: Session }> {
  const res = await fetch(`${API_BASE}/sessions/${encodeURIComponent(id)}`, { headers: authHeaders() })
  if (!res.ok) throw new Error(`Get session error: ${res.status}`)
  return res.json()
}

export async function updateSession(
  id: string,
  data: { title?: string; status?: string; customer_name?: string },
): Promise<{ session: Session }> {
  const res = await fetch(`${API_BASE}/sessions/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`Update session error: ${res.status}`)
  return res.json()
}

export async function deleteSession(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/sessions/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`Delete session error: ${res.status}`)
}

/** Backend message shape from API (snake_case) */
interface ApiMessage {
  id?: string
  role: 'user' | 'assistant'
  content: string
  created_at?: string
  timestamp?: number
}

export async function getSessionMessages(
  id: string,
): Promise<{ messages: ApiMessage[]; total: number }> {
  const res = await fetch(`${API_BASE}/sessions/${encodeURIComponent(id)}/messages`, { headers: authHeaders() })
  if (!res.ok) throw new Error(`Session messages error: ${res.status}`)
  return res.json()
}

/**
 * Fetch messages for a specific chat session from the B端 endpoint.
 */
export async function getChatMessages(sessionId: string): Promise<{ messages: ApiMessage[]; total: number }> {
  const res = await fetch(`${API_BASE}/chat/sessions/${encodeURIComponent(sessionId)}/messages`, {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`Chat messages error: ${res.status}`)
  return res.json()
}

/**
 * Convert an API message (snake_case) into the frontend ChatMessage shape.
 */
export function apiMessageToChatMessage(m: ApiMessage): ChatMessage {
  return {
    id: m.id || `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    role: m.role,
    content: m.content,
    timestamp: m.timestamp
      ? m.timestamp
      : m.created_at
        ? new Date(m.created_at).getTime()
        : Date.now(),
  }
}

/**
 * Switch handover mode (AI ↔ human) for a chat session.
 */
export async function switchHandover(
  sessionId: string,
  mode: 'ai' | 'human',
): Promise<{ session_id: string; handover_mode: string }> {
  const res = await fetch(`${API_BASE}/chat/sessions/${encodeURIComponent(sessionId)}/handover`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ mode }),
  })
  if (!res.ok) throw new Error(`Handover API error: ${res.status}`)
  return res.json()
}

/**
 * Request AI-suggested replies for human handover mode.
 */
export async function getSuggestedReplies(
  sessionId: string,
): Promise<{ suggestions: string[]; session_id: string }> {
  const res = await fetch(`${API_BASE}/chat/sessions/${encodeURIComponent(sessionId)}/handover/suggest`, {
    method: 'POST',
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`Handover suggest API error: ${res.status}`)
  return res.json()
}

export async function dismissHighIntent(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/chat/high-intent/${encodeURIComponent(sessionId)}/dismiss`, {
    method: 'POST',
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error(`Dismiss high intent error: ${res.status}`)
}

export async function sendHumanMessage(
  sessionId: string,
  message: string,
): Promise<{ session_id: string; status: string; role: string }> {
  const res = await fetch(`${API_BASE}/chat/sessions/${encodeURIComponent(sessionId)}/human-message`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ message }),
  })
  if (!res.ok) throw new Error(`Human message API error: ${res.status}`)
  return res.json()
}
