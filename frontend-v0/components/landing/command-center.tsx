'use client'

import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import { useState } from 'react'
import { formatUsdWhole } from '@/lib/format'
import { cn } from '@/lib/utils'
import { Reveal } from './reveal'
import { SectionHeading } from './section-heading'

const KPIS = [
  {
    label: 'Disbursed this quarter',
    value: '$48.6M',
    delta: '+6.2%',
    up: true,
    good: true,
    series: [22, 25, 24, 28, 27, 31, 30, 34, 33, 37, 36, 40],
  },
  {
    label: 'Fraud blocked',
    value: '$1.42M',
    delta: '+3 attempts',
    up: true,
    good: true,
    series: [2, 1, 3, 2, 4, 2, 5, 3, 4, 6, 5, 7],
  },
  {
    label: 'Median time to verify',
    value: '4m 12s',
    delta: '-81%',
    up: false,
    good: true,
    series: [40, 36, 31, 27, 22, 18, 15, 12, 10, 9, 8, 7],
  },
  {
    label: 'Straight-through rate',
    value: '96.4%',
    delta: '+1.8 pts',
    up: true,
    good: true,
    series: [88, 89, 90, 90, 91, 92, 93, 93, 94, 95, 95, 96],
  },
]

const WEEKS = [
  { week: 'W1', released: 3.1, held: 0.22, blocked: 0.04 },
  { week: 'W2', released: 3.6, held: 0.18, blocked: 0 },
  { week: 'W3', released: 3.3, held: 0.31, blocked: 0.19 },
  { week: 'W4', released: 4.2, held: 0.14, blocked: 0 },
  { week: 'W5', released: 3.8, held: 0.26, blocked: 0.08 },
  { week: 'W6', released: 4.5, held: 0.12, blocked: 0 },
  { week: 'W7', released: 4.1, held: 0.35, blocked: 0.41 },
  { week: 'W8', released: 4.8, held: 0.2, blocked: 0 },
  { week: 'W9', released: 4.4, held: 0.17, blocked: 0.06 },
  { week: 'W10', released: 5.1, held: 0.24, blocked: 0 },
  { week: 'W11', released: 4.7, held: 0.29, blocked: 0.52 },
  { week: 'W12', released: 5.4, held: 0.16, blocked: 0.12 },
]

const RAILS = [
  { rail: 'ACH', share: 58, tone: 'bg-primary' },
  { rail: 'Wire', share: 24, tone: 'bg-primary/70' },
  { rail: 'Check', share: 11, tone: 'bg-primary/45' },
  { rail: 'RTP', share: 7, tone: 'bg-primary/25' },
]

const TIERS = [
  { tier: 'Low risk', vendors: 412, exposure: 31.8, tone: 'bg-verified' },
  { tier: 'Elevated', vendors: 37, exposure: 4.6, tone: 'bg-held' },
  { tier: 'High risk', vendors: 6, exposure: 0.9, tone: 'bg-blocked' },
]

type Decision = 'Released' | 'Held' | 'Blocked'

const LEDGER: { ref: string; vendor: string; rail: string; amount: number; decision: Decision; reason: string }[] = [
  { ref: 'PR-20481', vendor: 'Harbor Steel', rail: 'Wire', amount: 241000, decision: 'Released', reason: 'Callback confirmed' },
  { ref: 'PR-20480', vendor: 'Summit Concrete', rail: 'Wire', amount: 186400, decision: 'Blocked', reason: 'Lookalike domain' },
  { ref: 'PR-20479', vendor: 'Keystone Lumber', rail: 'ACH', amount: 73940, decision: 'Held', reason: 'New bank account' },
  { ref: 'PR-20478', vendor: 'Granite Supply Co.', rail: 'ACH', amount: 48210, decision: 'Released', reason: 'Matches history' },
  { ref: 'PR-20477', vendor: 'Northline Electric', rail: 'RTP', amount: 12875, decision: 'Released', reason: 'Matches history' },
]

const DECISION_STYLE: Record<Decision, string> = {
  Released: 'bg-verified/10 text-verified',
  Held: 'bg-held/10 text-held',
  Blocked: 'bg-blocked/10 text-blocked',
}

