import { useMemo, useState } from "react";
import { Outlet } from "react-router-dom";
import { Play } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ActivityRail } from "@/components/board/activity-rail";
import { PaymentTable } from "@/components/board/payment-table";
import { PinnedAttack } from "@/components/board/pinned-attack";
import { RunHeader } from "@/components/board/run-header";
import { iconProps } from "@/components/shared/icon";
import { useCurrentRun } from "@/components/shared/run-context";
import { errorMessage } from "@/lib/api-error";
import { foldBoard, type BoardRow } from "@/lib/board";
import { foldCalls } from "@/lib/calls";

type Filter = "all" | "attention" | "paid" | "blocked";

const FILTERS: { value: Filter; label: string; test: (r: BoardRow) => boolean; empty: string }[] = [
  { value: "all", label: "All", test: () => true, empty: "No invoices read yet." },
  {
    value: "attention",
    label: "Needs attention",
    // Held for Dev, or a verification call still in progress.
    test: (r) => r.status === "held" || r.stage === "calling",
    empty: "Nothing needs attention. Held payments and live verification calls show here.",
  },
  { value: "paid", label: "Paid", test: (r) => r.status === "paid", empty: "No payments released yet." },
  { value: "blocked", label: "Blocked", test: (r) => r.status === "blocked", empty: "No payments blocked in this run." },
];

export function Board() {
  const { runId, events, summary, startRun, runFailed, pinned, pinnedEvents, unpin } = useCurrentRun();
  const [starting, setStarting] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const board = useMemo(() => foldBoard(events), [events]);
  const attack = useMemo(() => foldBoard(pinnedEvents, { attack: true }), [pinnedEvents]);
  const calls = useMemo(() => [...foldCalls(pinnedEvents), ...foldCalls(events)], [events, pinnedEvents]);
  // The pinned attack's lines join the run's, in time order, so the rail tells one story.
  const activity = useMemo(
    () => (attack.activity.length ? [...board.activity, ...attack.activity].sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : 0)) : board.activity),
    [board.activity, attack.activity],
  );
  const running = Boolean(runId) && !summary.completed && !runFailed;
  const loading = Boolean(runId) && !runFailed && board.rows.length === 0;

  async function start() {
    setStarting(true);
    try {
      await startRun();
      setFilter("all");
    } catch (err) {
      toast.error("Payment run not started", { description: errorMessage(err) });
    } finally {
      setStarting(false);
    }
  }

  const active = FILTERS.find((f) => f.value === filter)!;
  const rows = board.rows.filter(active.test);

  return (
    <div className="flex flex-col lg:h-[calc(100dvh-3rem)]">
      <RunHeader
        rows={board.rows}
        invoiceCount={board.invoiceCount}
        startedAt={board.startedAt}
        hasRun={Boolean(runId)}
        running={running}
        starting={starting}
        onStart={start}
      />

      {runId || pinned ? (
        <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
          <section aria-label="Payments" className="flex min-h-0 min-w-0 flex-1 flex-col bg-surface">
            {pinned && <PinnedAttack pinned={pinned} events={pinnedEvents} rows={attack.rows} onUnpin={unpin} />}
            {runId ? (
              <>
                <Tabs value={filter} onValueChange={(v) => setFilter(v as Filter)}>
                  <TabsList className="overflow-x-auto px-4 sm:px-6">
                    {FILTERS.map((f) => (
                      <TabsTrigger key={f.value} value={f.value}>
                        {f.label}
                        <span className="figure text-sm font-normal text-ink-muted">{board.rows.filter(f.test).length}</span>
                      </TabsTrigger>
                    ))}
                  </TabsList>
                </Tabs>
                <div className="min-h-0 flex-1">
                  <PaymentTable rows={rows} loading={loading} emptyText={active.empty} />
                </div>
              </>
            ) : (
              <StartPrompt starting={starting} onStart={start} />
            )}
          </section>
          <ActivityRail entries={activity} calls={calls} hasRun />
        </div>
      ) : (
        <StartPrompt starting={starting} onStart={start} />
      )}

      {/* Payment detail drawer renders here at /payments/:paymentId. */}
      <Outlet />
    </div>
  );
}

function StartPrompt({ starting, onStart }: { starting: boolean; onStart: () => void }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-3 px-4 py-8 sm:px-6">
      <p className="text-base">This week's 40 open invoices for Ridgeline Builders are ready to pay.</p>
      <Button variant="primary" onClick={onStart} disabled={starting}>
        <Play {...iconProps} />
        Start payment run
      </Button>
    </div>
  );
}
