import { ArrowDown, Check, Lock, PhoneCall, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Reveal } from './reveal'
import { SectionHeading } from './section-heading'
import { Waveform } from './waveform'

function Card({
  className,
  visual,
  title,
  body,
  delay = 0,
}: {
  className?: string
  visual: React.ReactNode
  title: string
  body: string
  delay?: number
}) {
  return (
    <Reveal delay={delay} className={cn('flex', className)}>
      <article className="flex w-full flex-col overflow-hidden rounded-2xl border border-border bg-card transition-shadow hover:shadow-[0_16px_48px_-24px_rgba(13,21,36,0.25)]">
        <div className="flex min-h-56 flex-1 flex-col justify-center border-b border-border bg-surface p-6">{visual}</div>
        <div className="flex flex-col gap-2 p-6">
          <h3 className="text-lg font-semibold tracking-tight">{title}</h3>
          <p className="text-pretty text-[15px] leading-relaxed text-muted-foreground">{body}</p>
        </div>
      </article>
    </Reveal>
  )
}

const SCORE_SIGNALS = [
  { label: 'Payee and vendor match', value: 6, tone: 'bg-verified' },
  { label: 'Amount vs 12-month average', value: 18, tone: 'bg-verified' },
  { label: 'Sender domain age', value: 72, tone: 'bg-held' },
  { label: 'Bank detail change', value: 96, tone: 'bg-blocked' },
]

