import { apiFetch, type ApiMessage } from '@/lib/api'
import type { Session, ChatMessage, ChatAnswerInfo } from '@/types'

export type SessionStatus = 'new' | 'active' | 'negotiating' | 'closed' | 'lost'

/** B端会话列表（string session_id 体系） */
export async function fetchSessions(): Promise<{ sessions: Session[]; total: number }> {
  const data = await apiFetch<{
    sessions: Array<{
      session_id: string
      last_message_preview: string
      last_updated: string | null
      message_count: number
      customer_name?: string | null
      status?: string
      handover_mode?: string
    }>
  }>('/chat/sessions')
  const sessions: Session[] = (data.sessions || []).map((item) => ({
    id: item.session_id,
    title: item.last_message_preview || '新会话',
    status: normalizeStatus(item.status),
    handover_mode: item.handover_mode === 'human' ? 'human' : 'ai',
    customer_name: item.customer_name ?? undefined,
    last_message: item.last_message_preview,
    updated_at: item.last_updated || new Date().toISOString(),
    created_at: item.last_updated || new Date().toISOString(),
  }))
  return { sessions, total: sessions.length }
}

/** 未知状态归一化为 active，避免 statusConfig 取到 undefined 导致崩溃 */
export function normalizeStatus(status: string | undefined): Session['status'] {
  const valid: Session['status'][] = ['new', 'active', 'negotiating', 'closed', 'lost']
  return valid.includes(status as Session['status']) ? (status as Session['status']) : 'active'
}

/** 拉取指定聊天会话的消息（B端） */
export async function getChatMessages(
  sessionId: string,
): Promise<{ messages: ApiMessage[]; total: number }> {
  return apiFetch(`/chat/sessions/${encodeURIComponent(sessionId)}/messages`)
}

/** 将 HTTP / WS / 两种历史消息统一映射；旧历史可从 metadata 恢复附件。 */
export function apiMessageToChatMessage(m: ApiMessage): ChatMessage {
  const metadata = m.metadata_json ?? m.metadata
  const answerInfo: ChatAnswerInfo = {
    citations: m.citations ?? metadata?.citations ?? undefined,
    knowledge_release_id: m.knowledge_release_id ?? metadata?.knowledge_release_id ?? undefined,
    answer_status: m.answer_status ?? metadata?.answer_status ?? undefined,
    data_as_of: m.data_as_of ?? metadata?.data_as_of ?? undefined,
    assumptions: m.assumptions ?? metadata?.assumptions ?? undefined,
    limitations: m.limitations ?? metadata?.limitations ?? undefined,
  }
  const rawDocuments = m.documents ?? metadata?.documents
  const timestamp = m.timestamp ?? m.created_at
  return {
    ...answerInfo,
    id: m.id != null ? String(m.id) : `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    role: m.role === 'user' ? 'user' : 'assistant',
    content: m.content,
    timestamp: typeof timestamp === 'number' ? timestamp : timestamp ? new Date(timestamp).getTime() : Date.now(),
    sessionId: m.session_id,
    status: 'sent',
    documents: rawDocuments?.map((document) => {
      const filename = document.file_name ?? document.filename ?? '文档'
      return {
        file_name: filename,
        file_path: document.file_path ?? document.path ?? `/api/v1/documents/${encodeURIComponent(filename)}`,
        doc_type: document.doc_type ?? document.type ?? 'unknown',
        file_size: document.file_size ?? document.size ?? 0,
      }
    }),
    images: m.images ?? metadata?.images,
  }
}

/** 切换 AI/人工 接管模式 */
export async function switchHandover(
  sessionId: string,
  mode: 'ai' | 'human',
): Promise<{ session_id: string; handover_mode: string }> {
  return apiFetch(`/chat/sessions/${encodeURIComponent(sessionId)}/handover`, {
    method: 'POST',
    body: JSON.stringify({ mode }),
  })
}

/** 更新会话状态（驱动报表漏斗） */
export async function updateSessionStatus(
  sessionId: string,
  status: SessionStatus,
): Promise<{ session_id: string; status: string }> {
  return apiFetch(`/chat/sessions/${encodeURIComponent(sessionId)}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  })
}

/** 请求 AI 建议回复（人工接管模式） */
export async function getSuggestedReplies(
  sessionId: string,
): Promise<{ suggestions: string[]; session_id: string }> {
  return apiFetch(`/chat/sessions/${encodeURIComponent(sessionId)}/handover/suggest`, {
    method: 'POST',
  })
}

/** 解除高意向提醒（允许该会话再次触发） */
export async function dismissHighIntent(sessionId: string): Promise<void> {
  await apiFetch(`/chat/high-intent/${encodeURIComponent(sessionId)}/dismiss`, { method: 'POST' })
}

/** 人工客服发送消息（推送到 C端） */
export async function sendHumanMessage(
  sessionId: string,
  message: string,
): Promise<{ session_id: string; status: string; role: string }> {
  return apiFetch(`/chat/sessions/${encodeURIComponent(sessionId)}/human-message`, {
    method: 'POST',
    body: JSON.stringify({ message }),
  })
}
