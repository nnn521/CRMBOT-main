import type { ChatMessage, DocumentInfo, Session, HighIntentAlert } from '@/types'
import { create } from 'zustand'

interface ChatStore {
  messages: ChatMessage[]
  sessionMessages: Record<string, ChatMessage[]>
  isLoading: boolean
  sessionId: string
  attachedDocs: Record<string, DocumentInfo[]>
  attachedImages: Record<string, string[]>
  sessions: Session[]
  handoverModes: Record<string, 'ai' | 'human'>
  highIntentAlerts: HighIntentAlert[]
  seenMessageIds: Set<string>
  addDedupKey: (key: string) => void
  hasDedupKey: (key: string) => boolean
  addMessage: (msg: ChatMessage) => void
  updateMessageStatus: (id: string, status: ChatMessage['status']) => void
  mergeMessages: (msgs: ChatMessage[]) => void
  appendSessionMessage: (sessionId: string, msg: ChatMessage) => void
  setSessionMessages: (sessionId: string, msgs: ChatMessage[]) => void
  attachDocuments: (messageId: string, docs: DocumentInfo[]) => void
  attachImages: (messageId: string, images: string[]) => void
  setLoading: (loading: boolean) => void
  clearMessages: () => void
  setSessions: (sessions: Session[]) => void
  addSession: (session: Session) => void
  setSessionId: (id: string) => void
  setMessages: (msgs: ChatMessage[]) => void
  setHandoverMode: (sessionId: string, mode: 'ai' | 'human') => void
  addHighIntentAlert: (alert: HighIntentAlert) => void
  dismissHighIntentAlert: (sessionId: string) => void
}

function generateId(): string {
  return `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

function getSessionId(): string {
  // 基于用户名生成稳定的 sessionId，保证刷新后 WS 频道不变
  try {
    const userStr = localStorage.getItem('crmbot_user')
    if (userStr) {
      const user = JSON.parse(userStr)
      if (user.username) {
        return `session_${user.username}`
      }
    }
  } catch { /* fall through */ }
  // 未登录时 fallback 随机值
  const arr = new Uint32Array(2)
  crypto.getRandomValues(arr)
  return `session_${arr[0].toString(36)}_${arr[1].toString(36)}`
}

export const useChatStore = create<ChatStore>((set) => ({
  messages: [],
  sessionMessages: {},
  isLoading: false,
  sessionId: getSessionId(),
  attachedDocs: {},
  attachedImages: {},
  sessions: [],
  handoverModes: {},
  highIntentAlerts: [],
  seenMessageIds: new Set<string>(),

  addMessage: (msg) =>
    set((state) => {
      if (state.seenMessageIds.has(msg.id)) return state
      const seen = new Set(state.seenMessageIds)
      seen.add(msg.id)
      return { messages: [...state.messages, msg], seenMessageIds: seen }
    }),

  updateMessageStatus: (id, status) =>
    set((state) => ({
      messages: state.messages.map((msg) => msg.id === id ? { ...msg, status } : msg),
    })),

  mergeMessages: (msgs) =>
    set((state) => {
      const seen = new Set(state.seenMessageIds)
      const merged = [...state.messages]
      for (const msg of msgs) {
        if (!seen.has(msg.id)) {
          seen.add(msg.id)
          merged.push(msg)
        }
      }
      merged.sort((a, b) => a.timestamp - b.timestamp)
      return { messages: merged, seenMessageIds: seen }
    }),

  appendSessionMessage: (sessionId, msg) =>
    set((state) => {
      if (state.seenMessageIds.has(msg.id)) return state
      const seen = new Set(state.seenMessageIds)
      seen.add(msg.id)
      const current = state.sessionMessages[sessionId] || []
      return {
        seenMessageIds: seen,
        sessionMessages: {
          ...state.sessionMessages,
          [sessionId]: [...current, msg].sort((a, b) => a.timestamp - b.timestamp),
        },
      }
    }),

  setSessionMessages: (sessionId, msgs) =>
    set((state) => {
      const seen = new Set(state.seenMessageIds)
      msgs.forEach((msg) => seen.add(msg.id))
      return {
        seenMessageIds: seen,
        sessionMessages: { ...state.sessionMessages, [sessionId]: msgs },
      }
    }),

  attachDocuments: (messageId, docs) =>
    set((state) => ({
      attachedDocs: { ...state.attachedDocs, [messageId]: docs },
    })),

  attachImages: (messageId, images) =>
    set((state) => ({
      attachedImages: { ...state.attachedImages, [messageId]: images },
    })),

  setLoading: (loading) => set({ isLoading: loading }),

  clearMessages: () => set({ messages: [], attachedDocs: {}, attachedImages: {}, seenMessageIds: new Set() }),

  setSessions: (sessions) => {
    const modes: Record<string, 'ai' | 'human'> = {}
    sessions.forEach((s) => {
      modes[s.id] = s.handover_mode || 'ai'
    })
    set({ sessions, handoverModes: { ...modes } })
  },

  addSession: (session) =>
    set((state) => ({
      sessions: [...state.sessions, session],
      handoverModes: { ...state.handoverModes, [session.id]: session.handover_mode || 'ai' },
    })),

  setSessionId: (id) => set({ sessionId: id }),

  setMessages: (msgs) => set((state) => {
    const seen = new Set(state.seenMessageIds)
    msgs.forEach((msg) => seen.add(msg.id))
    return { messages: msgs, seenMessageIds: seen }
  }),

  setHandoverMode: (sessionId, mode) =>
    set((state) => ({
      handoverModes: { ...state.handoverModes, [sessionId]: mode },
      sessions: state.sessions.map((s) =>
        s.id === sessionId ? { ...s, handover_mode: mode } : s,
      ),
    })),

  addHighIntentAlert: (alert) =>
    set((state) => ({ highIntentAlerts: [...state.highIntentAlerts, alert] })),

  dismissHighIntentAlert: (sessionId) =>
    set((state) => ({
      highIntentAlerts: state.highIntentAlerts.filter((a) => a.session_id !== sessionId),
    })),

  addDedupKey: (key) =>
    set((state) => {
      const next = new Set(state.seenMessageIds)
      next.add(key)
      if (next.size > 500) {
        const arr = [...next]
        return { seenMessageIds: new Set(arr.slice(-200)) }
      }
      return { seenMessageIds: next }
    }),
  hasDedupKey: (key: string): boolean => useChatStore.getState().seenMessageIds.has(key),
}))

export { generateId }
