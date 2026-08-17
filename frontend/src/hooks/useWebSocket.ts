import { useEffect, useRef, useCallback, useState } from 'react'
import type { WebSocketEvent } from '@/types'

export type WsStatus = 'idle' | 'connecting' | 'connected' | 'error' | 'closed'

type MessageHandler = (data: WebSocketEvent) => void

export function useWebSocket(
  sessionId: string | null,
  onMessage: MessageHandler,
  onConnected?: () => void,
) {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const pingTimer = useRef<ReturnType<typeof setInterval> | undefined>(undefined)
  const reconnectAttempt = useRef(0)
  const shouldReconnect = useRef(true)
  // Issue #12: use ref for onMessage to avoid reconnecting on callback change
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage
  const onConnectedRef = useRef(onConnected)
  onConnectedRef.current = onConnected
  
  // 🔍 Debug: expose WS connection status
  const [status, setStatus] = useState<WsStatus>('idle')
  const [lastError, setLastError] = useState<string>('')

  const connect = useCallback(() => {
    if (!sessionId) {
      console.warn('[WS] No sessionId, skipping connect')
      setStatus('idle')
      return
    }
    
    setStatus('connecting')
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    // Issue #9: 带上 JWT token 作为 query param 用于 WebSocket 鉴权
    const token = localStorage.getItem('crmbot_token') || ''
    const wsUrl = `${protocol}//${window.location.host}/api/v1/ws/${sessionId}?token=${encodeURIComponent(token)}`
    
    console.log('[WS] Connecting to:', wsUrl.replace(token, '***'))
    console.log('[WS] sessionId:', sessionId, 'token exists:', !!token)
    
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws
    
    ws.onopen = () => {
      console.log('[WS] ✅ Connected:', sessionId)
      setStatus('connected')
      setLastError('')
      reconnectAttempt.current = 0
      onConnectedRef.current?.()
    }
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        console.log('[WS] Message received:', data.type, data.session_id, data.message?.id)
        onMessageRef.current(data)
      } catch (e) {
        console.error('[WS] Parse error:', e)
      }
    }
    
    ws.onclose = (event) => {
      if (!shouldReconnect.current) return
      reconnectAttempt.current += 1
      const delay = Math.min(1000 * 2 ** reconnectAttempt.current, 10000)
      console.log(`[WS] Disconnected, reconnecting in ${delay}ms... code:`, event.code)
      setStatus('closed')
      reconnectTimer.current = setTimeout(connect, delay)
    }
    
    ws.onerror = (err) => {
      console.error('[WS] Error:', err)
      setStatus('error')
      setLastError(String(err))
    }
    
    // Keepalive ping every 30s
    if (pingTimer.current) clearInterval(pingTimer.current)
    pingTimer.current = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }))
      }
    }, 30000)
    
  }, [sessionId])
  
  useEffect(() => {
    shouldReconnect.current = true
    connect()
    return () => {
      shouldReconnect.current = false
      wsRef.current?.close()
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      if (pingTimer.current) clearInterval(pingTimer.current)
    }
  }, [connect])
  
  return { wsStatus: status, wsError: lastError } as const
}
