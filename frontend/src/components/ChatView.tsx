import { useEffect, useMemo, useRef } from 'react'
import { CalendarDays, Car, FileText, ReceiptText, ShieldCheck } from 'lucide-react'
import ChatBubble from './ChatBubble'
import ChatInput from './ChatInput'
import { useChat } from '@/hooks/useChat'
import type { ChatMessage } from '@/types'

interface ChatViewProps {
  hideInput?: boolean
  onSend?: (content: string) => Promise<void>
  messages?: ChatMessage[]
  customerMode?: boolean
  historyLoaded?: boolean
}

const QUICK_ACTIONS = [
  { icon: Car, title: '了解车型', desc: '查看热门车型与配置', query: '请介绍一下热门车型，图片也一起发给我', className: 'bg-sky-50 text-sky-900 border-sky-100' },
  { icon: ReceiptText, title: '获取报价', desc: '了解最新价格与优惠', query: '我想了解最新的车型报价', className: 'bg-amber-50 text-amber-900 border-amber-100' },
  { icon: CalendarDays, title: '预约试驾', desc: '安排门店试驾时间', query: '我想预约试驾', className: 'bg-emerald-50 text-emerald-900 border-emerald-100' },
  { icon: FileText, title: '购车方案', desc: '定制专属购车方案', query: '帮我制定一个购车方案', className: 'bg-rose-50 text-rose-900 border-rose-100' },
]

export function generateQuickReplies(aiMessage: string): string[] {
  if (aiMessage.includes('价格') || aiMessage.includes('报价')) return ['分期方案', '最新优惠', '对比其他车型']
  if (aiMessage.includes('试驾')) return ['查看门店', '预约时间', '试驾须知']
  if (aiMessage.includes('配置') || aiMessage.includes('参数')) return ['对比竞品', '查看实拍', '车主评价']
  return ['了解更多', '转人工服务', '查看其他车型']
}

export default function ChatView({ hideInput = false, onSend, messages: externalMessages, customerMode = false, historyLoaded = true }: ChatViewProps = {}) {
  const { messages: storeMessages, isLoading, attachedDocs, attachedImages, sendMessage } = useChat()
  const messages = externalMessages ?? storeMessages
  const bottomRef = useRef<HTMLDivElement>(null)
  const lastAssistant = useMemo(() => [...messages].reverse().find((message) => message.role === 'assistant'), [messages])
  const quickReplies = lastAssistant ? generateQuickReplies(lastAssistant.content) : []

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, isLoading])

  async function handleSend(content: string) {
    try { await (onSend ? onSend(content) : sendMessage(content)) } catch { /* hook owns error state */ }
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-white">
      <div className="flex-1 overflow-y-auto px-3 py-4 sm:px-5">
        {!historyLoaded ? <LoadingDots /> : messages.length === 0 ? (
          <div className="mx-auto flex min-h-full max-w-xl flex-col justify-center py-6">
            <div className="text-center">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-neutral-900 text-white"><Car size={26} /></div>
              <div className="mt-3 flex items-center justify-center gap-2"><h2 className="text-lg font-semibold">您好，我是您的智能购车顾问</h2><span className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" title="在线" /></div>
              <p className="mt-1 text-sm text-neutral-500">7x24小时智能服务</p>
              <div className="mt-2 flex items-center justify-center gap-1 text-xs text-neutral-400"><ShieldCheck size={13} />车型咨询、报价和试驾预约</div>
            </div>
            <div className="mt-6 grid grid-cols-2 gap-3">
              {QUICK_ACTIONS.map((action) => <button key={action.title} type="button" onClick={() => handleSend(action.query)} disabled={isLoading} className={`min-h-28 rounded-lg border p-3 text-left transition-transform duration-200 hover:scale-[1.02] disabled:opacity-40 ${action.className}`}><action.icon size={21} /><p className="mt-3 text-sm font-semibold">{action.title}</p><p className="mt-1 text-xs opacity-70">{action.desc}</p></button>)}
            </div>
          </div>
        ) : (
          messages.map((message) => (
            <ChatBubble
              key={message.id}
              reversed={customerMode}
              message={{ ...message, documents: message.documents || attachedDocs[message.id], images: message.images || attachedImages[message.id] }}
              images={message.images || attachedImages[message.id]}
            />
          ))
        )}

        {isLoading && <LoadingDots />}
        {!isLoading && customerMode && quickReplies.length > 0 && (
          <div className="ml-10 mt-1 flex gap-2 overflow-x-auto pb-2 animate-[fadeIn_250ms_ease-out] [scrollbar-width:none]">
            {quickReplies.map((reply) => <button key={reply} type="button" onClick={() => handleSend(reply)} className="shrink-0 rounded-full border border-neutral-200 bg-white px-3 py-1.5 text-xs text-neutral-700 hover:border-amber-300 hover:bg-amber-50">{reply}</button>)}
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      {!hideInput && <ChatInput onSend={handleSend} disabled={isLoading} />}
    </div>
  )
}

function LoadingDots() {
  return <div className="mb-4 flex justify-start"><div className="rounded-2xl rounded-bl-sm bg-neutral-100 px-4 py-3"><div className="flex gap-1.5">{[0, 150, 300].map((delay) => <span key={delay} className="h-2 w-2 animate-bounce rounded-full bg-neutral-400" style={{ animationDelay: `${delay}ms` }} />)}</div></div></div>
}
