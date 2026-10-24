import { cn } from "@/lib/utils";

export type PaymentStatus = "pending" | "paid" | "held" | "blocked";

const styles: Record<PaymentStatus, { label: string; className: string }> = {
  pending: { label: "Pending", className: "bg-pending-tint text-pending-ink [--mark:var(--status-pending)]" },
  paid: { label: "Paid", className: "bg-paid-tint text-paid-ink [--mark:var(--status-paid)]" },
  held: { label: "Held", className: "bg-held-tint text-held-ink [--mark:var(--status-held)]" },
  blocked: { label: "Blocked", className: "bg-blocked-tint text-blocked-ink [--mark:var(--status-blocked)]" },
};

// Status colors are for payment state only. The label is always present so state never depends on color.
export function StatusBadge({ status, className }: { status: PaymentStatus; className?: string }) {
  const s = styles[status];
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center gap-1.5 rounded-sm px-1.5 text-xs font-medium transition-colors duration-200 ease-out",
        s.className,
        className,
      )}
    >
      <span
        aria-hidden
        className={cn("size-1.5 bg-(--mark)", status === "pending" && "border border-(--mark) bg-transparent")}
      />
      {s.label}
    </span>
  );
}
