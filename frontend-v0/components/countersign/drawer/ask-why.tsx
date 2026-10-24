'use client'

import { useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { ArrowUp, LoaderCircle, Sparkles } from 'lucide-react'
import { toast } from 'sonner'
import { askAboutPayment, type AskResponse, type RiskDecision, type RiskSignal } from '@/lib/api'
import { cn } from '@/lib/utils'
import { DrawerSection } from './drawer-section'

const SUGGESTION: Record<RiskDecision, string> = {
  pay: 'Why did you release this?',
  hold: 'Why did you hold this?',
  block: 'Why did you block this?',
}

interface Exchange {
  question: string
  response?: AskResponse
}

export function AskWhy({
  paymentId,
  runId,
  decision,
  signals,
  onHighlight,
}: {
  paymentId: string
  runId: string
  decision: RiskDecision
  signals: RiskSignal[]
  onHighlight: (evidenceId: string | null) => void
}) {
  const [question, setQuestion] = useState('')
  const [exchanges, setExchanges] = useState<Exchange[]>([])
  const [pending, setPending] = useState(false)
  const reduceMotion = useReducedMotion() ?? false
  const weightByEvidence = new Map(signals.map((s) => [s.evidence_id, s.weight]))
  const detailById = new Map(signals.map((s) => [s.evidence_id, s.detail]))
  const [preview, setPreview] = useState<{ exchangeIndex: number; evidenceId: string } | null>(null)

  async function ask(text: string) {
    const trimmed = text.trim()
    if (!trimmed || pending) return
    setPending(true)
    setQuestion('')
    setExchanges((prev) => [...prev, { question: trimmed }])
    try {
      const response = await askAboutPayment(paymentId, trimmed, runId)
      setExchanges((prev) => prev.map((ex, i) => (i === prev.length - 1 ? { ...ex, response } : ex)))
    } catch {
      setExchanges((prev) => prev.slice(0, -1))
      setQuestion(trimmed)
      toast.error("Couldn't get an answer. Try again.")
    } finally {
      setPending(false)
    }
  }

  function previewSignal(exchangeIndex: number, evidenceId: string | null) {
    setPreview(evidenceId ? { exchangeIndex, evidenceId } : null)
    onHighlight(evidenceId)
  }

  function focusSignal(evidenceId: string) {
    onHighlight(evidenceId)
    document
      .getElementById(`signal-${evidenceId}`)
      ?.scrollIntoView({ block: 'center', behavior: reduceMotion ? 'auto' : 'smooth' })
  }

  return (
    <DrawerSection title="Ask why" id="ask">
      {exchanges.length > 0 && (
        <ol className="flex flex-col gap-4">
          {exchanges.map((exchange, index) => (
            <li key={index} className="flex flex-col gap-3">
              <p className="self-end rounded-lg rounded-br-sm bg-primary px-3 py-2 text-primary-foreground">
                {exchange.question}
              </p>
              {exchange.response ? (
                <motion.div
                  initial={reduceMotion ? false : { opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3 }}
                  className="flex flex-col gap-3 rounded-lg border border-border p-4"
                >
                  <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-primary">
                    <Sparkles className="size-3.5" aria-hidden="true" />
                    Countersign
                  </span>
                  <p className="text-pretty leading-relaxed">{exchange.response.answer}</p>
                  <div className="flex flex-col gap-2">
                    <span className="text-xs text-muted-foreground">
                      Evidence · hover to preview, click to jump to the signal
                    </span>
                    <ul className="flex flex-wrap gap-1.5">
                      {exchange.response.evidence.map((id) => (
                        <li key={id}>
                          <button
                            type="button"
                            aria-describedby={detailById.has(id) ? `ask-preview-${index}` : undefined}
                            onMouseEnter={() => previewSignal(index, id)}
                            onMouseLeave={() => previewSignal(index, null)}
                            onFocus={() => previewSignal(index, id)}
                            onBlur={() => previewSignal(index, null)}
                            onClick={() => focusSignal(id)}
                            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-2 py-1 font-mono text-xs transition-colors hover:border-primary/40 hover:bg-primary/[0.06] hover:text-primary focus-visible:border-primary/40 focus-visible:text-primary"
                          >
                            {id}
                            {weightByEvidence.has(id) && (
                              <span className="font-sans text-muted-foreground">+{weightByEvidence.get(id)}</span>
                            )}
                          </button>
                        </li>
                      ))}
                    </ul>
                    <p
                      id={`ask-preview-${index}`}
                      className="min-h-10 rounded-md border-l-2 border-primary/40 bg-primary/[0.04] px-3 py-2 text-xs leading-relaxed text-muted-foreground"
                    >
                      {preview?.exchangeIndex === index && detailById.has(preview.evidenceId)
                        ? detailById.get(preview.evidenceId)
                        : 'Hover a chip to see the signal it points to.'}
                    </p>
                  </div>
                </motion.div>
              ) : (
                <p className="flex items-center gap-2 text-muted-foreground" role="status">
                  <LoaderCircle className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
                  Checking the evidence
                </p>
              )}
            </li>
          ))}
        </ol>
      )}

      {exchanges.length === 0 && (
        <button
          type="button"
          onClick={() => ask(SUGGESTION[decision])}
          className="self-start rounded-full border border-border px-3 py-1 text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
        >
          {SUGGESTION[decision]}
        </button>
      )}

      <form
        onSubmit={(event) => {
          event.preventDefault()
          ask(question)
        }}
        className="flex items-center gap-2 rounded-lg border border-input bg-card p-1.5 pl-3 focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/15"
      >
        <label htmlFor="ask-why-input" className="sr-only">
          Ask Countersign about this payment
        </label>
        <input
          id="ask-why-input"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && (event.nativeEvent.isComposing || event.keyCode === 229)) event.preventDefault()
          }}
          placeholder={SUGGESTION[decision]}
          autoComplete="off"
          className="min-w-0 flex-1 bg-transparent py-1 outline-none placeholder:text-muted-foreground"
        />
        <button
          type="submit"
          disabled={pending || !question.trim()}
          aria-label="Ask"
          className={cn(
            'flex size-8 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground transition-opacity',
            'disabled:opacity-40',
          )}
        >
          <ArrowUp className="size-4" aria-hidden="true" />
        </button>
      </form>
    </DrawerSection>
  )
}
