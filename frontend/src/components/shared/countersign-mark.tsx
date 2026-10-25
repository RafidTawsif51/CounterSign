import { cn } from "@/lib/utils";

// A signature that ends in a check, written on a signature line: the payment, countersigned. Ink-blue tile, accent-ink stroke,
// so it reads in both themes. Legible down to 16px.
export function CountersignMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={cn("size-5 shrink-0", className)}>
      <rect x="1" y="1" width="22" height="22" rx="5.5" className="fill-accent" />
      <path
        d="M5.5 15.2c1.4-1.6 2.3-.2 3.2.9 1.6-3.1 3.6-6.3 6.3-8.6 1.1-.9 2.6-.6 2.4.7-.2 1.4-2 2.4-3.4 2.1"
        fill="none"
        stroke="var(--accent-ink)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M5.5 19h13" stroke="var(--accent-ink)" strokeOpacity="0.45" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}
