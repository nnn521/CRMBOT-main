import { useEffect, useRef, useState } from 'react'
import { Loader2, Send } from 'lucide-react'

interface Props {
  onSend: (message: string) => void
  disabled?: boolean
}

const QUICK_PHRASES = ['这款车多少钱？', '有哪些优惠？', '分期方案有哪些？']

export default function ChatInput({ onSend, disabled }: Props) {
  const [input, setInput] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (!disabled) textareaRef.current?.focus()
  }, [disabled])

  useEffect(() => {
    function handleFillInput(event: Event) {
      const text = (event as CustomEvent<string>).detail
      if (text) setInput(text)
    }
    window.addEventListener('fill-chat-input', handleFillInput)
    return () => window.removeEventListener('fill-chat-input', handleFillInput)
  }, [])

  useEffect(() => {
    const element = textareaRef.current
    if (!element) return
    element.style.height = 'auto'
    element.style.height = `${Math.min(element.scrollHeight, 120)}px`
  }, [input])

  function send(value = input) {
    const message = value.trim()
    if (!message || disabled) return
    onSend(message)
    setInput('')
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Escape') {
      setInput('')
      return
    }
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      send()
    }
  }

  return (
    <div className="shrink-0 border-t border-neutral-200 bg-white px-3 pb-3 pt-2 sm:px-4">
      <div className="mb-2 flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none]">
        {QUICK_PHRASES.map((phrase) => (
          <button
            key={phrase}
            type="button"
            onClick={() => send(phrase)}
            disabled={disabled}
            className="shrink-0 rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs text-amber-900 transition-colors hover:bg-amber-100 disabled:opacity-40"
          >
            {phrase}
          </button>
        ))}
      </div>
      <div className="flex items-end gap-2 rounded-2xl border border-neutral-200 bg-white p-2 shadow-inner transition-colors focus-within:border-amber-500 focus-within:ring-2 focus-within:ring-amber-500/15">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入消息"
          rows={1}
          disabled={disabled}
          className="min-h-10 max-h-[120px] flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-6 outline-none disabled:opacity-50"
        />
        <button
          type="button"
          onClick={() => send()}
          disabled={disabled || !input.trim()}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-neutral-900 text-white transition-colors hover:bg-neutral-700 disabled:opacity-35"
          title="发送"
        >
          {disabled ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
        </button>
      </div>
    </div>
  )
}
