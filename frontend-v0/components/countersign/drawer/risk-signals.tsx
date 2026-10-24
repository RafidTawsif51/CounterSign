import { Gavel } from 'lucide-react'
import type { RiskAssessment, RiskDecision } from '@/lib/api'
import { cn } from '@/lib/utils'
import { DrawerSection } from './drawer-section'

const MAX_WEIGHT = 30
const HOLD_AT = 40
const BLOCK_AT = 70

const DECISION: Record<RiskDecision, { heading: string; label: string; tone: string; fill: string }> = {
  pay: { heading: 'Why it was released', label: 'Pay', tone: 'text-verified', fill: 'bg-verified' },
  hold: { heading: 'Why it was held', label: 'Hold for review', tone: 'text-held', fill: 'bg-held' },
  block: { heading: 'Why it was blocked', label: 'Block', tone: 'text-blocked', fill: 'bg-blocked' },
}

function weightTone(weight: number) {
  if (weight >= 25) return 'bg-blocked'
  if (weight >= 15) return 'bg-held'
  return 'bg-muted-foreground/60'
}

export function RiskSignals({
  assessment,
  highlighted,
}: {
  assessment: RiskAssessment
  highlighted: string | null
}) {
  const decision = DECISION[assessment.decision]
  const signals = [...assessment.signals].sort((a, b) => b.weight - a.weight)

  return (
    <DrawerSection title={decision.heading} id="why">
      {assessment.hard_rules_fired.length > 0 && (
        <ul className="flex flex-col gap-2">
          {assessment.hard_rules_fired.map((rule) => (
            <li
              key={rule}
              className="flex items-start gap-2.5 rounded-md border border-blocked/25 bg-blocked/5 px-3 py-2.5 leading-relaxed"
            >
              <Gavel className="mt-0.5 size-4 shrink-0 text-blocked" aria-hidden="true" />
              <span>
                <span className="font-medium text-blocked">Hard rule: </span>
                {rule}
              </span>
            </li>
          ))}
        </ul>
      )}

      <ul className="flex flex-col divide-y divide-border rounded-lg border border-border">
        {signals.map((signal) => {
          const isHighlighted = highlighted === signal.evidence_id
          return (
            <li
              key={signal.name}
              id={`signal-${signal.evidence_id}`}
              className={cn(
                'flex scroll-mt-24 flex-col gap-2.5 px-4 py-3.5 transition-colors duration-200',
                isHighlighted && 'bg-primary/[0.06] shadow-[inset_3px_0_0_var(--primary)]',
              )}
            >
              <p className="text-pretty leading-relaxed">{signal.detail}</p>
              <div className="flex items-center gap-3">
                <div
                  className="h-1.5 w-24 overflow-hidden rounded-full bg-muted"
                  role="meter"
                  aria-label="Signal weight"
                  aria-valuemin={0}
                  aria-valuemax={MAX_WEIGHT}
                  aria-valuenow={signal.weight}
                >
                  <div
                    className={cn('h-full rounded-full', weightTone(signal.weight))}
                    style={{ width: `${(signal.weight / MAX_WEIGHT) * 100}%` }}
                  />
                </div>
                <span className="w-12 text-xs tabular-nums text-muted-foreground">
                  <span className="font-semibold text-foreground">{signal.weight}</span> / {MAX_WEIGHT}
                </span>
                <span
                  className={cn(
                    'ml-auto rounded border border-border bg-surface px-1.5 py-0.5 font-mono text-xs text-muted-foreground transition-colors',
                    isHighlighted && 'border-primary/40 text-primary',
                  )}
                >
                  {signal.evidence_id}
                </span>
              </div>
            </li>
          )
        })}
      </ul>

      <ScoreMeter score={assessment.score} decision={assessment.decision} />
    </DrawerSection>
  )
}

function ScoreMeter({ score, decision }: { score: number; decision: RiskDecision }) {
  const config = DECISION[decision]
  return (
    <div className="flex flex-col gap-3 rounded-lg bg-surface p-4">
      <div className="flex items-end justify-between gap-4">
        <div className="flex flex-col gap-0.5">
          <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Risk score</span>
          <p className="font-serif text-3xl font-semibold tabular-nums">
            {score}
            <span className="text-lg text-muted-foreground"> / 100</span>
          </p>
        </div>
        <div className="flex flex-col items-end gap-0.5">
          <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Decision</span>
          <p className={cn('text-lg font-semibold', config.tone)}>{config.label}</p>
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <div
          className="relative h-2 rounded-full bg-gradient-to-r from-verified/20 via-held/25 to-blocked/30"
          role="meter"
          aria-label="Risk score"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={score}
        >
          {[HOLD_AT, BLOCK_AT].map((at) => (
            <span key={at} aria-hidden="true" className="absolute inset-y-0 w-px bg-card" style={{ left: `${at}%` }} />
          ))}
          <span
            aria-hidden="true"
            className={cn('absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-card', config.fill)}
            style={{ left: `${score}%` }}
          />
        </div>
        <div className="relative h-4 text-xs tabular-nums text-muted-foreground" aria-hidden="true">
          <span className="absolute left-0">Pay</span>
          <span className="absolute -translate-x-1/2" style={{ left: `${HOLD_AT}%` }}>
            Hold {HOLD_AT}
          </span>
          <span className="absolute -translate-x-1/2" style={{ left: `${BLOCK_AT}%` }}>
            Block {BLOCK_AT}
          </span>
          <span className="absolute right-0">100</span>
        </div>
      </div>
    </div>
  )
}
