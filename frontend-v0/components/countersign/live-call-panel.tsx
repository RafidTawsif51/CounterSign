'use client'

import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { Ban, CircleCheck, Phone, X } from 'lucide-react'
import { Waveform } from '@/components/landing/waveform'
import type { CallState } from '@/hooks/use-payment-run'
import type { Payment } from '@/lib/api'
import { formatUsd } from '@/lib/format'
import { cn } from '@/lib/utils'
import { ContactSourceBadge } from './contact-source-badge'

interface LiveCallPanelProps {
  payment: Payment | null
  call: CallState | undefined
  onClose: () => void
}

export function LiveCallPanel({ payment, call, onClose }: LiveCallPanelProps) {
  const reduceMotion = useReducedMotion() ?? false
  const open = payment !== null && call !== undefined

  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => event.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="live-call"
          className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0, transition: { duration: 0.35, delay: 0.1 } }}
        >
          <div aria-hidden="true" className="absolute inset-0 bg-foreground/25 backdrop-blur-[3px]" onClick={onClose} />
          <motion.section
            role="dialog"
            aria-modal="false"
            aria-labelledby="live-call-title"
            className="relative flex w-full max-w-xl flex-col overflow-hidden rounded-2xl border border-border bg-card text-card-foreground shadow-card-physical"
            initial={reduceMotion ? false : { opacity: 0, y: 24, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 16, scale: 0.98 }}
            transition={{ type: 'spring', stiffness: 260, damping: 28 }}
          >
            <CallHeader call={call} onClose={onClose} />
            <CallIdentity payment={payment} call={call} />
            <Transcript call={call} payeeName={payment.payee} />
            <CallFooter call={call} />
          </motion.section>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

function CallHeader({ call, onClose }: { call: CallState; onClose: () => void }) {
  return (
    <header className="flex items-center justify-between gap-4 border-b border-border bg-surface px-5 py-3">
      <div className="flex items-center gap-3 text-sm">
        <span className="font-medium">Verification call</span>
        <CallStatusPill call={call} />
      </div>
      <button
        type="button"
        onClick={onClose}
        aria-label="Close call panel"
        className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2"
      >
        <X className="size-4" aria-hidden="true" />
      </button>
    </header>
  )
}

function CallStatusPill({ call }: { call: CallState }) {
  const elapsed = useElapsed(call.startedAt, call.status !== 'ended')

  if (call.status === 'ringing') {
    return (
      <span className="inline-flex items-center gap-1.5 text-muted-foreground">
        <span className="size-1.5 rounded-full bg-muted-foreground motion-safe:animate-pulse" aria-hidden="true" />
        Calling
      </span>
    )
  }

  const live = call.status === 'connected'
  return (
    <span className={cn('inline-flex items-center gap-1.5 tabular-nums', live ? 'text-verified' : 'text-muted-foreground')}>
      {live && (
        <span className="relative flex size-1.5" aria-hidden="true">
          <span className="absolute inset-0 rounded-full bg-verified opacity-70 motion-safe:animate-ping" />
          <span className="relative size-1.5 rounded-full bg-verified" />
        </span>
      )}
      {live ? 'Live' : 'Call ended'}
      <span className="text-muted-foreground">{elapsed}</span>
    </span>
  )
}

