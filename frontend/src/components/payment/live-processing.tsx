import { useMemo } from "react";
import { SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Money } from "@/components/shared/money";
import { useCurrentRun } from "@/components/shared/run-context";
import { foldBoard, type ActivityTone } from "@/lib/board";
import { formatClock } from "@/lib/format";
import { cn } from "@/lib/utils";

// What the judge sees for the second or so between launching an attack and its payment existing in the database. The steps
// are the same lines the board's activity log shows, straight from the event stream, so nothing here is invented: each
// line appears when the agent has actually done it. Once the payment row exists the drawer swaps to the full detail.

const MARK: Partial<Record<ActivityTone, string>> = { held: "bg-held", blocked: "bg-blocked" };

export function LiveProcessing({ who }: { who: string }) {
  const { pinnedEvents } = useCurrentRun();
  const entries = useMemo(() => foldBoard(pinnedEvents, { attack: true }).activity, [pinnedEvents]);
  const finished = pinnedEvents.some((e) => e.type === "run.completed");

  return (
    <div className="px-5 pt-4" aria-live="polite">
      <SheetTitle>Processing your attack</SheetTitle>
      <SheetDescription className="mt-1">{who}. Each step appears as the agent does it.</SheetDescription>
      <ol className="mt-5 divide-y divide-rule border-y border-rule">
        {entries.map((e) => (
          <li key={e.id} className="flex gap-3 py-2.5">
            <span className="figure w-16 shrink-0 pt-px text-xs text-ink-muted">{formatClock(e.at)}</span>
            <span className="min-w-0 flex-1">
              <span className="flex items-start gap-1.5 text-sm">
                {MARK[e.tone] && <span aria-hidden className={cn("mt-1.5 size-1.5 shrink-0", MARK[e.tone])} />}
                <span className={cn(e.tone !== "neutral" && "font-medium")}>
                  {e.text}
                  {e.amount != null && (
                    <>
                      {" "}
                      <Money amount={e.amount} className="whitespace-nowrap" />
                    </>
                  )}
                  {e.detail && <>: {e.detail}</>}
                </span>
              </span>
              {e.quote && <span className="mt-0.5 block border-l-2 border-rule-strong pl-2 text-sm text-ink-muted">“{e.quote}”</span>}
            </span>
          </li>
        ))}
        {!finished && (
          <li className="flex items-center gap-3 py-2.5 text-sm text-ink-muted">
            <span aria-hidden className="size-2 w-16 shrink-0 bg-transparent" />
            <span className="flex items-center gap-2">
              <span aria-hidden className="size-2 animate-call-pulse bg-accent" />
              Working
            </span>
          </li>
        )}
      </ol>
    </div>
  );
}
