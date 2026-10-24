import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Phone } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { iconProps } from "@/components/shared/icon";
import { Money } from "@/components/shared/money";
import { api } from "@/lib/api";
import { decisionLabel, type BoardRow } from "@/lib/board";
import { formatAccount, formatClock, formatScore } from "@/lib/format";
import type { PaymentStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import { requestedAccount } from "@/lib/verdict";

const MotionRow = motion.create(TableRow);

const statusLabel: Record<PaymentStatus, string> = { pending: "Pending", paid: "Paid", held: "Held", blocked: "Blocked" };
const statusText: Record<PaymentStatus, string> = {
  pending: "text-pending-ink",
  paid: "text-paid-ink",
  held: "text-held-ink",
  blocked: "text-blocked-ink",
};
const statusMark: Record<PaymentStatus, string> = {
  pending: "border border-pending",
  paid: "bg-paid",
  held: "bg-held",
  blocked: "bg-blocked",
};

// Rows that were already there when the board mounted (a replay, or coming back from another page) do not slide in.
const SETTLE_MS = 400;

export function PaymentTable({
  rows,
  loading,
  emptyText,
  skeletonRows = 8,
}: {
  rows: BoardRow[];
  loading: boolean;
  emptyText: string;
  skeletonRows?: number;
}) {
  const mountedAt = useRef(Date.now());

  return (
    <div className="h-full [&>[data-slot=table-container]]:h-full [&>[data-slot=table-container]]:overflow-auto">
      <Table className="min-w-[860px]">
        {/* Sticky as a whole: per-cell sticky backgrounds leave hairline seams at fractional column widths. */}
        <TableHeader className="sticky top-0 z-10 bg-surface shadow-[inset_0_-1px_0_var(--rule)]">
          <TableRow className="hover:bg-transparent">
            <Head>Status</Head>
            <Head>Vendor</Head>
            <Head>Invoice</Head>
            <Head className="text-right">Amount</Head>
            <Head>Destination</Head>
            <Head>Risk</Head>
            {/* Takes whatever width is left and truncates, so the table never scrolls sideways on a laptop. */}
            <Head className="w-full">Decision</Head>
            <Head className="text-right">Time</Head>
          </TableRow>
        </TableHeader>
        <TableBody>
          {loading ? (
            <SkeletonRows count={skeletonRows} />
          ) : rows.length === 0 ? (
            <TableRow className="hover:bg-transparent">
              <TableCell colSpan={8} className="h-16 text-sm text-ink-muted">
                {emptyText}
              </TableCell>
            </TableRow>
          ) : (
            <AnimatePresence initial={false}>
              {rows.map((row) => (
                <PaymentRow key={row.paymentId} row={row} mountedAt={mountedAt.current} />
              ))}
            </AnimatePresence>
          )}
        </TableBody>
      </Table>
    </div>
  );
}

function Head({ className, children }: { className?: string; children: React.ReactNode }) {
  return <TableHead className={className}>{children}</TableHead>;
}

function PaymentRow({ row, mountedAt }: { row: BoardRow; mountedAt: number }) {
  const navigate = useNavigate();
  const [slideIn] = useState(() => Date.now() - mountedAt > SETTLE_MS);
  const flagged = row.status === "held" || row.status === "blocked";
  const open = () => navigate(`/payments/${row.paymentId}`);

  return (
    <MotionRow
      layout="position"
      initial={slideIn ? { opacity: 0, y: -12 } : false}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.15, ease: [0.2, 0, 0, 1] }}
      data-status={row.status}
      className={cn("cursor-pointer", flagged && "row-flag")}
      tabIndex={0}
      aria-label={`${row.vendor}, ${statusLabel[row.status]}. Open payment detail`}
      onClick={open}
      onKeyDown={(e: React.KeyboardEvent) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          open();
        }
      }}
    >
      <TableCell>
        <span className={cn("inline-flex items-center gap-2 text-sm font-medium transition-colors duration-200", statusText[row.status])}>
          <span aria-hidden className={cn("size-1.5 shrink-0 transition-colors duration-200", statusMark[row.status])} />
          {statusLabel[row.status]}
        </span>
      </TableCell>
      <TableCell className="max-w-56 truncate font-medium" title={row.vendor}>
        {row.vendor}
      </TableCell>
      <DetailCells row={row} />
      <TableCell>
        <RiskScore score={row.score} />
      </TableCell>
      <TableCell className="max-w-0">
        <Decision row={row} />
      </TableCell>
      <TableCell className="figure text-right text-sm text-ink-muted">{formatClock(row.updatedAt)}</TableCell>
    </MotionRow>
  );
}

