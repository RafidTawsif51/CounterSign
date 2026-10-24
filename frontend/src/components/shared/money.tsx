import { formatUSD } from "@/lib/format";
import { cn } from "@/lib/utils";

// The only way to print a dollar amount. Right-align it in tables.
export function Money({ amount, className }: { amount: number | null | undefined; className?: string }) {
  return <span className={cn("figure", className)}>{formatUSD(amount)}</span>;
}
