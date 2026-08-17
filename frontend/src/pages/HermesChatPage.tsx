import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Cpu, Loader2, Package, Terminal, ExternalLink, AlertCircle, Trash2 } from 'lucide-react'
import { checkHermesHealth } from '@/api/hermes'
import { useHermesStore } from '@/stores/hermes'
import type { HermesChatMessage } from '@/stores/hermes'

export default function HermesChatPage() {
  const navigate = useNavigate()
  const {
    messages,
    isLoading,
    isOnline,
    healthError,
    setOnline,
    sendMessage,
    clearMessages,
  } = useHermesStore()

  const [input, setInput] = useState('')
  const [showDockerCommand, setShowDockerCommand] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [localError, setLocalError] = useState<string | null>(null)

  // Check Hermes health on mount
  useEffect(() => {
    let cancelled = false
    async function check() {
      const result = await checkHermesHealth()
      if (!cancelled) {
        setOnline(result.online, result.detail)
      }
    }
    check()
    return () => { cancelled = true }
  }, [setOnline])

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Focus input when online
  useEffect(() => {
    if (isOnline && textareaRef.current) {
      textareaRef.current.focus()
    }
  }, [isOnline])

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

  // --- Loading state (checking health) ---
  if (isOnline === null) {
    return (
      <div className="flex h-full flex-col bg-[#0d0d0d]">
        <HermesHeader onBack={() => navigate('/')} />
        <div className="flex flex-1 items-center justify-center">
          <div className="flex flex-col items-center gap-3">
            <Loader2 size={28} className="animate-spin text-neutral-500" />
            <p className="text-sm text-neutral-400">正在检测 Hermes 服务状态…</p>
          </div>
        </div>
      </div>
    )
  }

  // --- Offline: Installation guide ---
  if (isOnline === false) {
    return (
      <div className="flex h-full flex-col bg-[#0d0d0d]">
        <HermesHeader onBack={() => navigate('/')} />
        <div className="flex flex-1 items-center justify-center px-6">
          <div className="flex max-w-md flex-col items-center text-center">
            {/* Icon */}
            <div className="mb-5 flex h-20 w-20 items-center justify-center rounded-2xl bg-neutral-800/50 border border-neutral-700">
              <Package size={36} className="text-amber-400" />
            </div>

            <h2 className="mb-2 text-lg font-semibold text-white">
              Hermes 内部助手未安装
            </h2>
            <p className="mb-6 text-sm leading-relaxed text-neutral-400">
              Hermes 是 CRMBOT 的 AI 内部助手，基于 NousResearch Hermes 模型。
              可以帮你做数据分析、知识问答、客户洞察等内部工作，
              独立于客户聊天系统运行。
            </p>

            {/* Error detail if available */}
            {healthError && (
              <div className="mb-5 flex w-full items-start gap-2 rounded-lg border border-neutral-700 bg-neutral-800/30 px-3 py-2.5 text-left">
                <AlertCircle size={14} className="mt-0.5 shrink-0 text-neutral-500" />
                <p className="text-xs text-neutral-500">{healthError}</p>
              </div>
            )}

            {/* Action buttons */}
            <div className="flex w-full flex-col gap-3">
              <button
                onClick={() => setShowDockerCommand(!showDockerCommand)}
                className="flex items-center justify-center gap-2 rounded-xl bg-amber-500 px-5 py-3 text-sm font-medium text-black hover:bg-amber-400 transition-colors"
              >
                <Terminal size={16} />
                一键启动
              </button>

              {showDockerCommand && (
                <div className="rounded-xl border border-neutral-700 bg-[#1a1a1a] p-4 text-left">
                  <p className="mb-2 text-xs text-neutral-500">
                    在项目根目录下运行以下命令：
                  </p>
                  <code className="block rounded-lg bg-black px-3 py-2.5 text-xs text-green-400 font-mono leading-relaxed select-all">
                    docker-compose up -d hermes
                  </code>
                  <p className="mt-2 text-[11px] text-neutral-600">
                    这将拉取镜像并启动 Hermes 服务在 localhost:8642
                  </p>
                </div>
              )}

              <a
                href="/docs/hermes-setup.md"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center gap-1.5 text-xs text-neutral-500 hover:text-neutral-300 transition-colors"
              >
                <ExternalLink size={12} />
                查看手动安装指南
              </a>

              <button
                onClick={async () => {
                  setOnline(null)
                  const result = await checkHermesHealth()
                  setOnline(result.online, result.detail)
                }}
                className="mt-2 text-xs text-neutral-600 hover:text-neutral-400 transition-colors"
              >
                重新检测
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // --- Online: Chat interface ---
  return (
    <div className="flex h-full flex-col bg-[#0d0d0d]">
      <HermesHeader
        onBack={() => navigate('/')}
        onClear={messages.length > 0 ? clearMessages : undefined}
      />

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-neutral-800/50">
              <Cpu size={30} className="text-amber-400" />
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
        ) : (
          <>
            {messages.map((msg) => (
              <HermesBubble key={msg.id} message={msg} />
            ))}

            {/* Loading indicator while streaming */}
            {isLoading && messages[messages.length - 1]?.content === '' && (
              <div className="flex justify-start mb-4">
                <div className="rounded-xl bg-neutral-800 px-4 py-3">
                  <div className="flex gap-1.5">
                    <span className="h-2 w-2 animate-bounce rounded-full bg-neutral-500 [animation-delay:0ms]" />
                    <span className="h-2 w-2 animate-bounce rounded-full bg-neutral-500 [animation-delay:150ms]" />
                    <span className="h-2 w-2 animate-bounce rounded-full bg-neutral-500 [animation-delay:300ms]" />
                  </div>
                </div>
              </div>
            )}
          </>
        )}

        {/* Local error toast */}
        {localError && (
          <div className="mb-3 flex items-center gap-2 rounded-lg border border-red-800 bg-red-900/20 px-3 py-2">
            <AlertCircle size={14} className="text-red-400 shrink-0" />
            <p className="text-xs text-red-300">{localError}</p>
            <button
              onClick={() => setLocalError(null)}
              className="ml-auto text-xs text-red-400 hover:text-red-300"
            >
              关闭
            </button>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input area */}
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

// --- Sub-components ---

function HermesHeader({
  onBack,
  onClear,
}: {
  onBack: () => void
  onClear?: () => void
}) {
  return (
    <div className="flex items-center justify-between border-b border-neutral-800 bg-[#0d0d0d] px-4 py-3">
      <div className="flex items-center gap-3">
        <button
          onClick={onBack}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-neutral-400 hover:text-white hover:bg-neutral-800 transition-colors"
        >
          <ArrowLeft size={18} />
        </button>
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-neutral-900 border border-neutral-700">
            <Cpu size={15} className="text-amber-400" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white">Hermes 内部助手</h3>
            <p className="text-[10px] text-emerald-400">● 在线</p>
          </div>
        </div>
      </div>
      {onClear && (
        <button
          onClick={onClear}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-neutral-500 hover:text-red-400 hover:bg-neutral-800 transition-colors"
          title="清空对话"
        >
          <Trash2 size={14} />
        </button>
      )}
    </div>
  )
}

function HermesBubble({ message }: { message: HermesChatMessage }) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} mb-4`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 ${
          isUser
            ? 'bg-amber-500/15 text-neutral-200 border border-amber-500/20 rounded-br-sm'
            : 'bg-neutral-800 text-neutral-200 border border-neutral-700 rounded-bl-sm'
        }`}
      >
        <p className="text-sm leading-relaxed whitespace-pre-wrap">
          {message.content}
          {message.isStreaming && (
            <span className="inline-block w-1.5 h-4 ml-0.5 bg-amber-400 animate-pulse rounded-sm align-middle" />
          )}
        </p>
        <span className="text-[10px] mt-1 block text-neutral-500">
          {formatTime(message.timestamp)}
        </span>
      </div>
    </div>
  )
}

function formatTime(ts: number): string {
  const d = new Date(ts)
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}
