import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { AlertCircle, Bot, Check, Download, ImageOff, Loader2, User, X } from 'lucide-react'
import type { ChatMessage } from '@/types'

interface Props {
  message: ChatMessage
  reversed?: boolean
  images?: string[]
}

export default function ChatBubble({ message, reversed, images }: Props) {
  const isUser = message.role === 'user'
  const alignLeft = reversed ? !isUser : isUser
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null)
  const [failedImages, setFailedImages] = useState<Set<string>>(new Set())
  const allImages = images?.length ? images : message.images || []

  return (
    <div className={`mb-4 flex gap-2 ${alignLeft ? 'justify-start' : 'justify-end'}`}>
      {alignLeft && (
        <div className={`mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${isUser ? 'bg-neutral-200' : 'bg-amber-100'}`}>
          {isUser ? <User size={16} /> : <Bot size={17} className="text-amber-800" />}
        </div>
      )}
      <div className={`flex max-w-[84%] flex-col ${alignLeft ? 'items-start' : 'items-end'}`}>
        <div className={`rounded-2xl px-4 py-3 text-sm leading-6 ${
          isUser && reversed
            ? 'rounded-br-sm bg-amber-500/15 text-neutral-900'
            : alignLeft
              ? 'rounded-bl-sm border border-neutral-200 bg-neutral-50 text-neutral-800'
              : 'rounded-br-sm bg-neutral-900 text-white'
        }`}>
          <ReactMarkdown
            components={{
              p: ({ children }) => <p className="whitespace-pre-wrap">{children}</p>,
              strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
              ul: ({ children }) => <ul className="my-1 list-disc space-y-1 pl-5">{children}</ul>,
              ol: ({ children }) => <ol className="my-1 list-decimal space-y-1 pl-5">{children}</ol>,
              a: ({ href, children }) => (
                <a href={href} target="_blank" rel="noreferrer" className="underline underline-offset-2">
                  {children}
                </a>
              ),
            }}
          >
            {message.content}
          </ReactMarkdown>
          <div className={`mt-1 flex items-center gap-1 text-[10px] ${isUser && !reversed ? 'text-white/60' : 'text-neutral-400'}`}>
            <span>{formatTime(message.timestamp)}</span>
            {isUser && <MessageStatus status={message.status} />}
          </div>
        </div>

        {allImages.length > 0 && (
          <div className={`mt-2 grid w-full gap-2 ${allImages.length === 1 ? 'grid-cols-1' : 'grid-cols-2'}`}>
            {allImages.map((src) => failedImages.has(src) ? (
              <div key={src} className="flex aspect-[4/3] items-center justify-center rounded-lg border border-neutral-200 bg-neutral-100 text-neutral-400">
                <ImageOff size={22} />
              </div>
            ) : (
              <button key={src} type="button" onClick={() => setLightboxSrc(src)} className="overflow-hidden rounded-lg bg-neutral-100">
                <img
                  src={src}
                  alt="车型实拍"
                  className="aspect-[4/3] h-full w-full object-cover transition-transform duration-200 hover:scale-[1.02]"
                  loading="lazy"
                  onError={() => setFailedImages((current) => new Set(current).add(src))}
                />
              </button>
            ))}
          </div>
        )}

        {!isUser && message.documents?.map((doc) => (
          <a
            key={doc.file_name}
            href={doc.file_path || `/api/v1/documents/${encodeURIComponent(doc.file_name)}`}
            download={doc.file_name}
            className="mt-2 flex items-center gap-2 rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-xs font-medium text-sky-800 hover:bg-sky-100"
          >
            <Download size={14} />
            {doc.file_name}
          </a>
        ))}
      </div>

      {lightboxSrc && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4" onClick={() => setLightboxSrc(null)}>
          <button type="button" className="absolute right-4 top-4 text-white" onClick={() => setLightboxSrc(null)} title="关闭">
            <X size={28} />
          </button>
          <img src={lightboxSrc} alt="车型大图" className="max-h-[88vh] max-w-full rounded-lg object-contain" onClick={(event) => event.stopPropagation()} />
        </div>
      )}
    </div>
  )
}

function MessageStatus({ status }: { status?: ChatMessage['status'] }) {
  if (status === 'sending') return <Loader2 size={11} className="animate-spin" />
  if (status === 'failed') return <AlertCircle size={11} className="text-red-500" />
  return <Check size={11} />
}

function formatTime(timestamp: number): string {
  const date = new Date(timestamp)
  const now = new Date()
  const time = date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const day = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
  if (day === today) return time
  if (day === today - 86400000) return `昨天 ${time}`
  return `${date.toLocaleDateString('zh-CN')} ${time}`
}
