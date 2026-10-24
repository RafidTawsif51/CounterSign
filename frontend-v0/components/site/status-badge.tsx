'use client'

import { Ban, Check, LoaderCircle, Pause } from 'lucide-react'
import { motion, useReducedMotion } from 'framer-motion'
import type { CheckState, CheckStatus } from '@/hooks/use-payment-run'
import { cn } from '@/lib/utils'

export function StatusBadge({ status }: { status: CheckStatus }) {
  const reduceMotion = useReducedMotion() ?? false

  if (status === 'pending') {
    return <span className="text-sm text-muted-foreground">Queued</span>
  }

  if (status === 'reviewing') {
    return (
      <span className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
        <LoaderCircle className="size-3.5 animate-spin motion-reduce:animate-none" aria-hidden="true" />
        Reviewing
      </span>
    )
  }

  const config = {
    paid: { label: 'Verified', Icon: Check, className: 'bg-verified/10 text-verified' },
    held: { label: 'Held', Icon: Pause, className: 'bg-held/10 text-held' },
    blocked: { label: 'Blocked', Icon: Ban, className: 'bg-blocked/10 text-blocked' },
  }[status]

  return (
    <motion.span
      key={status}
      initial={reduceMotion ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
      className={cn('relative inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-sm font-medium', config.className)}
    >
      {status === 'blocked' && !reduceMotion && (
        <motion.span
          aria-hidden="true"
          className="absolute inset-0 rounded-full ring-2 ring-blocked/50"
          initial={{ opacity: 1, scale: 1 }}
          animate={{ opacity: 0, scale: 1.4 }}
          transition={{ duration: 1.1, ease: 'easeOut' }}
        />
      )}
      <config.Icon className="size-3.5" strokeWidth={2.5} aria-hidden="true" />
      {config.label}
    </motion.span>
  )
}

export function statusReason(state: CheckState) {
  if (state.status === 'held') return state.heldReasons?.join(', ') ?? 'Needs review'
  if (state.status === 'blocked') return state.blockedReason ?? 'Blocked'
  return null
}

export function statusText(state: CheckState) {
  switch (state.status) {
    case 'pending':
      return 'Queued'
    case 'reviewing':
      return 'Reviewing'
    case 'paid':
      return 'Verified and paid'
    case 'held':
      return `Held: ${statusReason(state)}`
    case 'blocked':
      return `Blocked: ${statusReason(state)}`
  }
}
