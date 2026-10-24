'use client'

import { useReducedMotion } from 'framer-motion'
import { Area, AreaChart, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { RiskDecision, VendorHistory, VendorHistoryPoint } from '@/lib/api'
import { formatUsd, formatUsdWhole } from '@/lib/format'
import { cn } from '@/lib/utils'
import { DrawerSection } from './drawer-section'

const MARKER: Record<RiskDecision, { color: string; tone: string }> = {
  pay: { color: 'var(--verified)', tone: 'text-verified' },
  hold: { color: 'var(--held)', tone: 'text-held' },
  block: { color: 'var(--blocked)', tone: 'text-blocked' },
}

function monthLabel(month: string, withYear = false) {
  const [year, m] = month.split('-').map(Number)
  return new Date(year, m - 1, 1).toLocaleDateString('en-US', withYear ? { month: 'short', year: 'numeric' } : { month: 'short' })
}

export function VendorHistoryChart({ history, decision }: { history: VendorHistory; decision: RiskDecision }) {
  const reduceMotion = useReducedMotion() ?? false
  const current = history.points.find((point) => point.is_current)
  const ratio = current ? current.amount_usd / history.average_usd : 1
  const marker = MARKER[decision]
  const first = history.points[0]
  const last = history.points.at(-1)

  return (
    <DrawerSection
      title="Vendor history"
      id="history"
      aside={<span className="text-xs text-muted-foreground">Vendor since {history.vendor_since}</span>}
    >
      <div className="flex flex-col gap-4 rounded-lg border border-border p-4">
        <dl className="grid grid-cols-3 gap-4">
          <div className="flex flex-col gap-0.5">
            <dt className="text-xs text-muted-foreground">12-month average</dt>
            <dd className="font-semibold tabular-nums">{formatUsdWhole(history.average_usd)}</dd>
          </div>
          <div className="flex flex-col gap-0.5">
            <dt className="text-xs text-muted-foreground">This invoice</dt>
            <dd className="font-semibold tabular-nums">{current ? formatUsdWhole(current.amount_usd) : '—'}</dd>
          </div>
          <div className="flex flex-col gap-0.5">
            <dt className="text-xs text-muted-foreground">Versus average</dt>
            <dd className={cn('font-semibold tabular-nums', ratio >= 1.25 ? marker.tone : 'text-foreground')}>
              {ratio.toFixed(1)}x
            </dd>
          </div>
        </dl>

        <figure className="flex flex-col gap-1.5">
          <div className="h-24" role="img" aria-label={`Monthly invoice amounts over 12 months. This invoice is ${ratio.toFixed(1)} times the average.`}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={history.points} margin={{ top: 10, right: 10, bottom: 2, left: 10 }}>
                <defs>
                  <linearGradient id="history-fill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.18} />
                    <stop offset="100%" stopColor="var(--primary)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="month" hide />
                <YAxis hide domain={[(min: number) => min * 0.8, (max: number) => max * 1.08]} />
                <ReferenceLine y={history.average_usd} stroke="var(--muted-foreground)" strokeDasharray="3 4" strokeOpacity={0.6} />
                <Tooltip
                  cursor={{ stroke: 'var(--border)' }}
                  content={({ active, payload }) => {
                    const point = payload?.[0]?.payload as VendorHistoryPoint | undefined
                    if (!active || !point) return null
                    return (
                      <div className="flex flex-col gap-0.5 rounded-md border border-border bg-popover px-2.5 py-1.5 text-xs shadow-md">
                        <span className="text-muted-foreground">
                          {monthLabel(point.month, true)} · <span className="font-mono">{point.invoice_number}</span>
                        </span>
                        <span className="font-semibold tabular-nums">
                          {formatUsd(point.amount_usd)}
                          {point.is_current && <span className={cn('ml-1.5 font-medium', marker.tone)}>This invoice</span>}
                        </span>
                      </div>
                    )
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="amount_usd"
                  stroke="var(--primary)"
                  strokeWidth={1.75}
                  fill="url(#history-fill)"
                  dot={false}
                  activeDot={{ r: 3, fill: 'var(--primary)', stroke: 'var(--card)' }}
                  isAnimationActive={!reduceMotion}
                />
                {current && (
                  <ReferenceDot
                    x={current.month}
                    y={current.amount_usd}
                    r={5}
                    fill={marker.color}
                    stroke="var(--card)"
                    strokeWidth={2}
                  />
                )}
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <figcaption className="flex items-center justify-between text-xs text-muted-foreground">
            <span>{first && monthLabel(first.month, true)}</span>
            <span className="flex items-center gap-3">
              <span className="flex items-center gap-1.5">
                <span aria-hidden="true" className="w-3 border-t border-dashed border-muted-foreground" />
                Average
              </span>
              <span className="flex items-center gap-1.5">
                <span aria-hidden="true" className="size-2 rounded-full" style={{ backgroundColor: marker.color }} />
                This invoice
              </span>
            </span>
            <span>{last && monthLabel(last.month, true)}</span>
          </figcaption>
        </figure>
      </div>
    </DrawerSection>
  )
}
