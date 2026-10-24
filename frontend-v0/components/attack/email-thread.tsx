'use client'

import { useState } from 'react'
import { ChevronDown, Paperclip } from 'lucide-react'
import type { InboxMessage, InboxThread } from '@/lib/api'
import { cn } from '@/lib/utils'

const dateFormat = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
  timeZone: 'America/Denver',
})

function initials(name: string) {
  return name
    .split(' ')
    .map((part) => part[0])
    .slice(0, 2)
    .join('')
}

export function EmailThread({ thread }: { thread: InboxThread }) {
  const lastId = thread.messages[thread.messages.length - 1]?.id
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(lastId ? [lastId] : []))

  const toggle = (id: string) =>
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  return (
    <div className="flex flex-col">
      <div className="flex flex-col gap-3 border-b border-border px-5 py-4">
        <div className="flex flex-wrap items-center gap-1.5">
          {thread.labels.map((label) => (
            <span
              key={label}
              className="rounded-sm bg-secondary px-1.5 py-0.5 text-[11px] font-medium text-secondary-foreground"
            >
              {label}
            </span>
          ))}
        </div>
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h3 className="text-pretty text-lg font-semibold tracking-tight">{thread.subject}</h3>
          <p className="text-sm text-muted-foreground">{thread.messages.length} messages</p>
        </div>
      </div>

      <ol className="flex flex-col divide-y divide-border">
        {thread.messages.map((message) => (
          <li key={message.id}>
            <Message message={message} open={expanded.has(message.id)} onToggle={() => toggle(message.id)} />
          </li>
        ))}
      </ol>
    </div>
  )
}

function Message({ message, open, onToggle }: { message: InboxMessage; open: boolean; onToggle: () => void }) {
  const isInternal = message.from_addr.endsWith('@ridgelinebuilders.com')

  return (
    <article className="flex gap-3 px-5 py-4">
      <span
        className={cn(
          'flex size-9 shrink-0 items-center justify-center rounded-full text-xs font-semibold',
          isInternal ? 'bg-primary text-primary-foreground' : 'bg-secondary text-secondary-foreground',
        )}
        aria-hidden="true"
      >
        {initials(message.from_name)}
      </span>

      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          className="flex w-full items-start justify-between gap-3 rounded-sm text-left focus-visible:outline-2 focus-visible:outline-offset-2"
        >
          <span className="flex min-w-0 flex-col">
            <span className="flex flex-wrap items-baseline gap-x-1.5">
              <span className="text-sm font-semibold">{message.from_name}</span>
              <span className="truncate text-sm text-muted-foreground">{`<${message.from_addr}>`}</span>
            </span>
            {open ? (
              <span className="text-xs text-muted-foreground">to {message.to_name}</span>
            ) : (
              <span className="truncate text-sm text-muted-foreground">{message.body.split('\n').find(Boolean)}</span>
            )}
          </span>
          <span className="flex shrink-0 items-center gap-1.5 text-xs tabular-nums text-muted-foreground">
            <time dateTime={message.sent_at}>{dateFormat.format(new Date(message.sent_at))}</time>
            <ChevronDown
              className={cn('size-3.5 transition-transform', open && 'rotate-180')}
              aria-hidden="true"
            />
          </span>
        </button>

        {open && (
          <>
            <p className="whitespace-pre-line text-sm leading-relaxed text-foreground">{message.body}</p>
            {message.attachments.length > 0 && (
              <ul className="flex flex-wrap gap-2 pt-1">
                {message.attachments.map((file) => (
                  <li
                    key={file.filename}
                    className="flex items-center gap-2 rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs"
                  >
                    <Paperclip className="size-3.5 text-muted-foreground" aria-hidden="true" />
                    <span className="font-medium">{file.filename}</span>
                    <span className="text-muted-foreground">{file.size_kb} KB</span>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </article>
  )
}