function CallIdentity({ payment, call }: { payment: Payment; call: CallState }) {
  const ringing = call.status === 'ringing'

  return (
    <div className="flex items-start gap-4 px-5 pb-5 pt-6">
      <div className="relative flex size-12 shrink-0 items-center justify-center">
        {ringing && (
          <>
            <span aria-hidden="true" className="absolute inset-0 rounded-full bg-primary/15 motion-safe:animate-ping [animation-duration:2.4s]" />
            <span aria-hidden="true" className="absolute -inset-2 rounded-full border border-primary/15" />
          </>
        )}
        <span className="relative flex size-12 items-center justify-center rounded-full bg-primary text-primary-foreground">
          <Phone className="size-5" aria-hidden="true" />
        </span>
      </div>

      <div className="flex min-w-0 flex-col gap-2">
        <div>
          <h2 id="live-call-title" className="text-balance text-2xl font-semibold tracking-tight">
            {payment.payee}
          </h2>
          <p className="text-sm text-muted-foreground">
            {payment.invoice_number} · {formatUsd(payment.amount_usd)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <p className="text-lg font-medium tabular-nums">{call.contactSource.phone}</p>
          <ContactSourceBadge kind={call.contactSource.kind} />
        </div>
        <p className="text-pretty text-sm leading-relaxed text-muted-foreground">
          {call.contactSource.detail && <span className="text-foreground">{call.contactSource.detail}</span>}
          {call.contactSource.detail && ' · '}
          Numbers in the email thread are never dialed.
        </p>
      </div>
    </div>
  )
}

function Transcript({ call, payeeName }: { call: CallState; payeeName: string }) {
  const reduceMotion = useReducedMotion() ?? false
  const scrollRef = useRef<HTMLOListElement>(null)
  const count = call.transcript.length

  useEffect(() => {
    const list = scrollRef.current
    if (!list) return
    list.scrollTo({ top: list.scrollHeight, behavior: reduceMotion ? 'auto' : 'smooth' })
  }, [count, reduceMotion])

  return (
    <div className="relative border-y border-border bg-surface/60">
      <h3 className="sr-only">Live transcript</h3>
      {count === 0 ? (
        <div className="flex h-60 flex-col items-center justify-center gap-4 text-center">
          <Waveform active={false} className="h-6 text-muted-foreground/40" />
          <div>
            <p className="font-medium">Calling {payeeName}</p>
            <p className="text-sm text-muted-foreground">Waiting for someone to pick up</p>
          </div>
        </div>
      ) : (
        <ol ref={scrollRef} className="flex h-60 flex-col gap-4 overflow-y-auto px-5 py-5">
          {call.transcript.map((line, index) => {
            const latest = index === count - 1
            const isAgent = line.speaker === 'countersign'
            return (
              <motion.li
                key={index}
                initial={reduceMotion ? false : { opacity: 0, y: 8, filter: 'blur(4px)' }}
                animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
                transition={{ duration: 0.45, ease: 'easeOut' }}
                className="flex gap-4"
              >
                <span
                  className={cn(
                    'w-24 shrink-0 pt-0.5 text-xs font-semibold uppercase tracking-wider',
                    isAgent ? 'text-primary' : 'text-muted-foreground',
                  )}
                >
                  {isAgent ? 'Countersign' : 'Vendor'}
                </span>
                <p
                  className={cn(
                    'text-pretty leading-relaxed transition-colors duration-700',
                    latest ? 'text-foreground' : 'text-muted-foreground',
                  )}
                >
                  {line.text}
                </p>
              </motion.li>
            )
          })}
        </ol>
      )}
      <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-6 bg-gradient-to-b from-surface to-transparent" />
    </div>
  )
}

function CallFooter({ call }: { call: CallState }) {
  const reduceMotion = useReducedMotion() ?? false

  return (
    <div className="min-h-28">
      <AnimatePresence mode="wait" initial={false}>
        {call.outcome ? (
          <OutcomeResult key="outcome" outcome={call.outcome} />
        ) : (
          <motion.div
            key="audio"
            initial={reduceMotion ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, transition: { duration: 0.2 } }}
            className="flex min-h-28 items-center gap-4 px-5"
          >
            <Waveform
              active={call.status === 'connected'}
              className={cn('flex-1 overflow-hidden', call.status === 'connected' ? 'text-primary' : 'text-muted-foreground/40')}
            />
            <p className="shrink-0 text-sm text-muted-foreground">
              {call.status === 'ringing' ? 'Ringing' : 'Listening for a decision'}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function OutcomeResult({ outcome }: { outcome: NonNullable<CallState['outcome']> }) {
  const reduceMotion = useReducedMotion() ?? false
  const denied = outcome === 'denied'
  const Icon = denied ? Ban : CircleCheck

  return (
    <motion.div
      role="status"
      initial={reduceMotion ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 300, damping: 26 }}
      className={cn('flex min-h-28 items-center gap-4 px-5 py-5', denied ? 'bg-blocked/[0.07]' : 'bg-verified/[0.07]')}
    >
      <motion.span
        initial={reduceMotion ? false : { scale: 0.4, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: 'spring', stiffness: 420, damping: 18, delay: 0.1 }}
        className={cn(
          'flex size-12 shrink-0 items-center justify-center rounded-full',
          denied ? 'bg-blocked text-primary-foreground' : 'bg-verified text-primary-foreground',
        )}
      >
        <Icon className="size-6" strokeWidth={2.25} aria-hidden="true" />
      </motion.span>
      <p className="text-balance text-2xl font-semibold leading-tight tracking-tight">
        {denied ? 'Vendor denied the change.' : 'Vendor confirmed.'}{' '}
        <span className={denied ? 'text-blocked' : 'text-verified'}>
          {denied ? 'Payment blocked.' : 'Payment released.'}
        </span>
      </p>
    </motion.div>
  )
}

function useElapsed(startedAt: number, running: boolean) {
  const [now, setNow] = useState(startedAt)

  useEffect(() => {
    if (!running) return
    setNow(Date.now())
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [running])

  const seconds = Math.max(0, Math.floor((now - startedAt) / 1000))
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}
