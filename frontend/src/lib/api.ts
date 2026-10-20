/**
 * 共享 API 客户端。
 *
 * 认证说明：JWT 由后端通过 httpOnly Cookie 下发（浏览器自动携带），
 * 前端不再读写 token；本地仅保留用户展示信息（crmbot_user）。
 */

import type { ApiDocumentInfo, ChatAnswerInfo } from '@/types'

export const API_BASE = '/api/v1'

export interface ApiMessage extends ChatAnswerInfo {
  id?: string | number
  role: string
  content: string
  created_at?: string
  timestamp?: number | string
  session_id?: string
  documents?: ApiDocumentInfo[]
  images?: string[]
  metadata?: ChatAnswerInfo & { documents?: ApiDocumentInfo[]; images?: string[] }
  metadata_json?: ChatAnswerInfo & { documents?: ApiDocumentInfo[]; images?: string[] }
  intent?: string | null
}

export function jsonHeaders(): Record<string, string> {
  return { 'Content-Type': 'application/json' }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  const isFormData = typeof FormData !== 'undefined' && init?.body instanceof FormData
  if (!isFormData && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  })
  if (!res.ok) {
    let detail = `API 错误: ${res.status}`
    try {
      const data = await res.json()
      if (data && typeof data.detail === 'string') detail = data.detail
    } catch {
      /* 非 JSON 错误体 */
    }
    if (res.status === 401) {
      // 会话失效：清理本地用户信息并通知守卫
      localStorage.removeItem('crmbot_user')
      window.dispatchEvent(new CustomEvent('auth-expired'))
    }
    throw new Error(detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

/** 以当前用户名推导的稳定会话 ID（登录后由 store 刷新）。 */
export function currentSessionId(): string {
  try {
    const raw = localStorage.getItem('crmbot_user')
    if (raw) {
      const user = JSON.parse(raw) as { username?: string }
      if (user.username) return `session_${user.username}`
    }
  } catch {
    /* fall through */
  }
  const arr = new Uint32Array(2)
  crypto.getRandomValues(arr)
  return `session_${arr[0].toString(36)}_${arr[1].toString(36)}`
}
