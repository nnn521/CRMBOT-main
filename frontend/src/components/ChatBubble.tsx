import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { AlertCircle, Bot, Check, Download, ImageOff, Loader2, User, X } from 'lucide-react'
import type { ChatMessage, CitationInfo } from '@/types'

interface Props {
  message: ChatMessage
  reversed?: boolean
  images?: string[]
}

export function ChatBubble({ message, reversed, images }: Props) {
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

        {!isUser && <AnswerDetails message={message} />}

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

export default ChatBubble

const answerStatusLabels = {
  answered: '已回答',
  partial: '部分回答',
  clarification: '需要补充信息',
  unavailable: '暂无法确认',
}

/** Defense in depth for legacy history: only link to authenticated citation JSON. */
function citationHref(citation: CitationInfo): string | undefined {
  try {
    let decoded = citation.url
    for (let index = 0; index < 8; index += 1) {
      const next = decodeURIComponent(decoded)
      if (next === decoded) break
      decoded = next
    }
    if (!/^\/api\/v1\/knowledge\/releases\/[^/\\?#\s%]+\/citations\/[^/\\?#\s%]+$/.test(decoded)) return undefined
    if (decoded.split('/').some((part) => part === '.' || part === '..')) return undefined
    return citation.url
  } catch {
    return undefined
  }
}

function AnswerDetails({ message }: { message: ChatMessage }) {
  const hasDetails = message.citations?.length || message.answer_status || message.knowledge_release_id || message.data_as_of || message.assumptions?.length || message.limitations?.length
  if (!hasDetails) return null
  return (
    <section aria-label="回答依据与条件" className="mt-2 w-full space-y-2 rounded-lg border border-neutral-200 bg-white p-3 text-xs text-neutral-700">
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-neutral-500">
        {message.answer_status && <span>{answerStatusLabels[message.answer_status]}</span>}
        {message.data_as_of && <span>数据截至：{message.data_as_of}</span>}
        {message.knowledge_release_id && <span className="break-all">知识版本：{message.knowledge_release_id}</span>}
      </div>
      {message.citations?.map((citation) => {
        const href = citationHref(citation)
        return (
          <details key={citation.citation_id} className="rounded border border-neutral-100 px-2 py-1.5">
            <summary className="cursor-pointer break-words font-medium">{citation.title || citation.source_id}</summary>
            <blockquote className="mt-2 whitespace-pre-wrap break-words border-l-2 border-amber-300 pl-2">{citation.quote}</blockquote>
            <dl className="mt-2 space-y-1 text-neutral-500">
              <div><dt className="inline">文档版本：</dt><dd className="inline break-all">{citation.document_version}</dd></div>
              {Object.entries(citation.locator).map(([key, value]) => (
                <div key={key}><dt className="inline">{key}：</dt><dd className="inline whitespace-pre-wrap break-all">{typeof value === 'string' ? value : JSON.stringify(value)}</dd></div>
              ))}
            </dl>
            {href && <a href={href} target="_blank" rel="noreferrer" className="mt-2 inline-block underline underline-offset-2">查看来源详情</a>}
          </details>
        )
      })}
      {!!message.assumptions?.length && (
        <div><p className="font-medium">适用条件</p><ul className="mt-1 list-disc space-y-1 pl-4">{message.assumptions.map((item, index) => <li key={index} className="whitespace-pre-wrap break-words">{item}</li>)}</ul></div>
      )}
      {!!message.limitations?.length && (
        <div><p className="font-medium">限制说明</p><ul className="mt-1 list-disc space-y-1 pl-4">{message.limitations.map((item, index) => <li key={index} className="whitespace-pre-wrap break-words">{item}</li>)}</ul></div>
      )}
    </section>
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
