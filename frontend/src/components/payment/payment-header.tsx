import { SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Money } from "@/components/shared/money";
import { StatusBadge } from "@/components/shared/status-badge";
import { EvidenceRef } from "@/components/payment/evidence";
import { formatDate } from "@/lib/format";
import { DECISIONS } from "@/lib/risk-catalog";
import type { PaymentDetail } from "@/lib/types";
import { cn } from "@/lib/utils";
import { verdictFor } from "@/lib/verdict";

export function PaymentHeader({ detail }: { detail: PaymentDetail }) {
  const { payment, invoice, vendor, risk } = detail;
  const verdict = verdictFor(detail);

  return (
    <div className="px-5 pt-4 pb-5">
      <div className="pr-10">
        <SheetTitle>{vendor.name}</SheetTitle>
        <SheetDescription className="mt-0.5 flex flex-wrap gap-x-3">
          <span>
            Invoice <span className="figure text-ink">{invoice.number}</span>
          </span>
          <span>Due {formatDate(invoice.due_date)}</span>
          <span className="capitalize">{vendor.trade}</span>
        </SheetDescription>
      </div>

      <div className="mt-4 flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <Money amount={payment.amount_usd} className="text-xl font-medium" />
        <div className="flex items-center gap-2.5 pb-1">
          <StatusBadge status={payment.status} />
          {risk && (
            <span className="text-sm text-ink-muted">
              Risk decision: <span className="text-ink">{DECISIONS[risk.decision].toLowerCase()}</span>
            </span>
          )}
        </div>
      </div>

      {verdict && (
        <p
          className={cn(
            "mt-4 border-l-2 py-2 pr-3 pl-3 text-base",
            payment.status === "blocked" ? "border-blocked bg-blocked-tint" : "border-held bg-held-tint",
          )}
        >
          {verdict.text}
          {verdict.evidence.map((id) => (
            <EvidenceRef key={id} id={id} className="ml-1.5" />
          ))}
        </p>
      )}
    </div>
  );
}
