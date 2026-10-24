import { useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft } from "lucide-react";
import { ThreadList } from "@/components/inbox/thread-list";
import { ThreadView } from "@/components/inbox/thread-view";
import { useDetections } from "@/components/inbox/use-detections";
import { VendorRail } from "@/components/inbox/vendor-rail";
import { iconProps } from "@/components/shared/icon";
import { InlineError } from "@/components/shared/inline-error";
import { useArrivals } from "@/hooks/use-arrivals";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

// AP inbox: threads | thread | vendor context. Message text is shown as received and never acted on.
// There is no inbox event stream, so the list and the open thread poll; 1.5 s keeps a new message under 2 s.
const POLL_MS = 1500;

export function Inbox() {
  const [params, setParams] = useSearchParams();
  const selected = params.get("thread");
  const vendorParam = params.get("vendor");

  const threads = useQuery({ queryKey: ["inbox", "threads"], queryFn: api.threads, refetchInterval: POLL_MS });
  const thread = useQuery({
    queryKey: ["inbox", "thread", selected],
    queryFn: () => api.thread(selected!),
    enabled: Boolean(selected),
    refetchInterval: POLL_MS,
  });
  const vendorId = thread.data?.vendor?.id ?? null;
  const history = useQuery({
    queryKey: ["vendor-history", vendorId],
    queryFn: () => api.vendorHistory(vendorId!),
    enabled: Boolean(vendorId),
    staleTime: 30_000,
  });
  const detections = useDetections();

  // A thread's activity key changes when a message lands in it, so it highlights even when it was already listed.
  const activity = threads.data?.map((t) => `${t.thread_id}@${t.last_received_at}`) ?? null;
  const freshKeys = useArrivals(activity);
  const fresh = useMemo(() => new Set([...freshKeys].map((k) => k.split("@")[0])), [freshKeys]);

  // New activity in the open thread: fetch it now rather than on its own next poll, so list and thread move together.
  const refetchThread = thread.refetch;
  useEffect(() => {
    if (selected && fresh.has(selected)) void refetchThread();
  }, [fresh, selected, refetchThread]);

  const select = (threadId: string | null) =>
    setParams(
      (p) => {
        p.delete("vendor");
        if (threadId) p.set("thread", threadId);
        else p.delete("thread");
        return p;
      },
      { replace: !threadId },
    );

  // Open something sensible: the vendor's newest thread when arriving from search, else the newest thread on wide screens.
  useEffect(() => {
    const list = threads.data;
    if (!list || selected) return;
    const pick = vendorParam ? list.find((t) => t.vendor?.id === vendorParam) : window.matchMedia("(min-width: 1024px)").matches ? list[0] : null;
    if (pick) setParams((p) => (p.delete("vendor"), p.set("thread", pick.thread_id), p), { replace: true });
  }, [threads.data, selected, vendorParam, setParams]);

  const rail = history.isError ? (
    <InlineError what="The vendor on file" error={history.error} onRetry={() => void history.refetch()} retrying={history.isFetching} className="px-4 py-5" />
  ) : (
    <VendorRail history={history.data} hasVendor={thread.data ? Boolean(thread.data.vendor) : true} />
  );

  return (
    <div className="flex flex-col lg:h-[calc(100dvh-3rem)]">
      <div className="flex min-h-0 flex-1">
        <section
          aria-label="Threads"
          className={cn("min-h-0 w-full overflow-y-auto bg-surface lg:block lg:w-80 lg:shrink-0 lg:border-r lg:border-rule", selected && "hidden")}
        >
          <div className="sticky top-0 z-10 flex h-10 items-center justify-between border-b border-rule bg-surface px-4">
            <h1 className="text-sm font-medium">AP inbox</h1>
            {threads.data && <span className="figure text-xs text-ink-muted">{threads.data.length} threads</span>}
          </div>
          {threads.isError ? (
            <InlineError what="The AP inbox" error={threads.error} onRetry={() => void threads.refetch()} retrying={threads.isFetching} className="px-4 py-6" />
          ) : (
            <ThreadList threads={threads.data} selected={selected} detections={detections} fresh={fresh} onSelect={select} />
          )}
        </section>

        <main className={cn("min-h-0 min-w-0 flex-1 overflow-y-auto", !selected && "hidden lg:block")}>
          {selected ? (
            <>
              <button
                type="button"
                onClick={() => select(null)}
                className="flex h-10 w-full items-center gap-1 border-b border-rule px-4 text-sm text-accent lg:hidden"
              >
                <ChevronLeft {...iconProps} />
                All threads
              </button>
              {thread.isError ? (
                <InlineError what="This thread" error={thread.error} onRetry={() => void thread.refetch()} retrying={thread.isFetching} className="px-6 py-6" />
              ) : (
                <ThreadView thread={thread.data} history={history.data} detection={detections.get(selected)} />
              )}
              {/* Below xl the vendor context follows the thread instead of taking a third column. */}
              <div className="border-t border-rule bg-surface xl:hidden">{rail}</div>
            </>
          ) : (
            <p className="px-6 py-6 text-sm text-ink-muted">Pick a thread to read it. Messages are shown as received and never acted on.</p>
          )}
        </main>

        {selected && (
          <aside aria-label="Vendor on file" className="hidden min-h-0 w-75 shrink-0 overflow-y-auto border-l border-rule bg-surface xl:block">
            {rail}
          </aside>
        )}
      </div>
    </div>
  );
}
