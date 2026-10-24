import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { iconProps } from "@/components/shared/icon";
import { shortUrl } from "@/components/call/call-parts";
import { api } from "@/lib/api";
import { formatAccount, formatDate, formatMonthYear, formatPhoneMasked, formatUSD } from "@/lib/format";
import type { HistoryInvoice, VendorHistory } from "@/lib/types";
import { cn } from "@/lib/utils";

// Context rail: who this vendor is on file. Everything here comes from GET /api/vendors/{id}/history, never from the
// email being read, so a lookalike sender cannot change it.

const SOURCE_LABEL = { on_file: "On file", website: "Vendor website", listing: "Public listing" } as const;

export function VendorRail({ history, hasVendor }: { history: VendorHistory | undefined; hasVendor: boolean }) {
  if (!hasVendor)
    return (
      <p className="px-4 py-5 text-sm text-ink-muted">
        No vendor. This thread did not start in a vendor's thread, and Countersign never picks a vendor from a sender address.
      </p>
    );
  if (!history) return <RailSkeleton />;

  const { vendor } = history;
  const trusted = history.bank_accounts.find((a) => a.trusted);
  const requested = history.bank_accounts.filter((a) => !a.trusted && a.verified_by.startsWith("requested"));

  return (
    <div className="divide-y divide-rule">
      <section className="px-4 py-4">
        <h2 className="font-semibold">{vendor.name}</h2>
        <p className="text-sm text-ink-muted capitalize">{vendor.trade}</p>
        <dl className="mt-3 space-y-2.5 text-sm">
          <div>
            <dt className="text-ink-muted">Known domain</dt>
            <dd className="figure">{vendor.email_domain}</dd>
          </div>
          <div>
            <dt className="text-ink-muted">Verified account</dt>
            {trusted ? (
              <dd>
                <span className="figure font-medium">{formatAccount(trusted.account_last4)}</span>{" "}
                <span className="text-ink-muted">{trusted.bank_name}</span>
                <span className="block text-xs text-ink-muted">
                  Since {formatDate(trusted.valid_from)}, {trusted.verified_by === "onboarding" ? "verified at onboarding" : `verified by ${trusted.verified_by}`}
                </span>
              </dd>
            ) : (
              <dd className="text-ink-muted">None verified</dd>
            )}
            <UnverifiedRequests vendorId={vendor.id} />
            {requested.map((a) => (
              <dd key={a.id} className="text-xs text-ink-muted">
                <span className="figure">{formatAccount(a.account_last4)}</span> {a.bank_name}, never verified
              </dd>
            ))}
          </div>
        </dl>
      </section>

      <section className="px-4 py-4">
        <h3 className="text-sm font-medium text-ink-muted">Verified contacts</h3>
        <ul className="mt-2 space-y-2">
          {history.contacts.map((c) => (
            <li key={c.id} className="text-sm">
              <div className="flex items-baseline justify-between gap-2">
                <span className="figure">{formatPhoneMasked(c.phone)}</span>
                <span className="text-xs text-ink-muted">{SOURCE_LABEL[c.source]}</span>
              </div>
              <div className="text-xs text-ink-muted">
                {c.source_url ? (
                  <a href={c.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-accent underline-offset-4 hover:underline">
                    {shortUrl(c.source_url)}
                    <ExternalLink {...iconProps} size={12} />
                  </a>
                ) : c.last_verified ? (
                  `Verified ${formatDate(c.last_verified)}`
                ) : (
                  `First seen ${formatMonthYear(c.first_seen)}`
                )}
              </div>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-ink-muted">Numbers in emails are never added here.</p>
      </section>

      <PaymentsSection invoices={history.invoices} />

      <section className="px-4 py-4">
        <h3 className="text-sm font-medium text-ink-muted">Identity check (CRS)</h3>
        {history.identity ? (
          <div className="mt-2 text-sm">
            <p>
              <span className="font-medium capitalize">{history.identity.status}</span>
              <span className="text-ink-muted">, match </span>
              <span className="figure">{history.identity.match_score.toFixed(2)}</span>
            </p>
            {history.identity.flags.length > 0 && <p className="text-xs">{history.identity.flags.join(", ").replace(/_/g, " ")}</p>}
            <p className="mt-0.5 text-xs text-ink-muted">
              <span className="figure">{history.identity.test_identity_id}</span>, checked {formatDate(history.identity.checked_at)}
              {history.identity.source === "crs-sandbox-mock" ? ", CRS sandbox (mock)" : ", CRS sandbox"}
            </p>
          </div>
        ) : (
          <p className="mt-2 text-sm text-ink-muted">No identity result on file yet.</p>
        )}
      </section>
    </div>
  );
}

/** The vendors API's count of bank changes a payment request asked for and no call verified. Hidden at 0. */
function UnverifiedRequests({ vendorId }: { vendorId: string }) {
  const { data } = useQuery({ queryKey: ["vendors"], queryFn: api.vendors, staleTime: 10_000 });
  const n = data?.find((v) => v.id === vendorId)?.unverified_requested_accounts ?? 0;
  if (n === 0) return null;
  return (
    <dd className="mt-1.5 flex items-center gap-1.5 text-sm text-held-ink">
      <span aria-hidden className="size-1.5 shrink-0 bg-held" />
      <span className="figure">{n}</span> unverified bank change {n === 1 ? "request" : "requests"}
    </dd>
  );
}

interface Month {
  key: string; // 2026-03
  label: string; // Mar 2026
  total: number;
  count: number;
}

/** Paid invoices by month for the 12 months up to the latest one. The history route dates invoices by due date. */
function months(invoices: HistoryInvoice[]): Month[] {
  const paid = invoices.filter((i) => i.status === "paid" && i.due_date && i.amount_usd != null);
  if (paid.length === 0) return [];
  const last = paid.map((i) => i.due_date!).sort().at(-1)!;
  const [y, m] = last.split("-").map(Number);
  return Array.from({ length: 12 }, (_, k) => {
    const d = new Date(Date.UTC(y, m - 12 + k, 1));
    const key = d.toISOString().slice(0, 7);
    const these = paid.filter((i) => i.due_date!.startsWith(key));
    return { key, label: formatMonthYear(d.toISOString()), total: these.reduce((t, i) => t + i.amount_usd!, 0), count: these.length };
  });
}

function PaymentsSection({ invoices }: { invoices: HistoryInvoice[] }) {
  const data = months(invoices);
  const total = data.reduce((t, d) => t + d.total, 0);
  const count = data.reduce((t, d) => t + d.count, 0);
  return (
    <section className="px-4 py-4">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-medium text-ink-muted">Paid, last 12 months</h3>
        <span className="figure text-xs text-ink-muted">{count} invoices</span>
      </div>
      <p className="figure mt-1 text-md">{formatUSD(total)}</p>
      {data.length > 0 ? <Sparkline data={data} /> : <p className="mt-2 text-sm text-ink-muted">No paid invoices yet.</p>}
    </section>
  );
}

const W = 268;
const H = 36;
const PAD = 3;

/** One series, so no legend: the heading names it. Muted line, the latest month marked in ink. Hover shows the month. */
function Sparkline({ data }: { data: Month[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(...data.map((d) => d.total), 1);
  const x = (i: number) => PAD + (i * (W - 2 * PAD)) / (data.length - 1);
  const y = (v: number) => H - PAD - (v / max) * (H - 2 * PAD);
  const line = data.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(d.total).toFixed(1)}`).join(" ");
  const last = data.length - 1;
  const shown = hover ?? last;

  return (
    <div className="mt-2">
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Monthly paid totals, ${data[0].label} to ${data[last].label}`} className="block overflow-visible">
        <line x1={PAD} x2={W - PAD} y1={H - PAD} y2={H - PAD} stroke="var(--rule)" strokeWidth={1} />
        <path d={line} fill="none" stroke="var(--ink-muted)" strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
        {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={PAD} y2={H - PAD} stroke="var(--rule-strong)" strokeWidth={1} />}
        <circle cx={x(shown)} cy={y(data[shown].total)} r={3} fill="var(--ink)" stroke="var(--surface)" strokeWidth={1.5} />
        {/* Hit targets wider than the mark: one column per month. */}
        {data.map((d, i) => (
          <rect
            key={d.key}
            x={x(i) - (W - 2 * PAD) / (data.length - 1) / 2}
            y={0}
            width={(W - 2 * PAD) / (data.length - 1)}
            height={H}
            fill="transparent"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
          />
        ))}
      </svg>
      <p className={cn("mt-1 flex justify-between text-xs", hover === null ? "text-ink-muted" : "text-ink")}>
        <span>{data[shown].label}</span>
        <span className="figure">
          {formatUSD(data[shown].total)}, {data[shown].count} {data[shown].count === 1 ? "invoice" : "invoices"}
        </span>
      </p>
      <table className="sr-only">
        <caption>Paid invoices per month</caption>
        <tbody>
          {data.map((d) => (
            <tr key={d.key}>
              <th>{d.label}</th>
              <td>{formatUSD(d.total)}</td>
              <td>{d.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RailSkeleton() {
  return (
    <div aria-busy className="space-y-3 px-4 py-4">
      <Skeleton className="h-4 w-40" />
      <Skeleton className="h-3 w-24" />
      <Skeleton className="mt-4 h-10 w-full" />
      <Skeleton className="h-16 w-full" />
      <Skeleton className="h-12 w-full" />
    </div>
  );
}
