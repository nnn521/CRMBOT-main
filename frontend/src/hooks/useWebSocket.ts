import { useEffect, useRef, useCallback, useState } from 'react'
import type { WebSocketEvent } from '@/types'

export type WsStatus = 'idle' | 'connecting' | 'connected' | 'error' | 'closed'

type MessageHandler = (data: WebSocketEvent) => void

const PING_INTERVAL = 30_000
const STALE_AFTER = 75_000
const MAX_RECONNECT_ATTEMPTS = 20

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
  const lastFrameAt = useRef(Date.now())
  // 用 ref 保存回调，避免回调变化触发重连
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage
  const onConnectedRef = useRef(onConnected)
  onConnectedRef.current = onConnected

  const [status, setStatus] = useState<WsStatus>('idle')
  const [lastError, setLastError] = useState('')

  const connect = useCallback(() => {
    if (!sessionId) {
      setStatus('idle')
      return
    }

    setStatus('connecting')
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    // 认证走 httpOnly Cookie（握手自动携带），JWT 不再出现在 URL 中
    const wsUrl = `${protocol}//${window.location.host}/api/v1/ws/${sessionId}`

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      lastFrameAt.current = Date.now()
      setStatus('connected')
      setLastError('')
      reconnectAttempt.current = 0
      onConnectedRef.current?.()
    }

    ws.onmessage = (event) => {
      lastFrameAt.current = Date.now()
      try {
        const data = JSON.parse(event.data) as WebSocketEvent
        onMessageRef.current(data)
      } catch (e) {
        console.error('[WS] Parse error:', e)
      }
    }

    ws.onclose = (event) => {
      if (!shouldReconnect.current) return
      if (event.code === 4001 || event.code === 4003) {
        // 鉴权失败：不再重连
        setStatus('error')
        setLastError('未授权')
        return
      }
      if (reconnectAttempt.current >= MAX_RECONNECT_ATTEMPTS) {
        setStatus('error')
        setLastError('连接失败次数过多，已停止重连')
        return
      }
      reconnectAttempt.current += 1
      const base = Math.min(1000 * 2 ** reconnectAttempt.current, 10000)
      const delay = base * (0.8 + Math.random() * 0.4) // 抖动，避免同步重连风暴
      setStatus('closed')
      reconnectTimer.current = setTimeout(connect, delay)
    }

    ws.onerror = () => {
      setStatus('error')
      setLastError('连接异常')
    }

    // 心跳：发送 ping 并检测半开连接（超时未收到任何帧则强制关闭触发重连）
    if (pingTimer.current) clearInterval(pingTimer.current)
    pingTimer.current = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }))
      }
      if (Date.now() - lastFrameAt.current > STALE_AFTER) {
        ws.close()
      }
    }, PING_INTERVAL)
  }, [sessionId])

  useEffect(() => {
    shouldReconnect.current = true
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
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
