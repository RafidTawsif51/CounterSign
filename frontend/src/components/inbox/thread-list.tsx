import { Paperclip, ShieldAlert } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { iconProps } from "@/components/shared/icon";
import type { Detection } from "@/lib/inbox";
import { formatRelativeTime } from "@/lib/format";
import type { InboxThreadSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

// Threads, newest activity first. The attack marker shows only once the run has caught something in the thread.
export function ThreadList({
  threads,
  selected,
  detections,
  fresh,
  onSelect,
}: {
  threads: InboxThreadSummary[] | undefined;
  selected: string | null;
  detections: Map<string, Detection>;
  fresh: Set<string>;
  onSelect: (threadId: string) => void;
}) {
  if (!threads) return <ListSkeleton />;
  if (threads.length === 0) return <p className="px-4 py-6 text-sm text-ink-muted">The AP inbox is empty. Reset the demo to restore this week's emails.</p>;

  return (
    <ul aria-label="Threads">
      {threads.map((t) => {
        const det = detections.get(t.thread_id);
        const active = t.thread_id === selected;
        return (
          <li key={t.thread_id}>
            <button
              type="button"
              onClick={() => onSelect(t.thread_id)}
              aria-current={active ? "true" : undefined}
              className={cn(
                "block w-full border-b border-rule px-4 py-3 text-left transition-colors duration-1000",
                active ? "bg-accent-tint shadow-[inset_2px_0_0_var(--accent)]" : fresh.has(t.thread_id) ? "bg-accent-tint duration-0" : "hover:bg-sunken",
              )}
            >
              <div className="flex items-baseline gap-2">
                <span className={cn("min-w-0 flex-1 truncate font-medium", !t.vendor && "text-ink-muted")}>
                  {t.vendor?.name ?? "No vendor"}
                </span>
                <span className="figure shrink-0 text-xs text-ink-muted">{formatRelativeTime(t.last_received_at)}</span>
              </div>
              <div className="mt-0.5 flex items-center gap-2">
                {/* Subject and preview are untrusted text: plain text only. */}
                <span className="min-w-0 flex-1 truncate text-sm">{t.subject}</span>
                {t.count > 1 && (
                  <span className="shrink-0 text-xs text-ink-muted">
                    <span className="figure">{t.count}</span> messages
                  </span>
                )}
              </div>
              <p className="mt-0.5 line-clamp-2 text-sm text-ink-muted">{t.preview}</p>
              {(det || (t.attachment_count ?? 0) > 0) && (
                <div className="mt-1.5 flex items-center gap-3 text-xs">
                  {det && (
                    <span className="inline-flex items-center gap-1" title={det.reviewed ? `${det.reason}. Reviewed by ${det.reviewed.by}.` : det.reason}>
                      <ShieldAlert {...iconProps} size={14} className="text-blocked-ink" />
                      <span className="font-medium text-blocked-ink">Attack</span>
                      {det.reviewed && <span className="text-ink-muted">reviewed</span>}
                    </span>
                  )}
                  {(t.attachment_count ?? 0) > 0 && (
                    <span className="inline-flex items-center gap-1 text-ink-muted">
                      <Paperclip {...iconProps} size={14} />
                      {t.attachment_count === 1 ? "Invoice PDF" : `${t.attachment_count} PDFs`}
                    </span>
                  )}
                </div>
              )}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function ListSkeleton() {
  return (
    <ul aria-busy aria-label="Loading threads">
      {Array.from({ length: 8 }, (_, i) => (
        <li key={i} className="space-y-2 border-b border-rule px-4 py-3">
          <Skeleton className="h-3.5 w-40" />
          <Skeleton className="h-3 w-56" />
          <Skeleton className="h-3 w-48" />
        </li>
      ))}
    </ul>
  );
}
