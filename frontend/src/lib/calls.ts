// Verification call state for the call panel and the board's compact call strip. Built from the run's events while a
// run is live (line by line, no refetch lag) and from the payment record otherwise (a call from an earlier run).

import type { CallOutcome, ContactSource, PaymentDetail, RunEvent, TranscriptLine, VendorContact } from "@/lib/types";

/** A stored contact or a history contact (phone masked to the last four). Both carry what the trust line needs. */
export type ContactLike = Pick<VendorContact, "id" | "phone" | "source" | "source_url"> & { first_seen?: string };

/** queued: held for a call that has not started. dialing: started, nobody has spoken. live: talking. ended: outcome in. */
export type CallPhase = "queued" | "dialing" | "live" | "ended";

export interface CallView {
  paymentId: string;
  vendor: string;
  phase: CallPhase;
  contactSource: ContactSource | null;
  startedAt: string | null;
  endedAt: string | null;
  lines: TranscriptLine[];
  outcome: CallOutcome | null;
}

/** verify.py hangs up at 60 seconds. */
export const CALL_LIMIT_S = 60;

const paymentIdFor = (invoiceId: string) => "pay_" + invoiceId.slice("inv_".length);

/** Every call in a run, in the order the agent queued them. */
export function foldCalls(events: RunEvent[]): CallView[] {
  const vendorOf = new Map<string, string>();
  const verify = new Set<string>();
  const calls = new Map<string, CallView>();

  for (const e of events) {
    if (e.type === "invoice.parsed") vendorOf.set(paymentIdFor(e.invoice_id), e.vendor);
    if (e.type === "risk.scored" && e.decision === "hold_and_verify") verify.add(e.payment_id);
    if (!("payment_id" in e)) continue;
    const pid = e.payment_id;
    let call = calls.get(pid);

    if (e.type === "payment.held" && verify.has(pid) && !call) {
      calls.set(pid, blank(pid, vendorOf.get(pid) ?? ""));
      continue;
    }
    if (e.type === "call.started") {
      call ??= blank(pid, vendorOf.get(pid) ?? "");
      // A second attempt (no answer, retried) starts the panel over.
      Object.assign(call, { phase: "dialing", contactSource: e.contact_source, startedAt: e.at, endedAt: null, lines: [], outcome: null });
      calls.set(pid, call);
      continue;
    }
    if (!call) continue;
    if (e.type === "call.transcript") {
      call.lines = [...call.lines, { speaker: e.speaker, text: e.text }];
      if (call.phase === "dialing") call.phase = "live";
    }
    if (e.type === "call.outcome") {
      call.phase = "ended";
      call.outcome = e.outcome;
      call.endedAt = e.at;
    }
  }
  return [...calls.values()];
}

function blank(paymentId: string, vendor: string): CallView {
  return { paymentId, vendor, phase: "queued", contactSource: null, startedAt: null, endedAt: null, lines: [], outcome: null };
}

/** The same view from the stored payment record. Null when no call was or will be placed. */
export function callFromDetail(d: PaymentDetail): CallView | null {
  const call = d.calls.at(-1);
  if (!call) {
    const waiting = d.payment.status === "held" && d.risk?.decision === "hold_and_verify";
    return waiting ? blank(d.payment.id, d.vendor?.name ?? "the vendor") : null;
  }
  const lines = call.transcript ?? [];
  // The record has no end time; the audit entry verify.py writes with the outcome does.
  const ended = [...d.audit].reverse().find((a) => a.action === "verification_call" && a.detail?.call_id === call.id);
  return {
    paymentId: d.payment.id,
    vendor: d.vendor?.name ?? "the vendor",
    phase: call.outcome ? "ended" : lines.length ? "live" : "dialing",
    contactSource: call.contact?.source ?? null,
    startedAt: call.started_at,
    endedAt: call.outcome ? (ended?.at ?? null) : null,
    lines,
    outcome: call.outcome,
  };
}

/**
 * Why the dialed number is trusted: where it came from, since when, and whether an independent source agrees.
 * Built from the dialed contact and the vendor's other contacts (GET /api/vendors/{id}/history).
 */
export interface NumberTrust {
  phone: string | null;
  source: ContactSource | null;
  since: string | null;
  crossCheck: { source: ContactSource; url: string | null; matches: boolean } | null;
}

export function numberTrust(dialed: ContactLike | null, others: ContactLike[]): NumberTrust {
  if (!dialed) return { phone: null, source: null, since: null, crossCheck: null };
  const independent = others.find((c) => c.id !== dialed.id && c.source !== dialed.source && c.source !== "on_file") ?? null;
  return {
    phone: dialed.phone,
    source: dialed.source,
    since: dialed.first_seen ?? null,
    crossCheck: independent
      ? { source: independent.source, url: independent.source_url, matches: last4(independent.phone) === last4(dialed.phone) }
      : null,
  };
}

// The history route masks phones to the last four digits, so that is all two numbers can be compared on.
const last4 = (p: string) => p.replace(/\D/g, "").slice(-4);
