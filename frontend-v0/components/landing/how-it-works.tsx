'use client'

import { useEffect, useId, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { Check, FileText, Mail, PhoneCall } from 'lucide-react'
import { StatusBadge } from '@/components/site/status-badge'
import { cn } from '@/lib/utils'
import { Reveal } from './reveal'
import { SectionHeading } from './section-heading'
import { Waveform } from './waveform'

const STEP_MS = 7000

const STEPS = [
  {
    title: 'Ingest invoices and emails',
    body: 'Countersign reads every invoice, remittance email and vendor update in your AP inbox and matches each one to an approved vendor.',
  },
  {
    title: 'Score every payment against 12 months of history',
    body: 'Payee, amount, timing, sender domain and bank details are compared with a year of your own payments. Anything unusual is held.',
  },
  {
    title: 'Verify new bank details by phone',
    body: 'When bank details change, Countersign calls the vendor on the number already on file, never one from the email, and asks them to confirm.',
  },
  {
    title: 'Pay and explain every decision',
    body: 'Clean payments go out on schedule. Every paid, held or blocked payment carries a plain-English reason your controller can audit.',
  },
]

const INBOX = [
  { Icon: FileText, from: 'Granite Peak Lumber', subject: 'Invoice INV-20931', match: true },
  { Icon: Mail, from: 'accounts@summit-concrete.co', subject: 'Updated remittance details', match: false },
  { Icon: FileText, from: 'Keystone HVAC', subject: 'Invoice KH-0458', match: true },
  { Icon: FileText, from: 'Apex Crane Services', subject: 'Invoice AC-1180', match: true },
]

function IngestPanel() {
  return (
    <ul className="flex flex-col divide-y divide-border rounded-xl border border-border bg-background shadow-xs">
      {INBOX.map(({ Icon, from, subject, match }) => (
        <li key={subject} className="flex items-center gap-3 px-4 py-3">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-surface">
            <Icon className="size-4 text-muted-foreground" aria-hidden="true" />
          </span>
          <div className="flex min-w-0 flex-1 flex-col">
            <span className="truncate text-sm font-medium">{from}</span>
            <span className="truncate text-sm text-muted-foreground">{subject}</span>
          </div>
          <span
            className={cn(
              'shrink-0 rounded-full px-2 py-0.5 text-xs font-medium',
              match ? 'bg-verified/10 text-verified' : 'bg-held/10 text-held',
            )}
          >
            {match ? 'Matched to vendor' : 'Unknown domain'}
          </span>
        </li>
      ))}
    </ul>
  )
}

const BASELINE = [
  { signal: 'Average invoice', history: '$41,260', current: '$48,720', flag: false },
  { signal: 'Usual payment day', history: 'Thursday', current: 'Thursday', flag: false },
  { signal: 'Sender domain', history: 'summitconcrete.com', current: 'summit-concrete.co', flag: true },
  { signal: 'Bank account', history: '••4410', current: '••7781', flag: true },
]

function ScorePanel() {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-background shadow-xs">
      <div className="grid grid-cols-[1fr_1fr_1fr] gap-3 border-b border-border bg-surface px-4 py-2 text-xs text-muted-foreground">
        <span>Signal</span>
        <span>12-month history</span>
        <span>This payment</span>
      </div>
      <ul className="divide-y divide-border">
        {BASELINE.map((row) => (
          <li key={row.signal} className="grid grid-cols-[1fr_1fr_1fr] items-center gap-3 px-4 py-3 text-sm">
            <span className="text-muted-foreground">{row.signal}</span>
            <span className="truncate tabular-nums">{row.history}</span>
            <span className={cn('truncate tabular-nums', row.flag && 'font-medium text-blocked')}>{row.current}</span>
          </li>
        ))}
      </ul>
      <div className="flex items-center justify-between border-t border-border px-4 py-3">
        <span className="text-sm font-medium">Risk score</span>
        <span className="text-sm tabular-nums">
          <span className="font-semibold text-blocked">94</span>
          <span className="text-muted-foreground"> / 100 · verification required</span>
        </span>
      </div>
    </div>
  )
}

function VerifyPanel() {
  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-background p-5 shadow-xs">
      <div className="flex items-center gap-3">
        <span className="flex size-10 items-center justify-center rounded-full bg-primary text-primary-foreground">
          <PhoneCall className="size-4" aria-hidden="true" />
        </span>
        <div className="flex flex-col">
          <span className="text-sm font-medium">Calling Summit Concrete</span>
          <span className="text-sm tabular-nums text-muted-foreground">+1 (512) 555-0148 · from vendor master</span>
        </div>
      </div>
      <Waveform className="h-9 text-primary" />
      <dl className="flex flex-col gap-3 border-t border-border pt-4 text-sm leading-relaxed">
        <div className="flex flex-col gap-0.5">
          <dt className="font-medium">Countersign</dt>
          <dd className="text-pretty text-muted-foreground">
            We received a request to move your payments to an account ending 7781. Can you confirm that change?
          </dd>
        </div>
        <div className="flex flex-col gap-0.5">
          <dt className="font-medium">Summit Concrete</dt>
          <dd className="text-pretty text-muted-foreground">
            {"No. We haven't changed our bank details. Please don't send anything there."}
          </dd>
        </div>
      </dl>
    </div>
  )
}

