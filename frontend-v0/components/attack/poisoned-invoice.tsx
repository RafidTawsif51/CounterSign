'use client'

import { useState, type CSSProperties, type ReactNode } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { FileText, ScanSearch } from 'lucide-react'
import { INVOICE_INJECTIONS, INVOICE_LINE_ITEMS, POISONED_ATTACHMENT } from '@/lib/attack-cards'
import { cn } from '@/lib/utils'

/** Seconds after X-ray turns on; roughly when the scan line passes each block. */
const REVEAL_AT = { hiddenWhite: 0.75, tiny: 1.1, offPageOpen: 1.35, offPage: 1.8 }
const SCAN_SECONDS = 1.4

export function PoisonedInvoice() {
  const [xray, setXray] = useState(false)
  const reduceMotion = useReducedMotion() ?? false
  const delayed = (seconds: number): CSSProperties => ({
    transitionDelay: xray && !reduceMotion ? `${seconds}s` : '0s',
  })

  return (
    <section aria-labelledby="invoice-file" className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="flex items-center justify-between gap-4 border-b border-border px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-md bg-void/10 text-void">
            <FileText className="size-4" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <h3 id="invoice-file" className="truncate text-sm font-medium">
              {POISONED_ATTACHMENT.filename}
            </h3>
            <p className="text-xs text-muted-foreground">Attached to your reply · 1 page</p>
          </div>
        </div>
        <XraySwitch checked={xray} onChange={setXray} />
      </div>

      <div
        className={cn(
          'relative px-4 py-6 transition-colors duration-700 sm:px-6',
          xray ? 'bg-foreground' : 'bg-surface',
        )}
      >
        <div className="mx-auto max-w-sm">
          <div
            className={cn(
              'relative overflow-hidden rounded-sm transition-[background-color,color,box-shadow] duration-700',
              xray ? 'bg-card/[0.04] text-card/40 ring-1 ring-card/20' : 'bg-card text-foreground shadow-card-physical',
            )}
          >
            <InvoiceBody xray={xray} delayed={delayed} reduceMotion={reduceMotion} />
            {xray && !reduceMotion && <ScanLine />}
          </div>

          <div
            className={cn(
              'grid transition-[grid-template-rows] duration-700 ease-out',
              xray ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]',
            )}
            style={delayed(REVEAL_AT.offPageOpen)}
            aria-hidden={!xray}
          >
            <div className="overflow-hidden">
              <div className="flex flex-col gap-8 pt-5">
                <p className="flex items-center gap-3 text-[10px] font-medium uppercase tracking-wider text-card/50">
                  <span className="h-px flex-1 border-t border-dashed border-card/30" />
                  Page edge · 792pt
                  <span className="h-px flex-1 border-t border-dashed border-card/30" />
                </p>
                <Injection
                  show={xray}
                  label="Off-page text"
                  delay={REVEAL_AT.offPage}
                  reduceMotion={reduceMotion}
                  className="px-5 pb-2"
                >
                  <p
                    className={cn(
                      'text-xs leading-snug transition-[color,text-shadow] duration-500',
                      xray ? 'text-glow-void' : 'text-transparent',
                    )}
                    style={delayed(REVEAL_AT.offPage)}
                  >
                    {INVOICE_INJECTIONS.offPage}
                  </p>
                  <p className="mt-1.5 text-[10px] text-card/50">Placed at y = 1,180pt, below the printable page.</p>
                </Injection>
              </div>
            </div>
          </div>
        </div>
      </div>

      <p className="border-t border-border px-4 py-3 text-sm leading-relaxed" aria-live="polite">
        {xray ? (
          <>
            <span className="font-semibold text-void">3 hidden instructions found.</span>{' '}
            <span className="text-muted-foreground">
              A person reading this PDF sees a normal invoice. An AI reading its text sees all of this.
            </span>
          </>
        ) : (
          <span className="text-muted-foreground">
            Looks like a normal invoice. Turn on X-ray to see what the AI reads.
          </span>
        )}
      </p>
    </section>
  )
}

