import { BriefcaseBusiness, Check, FileWarning, Landmark, PenLine, type LucideIcon } from 'lucide-react'
import type { AttackCardId } from '@/lib/api'
import type { AttackCard } from '@/lib/attack-cards'
import { cn } from '@/lib/utils'

const ICONS: Record<AttackCardId, LucideIcon> = {
  bank_change: Landmark,
  poisoned_invoice: FileWarning,
  ceo_pressure: BriefcaseBusiness,
  freestyle: PenLine,
}

interface AttackCardButtonProps {
  card: AttackCard
  selected: boolean
  dimmed: boolean
  onSelect: () => void
}

export function AttackCardButton({ card, selected, dimmed, onSelect }: AttackCardButtonProps) {
  const Icon = ICONS[card.id]
  const isHijack = card.id === 'poisoned_invoice'

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        'group relative flex rounded-2xl border border-border bg-card p-1.5 text-left shadow-card-physical',
        'transition-[transform,opacity,box-shadow] duration-300 ease-out motion-reduce:transition-none',
        'hover:-translate-y-1.5 hover:-rotate-1 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring',
        selected && '-translate-y-2 ring-2 ring-primary ring-offset-4 ring-offset-background hover:-translate-y-2 hover:rotate-0',
        dimmed && 'opacity-60 hover:opacity-100',
      )}
    >
      <span
        className={cn(
          'flex min-h-80 flex-1 flex-col gap-4 rounded-xl border p-4 lg:aspect-[5/7] lg:min-h-0',
          selected ? 'border-primary/30' : 'border-border',
        )}
      >
        <span className="flex items-start justify-between">
          <span className={cn('flex flex-col items-start gap-1', isHijack ? 'text-void' : 'text-foreground')}>
            <Icon className="size-4" aria-hidden="true" />
            <span className="text-[11px] font-semibold uppercase tracking-wider">{card.tag}</span>
          </span>
          <span
            className={cn(
              'flex size-6 items-center justify-center rounded-full border transition-colors',
              selected ? 'border-primary bg-primary text-primary-foreground' : 'border-border text-transparent',
            )}
            aria-hidden="true"
          >
            <Check className="size-3.5" strokeWidth={3} />
          </span>
        </span>

        <span className="relative flex flex-1 items-center justify-center overflow-hidden rounded-lg bg-surface">
          <span className="absolute inset-0 bg-dot-grid" aria-hidden="true" />
          <span
            className={cn(
              'relative flex size-14 items-center justify-center rounded-full border bg-card shadow-card-physical transition-transform duration-300 group-hover:scale-105 motion-reduce:transition-none',
              isHijack ? 'border-void/30 text-void' : 'border-border text-primary',
            )}
          >
            <Icon className="size-6" aria-hidden="true" />
          </span>
        </span>

        <span className="flex flex-col gap-1.5">
          <span className="text-lg font-semibold tracking-tight text-foreground">{card.title}</span>
          <span className="text-pretty text-sm leading-relaxed text-muted-foreground">{card.description}</span>
        </span>

        <span
          className={cn(
            'flex rotate-180 items-start gap-1 self-end',
            isHijack ? 'text-void' : 'text-muted-foreground',
          )}
          aria-hidden="true"
        >
          <Icon className="size-3.5" />
          <span className="text-[10px] font-semibold uppercase tracking-wider">{card.tag}</span>
        </span>
      </span>
    </button>
  )
}
