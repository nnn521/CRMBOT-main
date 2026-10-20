import { apiFetch, type ApiMessage } from '@/lib/api'
import type { ChatResponse } from '@/types'

export { apiFetch }

/** 发送聊天消息（历史由服务端 checkpoint 维护，不再传 history） */
export async function sendChatMessage(
  sessionId: string,
  message: string,
  imageUrl?: string,
): Promise<ChatResponse> {
  const body: Record<string, unknown> = {
    session_id: sessionId,
    message,
    input_image_url: imageUrl ?? null,
  }
  return apiFetch<ChatResponse>('/chat', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/** 登出：吊销服务端令牌（httpOnly Cookie 由后端清除） */
export async function logout(): Promise<void> {
  try {
    await apiFetch<{ status: string }>('/auth/logout', { method: 'POST' })
  } catch {
    /* 网络失败也继续本地清理 */
  }
}

/** 拉取当前客户的会话历史（C端） */
export async function fetchCustomerHistory(): Promise<{ sessions: { session_id: string }[] }> {
  return apiFetch('/chat/history')
}

/** 拉取指定会话的消息（C端） */
export async function fetchChatMessages(
  sessionId: string,
): Promise<{ messages: ApiMessage[]; total: number }> {
  return apiFetch(`/chat/history/${encodeURIComponent(sessionId)}`)
}

/** 清除指定会话历史（C端，服务端同步清除 Agent 记忆） */
export async function clearChatHistory(sessionId: string): Promise<void> {
  await apiFetch(`/chat/history/${encodeURIComponent(sessionId)}`, { method: 'DELETE' })
}