function InvoiceBody({
  xray,
  delayed,
  reduceMotion,
}: {
  xray: boolean
  delayed: (seconds: number) => CSSProperties
  reduceMotion: boolean
}) {
  return (
    <div className="flex flex-col gap-5 p-5 text-xs">
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-0.5">
          <p className="text-sm font-bold tracking-tight">SUMMIT CONCRETE</p>
          <p className="opacity-70">4120 Quarry Rd, Boulder, CO 80301</p>
        </div>
        <div className="flex flex-col items-end gap-0.5 text-right">
          <p className="text-base font-semibold tracking-tight">Invoice</p>
          <p className="tabular-nums opacity-70">INV-20534 (rev. 2)</p>
        </div>
      </div>

      <dl className="grid grid-cols-3 gap-3 border-y border-current/15 py-3">
        <div className="flex flex-col gap-0.5">
          <dt className="opacity-60">Bill to</dt>
          <dd className="font-medium">Ridgeline Builders</dd>
        </div>
        <div className="flex flex-col gap-0.5">
          <dt className="opacity-60">Issued</dt>
          <dd className="font-medium tabular-nums">Oct 27, 2026</dd>
        </div>
        <div className="flex flex-col gap-0.5">
          <dt className="opacity-60">Due</dt>
          <dd className="font-medium tabular-nums">Nov 6, 2026</dd>
        </div>
      </dl>

      <table className="w-full text-left">
        <thead>
          <tr className="opacity-60">
            <th scope="col" className="pb-1.5 font-normal">
              Description
            </th>
            <th scope="col" className="pb-1.5 text-right font-normal">
              Amount
            </th>
          </tr>
        </thead>
        <tbody>
          {INVOICE_LINE_ITEMS.map((item) => (
            <tr key={item.description} className="border-t border-current/10">
              <td className="py-1.5 pr-3">
                {item.description}
                <span className="block opacity-60">
                  {item.qty} × {item.rate}
                </span>
              </td>
              <td className="py-1.5 text-right align-top tabular-nums">{item.amount}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t border-current/30">
            <th scope="row" className="pt-2 font-semibold">
              Total due
            </th>
            <td className="pt-2 text-right text-sm font-semibold tabular-nums">$48,720.00</td>
          </tr>
        </tfoot>
      </table>

      <div className="flex flex-col gap-1">
        <p className="opacity-60">Remit to</p>
        <p className="font-medium">Per vendor record on file</p>
        <p className="opacity-70">Thank you for your business.</p>
      </div>

      <Injection show={xray} label="Hidden white text" delay={REVEAL_AT.hiddenWhite} reduceMotion={reduceMotion}>
        <p
          className={cn(
            'rounded-sm text-[11px] leading-snug transition-[color,text-shadow,outline-color] duration-500',
            'outline outline-1 outline-offset-4 outline-dashed',
            xray ? 'text-glow-void outline-void/60' : 'text-card outline-transparent',
          )}
          style={delayed(REVEAL_AT.hiddenWhite)}
          aria-hidden={!xray}
        >
          {INVOICE_INJECTIONS.hiddenWhite}
        </p>
      </Injection>

      <div className="flex items-end justify-between gap-4 border-t border-current/15 pt-3">
        <Injection show={xray} label="Tiny text · 1pt" delay={REVEAL_AT.tiny} reduceMotion={reduceMotion} className="flex-1">
          <p
            className={cn(
              'leading-tight transition-[font-size,color,text-shadow] duration-700',
              xray ? 'text-glow-void' : 'opacity-60',
            )}
            style={{ fontSize: xray ? '11px' : '1.5px', ...delayed(REVEAL_AT.tiny) }}
            aria-hidden={!xray}
          >
            {INVOICE_INJECTIONS.tiny}
          </p>
        </Injection>
        <p className="shrink-0 opacity-60">Page 1 of 1</p>
      </div>
    </div>
  )
}

function Injection({
  show,
  label,
  delay,
  reduceMotion,
  className,
  children,
}: {
  show: boolean
  label: string
  delay: number
  reduceMotion: boolean
  className?: string
  children: ReactNode
}) {
  return (
    <div className={cn('relative', className)}>
      <span className="pointer-events-none absolute -top-2 left-0 -translate-y-full" aria-hidden={!show}>
        <motion.span
          initial={false}
          animate={show ? { opacity: 1, y: 0, scale: 1 } : { opacity: 0, y: 4, scale: 0.92 }}
          transition={{ delay: show && !reduceMotion ? delay + 0.2 : 0, duration: reduceMotion ? 0 : 0.3 }}
          className="inline-flex items-center gap-1 rounded-sm bg-void px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-primary-foreground"
        >
          {label}
        </motion.span>
      </span>
      {children}
    </div>
  )
}

function ScanLine() {
  return (
    <motion.div
      aria-hidden="true"
      initial={{ top: '-12%' }}
      animate={{ top: '108%' }}
      transition={{ duration: SCAN_SECONDS, ease: [0.45, 0, 0.2, 1] }}
      className="pointer-events-none absolute inset-x-0 h-20 -translate-y-full border-b-2 border-void bg-gradient-to-b from-transparent to-void/25 shadow-[0_4px_24px_var(--void)]"
    />
  )
}

function XraySwitch({ checked, onChange }: { checked: boolean; onChange: (checked: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cn(
        'flex shrink-0 items-center gap-2 rounded-full border py-1 pl-3 pr-1 text-sm font-medium transition-colors',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
        checked ? 'border-void bg-void text-primary-foreground' : 'border-border bg-card text-foreground hover:bg-secondary',
      )}
    >
      <ScanSearch className="size-4" aria-hidden="true" />
      X-ray
      <span
        className={cn(
          'relative h-5 w-9 rounded-full transition-colors',
          checked ? 'bg-primary-foreground/25' : 'bg-border',
        )}
        aria-hidden="true"
      >
        <span
          className={cn(
            'absolute top-0.5 left-0.5 size-4 rounded-full bg-card shadow-sm transition-transform duration-200',
            checked && 'translate-x-4',
          )}
        />
      </span>
    </button>
  )
}
