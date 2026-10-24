import { memo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
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

// Which columns a narrow table keeps: on a phone the ledger is status, vendor and amount; the rest lives in the drawer.
const wide = "hidden @2xl:table-cell";
const amountEdge = "@max-2xl:pr-4";

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
    // A container, not the viewport, decides which columns fit: the activity rail and sidebar take a varying share.
    <div className="@container h-full [&>[data-slot=table-container]]:h-full [&>[data-slot=table-container]]:overflow-auto">
      <Table className="@2xl:min-w-[720px]">
        {/* Sticky as a whole: per-cell sticky backgrounds leave hairline seams at fractional column widths. */}
        <TableHeader className="sticky top-0 z-10 bg-surface shadow-[inset_0_-1px_0_var(--rule)]">
          <TableRow className="hover:bg-transparent">
            <Head>Status</Head>
            <Head>Vendor</Head>
            <Head className={wide}>Invoice</Head>
            <Head className={cn("text-right", amountEdge)}>Amount</Head>
            <Head className={wide}>Destination</Head>
            <Head className={wide}>Risk</Head>
            <Head className="hidden text-right @4xl:table-cell">Time</Head>
            {/* Last and takes whatever width is left: on a laptop it truncates so the table never scrolls sideways, and on
                a wide screen the reason fills it instead of a gap stranding the time at the far edge. */}
            <Head className={cn("w-full", wide)}>Decision</Head>
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
            // Memoized rows do not re-render when a new one lands above them; the group still has them measure and slide.
            <LayoutGroup>
              <AnimatePresence initial={false}>
                {rows.map((row) => (
                  <PaymentRow key={row.paymentId} row={row} mountedAt={mountedAt.current} />
                ))}
              </AnimatePresence>
            </LayoutGroup>
          )}
        </TableBody>
      </Table>
    </div>
  );
}

function Head({ className, children }: { className?: string; children: React.ReactNode }) {
  return <TableHead className={className}>{children}</TableHead>;
}

// foldBoard rebuilds every row object on each event, so compare what a row shows: with 40 rows streaming, an event
// re-renders the one row it touched instead of all of them.
const sameRow = (a: BoardRow, b: BoardRow) =>
  a.paymentId === b.paymentId &&
  a.status === b.status &&
  a.stage === b.stage &&
  a.score === b.score &&
  a.decision === b.decision &&
  a.changedTo === b.changedTo &&
  a.technique === b.technique &&
  a.callOutcome === b.callOutcome &&
  a.reason === b.reason &&
  a.reviewed?.decision === b.reviewed?.decision &&
  a.reviewed?.by === b.reviewed?.by &&
  a.updatedAt === b.updatedAt &&
  a.vendor === b.vendor &&
  a.amount === b.amount;

const PaymentRow = memo(PaymentRowView, (a, b) => a.mountedAt === b.mountedAt && sameRow(a.row, b.row));

function PaymentRowView({ row, mountedAt }: { row: BoardRow; mountedAt: number }) {
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
      data-payment-id={row.paymentId}
      // Inset: an outset ring on a row is clipped by the table's scroll container on three sides.
      className={cn("cursor-pointer focus-visible:-outline-offset-2", flagged && "row-flag")}
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
      <TableCell className="max-w-32 truncate font-medium @2xl:max-w-44 @5xl:max-w-56 @7xl:max-w-72" title={row.vendor}>
        {row.vendor}
      </TableCell>
      <DetailCells row={row} />
      <TableCell className={wide}>
        <RiskScore score={row.score} />
      </TableCell>
      <TableCell className="figure hidden text-right text-sm text-ink-muted @4xl:table-cell">{formatClock(row.updatedAt)}</TableCell>
      <TableCell className={cn("max-w-0", wide)}>
        <Decision row={row} />
      </TableCell>
    </MotionRow>
  );
}

/** Invoice number and destination come from the payment record, not the event stream. */
function DetailCells({ row }: { row: BoardRow }) {
  const { data, isError } = useQuery({
    // Its own key: the drawer's ["payment", id] refetches on every event, and a row only needs the static fields.
    // A review changes where the money went, so it is part of the key.
    queryKey: ["payment-row", row.paymentId, row.reviewed?.decision ?? null],
    queryFn: () => api.payment(row.paymentId),
    // run.py creates the payment just before risk.scored; asking at invoice.parsed would race it into a 404.
    enabled: row.stage !== "parsed",
    staleTime: Infinity,
    retry: 2,
  });
  const requested = data ? requestedAccount(data) : null;
  // Once paid, show where the money went; before that, the account the invoice asks for.
  const paidTo = row.status === "paid" ? data?.payment.destination?.account_last4 : null;
  const last4 = paidTo ?? row.changedTo ?? requested?.account_last4 ?? data?.payment.last_verified_account?.account_last4 ?? null;
  // A row's lookup failing is not worth a retry button in every cell; the drawer has one.
  const missing = isError ? <span title="Could not load from the server">–</span> : <Placeholder w="w-16" />;

  return (
    <>
      <TableCell className={cn("figure text-sm text-ink-muted", wide)}>{data?.invoice?.number ?? missing}</TableCell>
      <TableCell className={cn("text-right", amountEdge)}>
        <Money amount={row.amount} />
      </TableCell>
      <TableCell className={wide}>
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
      <span aria-hidden className={cn("hidden h-1 w-10 bg-sunken transition-opacity duration-200 @4xl:block", score === 0 && "opacity-0")}>
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
  const calling = row.stage === "calling";
  const quiet = row.status === "pending" || row.status === "paid";
  return (
    <span
      title={row.reason ? `${label}: ${row.reason}` : label}
      className={cn("flex min-w-0 items-center gap-1.5 text-sm", calling ? "font-medium text-ink" : quiet ? "text-ink-muted" : "text-ink")}
    >
      {calling && <Phone {...iconProps} className="shrink-0" />}
      <span className="min-w-0 truncate @5xl:shrink-0">{label}</span>
      {/* The evidence in a few words, on a wide table only; the full reasoning lives in the drawer. */}
      {row.reason && <span className="ml-1.5 hidden min-w-0 shrink-[100] truncate font-normal text-ink-muted @5xl:inline">{row.reason}</span>}
    </span>
  );
}

function Placeholder({ w }: { w: string }) {
  return <Skeleton className={cn("inline-block h-3 align-middle", w)} />;
}

function SkeletonRows({ count }: { count: number }) {
  return Array.from({ length: count }, (_, i) => (
    <TableRow key={i} className="hover:bg-transparent">
      {["w-14", "w-36", "w-16", "w-20 ml-auto", "w-16", "w-14", "w-14 ml-auto", "w-28"].map((w, j) => (
        <TableCell key={j} className={cn([2, 4, 5, 7].includes(j) && wide, j === 3 && amountEdge, j === 6 && "hidden @4xl:table-cell")}>
          <Skeleton className={cn("h-3", w)} />
        </TableCell>
      ))}
    </TableRow>
  ));
}
