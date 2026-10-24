'use client'

import { useId, useState, type FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import { LoaderCircle, Paperclip, Reply, Send } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { sendAttack, type InboxThread } from '@/lib/api'
import { POISONED_ATTACHMENT, poisonedInvoiceText, type AttackCard } from '@/lib/attack-cards'
import { cn } from '@/lib/utils'

interface ReplyComposerProps {
  card: AttackCard
  thread: InboxThread
  attackerName: string
  onAttackerNameChange: (name: string) => void
}

const fieldRow = 'flex items-center gap-3 border-b border-border px-5'
const fieldLabel = 'w-16 shrink-0 text-sm text-muted-foreground'

export function ReplyComposer({ card, thread, attackerName, onAttackerNameChange }: ReplyComposerProps) {
  const router = useRouter()
  const id = useId()
  const [fromAddr, setFromAddr] = useState(card.fromAddr)
  const [body, setBody] = useState(card.body)
  const [sending, setSending] = useState(false)
  const hasAttachment = card.id === 'poisoned_invoice'

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!attackerName.trim() || !body.trim() || !fromAddr.trim()) return

    setSending(true)
    try {
      const result = await sendAttack({
        attacker_name: attackerName.trim(),
        card: card.id,
        payload: {
          thread_id: thread.id,
          from_addr: fromAddr.trim(),
          body: hasAttachment ? `${body.trim()}\n\n${poisonedInvoiceText()}` : body.trim(),
        },
      })
      toast('Attack sent', { description: 'Starting the payment run with your email in the inbox.' })
      router.push(`/run?run=${encodeURIComponent(result.run_id)}&autostart=1`)
    } catch {
      toast.error("Couldn't send the attack. Try again.")
      setSending(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col border-t-4 border-double border-border" aria-label="Your reply">
      <div className="flex items-center justify-between gap-3 px-5 py-3">
        <p className="flex items-center gap-2 text-sm font-medium">
          <Reply className="size-4 text-muted-foreground" aria-hidden="true" />
          Your reply
        </p>
        <span className="rounded-sm bg-void/10 px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider text-void">
          {card.title}
        </span>
      </div>

      <div className={cn(fieldRow, 'border-t')}>
        <label htmlFor={`${id}-from`} className={fieldLabel}>
          From
        </label>
        <input
          id={`${id}-from`}
          type="email"
          required
          value={fromAddr}
          onChange={(event) => setFromAddr(event.target.value)}
          placeholder="anyone@anydomain.com"
          autoComplete="off"
          spellCheck={false}
          className="h-11 min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground/70"
        />
      </div>
      <div className={fieldRow}>
        <span className={fieldLabel}>To</span>
        <span className="flex h-11 items-center truncate text-sm">ap@ridgelinebuilders.com</span>
      </div>
      <div className={fieldRow}>
        <span className={fieldLabel}>Subject</span>
        <span className="flex h-11 items-center truncate text-sm">Re: {thread.subject}</span>
      </div>

      <label htmlFor={`${id}-body`} className="sr-only">
        Message
      </label>
      <textarea
        id={`${id}-body`}
        required
        value={body}
        onChange={(event) => setBody(event.target.value)}
        placeholder="Write the email you think gets Summit Concrete's $48,720 sent somewhere else."
        rows={12}
        className="min-h-64 resize-y bg-transparent px-5 py-4 text-sm leading-relaxed outline-none placeholder:text-muted-foreground/70 focus-visible:bg-surface/50"
      />

      {hasAttachment && (
        <div className="px-5 pb-4">
          <span className="inline-flex items-center gap-2 rounded-md border border-void/30 bg-void/5 px-2.5 py-1.5 text-xs">
            <Paperclip className="size-3.5 text-void" aria-hidden="true" />
            <span className="font-medium">{POISONED_ATTACHMENT.filename}</span>
            <span className="text-muted-foreground">{POISONED_ATTACHMENT.size_kb} KB</span>
          </span>
        </div>
      )}

      <div className="flex flex-col gap-4 border-t border-border bg-surface px-5 py-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-col gap-1.5">
          <label htmlFor={`${id}-name`} className="text-sm font-medium">
            Your name
          </label>
          <input
            id={`${id}-name`}
            required
            maxLength={40}
            value={attackerName}
            onChange={(event) => onAttackerNameChange(event.target.value)}
            placeholder="e.g. Jordan K."
            autoComplete="nickname"
            aria-describedby={`${id}-name-hint`}
            className="h-10 w-full rounded-md border border-input bg-card px-3 text-sm outline-none placeholder:text-muted-foreground/70 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/20 sm:w-64"
          />
          <p id={`${id}-name-hint`} className="text-xs text-muted-foreground">
            Shown on the leaderboard.
          </p>
        </div>

        <Button type="submit" disabled={sending} className="h-10 gap-2 bg-void px-5 text-primary-foreground hover:bg-void/90">
          {sending ? (
            <>
              <LoaderCircle className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
              Sending
            </>
          ) : (
            <>
              <Send className="size-4" aria-hidden="true" />
              Send attack
            </>
          )}
        </Button>
      </div>
    </form>
  )
}
