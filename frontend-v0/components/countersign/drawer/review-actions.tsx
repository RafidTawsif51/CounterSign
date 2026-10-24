'use client'

import { useId, useState } from 'react'
import { Check, LoaderCircle, TriangleAlert, X } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { reviewPayment, type ReviewDecision } from '@/lib/api'
import { cn } from '@/lib/utils'

const MIN_REASON = 8

export function ReviewActions({
  paymentId,
  payee,
  hardRuleFired,
  onReviewed,
}: {
  paymentId: string
  payee: string
  hardRuleFired: boolean
  onReviewed: (decision: ReviewDecision, reason: string, reviewedAt: string) => void
}) {
  const [mode, setMode] = useState<ReviewDecision | null>(null)
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const reasonId = useId()
  const errorId = useId()

  function open(next: ReviewDecision) {
    setMode(next)
    setError(null)
  }

  async function submit() {
    if (!mode) return
    const trimmed = reason.trim()
    if (trimmed.length < MIN_REASON) {
      setError(`Add a reason of at least ${MIN_REASON} characters. It goes in the audit log.`)
      return
    }
    setSubmitting(true)
    try {
      const result = await reviewPayment(paymentId, mode, trimmed)
      onReviewed(result.decision, trimmed, result.reviewed_at)
      toast.success(result.decision === 'approved' ? `Approved. ${payee} will be paid.` : `Rejected. ${payee} won't be paid.`)
    } catch {
      toast.error(`Couldn't ${mode === 'approved' ? 'approve' : 'reject'} the payment. Try again.`)
      setSubmitting(false)
    }
  }

  if (!mode) {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-muted-foreground">Countersign needs a person to decide on this payment.</p>
        <div className="grid grid-cols-2 gap-3">
          <Button variant="outline" size="lg" onClick={() => open('rejected')} className="border-blocked/30 text-blocked hover:bg-blocked/5 hover:text-blocked">
            <X aria-hidden="true" />
            Reject
          </Button>
          <Button size="lg" onClick={() => open('approved')}>
            <Check aria-hidden="true" />
            Approve
          </Button>
        </div>
      </div>
    )
  }

  const approving = mode === 'approved'
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(event) => {
        event.preventDefault()
        submit()
      }}
    >
      {approving && hardRuleFired && (
        <p className="flex items-start gap-2 rounded-md bg-held/10 px-3 py-2 leading-relaxed text-held">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          A hard rule fired on this payment. Approving overrides it and sends the money.
        </p>
      )}
      <label htmlFor={reasonId} className="font-medium">
        {approving ? 'Why are you approving this payment?' : 'Why are you rejecting this payment?'}
      </label>
      <textarea
        id={reasonId}
        value={reason}
        onChange={(event) => {
          setReason(event.target.value)
          if (error) setError(null)
        }}
        rows={3}
        autoFocus
        required
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        placeholder={approving ? 'e.g. Confirmed with the vendor on a call I placed' : 'e.g. Vendor says they never sent this request'}
        className={cn(
          'w-full resize-none rounded-md border border-input bg-card px-3 py-2 leading-relaxed outline-none placeholder:text-muted-foreground focus:border-ring focus:ring-3 focus:ring-ring/15',
          error && 'border-blocked focus:border-blocked focus:ring-blocked/15',
        )}
      />
      {error && (
        <p id={errorId} className="text-blocked">
          {error}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={() => setMode(null)} disabled={submitting}>
          Cancel
        </Button>
        <Button
          type="submit"
          disabled={submitting}
          className={cn(!approving && 'bg-blocked text-primary-foreground hover:bg-blocked/90')}
        >
          {submitting && <LoaderCircle className="animate-spin" aria-hidden="true" />}
          {approving ? 'Approve and pay' : 'Reject payment'}
        </Button>
      </div>
    </form>
  )
}