function PayPanel() {
  const rows = [
    { name: 'Granite Peak Lumber', status: 'paid' as const, why: 'Matches 12 months of history' },
    { name: 'Apex Crane Services', status: 'held' as const, why: 'Amount 3x usual, sent to approver' },
    { name: 'Summit Concrete', status: 'blocked' as const, why: 'Vendor denied bank change on call' },
  ]
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'Released', value: '37', tone: 'text-verified' },
          { label: 'Held', value: '2', tone: 'text-held' },
          { label: 'Blocked', value: '1', tone: 'text-blocked' },
        ].map((s) => (
          <div key={s.label} className="flex flex-col gap-0.5 rounded-xl border border-border bg-background p-4 shadow-xs">
            <span className="text-xs text-muted-foreground">{s.label}</span>
            <span className={cn('text-2xl font-semibold tabular-nums', s.tone)}>{s.value}</span>
          </div>
        ))}
      </div>
      <ul className="flex flex-col divide-y divide-border rounded-xl border border-border bg-background shadow-xs">
        {rows.map((r) => (
          <li key={r.name} className="flex items-center justify-between gap-3 px-4 py-3">
            <div className="flex min-w-0 flex-col">
              <span className="truncate text-sm font-medium">{r.name}</span>
              <span className="truncate text-sm text-muted-foreground">{r.why}</span>
            </div>
            <StatusBadge status={r.status} />
          </li>
        ))}
      </ul>
    </div>
  )
}

const PANELS = [IngestPanel, ScorePanel, VerifyPanel, PayPanel]

export function HowItWorks() {
  const [active, setActive] = useState(0)
  const [paused, setPaused] = useState(false)
  const reduceMotion = useReducedMotion() ?? false
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([])
  const baseId = useId()
  const autoplay = !paused && !reduceMotion

  useEffect(() => {
    if (!autoplay) return
    const id = window.setTimeout(() => setActive((a) => (a + 1) % STEPS.length), STEP_MS)
    return () => window.clearTimeout(id)
  }, [active, autoplay])

  function select(index: number) {
    setPaused(true)
    setActive(index)
  }

  function onKeyDown(event: React.KeyboardEvent, index: number) {
    const delta = event.key === 'ArrowDown' || event.key === 'ArrowRight' ? 1 : event.key === 'ArrowUp' || event.key === 'ArrowLeft' ? -1 : 0
    if (!delta) return
    event.preventDefault()
    const next = (index + delta + STEPS.length) % STEPS.length
    select(next)
    tabRefs.current[next]?.focus()
  }

  const Panel = PANELS[active]

  return (
    <section id="how-it-works" className="scroll-mt-16 border-t border-border">
      <div className="mx-auto flex max-w-6xl flex-col gap-14 px-6 py-24 md:py-32">
        <Reveal>
          <SectionHeading
            eyebrow="How it works"
            title="Four steps, on every run."
            description="The same process whether the run holds 4 payments or 400."
          />
        </Reveal>

        <div className="grid gap-8 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:gap-14">
          <div role="tablist" aria-orientation="vertical" aria-label="How it works" className="flex flex-col">
            {STEPS.map((step, index) => {
              const selected = index === active
              return (
                <button
                  key={step.title}
                  ref={(el) => {
                    tabRefs.current[index] = el
                  }}
                  role="tab"
                  id={`${baseId}-tab-${index}`}
                  aria-selected={selected}
                  aria-controls={`${baseId}-panel`}
                  tabIndex={selected ? 0 : -1}
                  onClick={() => select(index)}
                  onKeyDown={(e) => onKeyDown(e, index)}
                  className={cn(
                    'relative flex gap-5 border-l-2 py-5 pl-6 pr-2 text-left transition-colors focus-visible:outline-2 focus-visible:outline-offset-2',
                    selected ? 'border-transparent' : 'border-border hover:border-input',
                  )}
                >
                  {selected && (
                    <span className="absolute -left-0.5 top-0 h-full w-0.5 overflow-hidden bg-border" aria-hidden="true">
                      <motion.span
                        key={`${active}-${autoplay}`}
                        className="block w-full bg-primary"
                        initial={{ height: autoplay ? '0%' : '100%' }}
                        animate={{ height: '100%' }}
                        transition={{ duration: autoplay ? STEP_MS / 1000 : 0, ease: 'linear' }}
                      />
                    </span>
                  )}
                  <span
                    className={cn(
                      'flex size-7 shrink-0 items-center justify-center rounded-full border text-sm font-medium tabular-nums transition-colors',
                      selected ? 'border-primary bg-primary text-primary-foreground' : 'border-border text-muted-foreground',
                    )}
                  >
                    {index + 1}
                  </span>
                  <span className="flex flex-col gap-2">
                    <span
                      className={cn(
                        'text-balance text-lg font-semibold leading-snug tracking-tight transition-colors',
                        !selected && 'text-muted-foreground',
                      )}
                    >
                      {step.title}
                    </span>
                    <span
                      className={cn(
                        'grid text-pretty text-[15px] leading-relaxed text-muted-foreground transition-all duration-300',
                        selected ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0',
                      )}
                    >
                      <span className="overflow-hidden">{step.body}</span>
                    </span>
                  </span>
                </button>
              )
            })}
          </div>

          <div
            role="tabpanel"
            id={`${baseId}-panel`}
            aria-labelledby={`${baseId}-tab-${active}`}
            className="relative flex min-h-[26rem] flex-col justify-center overflow-hidden rounded-2xl border border-border bg-surface p-5 md:p-8"
          >
            <div className="bg-dot-grid pointer-events-none absolute inset-0 opacity-60" aria-hidden="true" />
            <div className="relative mb-5 flex items-center gap-2 text-sm text-muted-foreground">
              <Check className="size-4 text-primary" aria-hidden="true" />
              Step {active + 1} of {STEPS.length}
            </div>
            <AnimatePresence mode="wait">
              <motion.div
                key={active}
                className="relative"
                initial={reduceMotion ? false : { opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={reduceMotion ? undefined : { opacity: 0, y: -10 }}
                transition={{ duration: 0.3, ease: 'easeOut' }}
              >
                <Panel />
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </div>
    </section>
  )
}
