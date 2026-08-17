import { create } from 'zustand'
import { sendHermesMessageStream } from '@/api/hermes'
import type { HermesMessage } from '@/api/hermes'

export interface HermesChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: number
  isStreaming?: boolean
}

function generateId(): string {
  return `hermes_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

interface HermesStore {
  messages: HermesChatMessage[]
  isLoading: boolean
  isOnline: boolean | null // null = checking, true = online, false = offline
  healthError: string | null
  streamAbortController: AbortController | null

  setOnline: (online: boolean | null, error?: string) => void
  sendMessage: (content: string) => Promise<void>
  cancelStream: () => void
  clearMessages: () => void
  appendToLastAssistant: (chunk: string) => void
  finishStreaming: () => void
}

export const useHermesStore = create<HermesStore>((set, get) => ({
  messages: [],
  isLoading: false,
  isOnline: null,
  healthError: null,
  streamAbortController: null,

  setOnline: (online, error) => set({ isOnline: online, healthError: error || null }),

  sendMessage: async (content: string) => {
    const state = get()
    if (state.isLoading || !content.trim()) return

    const userMsg: HermesChatMessage = {
      id: generateId(),
      role: 'user',
      content: content.trim(),
      timestamp: Date.now(),
    }

    const assistantMsg: HermesChatMessage = {
      id: generateId(),
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
      isStreaming: true,
    }

    // Build API messages from current state + new user message（不包含空占位符）
    const historyMsgs: HermesMessage[] = state.messages
      .filter((m) => m.content.trim() !== '')
      .map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content }))
    const apiMessages: HermesMessage[] = [
      {
        role: 'system',
        content:
          '你是 CRMBOT 内部助手 Hermes，帮助管理员进行数据分析、知识问答和客户洞察。请用中文回复，保持专业但友好的态度。',
      },
      ...historyMsgs,
      { role: 'user' as const, content: content.trim() },
    ]

    set({
      messages: [...state.messages, userMsg, assistantMsg],
      isLoading: true,
    })

    const abortController = new AbortController()
    set({ streamAbortController: abortController })

    await sendHermesMessageStream(
      apiMessages,
      // onChunk
      (chunk: string) => {
        get().appendToLastAssistant(chunk)
      },
      // onDone
      () => {
        set({ streamAbortController: null })
        get().finishStreaming()
      },
      // onError
      (error: string) => {
        set({ streamAbortController: null })
        get().appendToLastAssistant(
          `\n\n⚠️ **出错了**：${error}\n\n请检查 Hermes 服务状态后重试。`
        )
        get().finishStreaming()
      },
      abortController.signal
    )
  },

  cancelStream: () => {
    const { streamAbortController } = get()
    if (streamAbortController) {
      streamAbortController.abort()
    }
    set({ isLoading: false })
  },

  clearMessages: () => set({ messages: [] }),

  appendToLastAssistant: (chunk: string) => {
    set((state) => {
      const msgs = [...state.messages]
      const last = msgs[msgs.length - 1]
      if (last && last.role === 'assistant') {
        msgs[msgs.length - 1] = { ...last, content: last.content + chunk }
      }
      return { messages: msgs }
    })
  },

  finishStreaming: () => {
    set((state) => {
      const msgs = [...state.messages]
      const last = msgs[msgs.length - 1]
      if (last && last.role === 'assistant') {
        msgs[msgs.length - 1] = { ...last, isStreaming: false }
      }
      return { messages: msgs, isLoading: false }
    })
  },
}))
