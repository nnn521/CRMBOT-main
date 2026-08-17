const API_BASE = '/api/v1/hermes'

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('crmbot_token')
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}

export interface HermesHealthResponse {
  online: boolean
  status_code?: number
  detail?: string
}

export interface HermesMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export interface HermesChatResponse {
  id: string
  object: string
  created: number
  model: string
  choices: Array<{
    index: number
    message: HermesMessage
    finish_reason: string
  }>
}

/** 检测 Hermes 是否在线 */
export async function checkHermesHealth(): Promise<HermesHealthResponse> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 8000)

  try {
    const res = await fetch(`${API_BASE}/health`, {
      headers: authHeaders(),
      signal: controller.signal,
    })
    clearTimeout(timeout)
    if (!res.ok) {
      return { online: false, status_code: res.status, detail: `HTTP ${res.status}` }
    }
    return res.json()
  } catch (err: unknown) {
    clearTimeout(timeout)
    if (err instanceof DOMException && err.name === 'AbortError') {
      return { online: false, detail: '连接超时' }
    }
    return { online: false, detail: '无法连接到 Hermes 服务' }
  }
}

/** 发送消息到 Hermes（非流式） */
export async function sendHermesMessage(
  messages: HermesMessage[]
): Promise<HermesChatResponse> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 60000)

  try {
    const res = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ messages }),
      signal: controller.signal,
    })
    clearTimeout(timeout)

    if (!res.ok) {
      const errorText = await res.text().catch(() => '')
      throw new Error(`Hermes API error (${res.status}): ${errorText}`)
    }
    return res.json()
  } catch (err: unknown) {
    clearTimeout(timeout)
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new Error('请求超时，Hermes 可能负载过高，请稍后重试')
    }
    if (err instanceof TypeError && err.message.includes('fetch')) {
      throw new Error('网络连接失败，请检查 Hermes 服务是否正常运行')
    }
    throw err
  }
}

/** 流式发送消息到 Hermes（SSE），返回 reader */
export async function sendHermesMessageStream(
  messages: HermesMessage[],
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (error: string) => void,
  signal?: AbortSignal
): Promise<void> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 120000)
  // 外部 signal 联动：外部取消时内部也取消
  if (signal) {
    if (signal.aborted) { controller.abort(); return }
    signal.addEventListener('abort', () => controller.abort(), { once: true })
  }

  try {
    const res = await fetch(`${API_BASE}/chat/stream`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ messages }),
      signal: controller.signal,
    })

    clearTimeout(timeout)

    if (!res.ok) {
      const errorText = await res.text().catch(() => '')
      onError(`Hermes 服务错误 (${res.status}): ${errorText || '未知错误'}`)
      return
    }

    const reader = res.body?.getReader()
    if (!reader) {
      onError('无法读取流式响应')
      return
    }

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      // Keep the last partial line in buffer
      buffer = lines.pop() || ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed || !trimmed.startsWith('data: ')) continue

        const data = trimmed.slice(6)
        if (data === '[DONE]') {
          onDone()
          return
        }

        try {
          const parsed = JSON.parse(data)
          const content = parsed.choices?.[0]?.delta?.content
          if (content) {
            onChunk(content)
          }
        } catch {
          // Skip unparseable SSE data
        }
      }
    }

    // Flush any remaining buffer
    if (buffer.trim()) {
      const trimmed = buffer.trim()
      if (trimmed.startsWith('data: ') && trimmed.slice(6) !== '[DONE]') {
        try {
          const parsed = JSON.parse(trimmed.slice(6))
          const content = parsed.choices?.[0]?.delta?.content
          if (content) onChunk(content)
        } catch { /* ignore */ }
      }
    }

    onDone()
  } catch (err: unknown) {
    clearTimeout(timeout)
    if (err instanceof DOMException && err.name === 'AbortError') {
      onError('请求超时，Hermes 响应时间过长，请稍后重试')
      return
    }
    if (err instanceof TypeError && err.message.includes('fetch')) {
      onError('网络连接失败，请检查 Hermes 服务是否正常运行')
      return
    }
    onError(err instanceof Error ? err.message : '未知错误')
  }
}
