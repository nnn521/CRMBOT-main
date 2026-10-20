import type { ChatMessage, DocumentInfo, Session, HighIntentAlert } from '@/types'
import { currentSessionId } from '@/lib/api'
import { create } from 'zustand'

const DEDUP_MAX = 500
const DEDUP_KEEP = 200

function cappedSeen(seen: Set<string>): Set<string> {
  if (seen.size <= DEDUP_MAX) return seen
  return new Set([...seen].slice(-DEDUP_KEEP))
}

/** Same server ID is one bubble; late HTTP/history fills fields missing from WS. */
function mergeMessage(existing: ChatMessage, incoming: ChatMessage): ChatMessage {
  const merged = { ...existing }
  for (const key of Object.keys(incoming) as (keyof ChatMessage)[]) {
    const value = incoming[key]
    const previous = existing[key]
    if (value == null) continue
    if (previous == null || previous === '' || (Array.isArray(previous) && previous.length === 0) || key === 'status') {
      Object.assign(merged, { [key]: value })
    }
  }
  return merged
}

function mergeMessageLists(current: ChatMessage[], incoming: ChatMessage[]): ChatMessage[] {
  const byId = new Map(current.map((message) => [message.id, message]))
  for (const message of incoming) {
    const existing = byId.get(message.id)
    byId.set(message.id, existing ? mergeMessage(existing, message) : message)
  }
  return [...byId.values()].sort((a, b) => a.timestamp - b.timestamp)
}

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
  updateMessageStatus: (id: string, status: ChatMessage['status'], serverId?: string) => void
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
  refreshSessionId: () => void
  setMessages: (msgs: ChatMessage[]) => void
  setHandoverMode: (sessionId: string, mode: 'ai' | 'human') => void
  addHighIntentAlert: (alert: HighIntentAlert) => void
  dismissHighIntentAlert: (sessionId: string) => void
}

function generateId(): string {
  return `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

/** 登录/登出后调用：按当前 localStorage 用户重新推导会话 ID */
export function getSessionId(): string {
  return currentSessionId()
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
      const seen = cappedSeen(new Set(state.seenMessageIds).add(msg.id))
      return { messages: mergeMessageLists(state.messages, [msg]), seenMessageIds: seen }
    }),

  updateMessageStatus: (id, status, serverId) =>
    set((state) => {
      const messages = state.messages.map((msg) => msg.id === id ? { ...msg, id: serverId || id, status } : msg)
      const seen = new Set(state.seenMessageIds)
      if (serverId) {
        seen.delete(id)
        seen.add(serverId)
      }
      return { messages: mergeMessageLists([], messages), seenMessageIds: cappedSeen(seen) }
    }),

  mergeMessages: (msgs) =>
    set((state) => {
      const seen = new Set(state.seenMessageIds)
      msgs.forEach((msg) => seen.add(msg.id))
      return { messages: mergeMessageLists(state.messages, msgs), seenMessageIds: cappedSeen(seen) }
    }),

  appendSessionMessage: (sessionId, msg) =>
    set((state) => {
      const seen = cappedSeen(new Set(state.seenMessageIds).add(msg.id))
      const current = state.sessionMessages[sessionId] || []
      return {
        seenMessageIds: seen,
        sessionMessages: {
          ...state.sessionMessages,
          [sessionId]: mergeMessageLists(current, [msg]),
        },
      }
    }),

  setSessionMessages: (sessionId, msgs) =>
    set((state) => {
      const seen = new Set(state.seenMessageIds)
      msgs.forEach((msg) => seen.add(msg.id))
      return {
        seenMessageIds: cappedSeen(seen),
        sessionMessages: {
          ...state.sessionMessages,
          [sessionId]: mergeMessageLists(state.sessionMessages[sessionId] || [], msgs),
        },
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

  clearMessages: () =>
    set({ messages: [], attachedDocs: {}, attachedImages: {}, seenMessageIds: new Set() }),

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

  refreshSessionId: () => set({ sessionId: getSessionId() }),

  setMessages: (msgs) =>
    set((state) => {
      const seen = new Set(state.seenMessageIds)
      msgs.forEach((msg) => seen.add(msg.id))
      return { messages: mergeMessageLists(state.messages, msgs), seenMessageIds: cappedSeen(seen) }
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
    set((state) => ({
      seenMessageIds: cappedSeen(new Set(state.seenMessageIds).add(key)),
    })),
  hasDedupKey: (key: string): boolean => useChatStore.getState().seenMessageIds.has(key),
}))

export { generateId }
