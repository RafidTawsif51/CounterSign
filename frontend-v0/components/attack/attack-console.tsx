'use client'

import { useEffect, useRef, useState } from 'react'
import useSWR from 'swr'
import { useReducedMotion } from 'framer-motion'
import { getInboxThreads, SUMMIT_THREAD_ID, type AttackCardId } from '@/lib/api'
import { ATTACK_CARDS } from '@/lib/attack-cards'
import { cn } from '@/lib/utils'
import { AttackCardButton } from './attack-card'
import { EmailThread } from './email-thread'
import { PoisonedInvoice } from './poisoned-invoice'
import { ReplyComposer } from './reply-composer'

export function AttackConsole() {
  const [selectedId, setSelectedId] = useState<AttackCardId | null>(null)
  const [attackerName, setAttackerName] = useState('')
  const workspaceRef = useRef<HTMLElement>(null)
  const reduceMotion = useReducedMotion() ?? false
  const { data: threads, error, isLoading } = useSWR('inbox-threads', getInboxThreads)

  const card = ATTACK_CARDS.find((item) => item.id === selectedId) ?? null
  const thread = threads?.find((item) => item.id === SUMMIT_THREAD_ID)
  const isPoisoned = card?.id === 'poisoned_invoice'

  useEffect(() => {
    if (!selectedId) return
    workspaceRef.current?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' })
  }, [selectedId, reduceMotion])

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-16 px-6 pb-24 pt-12">
      <section aria-labelledby="attack-title" className="flex flex-col gap-10">
        <div className="flex max-w-2xl flex-col gap-3">
          <p className="flex items-center gap-2 text-sm font-medium text-void">
            <span className="size-1.5 rounded-full bg-void" aria-hidden="true" />
            Attack console
          </p>
          <h1 id="attack-title" className="text-balance text-3xl font-semibold tracking-tight md:text-4xl">
            Your turn to be the scammer.
          </h1>
          <p className="text-pretty leading-relaxed text-muted-foreground">
            {
              "Pick a play and write the email. It lands in Ridgeline Builders' real Summit Concrete invoice thread, and Thursday's payment run decides what to do with it, live."
            }
          </p>
        </div>

        <div className="flex flex-col gap-4">
          <h2 className="text-sm font-medium text-muted-foreground">Step 1 of 2 · Pick a card</h2>
          <div role="group" aria-label="Attack cards" className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {ATTACK_CARDS.map((item) => (
              <AttackCardButton
                key={item.id}
                card={item}
                selected={item.id === selectedId}
                dimmed={selectedId !== null && item.id !== selectedId}
                onSelect={() => setSelectedId(item.id)}
              />
            ))}
          </div>
        </div>
      </section>

      {card && (
        <section ref={workspaceRef} aria-labelledby="workspace-title" className="flex scroll-mt-24 flex-col gap-6">
          <div className="flex max-w-2xl flex-col gap-2">
            <p className="text-sm font-medium text-muted-foreground">Step 2 of 2 · Write the email</p>
            <h2 id="workspace-title" className="text-balance text-2xl font-semibold tracking-tight">
              Reply in the Summit Concrete thread
            </h2>
            <p className="text-pretty leading-relaxed text-muted-foreground">
              {isPoisoned
                ? 'Your reply carries the poisoned invoice. Flip on X-ray to see what the AI will read that a person never would.'
                : 'This is the invoice thread Countersign reads on Thursday. Your reply lands at the bottom. Edit anything you like.'}
            </p>
          </div>

          <div
            className={cn(
              'grid gap-6',
              isPoisoned ? 'lg:grid-cols-[minmax(0,1fr)_400px] lg:items-start' : 'max-w-4xl',
            )}
          >
            <div className="overflow-hidden rounded-xl border border-border bg-card">
              {isLoading && <p className="px-5 py-16 text-center text-muted-foreground">Loading the inbox</p>}
              {(error || (threads && !thread)) && (
                <p role="alert" className="px-5 py-16 text-center text-blocked">
                  {"Couldn't load the Summit Concrete thread. Refresh to try again."}
                </p>
              )}
              {thread && (
                <>
                  <EmailThread thread={thread} />
                  <ReplyComposer
                    key={card.id}
                    card={card}
                    thread={thread}
                    attackerName={attackerName}
                    onAttackerNameChange={setAttackerName}
                  />
                </>
              )}
            </div>

            {isPoisoned && (
              <div className="lg:sticky lg:top-20">
                <PoisonedInvoice />
              </div>
            )}
          </div>
        </section>
      )}
    </main>
  )
}
