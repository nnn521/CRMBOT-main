import { useEffect, useRef, useState } from 'react'
import { CalendarDays, ChevronLeft, ChevronRight, ReceiptText } from 'lucide-react'
import type { CarCardData } from '@/types'

interface CarCardProps extends CarCardData {
  onQuote?: () => void
  onTestDrive?: () => void
}

export default function CarCard({ name, brand, price, images, highlights, specs, onQuote, onTestDrive }: CarCardProps) {
  const [index, setIndex] = useState(0)
  const touchStart = useRef<number | null>(null)

  useEffect(() => {
    if (images.length < 2) return
    const timer = window.setInterval(() => setIndex((current) => (current + 1) % images.length), 5000)
    return () => window.clearInterval(timer)
  }, [images.length])

  function move(direction: number) {
    setIndex((current) => (current + direction + images.length) % images.length)
  }

  return (
    <article className="overflow-hidden rounded-lg border border-neutral-200 bg-white shadow-sm">
      <div
        className="relative aspect-[16/10] bg-neutral-100"
        onTouchStart={(event) => { touchStart.current = event.touches[0].clientX }}
        onTouchEnd={(event) => {
          if (touchStart.current === null) return
          const distance = event.changedTouches[0].clientX - touchStart.current
          if (Math.abs(distance) > 45) move(distance > 0 ? -1 : 1)
          touchStart.current = null
        }}
      >
        {images[index] ? <img src={images[index]} alt={name} className="h-full w-full object-cover" /> : null}
        {images.length > 1 && (
          <>
            <button type="button" onClick={() => move(-1)} className="absolute left-2 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full bg-black/55 text-white" title="上一张"><ChevronLeft /></button>
            <button type="button" onClick={() => move(1)} className="absolute right-2 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full bg-black/55 text-white" title="下一张"><ChevronRight /></button>
          </>
        )}
      </div>
      <div className="p-4">
        <p className="text-xs text-neutral-500">{brand}</p>
        <h3 className="mt-0.5 text-base font-semibold text-neutral-900">{name}</h3>
        <p className="mt-2 text-xl font-bold text-red-600">{price}</p>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {highlights.map((item, itemIndex) => <span key={item} className={`rounded px-2 py-1 text-[11px] ${['bg-emerald-50 text-emerald-700', 'bg-sky-50 text-sky-700', 'bg-amber-50 text-amber-800'][itemIndex % 3]}`}>{item}</span>)}
        </div>
        <div className="mt-3 grid grid-cols-3 gap-2 border-y border-neutral-100 py-3 text-center text-xs text-neutral-600">
          <span>{specs.engine}</span><span>{specs.power}</span><span>{specs.fuel}</span>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2">
          <button type="button" onClick={onQuote} className="flex h-9 items-center justify-center gap-1.5 rounded-md bg-neutral-900 text-xs font-medium text-white"><ReceiptText size={14} />获取报价</button>
          <button type="button" onClick={onTestDrive} className="flex h-9 items-center justify-center gap-1.5 rounded-md border border-neutral-300 text-xs font-medium text-neutral-800"><CalendarDays size={14} />预约试驾</button>
        </div>
      </div>
    </article>
  )
}
