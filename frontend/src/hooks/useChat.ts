import { useChatStore, generateId } from '@/stores/chat'
import { sendChatMessage } from '@/api/chat'
import { useCallback, useRef } from 'react'
import type { ChatMessage, DocumentInfo } from '@/types'

export function useChat() {
  const { messages, isLoading, sessionId, attachedDocs, attachedImages, addMessage, updateMessageStatus, attachDocuments, attachImages, setLoading, setMessages } = useChatStore()
  const historyRef = useRef<{ role: string; content: string }[]>([])

  /** 用历史消息初始化 store 和 historyRef（页面加载时调用） */
  const initHistory = useCallback((msgs: ChatMessage[]) => {
    setMessages(msgs)
    historyRef.current = msgs.map((m) => ({ role: m.role, content: m.content }))
  }, [setMessages])

  const sendMessage = useCallback(async (content: string) => {
    if (!content.trim() || isLoading) return

    const userMsg: ChatMessage = {
      id: generateId(),
      role: 'user',
      content: content.trim(),
      timestamp: Date.now(),
      status: 'sending',
    }
    addMessage(userMsg)
    setLoading(true)

    historyRef.current = [
      ...historyRef.current,
      { role: 'user', content: content.trim() },
    ]

    try {
      const res = await sendChatMessage(sessionId, content.trim(), historyRef.current)
      updateMessageStatus(userMsg.id, 'sent')

      if (res.status === 'waiting_human') {
        addMessage({
          id: `handover-${res.user_message_id || generateId()}`,
          role: 'assistant',
          content: '已为您转接人工购车顾问，请稍候。',
          timestamp: Date.now(),
          status: 'sent',
        })
        return res
      }

      const msgId = res.message_id || generateId()

      // Map documents from response
      let msgDocs: DocumentInfo[] | undefined
      if (res.documents && res.documents.length > 0) {
        msgDocs = res.documents.map((d: any) => ({
          file_name: d.filename || d.file_name,
          file_path: d.path || d.file_path || `/api/v1/documents/${encodeURIComponent(d.filename || d.file_name)}`,
          doc_type: d.type || d.doc_type || 'unknown',
          file_size: d.size || d.file_size || 0,
        }))
        attachDocuments(msgId, msgDocs)
      }

      // 人工模式或 AI 无回复时，不添加空的 assistant 消息
      if (res.reply) {
        // WebSocket 可能比 HTTP 先到；服务端 message_id 是唯一去重依据。
        if (useChatStore.getState().hasDedupKey(msgId)) {
          // WS 已经处理过消息文本，但可能没处理图片/文档 → 补 attach
          if (res.images && res.images.length > 0) {
            attachImages(msgId, res.images)
          }
          historyRef.current = [
            ...historyRef.current,
            { role: 'assistant', content: res.reply },
          ]
          return res
        }
        // 先 attach 图片（WS 可能没带），再添加消息
        if (res.images && res.images.length > 0) {
          attachImages(msgId, res.images)
        }

        const assistantMsg: ChatMessage = {
          id: msgId,
          role: 'assistant',
          content: res.reply,
          timestamp: Date.now(),
          documents: msgDocs,
          status: 'sent',
        }
        addMessage(assistantMsg)
        historyRef.current = [
          ...historyRef.current,
          { role: 'assistant', content: res.reply },
        ]
      }

      return res
    } catch (err) {
      updateMessageStatus(userMsg.id, 'failed')
      const errorMsg: ChatMessage = {
        id: generateId(),
        role: 'assistant',
        content: '抱歉，请求出错了，请稍后重试。',
        timestamp: Date.now(),
      }
      addMessage(errorMsg)
      throw err
    } finally {
      setLoading(false)
    }
  }, [isLoading, sessionId, addMessage, updateMessageStatus, attachDocuments, attachImages, setLoading])

  return {
    messages,
    isLoading,
    sessionId,
    attachedDocs,
    attachedImages,
    sendMessage,
    addMessage,
    initHistory,
  }
}
