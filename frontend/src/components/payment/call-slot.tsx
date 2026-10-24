import { useMemo } from "react";
import { useNumberTrust } from "@/components/call/call-parts";
import { VerificationCallPanel } from "@/components/call/verification-call-panel";
import { EvidenceRef, useEvidenceSource } from "@/components/payment/evidence";
import { Section } from "@/components/payment/section";
import { useCurrentRun } from "@/components/shared/run-context";
import { callFromDetail, foldCalls } from "@/lib/calls";
import type { PaymentDetail } from "@/lib/types";

// The verification call. While the run is live the panel follows the event stream line by line; otherwise (or before
// the stream has this payment) it shows the stored call record.
export function CallSlot({ detail }: { detail: PaymentDetail }) {
  const { allEvents: events } = useCurrentRun();
  const record = detail.calls.at(-1);
  const live = useMemo(() => foldCalls(events).find((c) => c.paymentId === detail.payment.id), [events, detail.payment.id]);
  const call = live ?? callFromDetail(detail);
  const trust = useNumberTrust(detail.vendor.id, record?.contact ?? null, call?.contactSource ?? null);
  const source = useEvidenceSource([record?.id]);

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
    <Section title="Verification call" aside={<EvidenceRef id={record?.id} />}>
      <div {...source}>
        <VerificationCallPanel call={call} trust={trust} evidenceId={record?.id} />
      </div>
    </Section>
  );
}
