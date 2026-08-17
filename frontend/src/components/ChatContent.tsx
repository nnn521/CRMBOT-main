import { useState, useCallback, useEffect, useRef } from 'react'
import { useOutletContext } from 'react-router-dom'
import {
  MessageSquare,
  PanelRightClose,
  PanelRightOpen,
  Bot,
  User,
  AlertTriangle,
  X,
  Sparkles,
  Cpu,
} from 'lucide-react'
import ConversationList from './ConversationList'
import CustomerInfoPanel from './CustomerInfoPanel'
import ChatView from './ChatView'
import HermesChatArea from './HermesChatArea'
import { useChatStore } from '@/stores/chat'
import { useHermesStore } from '@/stores/hermes'
import { checkHermesHealth } from '@/api/hermes'
import { fetchSessions, createSession, getChatMessages, switchHandover, getSuggestedReplies, dismissHighIntent, sendHumanMessage } from '@/api/sessions'
import { useWebSocket } from '@/hooks/useWebSocket'
import type { Session, ChatMessage, DocumentInfo, HighIntentAlert } from '@/types'

const statusConfig: Record<Session['status'], { label: string; className: string }> = {
  new: { label: '🟡 新客户', className: 'bg-amber-50 text-amber-800 border-amber-200' },
  active: { label: '🔵 跟进中', className: 'bg-sky-50 text-sky-700 border-sky-200' },
  negotiating: { label: '🟠 洽谈中', className: 'bg-orange-50 text-orange-700 border-orange-200' },
  closed: { label: '🟢 已成交', className: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  lost: { label: '⚪ 已流失', className: 'bg-neutral-50 text-neutral-400 border-neutral-200' },
}

export default function ChatContent() {
  const sessions = useChatStore((s) => s.sessions)
  const setSessions = useChatStore((s) => s.setSessions)
  const addSession = useChatStore((s) => s.addSession)
  const attachedDocs = useChatStore((s) => s.attachedDocs)
  const attachedImages = useChatStore((s) => s.attachedImages)
  const attachDocuments = useChatStore((s) => s.attachDocuments)
  const attachImages = useChatStore((s) => s.attachImages)
  const handoverModes = useChatStore((s) => s.handoverModes)
  const setHandoverMode = useChatStore((s) => s.setHandoverMode)
  const highIntentAlerts = useChatStore((s) => s.highIntentAlerts)
  const addHighIntentAlert = useChatStore((s) => s.addHighIntentAlert)
  const dismissHighIntentAlert = useChatStore((s) => s.dismissHighIntentAlert)
  const sessionMessages = useChatStore((s) => s.sessionMessages)
  const appendSessionMessage = useChatStore((s) => s.appendSessionMessage)
  const setSessionMessages = useChatStore((s) => s.setSessionMessages)

  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [panelVisible, setPanelVisible] = useState(false)
  const [sessionLoading, setSessionLoading] = useState(false)
  const [aiSuggestions, setAiSuggestions] = useState<string[]>([])
  const [suggestLoading, setSuggestLoading] = useState(false)
  const [showSuggestPanel, setShowSuggestPanel] = useState(false)

  // Fetch sessions from backend on mount
  useEffect(() => {
    setSessionLoading(true)
    fetchSessions()
      .then((data) => {
        const list = data.sessions || []
        setSessions(list)
      })
      .catch((err) => {
        console.error('Failed to fetch sessions:', err)
      })
      .finally(() => setSessionLoading(false))
  }, [setSessions])

  const handleSelectSession = useCallback((id: string) => {
    if (id === 'hermes') {
      setActiveSessionId('hermes')
      setPanelVisible(false)
      setShowSuggestPanel(false)
      setAiSuggestions([])
      // Check Hermes health and set online status
      checkHermesHealth().then((r) => {
        useHermesStore.getState().setOnline(r.online, r.detail)
      }).catch(() => {})
      return
    }
    setActiveSessionId(id)
    setPanelVisible(true)
    setShowSuggestPanel(false)
    setAiSuggestions([])
    // Load messages for this session from API
    getChatMessages(id)
      .then((data) => {
        const msgs: ChatMessage[] = (data.messages || []).map((m: any) => ({
          id: String(m.id),
          role: m.role,
          content: m.content,
          timestamp: m.created_at ? new Date(m.created_at).getTime() : Date.now(),
        }))
        setSessionMessages(id, msgs)
      })
      .catch(console.error)
  }, [setSessionMessages])

  const handleNewSession = useCallback(async () => {
    try {
      const { session } = await createSession('新会话')
      addSession(session)
      setActiveSessionId(session.id)
      setPanelVisible(false)
    } catch (err) {
      console.error('Failed to create session:', err)
    }
  }, [addSession])

  // ── Handover: shared inner helper (accepts sessionId) ──
  const switchHandoverInner = useCallback(async (sessionId: string, mode: 'ai' | 'human') => {
    await switchHandover(sessionId, mode)
    setHandoverMode(sessionId, mode)
    if (mode === 'ai') {
      setShowSuggestPanel(false)
      setAiSuggestions([])
    }
  }, [setHandoverMode])

  // ── Handover: switch AI/human mode (UI button, uses activeSessionId) ──
  const handleSwitchHandover = useCallback(async (mode: 'ai' | 'human') => {
    if (!activeSessionId) return
    try {
      await switchHandoverInner(activeSessionId, mode)
    } catch (err) {
      console.error('Failed to switch handover:', err)
    }
  }, [activeSessionId, switchHandoverInner])

  // ── Handover: get AI suggestions ──
  const handleGetSuggestions = useCallback(async () => {
    if (!activeSessionId) return
    setSuggestLoading(true)
    setShowSuggestPanel(true)
    try {
      const result = await getSuggestedReplies(activeSessionId)
      setAiSuggestions(result.suggestions || [])
    } catch (err) {
      console.error('Failed to get suggestions:', err)
      setAiSuggestions([])
    } finally {
      setSuggestLoading(false)
    }
  }, [activeSessionId])

  // ── High intent alert: take over immediately (uses shared inner) ──
  const handleTakeOver = useCallback(async (sessionId: string) => {
    try {
      await switchHandoverInner(sessionId, 'human')
      dismissHighIntentAlert(sessionId)
      // Navigate to this session
      setActiveSessionId(sessionId)
      setPanelVisible(true)
      // Load messages
      getChatMessages(sessionId)
        .then((data) => {
          const msgs: ChatMessage[] = (data.messages || []).map((m: any) => ({
            id: String(m.id),
            role: m.role,
            content: m.content,
            timestamp: m.created_at ? new Date(m.created_at).getTime() : Date.now(),
          }))
          setSessionMessages(sessionId, msgs)
        })
        .catch(console.error)
    } catch (err) {
      console.error('Failed to take over:', err)
    }
  }, [switchHandoverInner, dismissHighIntentAlert, setSessionMessages])

  // ── Dismiss high intent alert (frontend + 后端 DB) ──
  const handleDismiss = useCallback(async (sessionId: string) => {
    dismissHighIntentAlert(sessionId)
    try {
      await dismissHighIntent(sessionId)
    } catch (err) {
      console.error('Failed to dismiss high intent:', err)
    }
  }, [dismissHighIntentAlert])

  // ── Human mode: send message via new API ──
  const handleAdminSend = useCallback(async (content: string) => {
    if (!activeSessionId) return
    // 不本地添加，等 WS 广播统一推送（避免重复+角色不一致）
    try {
      await sendHumanMessage(activeSessionId, content)
    } catch(e) {
      console.error('[B-SEND] Failed:', e)
    }
  }, [activeSessionId])

  // ── WebSocket: real-time updates ──
  const activeSessionIdRef = useRef(activeSessionId)
  activeSessionIdRef.current = activeSessionId
  const handleWsMessage = useCallback((data: any) => {
    console.log('[B-WS] event:', data.type, data.session_id, data.message?.id)
    if (data.type === 'new_message' && data.session_id && data.message?.id) {
      const payload = data.message
      const chatMsg: ChatMessage = {
        id: String(payload.id),
        sessionId: data.session_id,
        role: payload.role,
        content: payload.content,
        timestamp: payload.timestamp ? new Date(payload.timestamp).getTime() : Date.now(),
        status: 'sent',
      }
      appendSessionMessage(data.session_id, chatMsg)

      const docs: DocumentInfo[] = payload.documents ?? []
      if (docs.length > 0) {
        const mapped = docs.map((d: any) => ({
          file_name: d.filename || d.file_name,
          file_path: d.path || d.file_path || `/api/v1/documents/${encodeURIComponent(d.filename || d.file_name)}`,
          doc_type: d.type || d.doc_type || 'unknown',
          file_size: d.size || d.file_size || 0,
        }))
        attachDocuments(chatMsg.id, mapped)
      }
      const imgs: string[] = payload.images ?? []
      if (imgs.length > 0) attachImages(chatMsg.id, imgs)
    }

    // Handover mode update
    if (data.type === 'handover_update') {
      useChatStore.getState().setHandoverMode(data.session_id, data.mode)
    }

    // High intent alert
    if (data.type === 'high_intent_alert') {
      // Issue #4: 去重 — 同一会话只显示一次高意向提醒
      const existing = useChatStore.getState().highIntentAlerts
      if (existing.find((a: HighIntentAlert) => a.session_id === data.session_id)) return
      const alert: HighIntentAlert = {
        type: 'high_intent_alert',
        session_id: data.session_id,
        customer_name: data.customer_name || '客户',
        trigger_message: data.trigger_message || '',
        intent: data.intent || '',
        timestamp: data.timestamp || new Date().toISOString(),
      }
      useChatStore.getState().addHighIntentAlert(alert)
    }

    if (data.type === 'session_update') {
      fetchSessions()
        .then((result) => {
          if (result.sessions) useChatStore.getState().setSessions(result.sessions)
        })
        .catch(() => {})

      // Catch-up: replace from authoritative history; IDs make this deterministic.
      const activeId = activeSessionIdRef.current
      if (activeId && data.session_id === activeId) {
        getChatMessages(activeId)
          .then((data) => {
            const serverMsgs: ChatMessage[] = (data.messages || []).map((m: any) => ({
              id: String(m.id),
              role: m.role,
              content: m.content,
              timestamp: m.created_at ? new Date(m.created_at).getTime() : Date.now(),
              status: 'sent',
            }))
            setSessionMessages(activeId, serverMsgs)
          })
          .catch(() => {})
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appendSessionMessage, attachDocuments, attachImages, setSessionMessages])

  const handleWsConnected = useCallback(() => {
    console.log('[B-WS] connected, refreshing sessions and active history')
    fetchSessions()
      .then((result) => useChatStore.getState().setSessions(result.sessions || []))
      .catch((error) => console.error('[B-WS] session refresh failed:', error))
    const activeId = activeSessionIdRef.current
    if (activeId && activeId !== 'hermes') {
      getChatMessages(activeId)
        .then((data) => setSessionMessages(
          activeId,
          (data.messages || []).map((m: any) => ({
            id: String(m.id),
            role: m.role,
            content: m.content,
            timestamp: m.created_at ? new Date(m.created_at).getTime() : Date.now(),
            status: 'sent' as const,
          })),
        ))
        .catch((error) => console.error('[B-WS] history refresh failed:', error))
    }
  }, [setSessionMessages])

  useWebSocket('admin', handleWsMessage, handleWsConnected)
  // 注意: B端只监听 admin 广播通道，不监听会话专属WS（避免重复处理）

  const activeSession = sessions.find((s) => s.id === activeSessionId) || null
  const localMessages = activeSessionId ? (sessionMessages[activeSessionId] || []) : []
  const status = activeSession ? statusConfig[activeSession.status] : null
  const currentHandoverMode = activeSessionId ? (handoverModes[activeSessionId] || 'ai') : 'ai'

  // Find the alert for the current session (if any)
  const activeAlert = highIntentAlerts.find((a) => a.session_id === activeSessionId)

  return (
    <>
      {/* High Intent Alert Overlay */}
      {highIntentAlerts.length > 0 && (
        <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
          {highIntentAlerts.map((alert) => (
            <div
              key={alert.session_id}
              className="rounded-lg border border-amber-300 bg-gradient-to-r from-amber-50 to-orange-50 p-4 shadow-lg animate-in slide-in-from-right"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-2.5">
                  <AlertTriangle size={18} className="text-amber-600 shrink-0 mt-0.5" />
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-amber-900">
                      {alert.customer_name} 表现出强烈购买意向
                    </p>
                    {alert.trigger_message && (
                      <p className="mt-1 text-xs text-amber-700 line-clamp-2">
                        "{alert.trigger_message}"
                      </p>
                    )}
                    <div className="flex gap-2 mt-2.5">
                      <button
                        onClick={() => handleTakeOver(alert.session_id)}
                        className="rounded bg-amber-600 px-3 py-1 text-xs font-medium text-white hover:bg-amber-700 transition-colors"
                      >
                        立即接管
                      </button>
                      <button
                        onClick={() => handleDismiss(alert.session_id)}
                        className="rounded border border-amber-300 bg-white px-3 py-1 text-xs text-amber-700 hover:bg-amber-50 transition-colors"
                      >
                        稍后处理
                      </button>
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => handleDismiss(alert.session_id)}
                  className="shrink-0 text-amber-400 hover:text-amber-600 transition-colors"
                >
                  <X size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Middle: Conversation List (280px) */}
      <div className="w-[280px] shrink-0 overflow-hidden border-r border-neutral-200 bg-white">
        <ConversationList
          sessions={sessions}
          activeId={activeSessionId}
          onSelect={handleSelectSession}
          onNewSession={handleNewSession}
          isLoading={sessionLoading}
        />
      </div>

      {/* Right: Chat Area */}
      <div className="flex flex-1 min-w-0 flex-col">
        {/* Session header bar */}
        {activeSessionId === 'hermes' ? (
          <div className="flex items-center justify-between border-b border-neutral-100 px-4 py-3 shrink-0 bg-[#0d0d0d]">
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-neutral-800 border border-neutral-700">
                <Cpu size={15} className="text-amber-400" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-white">Hermes 内部助手</span>
                  <span className="inline-flex items-center gap-1 rounded border border-emerald-800 bg-emerald-900/30 px-1.5 py-0 text-[10px] text-emerald-400">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                    在线
                  </span>
                </div>
                <p className="text-[11px] text-neutral-400">AI 数据分析 · 知识问答 · 客户洞察</p>
              </div>
            </div>
          </div>
        ) : activeSession ? (
          <div className="flex items-center justify-between border-b border-neutral-100 px-4 py-3 shrink-0 bg-white">
            <div className="flex items-center gap-3 min-w-0">
              {/* Avatar */}
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-neutral-200 text-neutral-600 text-xs font-medium">
                {(activeSession.customer_name || '?')[0]}
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-neutral-800 truncate">
                    {activeSession.customer_name || activeSession.title}
                  </span>
                  {status && (
                    <span
                      className={`inline-flex shrink-0 items-center rounded border px-1.5 py-0 text-[10px] font-medium ${status.className}`}
                    >
                      {status.label}
                    </span>
                  )}
                  {/* Handover mode badge */}
                  {currentHandoverMode === 'ai' ? (
                    <span className="inline-flex shrink-0 items-center gap-1 rounded border border-neutral-200 bg-neutral-100 px-1.5 py-0 text-[10px] font-medium text-neutral-500">
                      <Bot size={10} strokeWidth={1.5} />
                      AI 客服中
                    </span>
                  ) : (
                    <span className="inline-flex shrink-0 items-center gap-1 rounded border border-green-200 bg-green-50 px-1.5 py-0 text-[10px] font-medium text-green-700">
                      <User size={10} strokeWidth={1.5} />
                      人工客服已接入
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3 mt-0.5">
                  <span className="text-[11px] text-neutral-400">
                    {activeSession.title}
                  </span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {/* Handover switch button */}
              {currentHandoverMode === 'ai' ? (
                <button
                  onClick={() => handleSwitchHandover('human')}
                  className="flex shrink-0 items-center gap-1 rounded border border-neutral-200 bg-white px-2.5 py-1.5 text-xs text-neutral-600 hover:bg-neutral-50 transition-colors"
                >
                  <User size={13} strokeWidth={1.5} />
                  转人工
                </button>
              ) : (
                <button
                  onClick={() => handleSwitchHandover('ai')}
                  className="flex shrink-0 items-center gap-1 rounded border border-green-200 bg-green-50 px-2.5 py-1.5 text-xs text-green-700 hover:bg-green-100 transition-colors"
                >
                  <Bot size={13} strokeWidth={1.5} />
                  切回AI
                </button>
              )}
              <button
                onClick={() => setPanelVisible((v) => !v)}
                className="flex shrink-0 items-center gap-1 rounded border border-neutral-200 bg-white px-2.5 py-1.5 text-xs text-neutral-600 hover:bg-neutral-50 transition-colors"
              >
                {panelVisible ? (
                  <PanelRightClose size={13} strokeWidth={1.5} />
                ) : (
                  <PanelRightOpen size={13} strokeWidth={1.5} />
                )}
                {panelVisible ? '收起' : '客户档案'}
              </button>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center h-12 bg-white border-b border-neutral-100 shrink-0">
            <div className="flex items-center gap-2 text-sm text-neutral-400">
              <MessageSquare size={15} strokeWidth={1.5} />
              选择一个客户会话开始沟通
            </div>
          </div>
        )}

        {/* Chat content */}
        <div className="flex-1 bg-white min-h-0 relative">
          {activeSessionId === 'hermes' ? (
            <HermesChatArea />
          ) : (
            <ChatView onSend={handleAdminSend} messages={localMessages} />
          )}

          {/* AI Suggestion floating panel (human mode) */}
          {currentHandoverMode === 'human' && (
            <div className="absolute bottom-0 left-0 right-0 z-10">
              {/* Trigger bar */}
              {!showSuggestPanel && (
                <div className="flex justify-center pb-2">
                  <button
                    onClick={handleGetSuggestions}
                    className="flex items-center gap-1.5 rounded-full border border-neutral-200 bg-white px-3 py-1.5 text-xs text-neutral-600 shadow-sm hover:bg-neutral-50 transition-colors"
                  >
                    <Sparkles size={12} className="text-amber-500" />
                    AI 建议回复
                  </button>
                </div>
              )}

              {/* Suggestions panel */}
              {showSuggestPanel && (
                <div className="border-t border-neutral-100 bg-white p-3 shadow-sm">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-1.5">
                      <Sparkles size={13} className="text-amber-500" />
                      <span className="text-xs font-medium text-neutral-700">AI 建议回复</span>
                    </div>
                    <div className="flex gap-1.5">
                      <button
                        onClick={handleGetSuggestions}
                        disabled={suggestLoading}
                        className="text-[10px] text-neutral-400 hover:text-neutral-600 transition-colors"
                      >
                        {suggestLoading ? '生成中...' : '刷新'}
                      </button>
                      <button
                        onClick={() => { setShowSuggestPanel(false); setAiSuggestions([]) }}
                        className="text-[10px] text-neutral-400 hover:text-neutral-600 transition-colors"
                      >
                        收起
                      </button>
                    </div>
                  </div>
                  {suggestLoading ? (
                    <div className="flex items-center justify-center py-3">
                      <div className="h-4 w-4 animate-spin rounded-full border-2 border-neutral-200 border-t-amber-500" />
                    </div>
                  ) : (
                    <div className="flex flex-col gap-1.5">
                      {aiSuggestions.map((s, i) => (
                        <button
                          key={i}
                          onClick={() => {
                            // Dispatch a custom event to fill the ChatView input
                            window.dispatchEvent(new CustomEvent('fill-chat-input', { detail: s }))
                          }}
                          className="w-full rounded-lg border border-neutral-200 bg-neutral-50 px-3 py-2 text-left text-xs text-neutral-700 hover:bg-amber-50 hover:border-amber-200 transition-colors"
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Right Panel: Customer Info */}
      {panelVisible && (
        <div className="w-72 shrink-0 overflow-hidden border-l border-neutral-200 transition-all duration-200">
          <CustomerInfoPanel session={activeSession} onClose={() => setPanelVisible(false)} />
        </div>
      )}
    </>
  )
}
