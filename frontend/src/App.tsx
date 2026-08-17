import { useEffect, useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { History, LogOut, MessageCircle, Square } from 'lucide-react'
import ChatView from './components/ChatView'
import LeadForm from './components/LeadForm'
import RatingModal from './components/RatingModal'
import { useChat } from './hooks/useChat'
import { useWebSocket } from './hooks/useWebSocket'
import { useChatStore } from './stores/chat'
import { getChatMessages, apiMessageToChatMessage } from './api/sessions'

export default function App() {
  const navigate = useNavigate()
  const { messages, sendMessage, sessionId, addMessage, initHistory } = useChat()
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const [leadOpen, setLeadOpen] = useState(false)
  const [ratingOpen, setRatingOpen] = useState(false)

  // Issue #7: C端 WebSocket — 接收人工客服消息
  // Bug #3: 用 messagesRef 避免 messages.length 作为依赖导致频繁重连
  const handleWsMessage = useCallback((data: any) => {
    if (data.type === 'new_message' && data.session_id === sessionId) {
      const payload = data.message
      if (!payload?.id || !payload?.content) return
      console.log('[C-WS] append message:', payload.id, payload.role)
      addMessage({
        id: String(payload.id),
        sessionId: data.session_id,
        role: payload.role,
        content: payload.content,
        timestamp: payload.timestamp ? new Date(payload.timestamp).getTime() : Date.now(),
        status: 'sent',
        documents: payload.documents,
        images: payload.images,
      })
      if (payload.documents?.length) useChatStore.getState().attachDocuments(String(payload.id), payload.documents)
      if (payload.images?.length) useChatStore.getState().attachImages(String(payload.id), payload.images)
    }
  }, [sessionId, addMessage])

  const refreshAfterReconnect = useCallback(() => {
    console.log('[C-WS] connected, refreshing history')
    getChatMessages(sessionId)
      .then((data) => useChatStore.getState().mergeMessages(
        (data.messages || []).map(apiMessageToChatMessage),
      ))
      .catch((error) => console.error('[C-WS] history refresh failed:', error))
  }, [sessionId])

  useWebSocket(sessionId, handleWsMessage, refreshAfterReconnect)

  // 加载历史消息：进入页面时从 API 拉取已有对话
  useEffect(() => {
    if (!sessionId) return
    let cancelled = false
    getChatMessages(sessionId)
      .then((data) => {
        if (cancelled) return
        const msgs = (data.messages || []).map(apiMessageToChatMessage)
        if (msgs.length > 0) {
          initHistory(msgs)
        }
      })
      .catch(() => { /* 静默处理，不影响新对话 */ })
      .finally(() => {
        if (!cancelled) setHistoryLoaded(true)
      })
    return () => { cancelled = true }
  }, [sessionId, initHistory])

  function handleLogout() {
    localStorage.removeItem('crmbot_token')
    localStorage.removeItem('crmbot_user')
    navigate('/register', { replace: true })
  }

  useEffect(() => {
    const dismissed = sessionStorage.getItem(`lead-dismissed:${sessionId}`)
    if (dismissed) return
    const userTurns = messages.filter((message) => message.role === 'user').length
    const latestText = messages[messages.length - 1]?.content || ''
    if (userTurns >= 3 || latestText.includes('价格') || latestText.includes('报价')) setLeadOpen(true)
  }, [messages, sessionId])

  async function handleSend(content: string) {
    try {
      await sendMessage(content)
    } catch {
      // handled in hook
    }
  }

  return (
    <div className="flex h-dvh flex-col bg-white">
      {/* Header */}
      <header className="flex items-center gap-2 border-b bg-background px-4 py-3 shrink-0">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
          <MessageCircle size={18} className="text-primary-foreground" />
        </div>
        <div className="flex-1">
          <h1 className="text-sm font-semibold">CRMBOT</h1>
          <p className="text-[11px] text-muted-foreground">智能销售 AI Agent</p>
        </div>
        <button type="button" onClick={() => navigate('/history')} className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground" title="对话历史"><History size={16} /></button>
        <button type="button" onClick={() => setRatingOpen(true)} className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground" title="结束对话"><Square size={15} /></button>
        <button
          onClick={handleLogout}
          className="flex items-center gap-1 rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          title="退出登录"
        >
          <LogOut size={14} />
        </button>
      </header>
      <div className="min-h-0 flex-1"><ChatView customerMode historyLoaded={historyLoaded} messages={messages} onSend={handleSend} /></div>
      <LeadForm open={leadOpen} sessionId={sessionId} onClose={() => { setLeadOpen(false); sessionStorage.setItem(`lead-dismissed:${sessionId}`, '1') }} />
      <RatingModal open={ratingOpen} sessionId={sessionId} onClose={() => setRatingOpen(false)} />
    </div>
  )
}
