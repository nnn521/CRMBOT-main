export interface HermesHealthResponse {
  online: boolean
  status_code?: number
  detail?: string
}

export interface HermesMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

/** 检测 Hermes 是否在线 */
export async function checkHermesHealth(): Promise<HermesHealthResponse> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 8000)
  try {
    const res = await fetch('/api/v1/hermes/health', {
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
    })
    if (!res.ok) {
      return { online: false, status_code: res.status, detail: `HTTP ${res.status}` }
    }
    return (await res.json()) as HermesHealthResponse
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      return { online: false, detail: '连接超时' }
    }
    return { online: false, detail: '无法连接到 Hermes 服务' }
  } finally {
    clearTimeout(timeout)
  }
}

/** 流式发送消息到 Hermes（SSE） */
export async function sendHermesMessageStream(
  messages: HermesMessage[],
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (error: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 120000)
  if (signal) {
    if (signal.aborted) {
      controller.abort()
      return
    }
    signal.addEventListener('abort', () => controller.abort(), { once: true })
  }

  try {
    const res = await fetch('/api/v1/hermes/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
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
          const parsed = JSON.parse(data) as {
            choices?: Array<{ delta?: { content?: string } }>
          }
          const content = parsed.choices?.[0]?.delta?.content
          if (content) onChunk(content)
        } catch {
          /* 跳过无法解析的 SSE 数据 */
        }
      }
    }

    if (buffer.trim()) {
      const trimmed = buffer.trim()
      if (trimmed.startsWith('data: ') && trimmed.slice(6) !== '[DONE]') {
        try {
          const parsed = JSON.parse(trimmed.slice(6)) as {
            choices?: Array<{ delta?: { content?: string } }>
          }
          const content = parsed.choices?.[0]?.delta?.content
          if (content) onChunk(content)
        } catch {
          /* ignore */
        }
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
