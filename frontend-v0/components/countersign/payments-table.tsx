'use client'

import { memo } from 'react'
import { StatusBadge, statusReason } from '@/components/site/status-badge'
import type { CheckState } from '@/hooks/use-payment-run'
import type { Payment } from '@/lib/api'
import { formatUsd } from '@/lib/format'
import { cn } from '@/lib/utils'
import { VoidStamp } from './void-stamp'

const PENDING: CheckState = { status: 'pending' }

interface PaymentsTableProps {
  payments: Payment[]
  checks: Record<string, CheckState>
  currentId: string | null
  onOpen: (id: string) => void
}

export function PaymentsTable({ payments, checks, currentId, onOpen }: PaymentsTableProps) {
  return (
    <div className="overflow-hidden rounded-xl border border-border">
      <table className="w-full table-fixed text-left text-sm">
        <caption className="sr-only">Payments in this run. Select a payee for details.</caption>
        <thead className="border-b border-border bg-surface text-muted-foreground">
          <tr>
            <th scope="col" className="px-5 py-3 font-medium">
              Payee
            </th>
            <th scope="col" className="hidden w-32 px-5 py-3 font-medium lg:table-cell">
              Invoice
            </th>
            <th scope="col" className="w-36 px-5 py-3 text-right font-medium">
              Amount
            </th>
            <th scope="col" className="hidden w-[38%] px-5 py-3 font-medium md:table-cell">
              Status
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {payments.map((payment) => (
            <PaymentRow
              key={payment.id}
              payment={payment}
              state={checks[payment.id] ?? PENDING}
              isCurrent={payment.id === currentId}
              onOpen={onOpen}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}

const PaymentRow = memo(function PaymentRow({
  payment,
  state,
  isCurrent,
  onOpen,
}: {
  payment: Payment
  state: CheckState
  isCurrent: boolean
  onOpen: (id: string) => void
}) {
  const reason = statusReason(state)
  const voided = state.status === 'blocked' && state.call?.outcome === 'denied'
  const status = (
    <div className="flex flex-col items-start gap-1">
      <StatusBadge status={state.status} />
      {reason && <p className="text-pretty text-sm text-muted-foreground">{reason}</p>}
    </div>
  )

  return (
    <tr
      data-payment-id={payment.id}
      className={cn(
        'scroll-mb-6 scroll-mt-24 align-top transition-colors',
        isCurrent && 'bg-accent',
        state.status === 'blocked' && 'bg-blocked/[0.04]',
      )}
    >
      <td className="px-5 py-3.5">
        <button
          type="button"
          onClick={() => onOpen(payment.id)}
          className="max-w-full truncate rounded-sm text-left font-medium underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2"
        >
          {payment.payee}
        </button>
        <p className="text-sm text-muted-foreground lg:hidden">{payment.invoice_number}</p>
        <div className="mt-2 md:hidden">{status}</div>
      </td>
      <td className="hidden px-5 py-3.5 text-muted-foreground lg:table-cell">{payment.invoice_number}</td>
      <td className="relative px-5 py-3.5 text-right tabular-nums">
        <span className={cn(voided && 'text-muted-foreground line-through decoration-void/60')}>
          {formatUsd(payment.amount_usd)}
        </span>
        {voided && (
          <>
            <span className="sr-only">, check voided</span>
            <VoidStamp />
          </>
        )}
      </td>
      <td className="hidden px-5 py-3.5 md:table-cell">{status}</td>
    </tr>
  )
})