function ScoreVisual() {
  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-background p-5 shadow-xs">
      <div className="flex items-baseline justify-between">
        <p className="text-sm font-medium">Risk breakdown · SC-30217</p>
        <p className="text-sm text-muted-foreground">
          <span className="text-xl font-semibold tabular-nums text-blocked">94</span> / 100
        </p>
      </div>
      <ul className="flex flex-col gap-3">
        {SCORE_SIGNALS.map((signal) => (
          <li key={signal.label} className="grid grid-cols-[minmax(0,1fr)_7rem_2rem] items-center gap-3 text-sm">
            <span className="truncate text-muted-foreground">{signal.label}</span>
            <span className="h-1.5 overflow-hidden rounded-full bg-muted">
              <span className={cn('block h-full rounded-full', signal.tone)} style={{ width: `${signal.value}%` }} />
            </span>
            <span className="text-right tabular-nums">{signal.value}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function DiffVisual() {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-col gap-1 rounded-xl border border-border bg-background p-4 shadow-xs">
        <p className="text-xs text-muted-foreground">On file since Aug 2024</p>
        <p className="flex items-center justify-between text-sm">
          <span className="font-medium">First Texas Bank</span>
          <span className="tabular-nums text-muted-foreground">Acct ••4410 · Rtg ••0193</span>
        </p>
      </div>
      <ArrowDown className="mx-auto size-4 text-muted-foreground" aria-hidden="true" />
      <div className="flex flex-col gap-1 rounded-xl border border-blocked/30 bg-background p-4 shadow-xs">
        <p className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">Requested by email · 2 days before due</span>
          <span className="font-medium text-blocked">Changed</span>
        </p>
        <p className="flex items-center justify-between text-sm">
          <span className="font-medium">Harbor Digital Bank</span>
          <span className="tabular-nums text-blocked">Acct ••7781 · Rtg ••2266</span>
        </p>
      </div>
    </div>
  )
}

function CallVisual() {
  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-background p-4 shadow-xs">
      <div className="flex items-center gap-3">
        <span className="flex size-9 items-center justify-center rounded-full bg-primary text-primary-foreground">
          <PhoneCall className="size-4" aria-hidden="true" />
        </span>
        <div className="flex flex-col">
          <p className="text-sm font-medium">Summit Concrete</p>
          <p className="text-xs tabular-nums text-muted-foreground">+1 (512) 555-0148 · on file</p>
        </div>
        <span className="ml-auto text-xs tabular-nums text-muted-foreground">0:42</span>
      </div>
      <Waveform className="text-primary" />
      <p className="rounded-md bg-blocked/10 px-2.5 py-1.5 text-xs font-medium text-blocked">
        Vendor denied the change
      </p>
    </div>
  )
}

const LOG = [
  { time: '14:01:58', text: 'Bank change detected on SC-30217' },
  { time: '14:02:03', text: 'Call placed to number on file' },
  { time: '14:02:11', text: 'Vendor denied change. Payment blocked' },
  { time: '14:02:12', text: 'Controller notified' },
]

function LogVisual() {
  return (
    <ol className="flex flex-col rounded-xl border border-border bg-background p-4 shadow-xs">
      {LOG.map((entry, i) => (
        <li key={entry.time} className="relative flex gap-3 pb-3 last:pb-0">
          {i < LOG.length - 1 && (
            <span className="absolute left-[3px] top-3 h-full w-px bg-border" aria-hidden="true" />
          )}
          <span
            className={cn('relative mt-1.5 size-[7px] shrink-0 rounded-full', i === 2 ? 'bg-blocked' : 'bg-input')}
            aria-hidden="true"
          />
          <div className="flex min-w-0 flex-col">
            <span className="text-xs tabular-nums text-muted-foreground">{entry.time}</span>
            <span className="text-pretty text-sm">{entry.text}</span>
          </div>
        </li>
      ))}
    </ol>
  )
}

const PERMISSIONS = [
  { label: 'Read invoices and emails', allowed: true },
  { label: 'Place verification calls', allowed: true },
  { label: 'Edit vendor bank details', allowed: false },
  { label: 'Pay an unverified account', allowed: false },
]

function PermissionsVisual() {
  return (
    <ul className="flex flex-col divide-y divide-border rounded-xl border border-border bg-background shadow-xs">
      {PERMISSIONS.map((p) => (
        <li key={p.label} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
          <span>{p.label}</span>
          {p.allowed ? (
            <Check className="size-4 text-verified" aria-label="Allowed" />
          ) : (
            <span className="flex items-center gap-1 text-muted-foreground">
              <Lock className="size-3.5" aria-hidden="true" />
              <X className="size-4" aria-label="Not allowed" />
            </span>
          )}
        </li>
      ))}
    </ul>
  )
}

export function Capabilities() {
  return (
    <section id="capabilities" className="scroll-mt-16">
      <div className="mx-auto flex max-w-6xl flex-col gap-14 px-6 py-24 md:py-32">
        <Reveal>
          <SectionHeading
            eyebrow="Capabilities"
            title="A controller's judgment, on every payment."
            description="Countersign checks each payment the way your most careful AP lead would, then writes down exactly what it saw."
          />
        </Reveal>

        <div className="grid gap-5 md:grid-cols-6">
          <Card
            className="md:col-span-3"
            visual={<ScoreVisual />}
            title="Risk scored against your own history"
            body="Every payment is compared with 12 months of your payments to that vendor. Scores come with the signals behind them."
          />
          <Card
            className="md:col-span-3"
            delay={0.05}
            visual={<DiffVisual />}
            title="Bank changes caught before release"
            body="Any difference from the account on file stops the payment, however routine the email requesting it looks."
          />
          <Card
            className="md:col-span-2"
            visual={<CallVisual />}
            title="Real verification calls"
            body="The agent calls the vendor on the number you already had, records the call and acts on the answer."
          />
          <Card
            className="md:col-span-2"
            delay={0.05}
            visual={<LogVisual />}
            title="An audit trail by default"
            body="Each step is time-stamped and written in plain English for your controller and auditors."
          />
          <Card
            className="md:col-span-2"
            delay={0.1}
            visual={<PermissionsVisual />}
            title="Permissions it can't exceed"
            body="Bank details are read-only to the agent. No prompt, email or invoice can change that."
          />
        </div>
      </div>
    </section>
  )
}
