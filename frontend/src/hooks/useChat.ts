import { useChatStore, generateId } from '@/stores/chat'
import { sendChatMessage } from '@/api/chat'
import { useCallback, useRef } from 'react'
import type { ChatMessage } from '@/types'
import { apiMessageToChatMessage } from '@/api/sessions'

export function useChat() {
  const {
    messages,
    isLoading,
    sessionId,
    attachedDocs,
    attachedImages,
    addMessage,
    updateMessageStatus,
    attachDocuments,
    attachImages,
    setLoading,
    setMessages,
  } = useChatStore()
  // 发送中防重入（修复 isLoading 闭包过期导致的双发）
  const sendingRef = useRef(false)

  /** 用历史消息初始化 store（页面加载时调用） */
  const initHistory = useCallback(
    (msgs: ChatMessage[]) => {
      setMessages(msgs)
    },
    [setMessages],
  )

  const sendMessage = useCallback(
    async (content: string, imageUrl?: string) => {
      if (!content.trim() || isLoading || sendingRef.current) return
      sendingRef.current = true

      const userMsg: ChatMessage = {
        id: generateId(),
        role: 'user',
        content: content.trim(),
        timestamp: Date.now(),
        status: 'sending',
      }
      addMessage(userMsg)
      setLoading(true)

      try {
        const res = await sendChatMessage(sessionId, content.trim(), imageUrl)
        updateMessageStatus(userMsg.id, 'sent', res.user_message_id)

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

        const assistantMsg = apiMessageToChatMessage({
          ...res,
          id: msgId,
          role: 'assistant',
          content: res.reply,
          timestamp: Date.now(),
        })
        if (assistantMsg.documents?.length) attachDocuments(msgId, assistantMsg.documents)
        if (res.images?.length) attachImages(msgId, res.images)

        // WS may arrive first; upsert still merges late citations/conditions by ID.
        if (res.reply || res.message_id) addMessage(assistantMsg)

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
        sendingRef.current = false
      }
    },
    [isLoading, sessionId, addMessage, updateMessageStatus, attachDocuments, attachImages, setLoading],
  )

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
