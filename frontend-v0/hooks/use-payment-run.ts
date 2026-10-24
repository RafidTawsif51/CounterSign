'use client'

import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react'
import { toast } from 'sonner'
import {
  startPaymentRun,
  subscribeToRun,
  type CallOutcome,
  type CallSpeaker,
  type ContactSource,
  type PaymentRun,
  type ReviewDecision,
  type RiskScoredData,
  type RunCompletedData,
  type RunEvent,
} from '@/lib/api'
import { formatUsd, lowerFirst } from '@/lib/format'

export type CheckStatus = 'pending' | 'reviewing' | 'paid' | 'held' | 'blocked'
export type RunPhase = 'idle' | 'running' | 'complete'

export interface CallLine {
  speaker: CallSpeaker
  text: string
}

export interface CallState {
  status: 'ringing' | 'connected' | 'ended'
  contactSource: ContactSource
  startedAt: number
  transcript: CallLine[]
  outcome?: CallOutcome
}

export interface CheckState {
  status: CheckStatus
  risk?: Omit<RiskScoredData, 'payment_id'>
  heldReasons?: string[]
  blockedReason?: string
  transferId?: string
  call?: CallState
  review?: { decision: ReviewDecision; reason: string; reviewedAt: string }
}

interface RunState {
  phase: RunPhase
  checks: Record<string, CheckState>
  currentId: string | null
  /** Payment whose verification call is shown in the live call panel. */
  activeCallId: string | null
  summary: RunCompletedData | null
  announcement: string
}

type Action =
  | { type: 'reset' }
  | { type: 'dismiss-call' }
  | { type: 'review'; paymentId: string; decision: ReviewDecision; reason: string; reviewedAt: string }
  | { type: 'event'; event: RunEvent; announcement: string }

const INITIAL: RunState = {
  phase: 'idle',
  checks: {},
  currentId: null,
  activeCallId: null,
  summary: null,
  announcement: '',
}

function patchCall(state: RunState, id: string, next: Partial<CallState>): RunState['checks'] {
  const call = state.checks[id]?.call
  if (!call) return state.checks
  return patch(state, id, { call: { ...call, ...next } })
}

/** Settling a payment closes its call panel so the board, and the VOID stamp, are visible. */
function closeCallFor(state: RunState, id: string) {
  return state.activeCallId === id ? null : state.activeCallId
}

function patch(state: RunState, id: string, next: Partial<CheckState>): RunState['checks'] {
  const current: CheckState = state.checks[id] ?? { status: 'pending' }
  return { ...state.checks, [id]: { ...current, ...next } }
}

function reducer(state: RunState, action: Action): RunState {
  if (action.type === 'reset') return { ...INITIAL, phase: 'running' }
  if (action.type === 'dismiss-call') return { ...state, activeCallId: null }
  if (action.type === 'review') {
    const { paymentId, decision, reason, reviewedAt } = action
    const review = { decision, reason, reviewedAt }
    return {
      ...state,
      checks: patch(
        state,
        paymentId,
        decision === 'approved'
          ? { status: 'paid', review }
          : { status: 'blocked', blockedReason: 'Rejected by reviewer', review },
      ),
      announcement: decision === 'approved' ? 'Payment approved and released' : 'Payment rejected',
    }
  }

  const { event, announcement } = action
  switch (event.type) {
    case 'run.started':
      return { ...state, phase: 'running', announcement }
    case 'risk.scored': {
      const { payment_id, ...risk } = event.data
      return {
        ...state,
        currentId: payment_id,
        checks: patch(state, payment_id, { status: 'reviewing', risk }),
        announcement,
      }
    }
    case 'call.started': {
      const { payment_id, contact_source } = event.data
      return {
        ...state,
        activeCallId: payment_id,
        checks: patch(state, payment_id, {
          call: { status: 'ringing', contactSource: contact_source, startedAt: Date.now(), transcript: [] },
        }),
        announcement,
      }
    }
    case 'call.transcript': {
      const { payment_id, speaker, text } = event.data
      const transcript = state.checks[payment_id]?.call?.transcript ?? []
      return {
        ...state,
        checks: patchCall(state, payment_id, { status: 'connected', transcript: [...transcript, { speaker, text }] }),
        announcement,
      }
    }
    case 'call.outcome':
      return {
        ...state,
        checks: patchCall(state, event.data.payment_id, { status: 'ended', outcome: event.data.outcome }),
        announcement,
      }
    case 'payment.paid':
      return {
        ...state,
        activeCallId: closeCallFor(state, event.data.payment_id),
        checks: patch(state, event.data.payment_id, { status: 'paid', transferId: event.data.nessie_transfer_id }),
        announcement,
      }
    case 'payment.held':
      return {
        ...state,
        activeCallId: closeCallFor(state, event.data.payment_id),
        checks: patch(state, event.data.payment_id, { status: 'held', heldReasons: event.data.reasons }),
        announcement,
      }
    case 'payment.blocked':
      return {
        ...state,
        activeCallId: closeCallFor(state, event.data.payment_id),
        checks: patch(state, event.data.payment_id, { status: 'blocked', blockedReason: event.data.reason }),
        announcement,
      }
    case 'run.completed':
      return { ...state, phase: 'complete', currentId: null, activeCallId: null, summary: event.data, announcement }
  }
}

