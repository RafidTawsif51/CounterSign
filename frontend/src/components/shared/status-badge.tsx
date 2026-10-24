import { Badge } from "@/components/ui/badge";
import type { PaymentStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const labels: Record<PaymentStatus, string> = {
  pending: "Pending",
  paid: "Paid",
  held: "Held",
  blocked: "Blocked",
};

const markColor: Record<PaymentStatus, string> = {
  pending: "border border-pending",
  paid: "bg-paid",
  held: "bg-held",
  blocked: "bg-blocked",
};

// Status colors are for payment state only. The label is always present so state never depends on color.
export function StatusBadge({ status, className }: { status: PaymentStatus; className?: string }) {
  return (
    <Badge variant={status} className={cn("duration-200", className)}>
      <span aria-hidden className={cn("size-1.5", markColor[status])} />
      {labels[status]}
    </Badge>
  );
}