/** Invoice number and destination come from the payment record, not the event stream. */
function DetailCells({ row }: { row: BoardRow }) {
  const { data, isError } = useQuery({
    // Its own key: the drawer's ["payment", id] refetches on every event, and a row only needs the static fields.
    queryKey: ["payment-row", row.paymentId],
    queryFn: () => api.payment(row.paymentId),
    // run.py creates the payment just before risk.scored; asking at invoice.parsed would race it into a 404.
    enabled: row.stage !== "parsed",
    staleTime: Infinity,
    retry: 2,
  });
  const requested = data ? requestedAccount(data) : null;
  const last4 = row.changedTo ?? requested?.account_last4 ?? data?.payment.last_verified_account?.account_last4 ?? null;
  // A row's lookup failing is not worth a retry button in every cell; the drawer has one.
  const missing = isError ? <span title="Could not load from the server">–</span> : <Placeholder w="w-16" />;

  return (
    <>
      <TableCell className="figure text-sm text-ink-muted">{data?.invoice?.number ?? missing}</TableCell>
      <TableCell className="text-right">
        <Money amount={row.amount} />
      </TableCell>
      <TableCell>
        <span className="inline-flex items-center gap-2">
          {last4 ? <span className="figure text-sm">{formatAccount(last4)}</span> : missing}
          {row.changedTo && (
            <Badge variant="neutral" className="h-4 px-1" title="Not the vendor's last verified account">
              changed
            </Badge>
          )}
        </span>
      </TableCell>
    </>
  );
}

function RiskScore({ score }: { score: number | null }) {
  if (score == null) return <span className="figure text-sm text-ink-faint">{formatScore(null)}</span>;
  const high = score >= 60;
  return (
    <span className="inline-flex items-center gap-2.5">
      <span className={cn("figure w-6 text-right text-sm", high ? "text-ink" : "text-ink-muted")}>{formatScore(score)}</span>
      {/* A zero score keeps the track's space but hides it, so a clean run reads quiet. */}
      <span aria-hidden className={cn("h-1 w-10 bg-sunken transition-opacity duration-200", score === 0 && "opacity-0")}>
        <span
          className={cn("block h-full transition-[width] duration-200", high ? "bg-ink" : "bg-ink-faint")}
          style={{ width: `${Math.max(score, 0)}%` }}
        />
      </span>
    </span>
  );
}

function Decision({ row }: { row: BoardRow }) {
  const label = decisionLabel(row);
  if (row.stage === "calling")
    return (
      <span className="inline-flex items-center gap-1.5 text-sm font-medium text-ink">
        <Phone {...iconProps} />
        {label}
      </span>
    );
  const working = row.status === "pending";
  return (
    <span title={label} className={cn("block truncate text-sm", working ? "text-ink-faint" : row.status === "paid" ? "text-ink-muted" : "text-ink")}>
      {label}
    </span>
  );
}

function Placeholder({ w }: { w: string }) {
  return <Skeleton className={cn("inline-block h-3 align-middle", w)} />;
}

function SkeletonRows({ count }: { count: number }) {
  return Array.from({ length: count }, (_, i) => (
    <TableRow key={i} className="hover:bg-transparent">
      {["w-14", "w-36", "w-16", "w-20 ml-auto", "w-16", "w-14", "w-28", "w-14 ml-auto"].map((w, j) => (
        <TableCell key={j}>
          <Skeleton className={cn("h-3", w)} />
        </TableCell>
      ))}
    </TableRow>
  ));
}
