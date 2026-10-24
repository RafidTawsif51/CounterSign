'use client'

import { useEffect, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import {
  ChevronsUpDown,
  FileText,
  LayoutList,
  PhoneCall,
  ScrollText,
  Search,
  SlidersHorizontal,
  Users,
} from 'lucide-react'
import { StatusBadge } from '@/components/site/status-badge'
import type { CheckStatus } from '@/hooks/use-payment-run'
import { cn } from '@/lib/utils'
import { Waveform } from './waveform'

type Row = {
  payee: string
  invoice: string
  due: string
  amount: number
  risk: number
  final: Exclude<CheckStatus, 'pending' | 'reviewing'>
  reason?: string
}

const ROWS: Row[] = [
  { payee: 'Granite Peak Lumber', invoice: 'INV-20931', due: 'Oct 24', amount: 18432.6, risk: 8, final: 'paid' },
  { payee: 'Ironclad Steel Fabricators', invoice: 'IS-7713', due: 'Oct 24', amount: 42915, risk: 12, final: 'paid' },
  {
    payee: 'Apex Crane Services',
    invoice: 'AC-1180',
    due: 'Oct 25',
    amount: 38600,
    risk: 61,
    final: 'held',
    reason: 'Amount 3x the 12-month average',
  },
  { payee: 'Keystone HVAC', invoice: 'KH-0458', due: 'Oct 25', amount: 31200, risk: 9, final: 'paid' },
  {
    payee: 'Summit Concrete',
    invoice: 'SC-30217',
    due: 'Oct 24',
    amount: 48720,
    risk: 94,
    final: 'blocked',
    reason: 'New bank details, vendor denied the change on a verification call',
  },
  { payee: 'Bluewater Plumbing', invoice: 'BW-2290', due: 'Oct 26', amount: 12880.4, risk: 6, final: 'paid' },
]

const SUMMIT_INDEX = ROWS.findIndex((row) => row.payee === 'Summit Concrete')
const TOTAL = ROWS.reduce((sum, row) => sum + row.amount, 0)
const TICK_MS = 950
const HOLD_TICKS = 8

const money = (value: number) =>
  value.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 })

const NAV = [
  { Icon: LayoutList, label: 'Payment runs', active: true },
  { Icon: Users, label: 'Vendors' },
  { Icon: PhoneCall, label: 'Verification calls' },
  { Icon: ScrollText, label: 'Audit log' },
  { Icon: SlidersHorizontal, label: 'Policies' },
]

const SIGNALS = [
  { tone: 'blocked', text: 'Bank account changed 2 days before due date' },
  { tone: 'blocked', text: 'Request sent from summit-concrete.co, a lookalike domain' },
  { tone: 'held', text: 'First change in 14 months with this vendor' },
  { tone: 'verified', text: 'Amount within normal range' },
] as const

const TRANSCRIPT = [
  { speaker: 'Countersign', line: 'We received a request to move payments to an account ending 7781. Can you confirm?' },
  { speaker: 'Summit Concrete', line: "No. We haven't changed our bank details." },
]

function useRunTicker() {
  const reduceMotion = useReducedMotion() ?? false
  const [step, setStep] = useState(0)

  useEffect(() => {
    if (reduceMotion) return
    const id = window.setInterval(() => {
      setStep((current) => (current >= ROWS.length + HOLD_TICKS ? 0 : current + 1))
    }, TICK_MS)
    return () => window.clearInterval(id)
  }, [reduceMotion])

  return reduceMotion ? ROWS.length : step
}

function statusAt(index: number, step: number): CheckStatus {
  if (index < step) return ROWS[index].final
  if (index === step) return 'reviewing'
  return 'pending'
}

function RiskMeter({ value, status }: { value: number; status: CheckStatus }) {
  const resolved = status === 'paid' || status === 'held' || status === 'blocked'
  const tone = value >= 80 ? 'bg-blocked' : value >= 40 ? 'bg-held' : 'bg-verified'
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-14 overflow-hidden rounded-full bg-muted">
        <motion.div
          className={cn('h-full rounded-full', resolved ? tone : 'bg-input')}
          initial={false}
          animate={{ width: resolved ? `${Math.max(value, 6)}%` : '0%' }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
        />
      </div>
      <span className="w-6 text-xs tabular-nums text-muted-foreground">{resolved ? value : '–'}</span>
    </div>
  )
}

