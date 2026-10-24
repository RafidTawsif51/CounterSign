import type { ReactNode } from "react";
import { Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { NumberTicker } from "@/components/board/number-ticker";
import { iconProps } from "@/components/shared/icon";
import { formatDate, formatUSD } from "@/lib/format";
import type { BoardRow } from "@/lib/board";
import type { PaymentStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const count = (n: number) => String(Math.round(n));

export function RunHeader({
  rows,
  invoiceCount,
  startedAt,
  hasRun,
  running,
  starting,
  onStart,
}: {
  rows: BoardRow[];
  invoiceCount: number | null;
  startedAt: string | null;
  hasRun: boolean;
  running: boolean;
  starting: boolean;
  onStart: () => void;
}) {
  const sum = (s: PaymentStatus) => rows.filter((r) => r.status === s).reduce((t, r) => t + r.amount, 0);
  const n = (s: PaymentStatus) => rows.filter((r) => r.status === s).length;
  const decided = rows.filter((r) => r.status !== "pending");
  const total = invoiceCount ?? 40;

  return (
    <div className="border-b border-rule bg-paper">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 px-4 pt-5 pb-4 sm:px-6">
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-3">
          <h1 className="text-lg font-semibold">Thursday payment run</h1>
          <span className="figure text-sm whitespace-nowrap text-ink-muted">{formatDate(startedAt ?? new Date().toISOString())}</span>
        </div>
        {hasRun && (
          <Button variant="primary" onClick={onStart} disabled={starting || running}>
            <Play {...iconProps} />
            {running ? "Run in progress" : "Start payment run"}
          </Button>
        )}
      </div>

      <dl className="grid grid-cols-2 border-t border-rule sm:grid-cols-4">
        <Total label="Paid" status="paid" muted={!hasRun}>
          <NumberTicker value={sum("paid")} format={formatUSD} />
          <Sub>
            <NumberTicker value={n("paid")} format={count} /> payments
          </Sub>
        </Total>
        <Total label="Held" status="held" muted={!hasRun}>
          <NumberTicker value={n("held")} format={count} />
          <Sub>
            <span className="figure">{formatUSD(sum("held"))}</span> waiting on Dev
          </Sub>
        </Total>
        <Total label="Blocked" status="blocked" muted={!hasRun}>
          <NumberTicker value={n("blocked")} format={count} />
          <Sub>
            <span className="figure">{formatUSD(sum("blocked"))}</span> stopped
          </Sub>
        </Total>
        <Total label="Total processed" muted={!hasRun}>
          <span>
            <NumberTicker value={decided.length} format={count} />
            <span className="font-sans text-base text-ink-muted"> of </span>
            <span className="figure">{total}</span>
          </span>
          <Sub>
            <span className="figure">{formatUSD(decided.reduce((t, r) => t + r.amount, 0))}</span> decided
          </Sub>
        </Total>
      </dl>
    </div>
  );
}

const marker: Record<"paid" | "held" | "blocked", string> = { paid: "bg-paid", held: "bg-held", blocked: "bg-blocked" };

function Total({
  label,
  status,
  muted,
  children,
}: {
  label: string;
  status?: "paid" | "held" | "blocked";
  muted: boolean;
  children: [ReactNode, ReactNode];
}) {
  return (
    <div className="min-w-0 border-rule px-4 py-3 not-first:border-l max-sm:nth-3:border-l-0 max-sm:nth-[n+3]:border-t sm:px-6">
      <dt className="flex items-center gap-1.5 text-sm text-ink-muted">
        {status && <span aria-hidden className={cn("size-1.5", marker[status])} />}
        {label}
      </dt>
      <dd className={cn("mt-1 text-lg font-medium [&_.figure]:font-normal", muted && "text-ink-faint")}>
        <span className="figure">{muted ? "–" : children[0]}</span>
      </dd>
      <dd className="mt-0.5 truncate text-sm text-ink-muted">{muted ? "\u00a0" : children[1]}</dd>
    </div>
  );
}

function Sub({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
