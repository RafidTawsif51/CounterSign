import { Check } from 'lucide-react'

export function Wordmark() {
  return (
    <span className="flex items-center gap-2">
      <span className="flex size-6 items-center justify-center rounded-md bg-primary text-primary-foreground">
        <Check className="size-3.5" strokeWidth={3} aria-hidden="true" />
      </span>
      <span className="text-[15px] font-semibold tracking-tight text-foreground">Countersign</span>
    </span>
  )
}
