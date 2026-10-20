interface Props {
  title: string
  description: string
}

export default function ComingSoon({ title, description }: Props) {
  return (
    <div className="flex h-full items-center justify-center bg-neutral-50 p-6">
      <div className="w-full max-w-sm rounded-2xl border border-neutral-200 bg-white p-8 text-center shadow-sm">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-neutral-900 text-lg text-white">
          ⏳
        </div>
        <h2 className="mt-4 text-base font-semibold text-neutral-800">{title}</h2>
        <p className="mt-2 text-sm leading-relaxed text-neutral-500">{description}</p>
      </div>
    </div>
  )
}
