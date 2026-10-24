import { Phone } from "lucide-react";
import { iconProps } from "@/components/shared/icon";
import { EvidenceRef, useEvidenceSource } from "@/components/payment/evidence";
import { Section } from "@/components/payment/section";
import { formatClock, formatPhone } from "@/lib/format";
import { CONTACT_SOURCES } from "@/lib/risk-catalog";
import type { PaymentDetail } from "@/lib/types";
import { cn } from "@/lib/utils";

const OUTCOMES = { confirmed: "Confirmed", denied: "Denied", no_answer: "No answer", unclear: "Unclear" } as const;

// Slot for the live call panel (transcript, audio). Until then it shows the call record.
export function CallSlot({ detail }: { detail: PaymentDetail }) {
  const call = detail.calls.at(-1);
  const source = useEvidenceSource([call?.id]);

  if (!call) {
    const quarantined = detail.findings.length > 0;
    return (
      <Section title="Verification call">
        <p className="text-sm text-ink-muted">
          {quarantined
            ? "No call: the document was quarantined before any call, and a call cannot clear hidden instructions."
            : "No call needed: this payment goes to the last verified account."}
        </p>
      </Section>
    );
  }

  return (
    <Section title="Verification call" aside={<EvidenceRef id={call.id} />}>
      <div {...source} className={cn(source.className, "border border-dashed border-rule-strong p-3")}>
        <dl className="grid grid-cols-[96px_1fr] gap-x-4 gap-y-1.5 text-sm">
          <dt className="text-ink-muted">Called</dt>
          <dd className="flex flex-wrap items-center gap-x-2">
            <Phone {...iconProps} className="text-ink-muted" />
            <span className="figure">{formatPhone(call.contact?.phone)}</span>
            <span className="text-ink-muted">{call.contact ? CONTACT_SOURCES[call.contact.source] : ""}</span>
          </dd>
          <dt className="text-ink-muted">Started</dt>
          <dd className="figure">{formatClock(call.started_at)}</dd>
          <dt className="text-ink-muted">Outcome</dt>
          <dd className="font-medium">{call.outcome ? OUTCOMES[call.outcome] : "In progress"}</dd>
          <dt className="text-ink-muted">Transcript</dt>
          <dd className="text-ink-muted">
            <span className="figure text-ink">{call.transcript?.length ?? 0}</span> lines. The live call panel goes here.
          </dd>
        </dl>
      </div>
    </Section>
  );
}