function Sparkline({ series }: { series: number[] }) {
  const max = Math.max(...series)
  const min = Math.min(...series)
  const range = max - min || 1
  const points = series
    .map((v, i) => `${(i / (series.length - 1)) * 100},${28 - ((v - min) / range) * 24}`)
    .join(' ')
  return (
    <svg viewBox="0 0 100 30" preserveAspectRatio="none" className="h-8 w-full" aria-hidden="true">
      <polyline points={`0,30 ${points} 100,30`} className="fill-primary/8 stroke-none" />
      <polyline
        points={points}
        fill="none"
        className="stroke-primary"
        strokeWidth="1.5"
        vectorEffect="non-scaling-stroke"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function VolumeChart() {
  const [active, setActive] = useState(WEEKS.length - 1)
  const max = Math.max(...WEEKS.map((w) => w.released + w.held + w.blocked))
  const current = WEEKS[active]

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-1">
          <p className="text-sm text-muted-foreground">Volume screened, last 12 weeks</p>
          <p className="text-2xl font-semibold tabular-nums tracking-tight">
            ${(current.released + current.held + current.blocked).toFixed(2)}M
            <span className="ml-2 text-sm font-normal text-muted-foreground">in {current.week}</span>
          </p>
        </div>
        <dl className="flex gap-5 text-xs">
          {[
            { label: 'Released', value: current.released, tone: 'bg-primary' },
            { label: 'Held', value: current.held, tone: 'bg-held' },
            { label: 'Blocked', value: current.blocked, tone: 'bg-blocked' },
          ].map((item) => (
            <div key={item.label} className="flex flex-col gap-1">
              <dt className="flex items-center gap-1.5 text-muted-foreground">
                <span className={cn('size-2 rounded-sm', item.tone)} aria-hidden="true" />
                {item.label}
              </dt>
              <dd className="font-semibold tabular-nums">${item.value.toFixed(2)}M</dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="relative">
        <div className="pointer-events-none absolute inset-0 flex flex-col justify-between" aria-hidden="true">
          {[0, 1, 2, 3].map((line) => (
            <span key={line} className="border-t border-dashed border-border" />
          ))}
        </div>
        <div
          role="group"
          aria-label="Weekly volume. Use the buttons to inspect a week."
          className="relative flex h-44 items-end gap-1.5 sm:gap-2.5"
        >
          {WEEKS.map((w, i) => {
            const total = w.released + w.held + w.blocked
            return (
              <button
                key={w.week}
                type="button"
                onMouseEnter={() => setActive(i)}
                onFocus={() => setActive(i)}
                onClick={() => setActive(i)}
                aria-pressed={active === i}
                aria-label={`${w.week}: $${total.toFixed(2)} million screened`}
                className="group flex h-full flex-1 flex-col justify-end rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2"
              >
                <span
                  className={cn(
                    'flex w-full flex-col-reverse overflow-hidden rounded-t-sm transition-opacity',
                    active === i ? 'opacity-100' : 'opacity-55 group-hover:opacity-80',
                  )}
                  style={{ height: `${(total / max) * 100}%` }}
                >
                  <span className="block bg-primary" style={{ flexGrow: w.released }} />
                  <span className="block bg-held" style={{ flexGrow: w.held, minHeight: w.held ? 2 : 0 }} />
                  <span className="block bg-blocked" style={{ flexGrow: w.blocked, minHeight: w.blocked ? 2 : 0 }} />
                </span>
              </button>
            )
          })}
        </div>
      </div>
      <div className="flex gap-1.5 text-[11px] text-muted-foreground sm:gap-2.5" aria-hidden="true">
        {WEEKS.map((w, i) => (
          <span key={w.week} className={cn('flex-1 text-center tabular-nums', active === i && 'font-semibold text-foreground')}>
            {w.week}
          </span>
        ))}
      </div>
    </div>
  )
}

export function CommandCenter() {
  return (
    <section id="dashboard" aria-labelledby="dashboard-heading" className="scroll-mt-20 border-t">
      <div className="mx-auto flex max-w-6xl flex-col gap-14 px-6 py-24 md:py-32">
        <Reveal className="flex flex-col justify-between gap-6 md:flex-row md:items-end">
          <div id="dashboard-heading">
            <SectionHeading
              eyebrow="Treasury view"
              title="Your whole payables book, under one control room."
              description="Controllers see what was released, what was held and why, how much money each vendor tier puts at risk, and how fast the team is clearing payments."
            />
          </div>
        </Reveal>

        <Reveal delay={0.05}>
          <div className="overflow-hidden rounded-xl border bg-card shadow-[0_30px_80px_-40px_color-mix(in_oklab,var(--primary)_45%,transparent)]">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b bg-surface px-5 py-3">
              <div className="flex items-center gap-3">
                <span className="text-sm font-semibold">AP control room</span>
                <span className="rounded-full border bg-card px-2 py-0.5 text-xs text-muted-foreground">Q3 FY26</span>
              </div>
              <div className="flex items-center gap-1 rounded-md border bg-card p-0.5 text-xs" aria-hidden="true">
                <span className="rounded-sm px-2 py-1 text-muted-foreground">30D</span>
                <span className="rounded-sm bg-primary px-2 py-1 text-primary-foreground">90D</span>
                <span className="rounded-sm px-2 py-1 text-muted-foreground">YTD</span>
              </div>
            </div>

            <dl className="grid grid-cols-2 border-b lg:grid-cols-4">
              {KPIS.map((kpi, i) => (
                <div
                  key={kpi.label}
                  className={cn(
                    'flex flex-col gap-3 p-5',
                    i % 2 === 0 && 'border-r',
                    i < 2 && 'border-b lg:border-b-0',
                    i === 1 && 'lg:border-r',
                  )}
                >
                  <dt className="text-xs text-muted-foreground">{kpi.label}</dt>
                  <dd className="flex items-baseline justify-between gap-2">
                    <span className="text-2xl font-semibold tabular-nums tracking-tight">{kpi.value}</span>
                    <span
                      className={cn(
                        'inline-flex items-center gap-0.5 text-xs font-medium tabular-nums',
                        kpi.good ? 'text-verified' : 'text-blocked',
                      )}
                    >
                      {kpi.up ? (
                        <ArrowUpRight className="size-3.5" aria-hidden="true" />
                      ) : (
                        <ArrowDownRight className="size-3.5" aria-hidden="true" />
                      )}
                      {kpi.delta}
                    </span>
                  </dd>
                  <dd>
                    <Sparkline series={kpi.series} />
                  </dd>
                </div>
              ))}
            </dl>

            <div className="grid lg:grid-cols-[1.6fr_1fr]">
              <div className="border-b p-5 md:p-6 lg:border-r lg:border-b-0">
                <VolumeChart />
              </div>

              <div className="flex flex-col gap-8 p-5 md:p-6">
                <div className="flex flex-col gap-3">
                  <p className="text-sm text-muted-foreground">Payment rail mix</p>
                  <div className="flex h-2.5 overflow-hidden rounded-full" aria-hidden="true">
                    {RAILS.map((r) => (
                      <span key={r.rail} className={r.tone} style={{ width: `${r.share}%` }} />
                    ))}
                  </div>
                  <ul className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                    {RAILS.map((r) => (
                      <li key={r.rail} className="flex items-center justify-between gap-2">
                        <span className="flex items-center gap-2 text-muted-foreground">
                          <span className={cn('size-2 rounded-sm', r.tone)} aria-hidden="true" />
                          {r.rail}
                        </span>
                        <span className="font-medium tabular-nums">{r.share}%</span>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="flex flex-col gap-3">
                  <p className="text-sm text-muted-foreground">Open exposure by vendor tier</p>
                  <ul className="flex flex-col gap-3">
                    {TIERS.map((t) => (
                      <li key={t.tier} className="flex flex-col gap-1.5">
                        <div className="flex items-center justify-between text-sm">
                          <span className="flex items-center gap-2">
                            <span className={cn('size-2 rounded-full', t.tone)} aria-hidden="true" />
                            {t.tier}
                            <span className="text-xs text-muted-foreground tabular-nums">{t.vendors} vendors</span>
                          </span>
                          <span className="font-medium tabular-nums">${t.exposure.toFixed(1)}M</span>
                        </div>
                        <span className="h-1 overflow-hidden rounded-full bg-muted" aria-hidden="true">
                          <span
                            className={cn('block h-full rounded-full', t.tone)}
                            style={{ width: `${Math.max((t.exposure / 31.8) * 100, 3)}%` }}
                          />
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>

            <div className="overflow-x-auto border-t">
              <table className="w-full min-w-[40rem] text-sm">
                <caption className="sr-only">Latest payment decisions</caption>
                <thead>
                  <tr className="bg-surface text-left text-xs text-muted-foreground">
                    <th scope="col" className="px-5 py-2.5 font-medium">Reference</th>
                    <th scope="col" className="px-3 py-2.5 font-medium">Vendor</th>
                    <th scope="col" className="px-3 py-2.5 font-medium">Rail</th>
                    <th scope="col" className="px-3 py-2.5 text-right font-medium">Amount</th>
                    <th scope="col" className="px-3 py-2.5 font-medium">Decision</th>
                    <th scope="col" className="px-5 py-2.5 font-medium">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {LEDGER.map((row) => (
                    <tr key={row.ref} className="border-t transition-colors hover:bg-surface">
                      <td className="px-5 py-3 tabular-nums text-muted-foreground">{row.ref}</td>
                      <td className="px-3 py-3 font-medium">{row.vendor}</td>
                      <td className="px-3 py-3 text-muted-foreground">{row.rail}</td>
                      <td className="px-3 py-3 text-right font-medium tabular-nums">{formatUsdWhole(row.amount)}</td>
                      <td className="px-3 py-3">
                        <span className={cn('rounded-full px-2 py-0.5 text-xs font-medium', DECISION_STYLE[row.decision])}>
                          {row.decision}
                        </span>
                      </td>
                      <td className="px-5 py-3 text-muted-foreground">{row.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
