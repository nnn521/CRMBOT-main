import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowLeft, MessageSquare, Search, Trash2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { deleteHistory, fetchHistory } from '@/api/engagement'
import { useChatStore } from '@/stores/chat'
import type { HistorySession } from '@/types'

export default function HistoryPage() {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<HistorySession[]>([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const touchStart = useRef<Record<string, number>>({})
  const [revealed, setRevealed] = useState<string | null>(null)

  useEffect(() => {
    fetchHistory().then(setSessions).finally(() => setLoading(false))
  }, [])

  const filtered = useMemo(() => sessions.filter((item) => item.preview.toLowerCase().includes(query.toLowerCase())), [sessions, query])

  function openSession(sessionId: string) {
    useChatStore.getState().setSessionId(sessionId)
    useChatStore.getState().clearMessages()
    navigate('/chat')
  }

  async function remove(sessionId: string) {
    await deleteHistory(sessionId)
    setSessions((current) => current.filter((item) => item.session_id !== sessionId))
  }

  return (
    <div className="min-h-screen bg-neutral-50">
      <header className="sticky top-0 z-10 border-b border-neutral-200 bg-white px-4 py-3">
        <div className="mx-auto flex max-w-2xl items-center gap-3"><button type="button" onClick={() => navigate('/chat')} aria-label="返回聊天" title="返回"><ArrowLeft /></button><h1 className="font-semibold">对话历史</h1></div>
      </header>
      <main className="mx-auto max-w-2xl p-4">
        <label className="flex h-11 items-center gap-2 rounded-lg border border-neutral-200 bg-white px-3"><Search size={18} className="text-neutral-400" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索对话内容" className="flex-1 bg-transparent text-sm outline-none" /></label>
        <div className="mt-4 space-y-2">
          {loading && <p className="py-10 text-center text-sm text-neutral-500">正在加载</p>}
          {!loading && filtered.length === 0 && <div className="py-14 text-center text-neutral-400"><MessageSquare className="mx-auto" /><p className="mt-2 text-sm">暂无对话记录</p></div>}
          {filtered.map((item) => (
            <div key={item.session_id} className="relative overflow-hidden rounded-lg bg-red-600">
              <button type="button" onClick={() => remove(item.session_id)} className="absolute right-0 top-0 flex h-full w-20 items-center justify-center text-white" title="删除"><Trash2 size={20} /></button>
              <button
                type="button"
                onClick={() => revealed === item.session_id ? setRevealed(null) : openSession(item.session_id)}
                onTouchStart={(event) => { touchStart.current[item.session_id] = event.touches[0].clientX }}
                onTouchEnd={(event) => {
                  const delta = event.changedTouches[0].clientX - (touchStart.current[item.session_id] || 0)
                  if (delta < -40) setRevealed(item.session_id)
                  if (delta > 40) setRevealed(null)
                }}
                className={`relative z-[1] w-full bg-white p-4 text-left transition-transform ${revealed === item.session_id ? '-translate-x-20' : ''}`}
              >
                <div className="flex items-center justify-between gap-3"><p className="truncate text-sm font-medium text-neutral-900">{item.preview}</p><time className="shrink-0 text-xs text-neutral-400">{formatDate(item.updated_at)}</time></div>
                <p className="mt-2 text-xs text-neutral-500">{item.message_count} 条消息</p>
              </button>
            </div>
          ))}
        </div>
      </main>
    </div>
  )
}

function formatDate(value: string | null) {
  if (!value) return ''
  return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })
}
