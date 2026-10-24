import { PhoneCall, PhoneOff, Phone } from 'lucide-react'
import type { CallOutcome, CallSpeaker, ContactSource } from '@/lib/api'
import { cn } from '@/lib/utils'
import { ContactSourceBadge } from '../contact-source-badge'
import { DrawerSection } from './drawer-section'

export interface CallRecordViewModel {
  contactSource: ContactSource
  outcome?: CallOutcome
  transcript: Array<{ speaker: CallSpeaker; text: string }>
}

function OutcomeBadge({ outcome }: { outcome?: CallOutcome }) {
  if (!outcome) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-muted px-2.5 py-0.5 text-sm font-medium text-muted-foreground">
        <PhoneCall className="size-3.5" aria-hidden="true" />
        In progress
      </span>
    )
  }
  const denied = outcome === 'denied'
  const Icon = denied ? PhoneOff : Phone
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-sm font-medium',
        denied ? 'bg-blocked/10 text-blocked' : 'bg-verified/10 text-verified',
      )}
    >
      <Icon className="size-3.5" aria-hidden="true" />
      {denied ? 'Vendor denied' : 'Vendor confirmed'}
    </span>
  )
}

export function CallRecord({ call }: { call: CallRecordViewModel }) {
  return (
    <DrawerSection title="Verification call" id="call" aside={<OutcomeBadge outcome={call.outcome} />}>
      <div className="flex flex-wrap items-center gap-2.5">
        <span className="font-medium tabular-nums">{call.contactSource.phone}</span>
        <ContactSourceBadge kind={call.contactSource.kind} />
      </div>
      {call.transcript.length > 0 && (
        <ol className="flex flex-col gap-3.5 rounded-lg border border-border bg-surface p-4">
          {call.transcript.map((line, index) => (
            <li key={index} className="grid grid-cols-[6.5rem_1fr] gap-3">
              <span
                className={cn(
                  'pt-0.5 text-xs font-semibold uppercase tracking-wider',
                  line.speaker === 'countersign' ? 'text-primary' : 'text-muted-foreground',
                )}
              >
                {line.speaker === 'countersign' ? 'Countersign' : 'Vendor'}
              </span>
              <p className="text-pretty leading-relaxed">{line.text}</p>
            </li>
          ))}
        </ol>
      )}
    </DrawerSection>
  )
}
