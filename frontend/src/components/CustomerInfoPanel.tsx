import { X, Calendar, FileText, Clock } from 'lucide-react'
import type { Session } from '@/types'

interface Props {
  session: Session | null
  onClose: () => void
}

const statusConfig: Record<Session['status'], { label: string; className: string }> = {
  new: { label: '待跟进', className: 'bg-amber-50 text-amber-800 border-amber-200' },
  active: { label: '跟进中', className: 'bg-neutral-100 text-neutral-600 border-neutral-200' },
  negotiating: { label: '洽谈中', className: 'bg-neutral-100 text-neutral-800 border-neutral-300' },
  closed: { label: '已成交', className: 'bg-neutral-100 text-neutral-600 border-neutral-200' },
  lost: { label: '已流失', className: 'bg-neutral-50 text-neutral-400 border-neutral-200' },
}

function formatDateTime(iso: string): string {
  const d = new Date(iso)
  return `${d.getFullYear()}/${(d.getMonth() + 1).toString().padStart(2, '0')}/${d.getDate().toString().padStart(2, '0')} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}

export default function CustomerInfoPanel({ session, onClose }: Props) {
  if (!session) {
    return (
      <div className="flex h-full flex-col bg-white">
        <div className="flex items-center justify-between px-4 py-3 border-b border-neutral-100">
          <h3 className="text-sm font-semibold text-neutral-700">客户档案</h3>
          <button onClick={onClose} className="rounded p-1 hover:bg-neutral-100 transition-colors">
            <X size={15} className="text-neutral-400" strokeWidth={1.5} />
          </button>
        </div>
        <div className="flex flex-1 items-center justify-center px-6">
          <p className="text-sm text-neutral-400 text-center">
            点击左侧会话<br />查看客户详情
          </p>
        </div>
      </div>
    )
  }

  const status = statusConfig[session.status]

  return (
    <div className="flex h-full flex-col bg-white">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-neutral-100">
        <h3 className="text-sm font-semibold text-neutral-700">客户档案</h3>
        <button onClick={onClose} className="rounded p-1 hover:bg-neutral-100 transition-colors">
          <X size={15} className="text-neutral-400" strokeWidth={1.5} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* Customer header */}
        <div className="px-4 py-4 border-b border-neutral-100 bg-white">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-neutral-200 text-neutral-700 text-sm font-medium">
              {(session.customer_name || session.title || '?')[0]}
            </div>
            <div className="min-w-0">
              <h4 className="text-sm font-semibold text-neutral-800">
                {session.customer_name || session.title}
              </h4>
              <span
                className={`inline-flex items-center rounded border px-1.5 py-0 text-[10px] font-medium mt-1 ${status.className}`}
              >
                {status.label}
              </span>
            </div>
          </div>
        </div>

        {/* Info sections */}
        <div className="divide-y divide-neutral-100">
          {/* Session info */}
          <div className="px-4 py-3">
            <h5 className="flex items-center gap-1.5 text-[11px] font-semibold text-neutral-400 uppercase tracking-wide mb-2">
              <FileText size={12} strokeWidth={1.5} /> 会话信息
            </h5>
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-xs">
                <span className="text-neutral-400 w-12 shrink-0">主题</span>
                <span className="text-neutral-700 truncate">{session.title || '-'}</span>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <span className="text-neutral-400 w-12 shrink-0">客户</span>
                <span className="text-neutral-700">{session.customer_name || '未填写'}</span>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <span className="text-neutral-400 w-12 shrink-0">状态</span>
                <span
                  className={`inline-flex items-center rounded border px-1.5 py-0 text-[10px] font-medium ${status.className}`}
                >
                  {status.label}
                </span>
              </div>
            </div>
          </div>

          {/* Timestamps */}
          <div className="px-4 py-3">
            <h5 className="flex items-center gap-1.5 text-[11px] font-semibold text-neutral-400 uppercase tracking-wide mb-2">
              <Calendar size={12} strokeWidth={1.5} /> 时间信息
            </h5>
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-xs">
                <span className="text-neutral-400 w-12 shrink-0">创建</span>
                <span className="text-neutral-500 flex items-center gap-1">
                  <Clock size={10} strokeWidth={1.5} />
                  {formatDateTime(session.created_at || session.updated_at)}
                </span>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <span className="text-neutral-400 w-12 shrink-0">更新</span>
                <span className="text-neutral-500 flex items-center gap-1">
                  <Clock size={10} strokeWidth={1.5} />
                  {formatDateTime(session.updated_at)}
                </span>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="px-4 py-3 space-y-2">
            <button className="flex items-center justify-center gap-1.5 w-full rounded-lg bg-black px-3 py-2 text-xs font-medium text-white hover:bg-neutral-800 transition-colors">
              <FileText size={13} strokeWidth={1.5} />
              创建报价单
            </button>
            <button className="flex items-center justify-center gap-1.5 w-full rounded-lg border border-neutral-200 bg-white px-3 py-2 text-xs font-medium text-neutral-600 hover:bg-neutral-50 transition-colors">
              安排试驾
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
