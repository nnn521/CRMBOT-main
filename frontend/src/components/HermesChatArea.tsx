import { useRef, useState, useEffect } from 'react'
import { Loader2, Cpu } from 'lucide-react'
import { useHermesStore } from '@/stores/hermes'

export default function HermesChatArea() {
  const { messages, isLoading, sendMessage } = useHermesStore()
  const [input, setInput] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleSend() {
    if (!input.trim() || isLoading) return
    const content = input.trim()
    setInput('')
    setLocalError(null)
    try {
      await sendMessage(content)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '发送失败，请重试'
      setLocalError(msg)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // Welcome screen
  if (messages.length === 0) {
    return (
      <div className="flex h-full flex-col bg-[#0d0d0d]">
        {/* Welcome */}
        <div className="flex flex-1 flex-col items-center justify-center px-4 text-center">
          <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-neutral-800/50 border border-neutral-700">
            <Cpu size={28} className="text-amber-400" />
          </div>
          <h2 className="mb-1 text-base font-semibold text-white">Hermes 内部助手</h2>
          <p className="mb-5 text-sm text-neutral-400 max-w-xs">
            我是你的 AI 数据分析助手。可以问我客户数据、报表分析、知识库查询等问题。
          </p>
          <div className="flex flex-wrap gap-2 justify-center">
            {[
              '最近一周有多少新客户？',
              '分析本月销售趋势',
              '查询知识库中的常见问题',
              '帮我分析高意向客户画像',
            ].map((q) => (
              <button
                key={q}
                onClick={() => {
                  setInput(q)
                  textareaRef.current?.focus()
                }}
                disabled={isLoading}
                className="rounded-lg border border-neutral-700 bg-neutral-800/40 px-3 py-1.5 text-xs text-neutral-300 hover:bg-neutral-700/50 hover:text-white transition-colors disabled:opacity-40"
              >
                {q}
              </button>
            ))}
          </div>
        </div>

        {/* Input */}
        <div className="flex items-end gap-2 border-t border-neutral-800 bg-[#0d0d0d] p-4">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="向 Hermes 提问…"
            rows={1}
            disabled={isLoading}
            className="flex-1 resize-none rounded-xl border border-neutral-700 bg-neutral-800/50 px-4 py-3 text-sm text-white placeholder:text-neutral-500 outline-none focus:ring-2 focus:ring-amber-500/30 disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={isLoading || !input.trim()}
            className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500 text-black hover:bg-amber-400 disabled:opacity-40 transition-colors"
          >
            {isLoading ? (
              <Loader2 size={18} className="animate-spin" />
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            )}
          </button>
        </div>
      </div>
    )
  }

  // Chat mode
  return (
    <div className="flex h-full flex-col bg-[#0d0d0d]">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {messages.map((msg) => {
          const isUser = msg.role === 'user'
          return (
            <div key={msg.id} className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} mb-4`}>
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                  isUser
                    ? 'bg-amber-500/15 text-neutral-200 border border-amber-500/20 rounded-br-sm'
                    : 'bg-neutral-800 text-neutral-200 border border-neutral-700 rounded-bl-sm'
                }`}
              >
                <p className="text-sm leading-relaxed whitespace-pre-wrap">
                  {msg.content}
                  {msg.isStreaming && (
                    <span className="inline-block w-1.5 h-4 ml-0.5 bg-amber-400 animate-pulse rounded-sm align-middle" />
                  )}
                </p>
                <span className="text-[10px] mt-1 block text-neutral-500">
                  {formatHermesTime(msg.timestamp)}
                </span>
              </div>
            </div>
          )
        })}

        {/* Loading dots */}
        {isLoading && messages[messages.length - 1]?.content === '' && (
          <div className="flex justify-start mb-4">
            <div className="rounded-xl bg-neutral-800 px-4 py-3 border border-neutral-700">
              <div className="flex gap-1.5">
                <span className="h-2 w-2 animate-bounce rounded-full bg-neutral-500 [animation-delay:0ms]" />
                <span className="h-2 w-2 animate-bounce rounded-full bg-neutral-500 [animation-delay:150ms]" />
                <span className="h-2 w-2 animate-bounce rounded-full bg-neutral-500 [animation-delay:300ms]" />
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Error toast */}
      {localError && (
        <div className="mx-4 mb-2 flex items-center gap-2 rounded-lg border border-red-800 bg-red-900/20 px-3 py-2">
          <span className="text-xs text-red-300">{localError}</span>
          <button onClick={() => setLocalError(null)} className="ml-auto text-xs text-red-400 hover:text-red-300">
            关闭
          </button>
        </div>
      )}

      {/* Input */}
      <div className="flex items-end gap-2 border-t border-neutral-800 bg-[#0d0d0d] p-4">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="向 Hermes 提问…"
          rows={1}
          disabled={isLoading}
          className="flex-1 resize-none rounded-xl border border-neutral-700 bg-neutral-800/50 px-4 py-3 text-sm text-white placeholder:text-neutral-500 outline-none focus:ring-2 focus:ring-amber-500/30 disabled:opacity-50"
        />
        <button
          onClick={handleSend}
          disabled={isLoading || !input.trim()}
          className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500 text-black hover:bg-amber-400 disabled:opacity-40 transition-colors"
        >
          {isLoading ? (
            <Loader2 size={18} className="animate-spin" />
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          )}
        </button>
      </div>
    </div>
  )
}

function formatHermesTime(ts: number): string {
  const d = new Date(ts)
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}
