import { formatUsdWhole } from '@/lib/format'
import { cn } from '@/lib/utils'

type Decision = 'Verified' | 'Held' | 'Blocked'

const TAPE: { rail: string; vendor: string; amount: number; decision: Decision }[] = [
  { rail: 'ACH', vendor: 'Granite Supply Co.', amount: 48210, decision: 'Verified' },
  { rail: 'WIRE', vendor: 'Summit Concrete', amount: 186400, decision: 'Blocked' },
  { rail: 'RTP', vendor: 'Northline Electric', amount: 12875, decision: 'Verified' },
  { rail: 'ACH', vendor: 'Keystone Lumber', amount: 73940, decision: 'Held' },
  { rail: 'CHECK', vendor: 'Atlas Rentals', amount: 9620, decision: 'Verified' },
  { rail: 'WIRE', vendor: 'Harbor Steel', amount: 241000, decision: 'Verified' },
  { rail: 'ACH', vendor: 'Pioneer HVAC', amount: 31450, decision: 'Verified' },
  { rail: 'WIRE', vendor: 'Bluewater Logistics', amount: 98300, decision: 'Held' },
  { rail: 'ACH', vendor: 'Cedar Glass', amount: 18760, decision: 'Verified' },
  { rail: 'RTP', vendor: 'Meridian Fuel', amount: 6240, decision: 'Blocked' },
]

const DOT: Record<Decision, string> = {
  Verified: 'bg-verified',
  Held: 'bg-held',
  Blocked: 'bg-blocked',
}

function TapeRow({ hidden = false }: { hidden?: boolean }) {
  return (
    <ul className="flex shrink-0 items-center" aria-hidden={hidden || undefined}>
      {TAPE.map((item) => (
        <li
          key={`${item.vendor}-${item.amount}`}
          className="flex items-center gap-3 border-r border-primary-foreground/10 px-6 py-3 text-sm"
        >
          <span className="rounded-sm bg-primary-foreground/10 px-1.5 py-0.5 text-[11px] font-semibold tracking-wider text-primary-foreground/80">
            {item.rail}
          </span>
          <span className="whitespace-nowrap text-primary-foreground/80">{item.vendor}</span>
          <span className="font-semibold tabular-nums text-primary-foreground">{formatUsdWhole(item.amount)}</span>
          <span className="flex items-center gap-1.5 whitespace-nowrap text-xs text-primary-foreground/70">
            <span className={cn('size-1.5 rounded-full', DOT[item.decision])} aria-hidden="true" />
            {item.decision}
          </span>
        </li>
      ))}
    </ul>
  )
}

export function PaymentsTicker() {
  return (
    <section aria-label="Recent payment decisions" className="bg-primary text-primary-foreground">
      <div className="mx-auto flex max-w-[100rem] items-stretch">
        <p className="z-10 flex shrink-0 items-center gap-2 border-r border-primary-foreground/15 bg-primary px-5 text-xs font-semibold tracking-widest text-primary-foreground/90">
          <span className="relative flex size-2" aria-hidden="true">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-verified opacity-60 motion-reduce:hidden" />
            <span className="relative inline-flex size-2 rounded-full bg-verified" />
          </span>
          LIVE TAPE
        </p>
        <div className="flex min-w-0 flex-1 overflow-hidden mask-fade-x">
          <div className="flex animate-marquee motion-reduce:animate-none">
            <TapeRow />
            <TapeRow hidden />
          </div>
        </div>
      </div>
    </section>
  )
}
