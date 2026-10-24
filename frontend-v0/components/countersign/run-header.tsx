'use client'

import { LoaderCircle, Play, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { RunPhase } from '@/hooks/use-payment-run'
import { formatRunDate, formatUsd } from '@/lib/format'
import { cn } from '@/lib/utils'

interface Totals {
  paid: number
  held: number
  blocked: number
  paidUsd: number
  processed: number
  total: number
}

interface RunHeaderProps {
  company: string
  runDate: string
  accountLast4: string
  phase: RunPhase
  totals: Totals
  onStart: () => void
}

function Stat({ label, value, dot }: { label: string; value: string; dot?: string }) {
  return (
    <div className="flex flex-col gap-1.5 px-5 py-4">
      <dt className="flex items-center gap-2 text-sm text-muted-foreground">
        {dot && <span className={cn('size-1.5 rounded-full', dot)} aria-hidden="true" />}
        {label}
      </dt>
      <dd className="text-2xl font-semibold tracking-tight tabular-nums">{value}</dd>
    </div>
  )
}

export function RunHeader({ company, runDate, accountLast4, phase, totals, onStart }: RunHeaderProps) {
  const pct = (n: number) => (totals.total ? (n / totals.total) * 100 : 0)
  const phaseText = phase === 'idle' ? 'Not started' : phase === 'running' ? 'In progress' : 'Complete'

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div className="flex flex-col gap-2">
          <p className="text-sm text-muted-foreground">Thursday payment run</p>
          <h1 className="text-balance text-3xl font-semibold tracking-tight md:text-4xl">{company}</h1>
          <p className="text-sm text-muted-foreground">
            {formatRunDate(runDate)} · Funding account ending {accountLast4}
          </p>
        </div>

        <Button onClick={onStart} disabled={phase === 'running'} className="h-10 gap-2 px-4">
          {phase === 'running' ? (
            <>
              <LoaderCircle className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
              Run in progress
            </>
          ) : phase === 'complete' ? (
            <>
              <RotateCcw className="size-4" aria-hidden="true" />
              Run again
            </>
          ) : (
            <>
              <Play className="size-4" aria-hidden="true" />
              Start payment run
            </>
          )}
        </Button>
      </div>

      <div className="overflow-hidden rounded-xl border border-border">
        <dl className="grid grid-cols-2 divide-border md:grid-cols-4 md:divide-x [&>*:nth-child(-n+2)]:border-b md:[&>*:nth-child(-n+2)]:border-b-0 [&>*:nth-child(odd)]:border-r md:[&>*:nth-child(odd)]:border-r-0">
          <Stat label="Verified" value={String(totals.paid)} dot="bg-verified" />
          <Stat label="Held" value={String(totals.held)} dot="bg-held" />
          <Stat label="Blocked" value={String(totals.blocked)} dot="bg-blocked" />
          <Stat label="Paid out" value={formatUsd(totals.paidUsd)} />
        </dl>
        <div className="flex items-center gap-4 border-t border-border bg-surface px-5 py-3">
          <div
            role="progressbar"
            aria-label="Run progress"
            aria-valuemin={0}
            aria-valuemax={totals.total}
            aria-valuenow={totals.processed}
            className="flex h-1.5 flex-1 overflow-hidden rounded-full bg-border"
          >
            <div className="h-full bg-verified transition-[width] duration-300" style={{ width: `${pct(totals.paid)}%` }} />
            <div className="h-full bg-held transition-[width] duration-300" style={{ width: `${pct(totals.held)}%` }} />
            <div className="h-full bg-blocked transition-[width] duration-300" style={{ width: `${pct(totals.blocked)}%` }} />
          </div>
          <p className="shrink-0 text-sm tabular-nums text-muted-foreground">
            <span className="font-medium text-foreground">
              {totals.processed} of {totals.total}
            </span>{' '}
            reviewed · {phaseText}
          </p>
        </div>
      </div>
    </div>
  )
}
