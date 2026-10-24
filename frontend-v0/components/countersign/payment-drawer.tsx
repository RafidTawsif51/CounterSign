'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { UserCheck, UserX } from 'lucide-react'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { getPaymentDetail, type Payment, type ReviewDecision } from '@/lib/api'
import type { CheckState } from '@/hooks/use-payment-run'
import { AskWhy } from './drawer/ask-why'
import { BankAccountTimeline } from './drawer/bank-account-timeline'
import { CallRecord, type CallRecordViewModel } from './drawer/call-record'
import { DecisionSummary } from './drawer/decision-summary'
import { ReviewActions } from './drawer/review-actions'
import { RiskSignals } from './drawer/risk-signals'
import { VendorHistoryChart } from './drawer/vendor-history-chart'

interface PaymentDrawerProps {
  runId: string
  payment: Payment | null
  state: CheckState | undefined
  onClose: () => void
  onReviewed: (paymentId: string, decision: ReviewDecision, reason: string, reviewedAt: string) => void
}

export function PaymentDrawer({ runId, payment, state, onClose, onReviewed }: PaymentDrawerProps) {
  return (
    <Sheet open={payment !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-xl">
        {payment && (
          <PaymentDetailView
            key={payment.id}
            runId={runId}
            payment={payment}
            state={state ?? { status: 'pending' }}
            onReviewed={(decision, reason, reviewedAt) => onReviewed(payment.id, decision, reason, reviewedAt)}
          />
        )}
      </SheetContent>
    </Sheet>
  )
}

function PaymentDetailView({
  runId,
  payment,
  state,
  onReviewed,
}: {
  runId: string
  payment: Payment
  state: CheckState
  onReviewed: (decision: ReviewDecision, reason: string, reviewedAt: string) => void
}) {
  const [highlighted, setHighlighted] = useState<string | null>(null)
  const scored = state.status !== 'pending'
  const { data: detail, error } = useSWR(scored ? ['payment-detail', runId, payment.id] : null, () =>
    getPaymentDetail(payment.id, runId),
  )

  const settled = state.status === 'paid' || state.status === 'held' || state.status === 'blocked'
  const apiCall = settled ? detail?.calls[0] : undefined
  const call: CallRecordViewModel | undefined = state.call
    ? { contactSource: state.call.contactSource, outcome: state.call.outcome, transcript: state.call.transcript }
    : apiCall
      ? { contactSource: apiCall.contact_source, outcome: apiCall.outcome, transcript: apiCall.transcript }
      : undefined
  const needsReview = !state.review && (state.status === 'held' || state.status === 'blocked')

  return (
    <div className="flex h-full flex-col">
      <SheetHeader className="shrink-0 gap-1 border-b border-border px-6 py-4 pr-12">
        <SheetTitle className="text-base font-semibold tracking-tight">{payment.payee}</SheetTitle>
        <SheetDescription className="font-mono text-xs">
          {payment.invoice_number} · Check {payment.check_number}
          {state.transferId && ` · ${state.transferId}`}
        </SheetDescription>
      </SheetHeader>

      <div className="flex flex-1 flex-col gap-9 overflow-y-auto px-6 py-6 text-sm">
        <DecisionSummary payment={payment} state={state} />
        {!scored && (
          <p className="leading-relaxed text-muted-foreground">
            Signals, history and bank details will appear here once Countersign reviews this payment.
          </p>
        )}

        {scored && error && (
          <p className="leading-relaxed text-blocked" role="alert">
            {"Couldn't load this payment's details. Close the drawer and try again."}
          </p>
        )}

        {scored && !detail && !error && <DetailSkeleton />}

        {detail && (
          <>
            <RiskSignals assessment={detail.risk_assessment} highlighted={highlighted} />
            <VendorHistoryChart history={detail.vendor_history} decision={detail.risk_assessment.decision} />
            <BankAccountTimeline accounts={detail.bank_accounts} callOutcome={call?.outcome} />
            {call && <CallRecord call={call} />}
            <AskWhy
              paymentId={payment.id}
              runId={runId}
              decision={detail.risk_assessment.decision}
              signals={detail.risk_assessment.signals}
              onHighlight={setHighlighted}
            />
          </>
        )}
      </div>

      {(needsReview || state.review) && (
        <footer className="shrink-0 border-t border-border bg-surface px-6 py-4 text-sm">
          {state.review ? (
            <ReviewRecord review={state.review} />
          ) : (
            <ReviewActions
              paymentId={payment.id}
              payee={payment.payee}
              hardRuleFired={(detail?.risk_assessment.hard_rules_fired.length ?? 0) > 0}
              onReviewed={onReviewed}
            />
          )}
        </footer>
      )}
    </div>
  )
}

function ReviewRecord({ review }: { review: NonNullable<CheckState['review']> }) {
  const approved = review.decision === 'approved'
  const Icon = approved ? UserCheck : UserX
  const time = new Date(review.reviewedAt).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
  return (
    <div className="flex items-start gap-3">
      <Icon className={approved ? 'mt-0.5 size-4 shrink-0 text-verified' : 'mt-0.5 size-4 shrink-0 text-blocked'} aria-hidden="true" />
      <div className="flex flex-col gap-0.5">
        <p className="font-medium">
          {approved ? 'You approved this payment' : 'You rejected this payment'} at {time}
        </p>
        <p className="leading-relaxed text-muted-foreground">{review.reason}</p>
      </div>
    </div>
  )
}

function DetailSkeleton() {
  return (
    <div className="flex flex-col gap-3" aria-hidden="true">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="h-16 animate-pulse rounded-lg bg-muted motion-reduce:animate-none" />
      ))}
    </div>
  )
}
