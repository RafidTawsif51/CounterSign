import { cn } from "@/lib/utils";

// Two offset sheets: a document and the countersignature laid over it.
export function CountersignMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" aria-hidden className={cn("size-5 shrink-0", className)}>
      <rect x="2.5" y="1.5" width="11" height="14" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-ink-muted" />
      <rect x="6.5" y="4.5" width="11" height="14" rx="1.5" className="fill-accent" />
      <path d="M9 14.5h6" stroke="var(--accent-ink)" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}
