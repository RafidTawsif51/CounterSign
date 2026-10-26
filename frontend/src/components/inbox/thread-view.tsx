import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, FileText, ShieldAlert } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { InvoicePreview } from "@/components/inbox/invoice-preview";
import { iconProps } from "@/components/shared/icon";
import { Money } from "@/components/shared/money";
import { useArrivals } from "@/hooks/use-arrivals";
import { api, invoicePdfUrl } from "@/lib/api";
import { isMock } from "@/lib/data-mode";
import type { DiffPart } from "@/lib/domain-diff";
import { formatClock, formatDate, formatRelativeTime } from "@/lib/format";
import { bodyText, headerFlags, type Detection, type HeaderFlag } from "@/lib/inbox";
import type { HistoryInvoice, InboxMessage, InboxThreadDetail, VendorHistory } from "@/lib/types";
import { cn } from "@/lib/utils";

export function ThreadView({
  thread,
  history,
  detection,
}: {
  thread: InboxThreadDetail | undefined;
  history: VendorHistory | undefined;
  detection: Detection | undefined;
}) {
  const fresh = useArrivals(thread ? thread.messages.map((m) => m.id) : null, thread?.thread_id);
  const end = useRef<HTMLDivElement>(null);

  // A message that arrives while the thread is open is brought into view.
  useEffect(() => {
    if (fresh.size) end.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [fresh]);

  if (!thread) return <ViewSkeleton />;
  const vendorDomain = history?.vendor.email_domain ?? null;

  return (
    <article aria-label={thread.subject} className="px-4 py-5 sm:px-6">
      <h2 className="text-lg font-semibold">{thread.subject}</h2>
      <p className="mt-0.5 text-sm text-ink-muted">
        {thread.vendor ? thread.vendor.name : "No vendor: this thread did not start in a vendor thread"}
        {vendorDomain && (
          <>
            , known domain <span className="figure text-ink">{vendorDomain}</span>
          </>
        )}
      </p>
      <ol className="mt-5 space-y-3">
        {thread.messages.map((m) => (
          <MessageItem
            key={m.id}
            msg={m}
            vendorDomain={vendorDomain}
            invoices={history?.invoices ?? []}
            history={history}
            detection={detection?.messageId === m.id ? detection : undefined}
            fresh={fresh.has(m.id)}
          />
        ))}
      </ol>
      <div ref={end} />
    </article>
  );
}

function MessageItem({
  msg,
  vendorDomain,
  invoices,
  history,
  detection,
  fresh,
}: {
  msg: InboxMessage;
  vendorDomain: string | null;
  invoices: HistoryInvoice[];
  history: VendorHistory | undefined;
  detection: Detection | undefined;
  fresh: boolean;
}) {
  const [open, setOpen] = useState(false);
  const flags = headerFlags(msg, vendorDomain);
  const fromLook = flags.find((f) => f.field === "from" && f.diff);
  // A Reply-To on the same lookalike domain as the sender keeps its marked characters but does not repeat the reason.
  const flagFor = (field: HeaderFlag["field"]) =>
    flags.filter((f) => f.field === field && !(field === "reply_to" && f.diff && fromLook && domainKey(f) === domainKey(fromLook)));
  const marksFor = (field: HeaderFlag["field"]) => flags.filter((f) => f.field === field && f.diff);

  return (
    <li
      className={cn(
        "rounded-lg border border-rule bg-surface transition-colors duration-1000",
        fresh && "bg-accent-tint duration-0",
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-start gap-2 px-4 py-2.5 text-left"
      >
        <ChevronRight {...iconProps} className={cn("mt-0.5 shrink-0 text-ink-muted transition-transform", open && "rotate-90")} />
        <span className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-4 gap-y-0.5 text-sm">
          <span className="min-w-0">
            <span className="text-ink-muted">From </span>
            <Address address={msg.from_addr} flags={flagFor("from")} marks={marksFor("from")} />
          </span>
          {msg.reply_to && (
            <span className="min-w-0">
              <span className="text-ink-muted">Reply-To </span>
              <Address address={msg.reply_to} flags={flagFor("reply_to")} marks={marksFor("reply_to")} />
            </span>
          )}
        </span>
        <span className="figure shrink-0 pt-px text-xs text-ink-muted" title={msg.received_at}>
          {formatRelativeTime(msg.received_at)}
        </span>
      </button>

      {open && (
        <dl className="mx-4 mb-2 grid grid-cols-[88px_1fr] gap-x-3 gap-y-1 border-t border-rule pt-2 text-sm">
          <dt className="text-ink-muted">From</dt>
          <dd className="figure break-all">{msg.from_addr}</dd>
          {msg.reply_to && (
            <>
              <dt className="text-ink-muted">Reply-To</dt>
              <dd className="figure break-all">{msg.reply_to}</dd>
            </>
          )}
          <dt className="text-ink-muted">Subject</dt>
          <dd>{msg.subject}</dd>
          <dt className="text-ink-muted">Received</dt>
          <dd className="figure">
            {formatDate(msg.received_at)} {formatClock(msg.received_at)}
          </dd>
          <dt className="text-ink-muted">Message</dt>
          <dd className="figure text-ink-muted">{msg.id}</dd>
          {flags
            .filter((f, i, all) => f.diff && all.findIndex((g) => g.diff && domainKey(g) === domainKey(f)) === i)
            .map((f, i) => (
              <LookalikeRow key={i} flag={f} />
            ))}
        </dl>
      )}

      {detection && (
        <p className="mx-4 flex flex-wrap items-center gap-x-2 border-t border-rule py-2 text-sm text-blocked-ink">
          <ShieldAlert {...iconProps} />
          <span className="font-medium">{detectionLabel(detection)}:</span>
          <span>{detection.reason}.</span>
          <Link to={`/app/payments/${detection.paymentId}`} className="text-accent underline-offset-4 hover:underline">
            Open payment
          </Link>
        </p>
      )}

      {/* Untrusted text: shown as received, never rendered as HTML, never acted on. */}
      <div className="border-t border-rule px-4 py-3 text-base whitespace-pre-wrap">{bodyText(msg)}</div>

      {msg.invoices.length > 0 && (
        <ul className="border-t border-rule px-2 py-1.5">
          {msg.invoices.map((ref) => (
            <AttachmentRow key={ref.id} invoiceId={ref.id} paymentId={ref.payment_id} hasPdf={ref.has_pdf} invoice={invoices.find((i) => i.id === ref.id)} history={history} />
          ))}
        </ul>
      )}
    </li>
  );
}

/** An address with its lookalike domain's differing characters marked, plus the short reason inline. */
function Address({ address, flags, marks }: { address: string; flags: HeaderFlag[]; marks: HeaderFlag[] }) {
  const look = marks[0];
  const [local] = address.split("@");
  return (
    <>
      <span className={cn("figure break-all", (flags.length > 0 || look) && "text-blocked-ink")}>
        {look ? (
          <>
            {local}@
            <Parts parts={look.diff!.fake} />
          </>
        ) : (
          address
        )}
      </span>
      {flags.map((f, i) => (
        <span key={i} className="ml-2 text-xs font-medium text-blocked-ink">
          {f.reason}
        </span>
      ))}
    </>
  );
}

/** What happened to the caught payment, in the order it happened. */
function detectionLabel(d: Detection) {
  if (d.reviewed?.decision === "approved") return `Held, then approved by ${d.reviewed.by} to the verified account`;
  if (d.reviewed?.decision === "rejected") return `Held, then rejected by ${d.reviewed.by}`;
  return d.status === "blocked" ? "Payment blocked" : "Payment held";
}

const domainKey = (f: HeaderFlag) => f.diff!.fake.map((p) => p.text).join("");

function Parts({ parts }: { parts: DiffPart[] }) {
  return parts.map((p, i) =>
    p.changed ? (
      <mark key={i} className="rounded-sm bg-blocked-tint text-blocked-ink underline decoration-blocked decoration-2 underline-offset-2">
        {p.text}
      </mark>
    ) : (
      <span key={i}>{p.text}</span>
    ),
  );
}

function LookalikeRow({ flag }: { flag: HeaderFlag }) {
  const d = flag.diff!;
  return (
    <>
      <dt className="text-blocked-ink">Lookalike</dt>
      <dd className="figure">
        <span className="text-blocked-ink">
          <Parts parts={d.fake} />
        </span>
        <span className="font-sans text-ink-muted"> imitates </span>
        <Parts parts={d.real} />
      </dd>
    </>
  );
}

function AttachmentRow({
  invoiceId,
  paymentId: pid,
  hasPdf,
  invoice,
  history,
}: {
  invoiceId: string;
  paymentId: string;
  hasPdf: boolean;
  invoice?: HistoryInvoice;
  history?: VendorHistory;
}) {
  const [open, setOpen] = useState(false);
  // The payment record exists once a run has read the invoice; it carries the injection findings.
  const { data: detail } = useQuery({ queryKey: ["payment", pid], queryFn: () => api.payment(pid), retry: false });
  const findings = detail?.injection_findings.filter((f) => f.invoice_id === invoiceId) ?? [];
  const name = `${invoice?.number ?? invoiceId}.pdf`;

  return (
    <li>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex w-full items-center gap-3 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-sunken"
      >
        <FileText {...iconProps} className="text-ink-muted" />
        <span className="figure text-sm">{name}</span>
        {invoice?.amount_usd != null && <Money amount={invoice.amount_usd} className="text-sm text-ink-muted" />}
        {findings.length > 0 && (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-blocked-ink">
            <ShieldAlert {...iconProps} size={14} />
            Hidden text found
          </span>
        )}
        <span className="ml-auto text-sm text-accent">Preview</span>
      </button>
      {invoice && history && (
        <InvoicePreview open={open} onOpenChange={setOpen} pdfUrl={hasPdf && !isMock() ? invoicePdfUrl(invoiceId) : null} name={name} invoice={invoice} vendor={history.vendor} findings={findings} />
      )}
    </li>
  );
}

function ViewSkeleton() {
  return (
    <div aria-busy className="space-y-3 px-6 py-5">
      <Skeleton className="h-6 w-72" />
      <Skeleton className="h-3.5 w-56" />
      <Skeleton className="mt-5 h-36 w-full" />
      <Skeleton className="h-24 w-full" />
    </div>
  );
}
