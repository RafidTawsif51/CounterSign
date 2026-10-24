import { memo } from "react";
import { Link } from "react-router-dom";
import { CallStrips } from "@/components/call/call-strip";
import { Money } from "@/components/shared/money";
import { useStickToBottom } from "@/hooks/use-stick-to-bottom";
import type { ActivityEntry, ActivityTone } from "@/lib/board";
import type { CallView } from "@/lib/calls";
import { formatClock } from "@/lib/format";
import { cn } from "@/lib/utils";

const mark: Partial<Record<ActivityTone, string>> = { held: "bg-held", blocked: "bg-blocked" };

// What the agent did, oldest first, in plain words. Follows the newest line unless the reader has scrolled up.
export function ActivityRail({ entries, calls, hasRun }: { entries: ActivityEntry[]; calls: CallView[]; hasRun: boolean }) {
  const scroll = useStickToBottom<HTMLOListElement>(entries.length);

  return (
    <aside aria-label="Agent activity" className="flex min-h-0 flex-col border-t border-rule bg-paper lg:w-72 lg:shrink-0 2xl:w-80 lg:border-t-0 lg:border-l">
      <div className="flex h-10 shrink-0 items-center justify-between border-b border-rule px-4">
        <h2 className="text-sm font-medium">Agent activity</h2>
        {entries.length > 0 && <span className="figure text-xs text-ink-muted">{entries.length}</span>}
      </div>
      <CallStrips calls={calls} />
      {entries.length === 0 ? (
        <p className="px-4 py-4 text-sm text-ink-muted">
          {hasRun ? "Reading invoices." : "Every payment the agent makes, holds or blocks is logged here as it happens."}
        </p>
      ) : (
        <ol
          ref={scroll.ref}
          onScroll={scroll.onScroll}
          aria-live="polite"
          className="max-h-96 min-h-0 flex-1 overflow-y-auto py-2 lg:max-h-none"
        >
          {entries.map((entry) => (
            <Entry key={entry.id} entry={entry} />
          ))}
        </ol>
      )}
    </aside>
  );
}

// Entries are rebuilt on every event like the rows; an entry never changes once logged, so its id is enough.
const Entry = memo(EntryView, (a, b) => a.entry.id === b.entry.id && a.entry.text === b.entry.text);

function EntryView({ entry }: { entry: ActivityEntry }) {
  const quiet = entry.tone === "paid";
  const body = (
    <>
      <span className="figure w-15 shrink-0 pt-px text-xs text-ink-muted">{formatClock(entry.at)}</span>
      <span className="min-w-0 flex-1">
        <span className={cn("flex min-w-0 items-start gap-1.5 text-sm", quiet ? "text-ink-muted" : "text-ink")}>
          {mark[entry.tone] && <span aria-hidden className={cn("mt-1.5 size-1.5 shrink-0", mark[entry.tone])} />}
          {quiet ? (
            // A paid line stays on one line: the vendor truncates, the amount never does.
            <>
              <span className="min-w-0 flex-1 truncate">{entry.text}</span>
              {entry.amount != null && <Money amount={entry.amount} className="shrink-0 text-right" />}
            </>
          ) : (
            <span className={cn(entry.tone !== "neutral" && "font-medium")}>
              {entry.text}
              {entry.amount != null && (
                <>
                  {" "}
                  <Money amount={entry.amount} className="whitespace-nowrap" />
                </>
              )}
              {entry.detail && <>: {entry.detail}</>}
            </span>
          )}
        </span>
        {entry.quote && <span className="mt-0.5 block border-l-2 border-rule-strong pl-2 text-sm text-ink-muted">“{entry.quote}”</span>}
      </span>
    </>
  );
  const cls = "flex gap-3 px-4 py-1.5";
  return (
    <li>
      {entry.paymentId ? (
        <Link to={`/payments/${entry.paymentId}`} className={cn(cls, "transition-colors hover:bg-sunken")}>
          {body}
        </Link>
      ) : (
        <div className={cls}>{body}</div>
      )}
    </li>
  );
}
