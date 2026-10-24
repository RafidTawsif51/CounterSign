'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import useSWR from 'swr'
import { useReducedMotion } from 'framer-motion'
import { Crosshair } from 'lucide-react'
import { usePaymentRun } from '@/hooks/use-payment-run'
import { DEMO_RUN_ID, getPaymentRun } from '@/lib/api'
import { LiveCallPanel } from './live-call-panel'
import { PaymentDrawer } from './payment-drawer'
import { PaymentsTable } from './payments-table'
import { RunHeader } from './run-header'

export function PaymentRunScreen({ runId, autoStart = false }: { runId: string; autoStart?: boolean }) {
  const { data: run, error, isLoading } = useSWR(['payment-run', runId], () => getPaymentRun(runId))
  const { phase, checks, currentId, activeCallId, totals, announcement, start, dismissCall, recordReview } =
    usePaymentRun(run)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const reduceMotion = useReducedMotion() ?? false
  const autoStarted = useRef(false)
  const isAttackRun = runId !== DEMO_RUN_ID

  const openPayment = useCallback((id: string) => setSelectedId(id), [])

  useEffect(() => {
    if (!autoStart || !run || autoStarted.current) return
    autoStarted.current = true
    start()
  }, [autoStart, run, start])

  // Keep the payment under review visible while the run streams in.
  useEffect(() => {
    if (!currentId) return
    document
      .querySelector(`[data-payment-id="${currentId}"]`)
      ?.scrollIntoView({ block: 'nearest', behavior: reduceMotion ? 'auto' : 'smooth' })
  }, [currentId, reduceMotion])

  const selectedPayment = run?.payments.find((payment) => payment.id === selectedId) ?? null
  const callPayment = run?.payments.find((payment) => payment.id === activeCallId) ?? null

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-6 pb-24 pt-12">
      {isLoading && <p className="py-16 text-center text-muted-foreground">Loading the payment run</p>}
      {error && (
        <p role="alert" className="py-16 text-center text-blocked">
          {"Couldn't load the payment run. Refresh to try again."}
        </p>
      )}

      {run && (
        <>
          {isAttackRun && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-void/25 bg-void/5 px-4 py-3 text-sm">
              <p className="flex items-center gap-2.5">
                <Crosshair className="size-4 shrink-0 text-void" aria-hidden="true" />
                <span>
                  Your attack is in the Summit Concrete thread.{' '}
                  <span className="text-muted-foreground">Watch what Countersign does when it gets there.</span>
                </span>
              </p>
              <a href="/attack" className="font-medium text-void underline-offset-4 hover:underline">
                Send another attack
              </a>
            </div>
          )}
          <RunHeader
            company={run.company}
            runDate={run.run_date}
            accountLast4={run.funding_account_last4}
            phase={phase}
            totals={totals}
            onStart={start}
          />
          <PaymentsTable payments={run.payments} checks={checks} currentId={currentId} onOpen={openPayment} />
          <PaymentDrawer
            runId={runId}
            onReviewed={recordReview}
            payment={selectedPayment}
            state={selectedId ? checks[selectedId] : undefined}
            onClose={() => setSelectedId(null)}
          />
          <LiveCallPanel
            payment={callPayment}
            call={activeCallId ? checks[activeCallId]?.call : undefined}
            onClose={dismissCall}
          />
        </>
      )}

      <p className="sr-only" aria-live="polite">
        {announcement}
      </p>
    </main>
  )
}
