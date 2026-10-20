import { useEffect, useState } from 'react'
import { Frown, Heart, Meh, Smile, Sparkles, Star, X } from 'lucide-react'
import { submitFeedback } from '@/api/engagement'

interface Props { open: boolean; sessionId: string; onClose: () => void }
const MOODS = [Frown, Meh, Smile, Heart]

export default function RatingModal({ open, sessionId, onClose }: Props) {
  const [rating, setRating] = useState(5)
  const [speed, setSpeed] = useState(3)
  const [professionalism, setProfessionalism] = useState(3)
  const [comment, setComment] = useState('')
  const [recommend, setRecommend] = useState(true)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  if (!open) return null

  async function submit() {
    try {
      await submitFeedback({ session_id: sessionId, rating, speed, professionalism, comment, would_recommend: recommend })
      setSubmitted(true)
    } catch {
      setError('提交失败，请稍后重试')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4" role="dialog" aria-modal="true">
      <div className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl">
        <div className="flex justify-between"><h2 className="font-semibold">服务评价</h2><button type="button" onClick={onClose} aria-label="关闭" title="关闭"><X size={20} /></button></div>
        {submitted ? <div className="py-10 text-center"><Sparkles size={42} className="mx-auto text-amber-500" /><h3 className="mt-3 font-semibold">感谢您的反馈</h3><p className="mt-1 text-sm text-neutral-500">我们会继续改进购车服务体验</p></div> : <div className="mt-5 space-y-5">
          <div><p className="text-sm">整体满意度</p><div className="mt-2 flex gap-2">{[1,2,3,4,5].map((value) => <button type="button" key={value} onClick={() => setRating(value)} title={`${value}星`}><Star size={28} className={value <= rating ? 'fill-amber-400 text-amber-400' : 'text-neutral-300'} /></button>)}</div></div>
          <MoodRow label="响应速度" value={speed} onChange={setSpeed} />
          <MoodRow label="专业程度" value={professionalism} onChange={setProfessionalism} />
          <label className="block text-sm">文字评价<textarea value={comment} onChange={(event) => setComment(event.target.value)} className="mt-1 min-h-20 w-full rounded-md border border-neutral-300 p-3" placeholder="选填" /></label>
          <div className="flex items-center justify-between text-sm"><span>愿意推荐给朋友吗？</span><div className="flex gap-2"><button type="button" onClick={() => setRecommend(true)} className={`rounded-md px-3 py-1.5 ${recommend ? 'bg-neutral-900 text-white' : 'bg-neutral-100'}`}>是</button><button type="button" onClick={() => setRecommend(false)} className={`rounded-md px-3 py-1.5 ${!recommend ? 'bg-neutral-900 text-white' : 'bg-neutral-100'}`}>否</button></div></div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button type="button" onClick={submit} className="h-10 w-full rounded-md bg-neutral-900 text-sm font-medium text-white">提交评价</button>
        </div>}
      </div>
    </div>
  )
}

function MoodRow({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return <div><p className="text-sm">{label}</p><div className="mt-2 flex gap-3">{MOODS.map((Icon, index) => <button type="button" key={index} onClick={() => onChange(index + 1)} className={`flex h-10 w-10 items-center justify-center rounded-full ${value === index + 1 ? 'bg-amber-100 text-amber-800 ring-2 ring-amber-400' : 'bg-neutral-100 text-neutral-500'}`} title={`${index + 1}级`}><Icon size={21} /></button>)}</div></div>
}
