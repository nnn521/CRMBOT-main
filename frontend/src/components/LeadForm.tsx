import { useEffect, useMemo, useRef, useState } from 'react'
import { CheckCircle2, ChevronLeft, ChevronRight, X } from 'lucide-react'
import { submitLead } from '@/api/engagement'

interface Props {
  open: boolean
  sessionId: string
  initialModel?: string
  onClose: () => void
}

export default function LeadForm({ open, sessionId, initialModel = '', onClose }: Props) {
  const [step, setStep] = useState(1)
  const [form, setForm] = useState({ name: '', phone: '', car_model: initialModel, budget_range: '', purchase_time: '', notes: '' })
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [coupon, setCoupon] = useState('')
  const phoneValid = useMemo(() => /^1[3-9]\d{9}$/.test(form.phone), [form.phone])
  const firstFieldRef = useRef<HTMLInputElement>(null)

  // Escape 关闭 + 初始焦点
  useEffect(() => {
    if (!open) return
    firstFieldRef.current?.focus()
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  if (!open) return null

  function next() {
    if (step === 1 && (!form.name.trim() || !phoneValid)) {
      setError('请填写姓名和有效的手机号')
      return
    }
    setError('')
    setStep((current) => Math.min(current + 1, 3))
  }

  async function submit() {
    setSubmitting(true)
    setError('')
    try {
      const result = await submitLead({ session_id: sessionId, ...form })
      setCoupon(result.coupon_code)
    } catch {
      setError('提交失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/45 p-0 sm:items-center sm:p-4" role="dialog" aria-modal="true">
      <div className="w-full max-w-md rounded-t-lg bg-white p-5 shadow-xl sm:rounded-lg">
        <div className="flex items-start justify-between">
          <div><h2 className="text-base font-semibold">获取专属购车服务</h2><p className="mt-1 text-xs text-neutral-500">留下需求，销售顾问将尽快联系您</p></div>
          <button type="button" onClick={onClose} aria-label="关闭" className="text-neutral-400 hover:text-neutral-700" title="关闭"><X size={20} /></button>
        </div>

        {coupon ? (
          <div className="py-8 text-center">
            <CheckCircle2 size={44} className="mx-auto text-emerald-500 animate-[pulse_800ms_ease-out_1]" />
            <h3 className="mt-3 font-semibold">需求已提交</h3>
            <p className="mt-1 text-sm text-neutral-500">您的专属优惠券码</p>
            <p className="mt-3 rounded-md bg-amber-50 py-3 font-mono text-xl font-bold text-amber-900">{coupon}</p>
          </div>
        ) : (
          <>
            <div className="my-5 flex gap-2">
              {[1, 2, 3].map((item) => <span key={item} className={`h-1.5 flex-1 rounded-full ${item <= step ? 'bg-amber-500' : 'bg-neutral-200'}`} />)}
            </div>
            <div className="min-h-48 space-y-3">
              {step === 1 && <><Field label="姓名" value={form.name} onChange={(name) => setForm({ ...form, name })} required fieldRef={firstFieldRef} /><Field label="手机号" value={form.phone} onChange={(phone) => setForm({ ...form, phone })} inputMode="tel" required /></>}
              {step === 2 && <><Field label="意向车型" value={form.car_model} onChange={(car_model) => setForm({ ...form, car_model })} /><label className="block text-sm">预算范围<select value={form.budget_range} onChange={(event) => setForm({ ...form, budget_range: event.target.value })} className="mt-1 h-10 w-full rounded-md border border-neutral-300 px-3"><option value="">请选择</option><option>15万以内</option><option>15-25万</option><option>25-40万</option><option>40万以上</option></select></label></>}
              {step === 3 && <><label className="block text-sm">预计购买时间<select value={form.purchase_time} onChange={(event) => setForm({ ...form, purchase_time: event.target.value })} className="mt-1 h-10 w-full rounded-md border border-neutral-300 px-3"><option value="">请选择</option><option>1个月内</option><option>1-3个月</option><option>3-6个月</option><option>暂未确定</option></select></label><label className="block text-sm">备注<textarea value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} className="mt-1 min-h-20 w-full rounded-md border border-neutral-300 p-3" /></label></>}
            </div>
            {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
            <div className="mt-5 flex justify-between">
              <button type="button" onClick={() => setStep((current) => Math.max(current - 1, 1))} disabled={step === 1} className="flex h-9 items-center gap-1 rounded-md px-3 text-sm text-neutral-600 disabled:invisible"><ChevronLeft size={16} />上一步</button>
              {step < 3 ? <button type="button" onClick={next} className="flex h-9 items-center gap-1 rounded-md bg-neutral-900 px-4 text-sm text-white">下一步<ChevronRight size={16} /></button> : <button type="button" onClick={submit} disabled={submitting} className="h-9 rounded-md bg-neutral-900 px-4 text-sm text-white disabled:opacity-50">{submitting ? '提交中' : '提交需求'}</button>}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function Field({ label, value, onChange, required, inputMode, fieldRef }: { label: string; value: string; onChange: (value: string) => void; required?: boolean; inputMode?: 'tel'; fieldRef?: React.Ref<HTMLInputElement> }) {
  return <label className="block text-sm">{label}{required && <span className="text-red-500"> *</span>}<input ref={fieldRef} value={value} onChange={(event) => onChange(event.target.value)} inputMode={inputMode} className="mt-1 h-10 w-full rounded-md border border-neutral-300 px-3 outline-none focus:border-amber-500" /></label>
}
