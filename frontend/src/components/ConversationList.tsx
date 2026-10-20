import { useMemo, useState } from 'react'
import { Search, Clock, Loader2, AlertTriangle } from 'lucide-react'
import { useChatStore } from '@/stores/chat'
import { normalizeStatus } from '@/api/sessions'
import type { Session } from '@/types'

interface Props {
  sessions: Session[]
  activeId: string | null
  onSelect: (id: string) => void
  isLoading?: boolean
}

const statusConfig: Record<Session['status'], { label: string; className: string }> = {
  new: { label: '🟡 新客户', className: 'bg-amber-50 text-amber-800 border-amber-200' },
  active: { label: '🔵 跟进中', className: 'bg-sky-50 text-sky-700 border-sky-200' },
  negotiating: { label: '🟠 洽谈中', className: 'bg-orange-50 text-orange-700 border-orange-200' },
  closed: { label: '🟢 已成交', className: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  lost: { label: '⚪ 已流失', className: 'bg-neutral-50 text-neutral-400 border-neutral-200' },
}

function formatTime(ts: string): string {
  const d = new Date(ts)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (d.toDateString() === now.toDateString()) {
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
  }
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}

export default function ConversationList({
  sessions,
  activeId,
  onSelect,
  isLoading,
}: Props) {
  const [search, setSearch] = useState('')
  const highIntentAlerts = useChatStore((s) => s.highIntentAlerts)
  const highIntentSessionIds = useMemo(
    () => new Set(highIntentAlerts.map((a) => a.session_id)),
    [highIntentAlerts],
  )

  const filtered = sessions
    .filter(
      (s) =>
        s.title.toLowerCase().includes(search.toLowerCase()) ||
        (s.customer_name &&
          s.customer_name.toLowerCase().includes(search.toLowerCase())),
    )
    .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())

  return (
    <div className="flex h-full flex-col bg-white">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-3">
        <h2 className="text-sm font-semibold text-neutral-800">客户会话</h2>
        <span className="rounded-full bg-neutral-100 px-1.5 py-0.5 text-[10px] font-medium text-neutral-500">
          {sessions.length}
        </span>
      </div>

      {/* Search */}
      <div className="px-3 pb-2">
        <div className="flex items-center gap-2 rounded-lg border border-neutral-200 bg-neutral-50 px-2.5 py-1.5">
          <Search size={13} className="text-neutral-400 shrink-0" strokeWidth={1.5} />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索客户、车型..."
            className="flex-1 bg-transparent text-xs text-neutral-700 placeholder:text-neutral-400 outline-none"
          />
        </div>
      </div>

      {/* 会话列表（会话由客户发消息自动创建，B端不再手动新建空会话） */}
      <div className="px-3 pb-2">
        <p className="text-[11px] text-neutral-400">客户发消息后自动出现在此列表</p>
      </div>

      {/* Hermes AI Assistant card */}
      <div className="px-3 pb-3">
        <button
          onClick={() => onSelect('hermes')}
          className={`flex w-full rounded-lg overflow-hidden hover:bg-neutral-50 transition-colors text-left ${
            activeId === 'hermes'
              ? 'bg-neutral-50 border-2 border-amber-400'
              : 'border border-neutral-200 bg-white'
          }`}
        >
          {/* Left gold accent bar */}
          <div className={`w-1 shrink-0 ${activeId === 'hermes' ? 'bg-amber-400' : 'bg-amber-400'}`} />
          <div className="flex-1 flex items-center gap-3 px-3 py-3">
            {/* Brand icon */}
            <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${activeId === 'hermes' ? 'bg-black' : 'bg-neutral-900'}`}>
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="white"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M12 2a4 4 0 0 1 4 4v1h2a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h2V6a4 4 0 0 1 4-4z" />
              </svg>
            </div>
            {/* Title + subtitle */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-[13px] font-semibold text-neutral-800">Hermes 内部助手</span>
                <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0 text-[10px] ${activeId === 'hermes' ? 'bg-amber-100 text-amber-700' : 'border border-neutral-200 bg-neutral-50 text-neutral-400'}`}>
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  内部
                </span>
              </div>
              <div className="mt-0.5 text-[11px] text-neutral-400">
                报表查询 · 知识问答 · 数据分析
              </div>
            </div>
          </div>
        </button>
      </div>

      {/* Divider */}
      <div className="mx-3 border-t border-neutral-100" />

      {/* Session List */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 size={20} className="animate-spin text-neutral-300" />
          </div>
        ) : filtered.length === 0 ? (
          <p className="px-4 py-8 text-center text-xs text-neutral-400">
            {search ? '无匹配会话' : '暂无会话'}
          </p>
        ) : (
          filtered.map((session) => {
            const isActive = session.id === activeId
            const status = statusConfig[normalizeStatus(session.status)]
            const isHighIntent = highIntentSessionIds.has(session.id)

            return (
              <button
                key={session.id}
                onClick={() => onSelect(session.id)}
                className={`flex w-full items-stretch gap-2.5 px-3 py-2.5 text-left transition-colors ${
                  isActive
                    ? 'bg-neutral-50'
                    : 'hover:bg-neutral-50/50'
                } ${isHighIntent ? 'border-l-2 border-l-orange-400' : ''}`}
              >
                {/* Active indicator */}
                <div
                  className={`w-0.5 shrink-0 rounded-full self-stretch ${
                    isActive ? 'bg-black' : 'bg-transparent'
                  }`}
                />

                {/* Avatar */}
                <div
                  className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-xs font-medium ${
                    isActive
                      ? 'bg-black text-white'
                      : 'bg-neutral-100 text-neutral-500'
                  }`}
                >
                  {(session.customer_name || '?')[0]}
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-1">
                    <span className="text-[13px] font-medium text-neutral-800 truncate">
                      {session.customer_name || session.title}
                    </span>
                    <span className="flex items-center gap-0.5 text-[10px] text-neutral-400 shrink-0">
                      <Clock size={10} strokeWidth={1.5} />
                      {formatTime(session.updated_at)}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <span
                      className={`inline-flex items-center rounded border px-1.5 py-0 text-[10px] font-medium ${status.className}`}
                    >
                      {status.label}
                    </span>
                    {session.handover_mode === 'human' && (
                      <span className="inline-flex items-center rounded border border-green-200 bg-green-50 px-1.5 py-0 text-[10px] font-medium text-green-700">
                        人工
                      </span>
                    )}
                    {isHighIntent && (
                      <span className="inline-flex items-center gap-0.5 rounded border border-orange-200 bg-orange-50 px-1.5 py-0 text-[10px] font-medium text-orange-700">
                        <AlertTriangle size={9} />
                        高意向
                      </span>
                    )}
                  </div>
                  <div className="mt-1 text-[11px] text-neutral-400 truncate leading-relaxed">
                    {session.title}
                  </div>
                </div>
              </button>
            )
          })
        )}
      </div>
    </div>
  )
}