export function usePaymentRun(run: PaymentRun | undefined) {
  const [state, dispatch] = useReducer(reducer, INITIAL)
  const unsubscribeRef = useRef<(() => void) | null>(null)

  const payeeById = useMemo(
    () => new Map(run?.payments.map((payment) => [payment.id, payment.payee]) ?? []),
    [run],
  )

  const start = useCallback(async () => {
    if (!run) return
    unsubscribeRef.current?.()
    dispatch({ type: 'reset' })

    try {
      await startPaymentRun(run.id)
    } catch {
      toast.error("Couldn't start the run. Try again.")
      return
    }

    unsubscribeRef.current = subscribeToRun(run.id, (event) => {
      dispatch({ type: 'event', event, announcement: describe(event, payeeById) })

      if (event.type === 'run.started') toast('Run started')
      if (event.type === 'run.completed') {
        const { paid, held, blocked, total_usd } = event.data
        toast.success(`Run complete: paid ${paid}, held ${held}, blocked ${blocked}`, {
          description: `${formatUsd(total_usd)} sent to vendors`,
        })
        unsubscribeRef.current?.()
        unsubscribeRef.current = null
      }
    })
  }, [run, payeeById])

  useEffect(() => () => unsubscribeRef.current?.(), [])

  const dismissCall = useCallback(() => dispatch({ type: 'dismiss-call' }), [])
  const recordReview = useCallback(
    (paymentId: string, decision: ReviewDecision, reason: string, reviewedAt: string) =>
      dispatch({ type: 'review', paymentId, decision, reason, reviewedAt }),
    [],
  )

  const totals = useMemo(() => {
    let paid = 0
    let held = 0
    let blocked = 0
    let paidUsd = 0
    for (const payment of run?.payments ?? []) {
      const status = state.checks[payment.id]?.status
      if (status === 'paid') {
        paid++
        paidUsd += payment.amount_usd
      } else if (status === 'held') held++
      else if (status === 'blocked') blocked++
    }
    return {
      paid,
      held,
      blocked,
      // Computed from statuses, not the run summary, so reviewer approvals count toward the total.
      paidUsd: Math.round(paidUsd * 100) / 100,
      processed: paid + held + blocked,
      total: run?.payments.length ?? 0,
    }
  }, [run, state.checks])

  return { ...state, totals, start, dismissCall, recordReview }
}

function describe(event: RunEvent, payeeById: Map<string, string>) {
  const payee = 'payment_id' in event.data ? payeeById.get(event.data.payment_id) : undefined
  switch (event.type) {
    case 'run.started':
      return `Run started with ${event.data.invoice_count} invoices`
    case 'risk.scored':
      return `Reviewing ${payee}`
    case 'call.started':
      return `Calling ${payee} at ${event.data.contact_source.phone}`
    case 'call.transcript':
      return `${event.data.speaker === 'countersign' ? 'Countersign' : 'Vendor'}: ${event.data.text}`
    case 'call.outcome':
      return event.data.outcome === 'denied'
        ? 'Vendor denied the change. Payment blocked.'
        : 'Vendor confirmed. Payment released.'
    case 'payment.paid':
      return `Paid ${payee}`
    case 'payment.held':
      return `Held ${payee}: ${lowerFirst(event.data.reasons[0] ?? 'needs review')}`
    case 'payment.blocked':
      return `Blocked ${payee}: ${lowerFirst(event.data.reason)}`
    case 'run.completed':
      return `Run complete. Paid ${event.data.paid}, held ${event.data.held}, blocked ${event.data.blocked}`
  }
}