export function HeroProduct() {
  const step = useRunTicker()
  const statuses = ROWS.map((_, index) => statusAt(index, step))
  const count = (status: CheckStatus) => statuses.filter((s) => s === status).length
  const verifiedTotal = ROWS.reduce((sum, row, i) => (statuses[i] === 'paid' ? sum + row.amount : sum), 0)
  const summitResolved = statuses[SUMMIT_INDEX] === 'blocked'
  const summitCalling = statuses[SUMMIT_INDEX] === 'reviewing'

  const kpis = [
    { label: 'Scheduled', value: money(TOTAL), sub: `${ROWS.length} payments` },
    { label: 'Verified', value: money(verifiedTotal), sub: `${count('paid')} released`, tone: 'text-verified' },
    { label: 'Held for review', value: String(count('held')), sub: 'Awaiting approver', tone: 'text-held' },
    { label: 'Blocked', value: String(count('blocked')), sub: 'Fraud prevented', tone: 'text-blocked' },
  ]

  return (
    <div className="relative">
      <figure
        aria-label="Product preview: a live payment run in Countersign"
        className="overflow-hidden rounded-2xl border border-border bg-card shadow-[0_1px_2px_rgba(13,21,36,0.05),0_24px_80px_-24px_rgba(13,21,36,0.25)] ring-8 ring-surface"
      >
        <div className="flex items-center gap-4 border-b border-border bg-surface px-4 py-2.5">
          <div className="flex gap-1.5" aria-hidden="true">
            <span className="size-2.5 rounded-full bg-input" />
            <span className="size-2.5 rounded-full bg-input" />
            <span className="size-2.5 rounded-full bg-input" />
          </div>
          <div className="mx-auto flex w-full max-w-sm items-center justify-center gap-2 rounded-md border border-border bg-background px-3 py-1 text-xs text-muted-foreground">
            <Search className="size-3" aria-hidden="true" />
            app.countersign.ai/runs/thursday
          </div>
          <div className="w-10" aria-hidden="true" />
        </div>

        <div className="flex text-left">
          <aside className="hidden w-52 shrink-0 flex-col gap-6 border-r border-border bg-surface/60 p-3 md:flex">
            <div className="flex items-center gap-2.5 rounded-lg border border-border bg-background p-2">
              <span className="flex size-7 items-center justify-center rounded-md bg-primary text-xs font-semibold text-primary-foreground">
                RB
              </span>
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-xs font-medium">Ridgeline Builders</span>
                <span className="text-xs text-muted-foreground">Accounts payable</span>
              </span>
              <ChevronsUpDown className="size-3.5 text-muted-foreground" aria-hidden="true" />
            </div>
            <ul className="flex flex-col gap-0.5">
              {NAV.map(({ Icon, label, active }) => (
                <li
                  key={label}
                  className={cn(
                    'flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm',
                    active ? 'bg-background font-medium text-foreground shadow-xs' : 'text-muted-foreground',
                  )}
                >
                  <Icon className="size-4" aria-hidden="true" />
                  {label}
                </li>
              ))}
            </ul>
            <div className="mt-auto flex flex-col gap-2 rounded-lg border border-border bg-background p-3">
              <p className="text-xs font-medium">Policy</p>
              <p className="text-pretty text-xs leading-relaxed text-muted-foreground">
                New bank details require a verified call before release.
              </p>
            </div>
          </aside>

          <div className="flex min-w-0 flex-1 flex-col">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
              <div className="flex flex-col gap-0.5">
                <div className="flex items-center gap-2.5">
                  <p className="font-semibold tracking-tight">Thursday payment run</p>
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground">
                    <span className="relative flex size-1.5">
                      <span className="absolute inline-flex size-full animate-ping rounded-full bg-verified opacity-60 motion-reduce:animate-none" />
                      <span className="relative inline-flex size-1.5 rounded-full bg-verified" />
                    </span>
                    Live
                  </span>
                </div>
                <p className="text-sm text-muted-foreground">Oct 23 · Operating account ••2201</p>
              </div>
              <span className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground">
                Release {count('paid')} verified
              </span>
            </div>

            <dl className="grid grid-cols-2 border-b border-border lg:grid-cols-4">
              {kpis.map((kpi, i) => (
                <div
                  key={kpi.label}
                  className={cn(
                    'flex flex-col gap-1 px-5 py-3.5',
                    i % 2 === 1 && 'border-l border-border',
                    i >= 2 && 'border-t border-border lg:border-t-0',
                    i === 2 && 'lg:border-l',
                  )}
                >
                  <dt className="text-xs text-muted-foreground">{kpi.label}</dt>
                  <dd className={cn('text-lg font-semibold tracking-tight tabular-nums', kpi.tone)}>{kpi.value}</dd>
                  <dd className="text-xs text-muted-foreground">{kpi.sub}</dd>
                </div>
              ))}
            </dl>

            <div className="grid lg:grid-cols-[minmax(0,1fr)_300px]">
              <div className="min-w-0">
                <div className="hidden grid-cols-[minmax(0,1.6fr)_0.8fr_0.6fr_1fr_0.9fr_6.5rem] gap-3 border-b border-border px-5 py-2 text-xs text-muted-foreground sm:grid">
                  <span>Vendor</span>
                  <span>Invoice</span>
                  <span>Due</span>
                  <span className="text-right">Amount</span>
                  <span>Risk</span>
                  <span className="text-right">Status</span>
                </div>
                <ul className="divide-y divide-border">
                  {ROWS.map((row, i) => {
                    const status = statuses[i]
                    return (
                      <li
                        key={row.payee}
                        className={cn(
                          'flex flex-col gap-1 px-5 py-3 transition-colors duration-500',
                          status === 'reviewing' && 'bg-surface',
                          status === 'blocked' && 'bg-blocked/[0.045]',
                        )}
                      >
                        <div className="flex items-center justify-between gap-3 sm:grid sm:grid-cols-[minmax(0,1.6fr)_0.8fr_0.6fr_1fr_0.9fr_6.5rem]">
                          <span className="truncate text-sm font-medium">{row.payee}</span>
                          <span className="hidden text-sm tabular-nums text-muted-foreground sm:block">
                            {row.invoice}
                          </span>
                          <span className="hidden text-sm text-muted-foreground sm:block">{row.due}</span>
                          <span className="hidden text-right text-sm tabular-nums sm:block">{money(row.amount)}</span>
                          <span className="hidden sm:block">
                            <RiskMeter value={row.risk} status={status} />
                          </span>
                          <span className="flex justify-end">
                            <StatusBadge status={status} />
                          </span>
                        </div>
                        {row.reason && (status === 'held' || status === 'blocked') && (
                          <motion.p
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            className="text-pretty text-xs leading-relaxed text-muted-foreground"
                          >
                            {row.reason}
                          </motion.p>
                        )}
                      </li>
                    )
                  })}
                </ul>
              </div>

              <aside
                aria-label="Summit Concrete payment detail"
                className="flex flex-col gap-5 border-t border-border bg-surface/60 p-5 lg:border-l lg:border-t-0"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex flex-col gap-0.5">
                    <p className="text-sm font-semibold">Summit Concrete</p>
                    <p className="text-xs text-muted-foreground">SC-30217 · {money(48720)}</p>
                  </div>
                  <div className="flex flex-col items-end">
                    <p
                      className={cn(
                        'text-2xl font-semibold leading-none tracking-tight tabular-nums transition-colors',
                        summitResolved ? 'text-blocked' : 'text-muted-foreground',
                      )}
                    >
                      {summitResolved || summitCalling ? 94 : '–'}
                    </p>
                    <p className="text-xs text-muted-foreground">Risk score</p>
                  </div>
                </div>

                <ul className="flex flex-col gap-2">
                  {SIGNALS.map((signal) => (
                    <li key={signal.text} className="flex items-start gap-2 text-xs leading-relaxed">
                      <span
                        aria-hidden="true"
                        className={cn(
                          'mt-1.5 size-1.5 shrink-0 rounded-full',
                          signal.tone === 'blocked' && 'bg-blocked',
                          signal.tone === 'held' && 'bg-held',
                          signal.tone === 'verified' && 'bg-verified',
                        )}
                      />
                      <span className="text-pretty">{signal.text}</span>
                    </li>
                  ))}
                </ul>

                <div className="flex flex-col gap-3 rounded-lg border border-border bg-background p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="flex items-center gap-1.5 text-xs font-medium">
                      <PhoneCall className="size-3.5 text-muted-foreground" aria-hidden="true" />
                      Verification call
                    </p>
                    <span className="text-xs tabular-nums text-muted-foreground">
                      {summitCalling ? 'In progress' : summitResolved ? '0:42 · Ended' : 'Queued'}
                    </span>
                  </div>
                  <Waveform
                    active={summitCalling}
                    className={cn('text-primary transition-opacity', !summitCalling && 'opacity-40')}
                  />
                  <p className="text-xs text-muted-foreground">Dialed +1 (512) 555-0148 · number on file</p>
                  <dl className="flex flex-col gap-2 border-t border-border pt-3">
                    {TRANSCRIPT.map((entry) => (
                      <div key={entry.speaker} className="flex flex-col gap-0.5 text-xs leading-relaxed">
                        <dt className="font-medium">{entry.speaker}</dt>
                        <dd className="text-pretty text-muted-foreground">{entry.line}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              </aside>
            </div>
          </div>
        </div>
      </figure>

      <div
        aria-hidden="true"
        className="absolute -left-14 bottom-16 hidden w-64 flex-col gap-2 rounded-xl border border-border bg-card p-4 text-left shadow-[0_16px_48px_-16px_rgba(13,21,36,0.3)] xl:flex"
      >
        <div className="flex items-center gap-2">
          <span className="flex size-7 items-center justify-center rounded-md bg-surface">
            <FileText className="size-3.5 text-primary" />
          </span>
          <p className="text-sm font-medium">Audit entry</p>
          <span className="ml-auto text-xs tabular-nums text-muted-foreground">14:02:11</span>
        </div>
        <p className="text-pretty text-xs leading-relaxed text-muted-foreground">
          Payment SC-30217 blocked. Vendor denied the bank change on a call to the number on file. No funds moved.
        </p>
      </div>
    </div>
  )
}
