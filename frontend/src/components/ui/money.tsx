import { cn } from "@/lib/utils";

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2 });

// All money renders in Plex Mono with tabular figures. Right-align it in tables.
export function Money({ amount, className }: { amount: number; className?: string }) {
  return <span className={cn("figure", className)}>{usd.format(amount)}</span>;
}

export function formatUsd(amount: number) {
  return usd.format(amount);
}
