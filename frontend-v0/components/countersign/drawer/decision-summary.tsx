import { Ban, Check, Clock, LoaderCircle, Pause, UserCheck, UserX } from 'lucide-react'
import type { Payment } from '@/lib/api'
import type { CheckState } from '@/hooks/use-payment-run'
import { formatUsd } from '@/lib/format'
import { cn } from '@/lib/utils'

function describeStatus(state: CheckState) {
  if (state.review?.decision === 'approved') {
    return { label: 'Approved', Icon: UserCheck, tone: 'text-verified', reason: `Released by a reviewer: ${state.review.reason}` }
  }
  if (state.review?.decision === 'rejected') {
    return { label: 'Rejected', Icon: UserX, tone: 'text-blocked', reason: `Rejected by a reviewer: ${state.review.reason}` }
  }
  switch (state.status) {
    case 'pending':
      return { label: 'Queued', Icon: Clock, tone: 'text-muted-foreground', reason: 'Waiting for Countersign to review this payment.' }
    case 'reviewing':
      return { label: 'Reviewing', Icon: LoaderCircle, tone: 'text-muted-foreground', reason: 'Countersign is checking this payment now.' }
    case 'paid':
      return { label: 'Released', Icon: Check, tone: 'text-verified', reason: 'Matched this vendor’s history, so it was paid.' }
    case 'held':
      return { label: 'Held', Icon: Pause, tone: 'text-held', reason: `${state.heldReasons?.join(', ') ?? 'Needs review'}. Waiting for a person to decide.` }
    case 'blocked':
      return { label: 'Blocked', Icon: Ban, tone: 'text-blocked', reason: `${state.blockedReason ?? 'Blocked'}. No money has moved.` }
  }
}

export function DecisionSummary({ payment, state }: { payment: Payment; state: CheckState }) {
  const { label, Icon, tone, reason } = describeStatus(state)
  const voided = state.status === 'blocked'

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <p className={cn('flex items-center gap-2.5 font-serif text-4xl font-semibold tracking-tight', tone)}>
          <Icon
            className={cn('size-7 shrink-0', state.status === 'reviewing' && 'animate-spin motion-reduce:animate-none')}
            strokeWidth={2.25}
            aria-hidden="true"
          />
          {label}
        </p>
        <p
          className={cn(
            'font-serif text-4xl font-semibold tabular-nums tracking-tight',
            voided && 'text-muted-foreground line-through decoration-blocked decoration-2',
          )}
        >
          {formatUsd(payment.amount_usd)}
        </p>
      </div>
      <p className="text-pretty leading-relaxed text-muted-foreground">{reason}</p>
    </div>
  )
}
