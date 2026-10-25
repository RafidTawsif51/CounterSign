// "How this decision was made": one step per thing that actually happened to this payment, with the service behind it.
//
// Built only from the stored payment record. A step that did not happen is not listed (a quarantined invoice never had a
// phone call, so it has no call step). A service is marked simulated when the record says so: a call's own `simulated`, the
// number check's `simulated`, the CRS result's `source`, the payment's `transfer_mode`, the invoice's `extraction_source`.

import { formatUSD } from "@/lib/format";
import { DECISIONS, TECHNIQUES, hardRuleInfo } from "@/lib/risk-catalog";
import { callSimulated, type ServiceModes } from "@/lib/services";
import type { CallOutcome, PaymentDetail, PaymentStatus } from "@/lib/types";

export type StepMode = "real" | "simulated" | "local";

export interface TimelineStep {
  key: string;
  title: string;
  result: string;
  /** The service that did it, in words. */
  service: string;
  mode: StepMode;
  /** Set for the payment's own outcome and for a call outcome, which carry a payment status colour. */
  status?: PaymentStatus;
  /** Attack evidence is marked in brick. */
  evidence?: boolean;
  active?: boolean;
  link?: { href: string; label: string };
}

/** Hiding and instruction techniques the scanner reports, in words. The catalog covers the main ones; the rest read plainly. */
const MORE_TECHNIQUES: Record<string, string> = {
  near_background_text: "Text colored like the page",
  same_color_text: "Text colored like its background",
  hidden_element: "Hidden HTML element",
  hidden_mime_part: "Hidden email part",
  instruction_keyword: "Instruction words",
  "instruction_keyword+classifier": "Instructions to an AI",
  classifier_incomplete: "Document too long to classify",
};
export const techniqueLabel = (t: string): string => (TECHNIQUES as Record<string, string>)[t] ?? MORE_TECHNIQUES[t] ?? t.replace(/_/g, " ");

/** Who found it: the pattern scan is our code, the classifier is Claude Haiku. */
export const isClassifierFinding = (technique: string) => technique.includes("classifier");

const CALL_RESULT: Record<CallOutcome, { text: string; status: PaymentStatus }> = {
  denied: { text: "The vendor said they never made the change", status: "blocked" },
  confirmed: { text: "The vendor confirmed the change", status: "paid" },
  unclear: { text: "The answer was unclear", status: "held" },
  no_answer: { text: "Nobody answered", status: "held" },
};

export function buildTimeline(d: PaymentDetail, modes: ServiceModes): TimelineStep[] {
  const steps: TimelineStep[] = [];
  const inv = d.invoice;

  // 1. Read the document.
  if (inv) {
    const src = inv.extraction_source;
    const account = inv.requested_remittance?.account_last4;
    const failed = inv.extraction_status === "extraction_failed";
    steps.push({
      key: "read",
      title: inv.has_pdf ? "Read the invoice" : "Read the email",
      result: failed
        ? "The document could not be read, so the payment was held."
        : `${inv.number ? `Invoice ${inv.number}, ` : ""}${formatUSD(inv.amount_usd)}${account ? `, asks to be paid to the account ending ${account}` : ""}`,
      service: src === "claude" ? `Claude${inv.extraction_model ? `, ${inv.extraction_model}` : ""}` : src === "cache" ? "Claude, an earlier result reused" : src === "mock" ? "Claude" : "Our parser",
      mode: src === "claude" || src === "cache" ? "real" : src === "mock" ? "simulated" : "local",
    });
  }

  // 2. Scan it.
  const finds = d.injection_findings;
  if (inv || finds.length) {
    const techniques = [...new Set(finds.map((f) => techniqueLabel(f.technique)))];
    const classifier = finds.some((f) => isClassifierFinding(f.technique));
    steps.push({
      key: "scan",
      title: "Checked for hidden instructions",
      result: finds.length ? `Found ${finds.length === 1 ? "one" : finds.length}: ${techniques.join(", ").toLowerCase()}. The document was quarantined.` : "Nothing hidden found.",
      service: classifier ? "Hidden-text scan (our code) and Claude Haiku" : "Hidden-text scan, our code",
      mode: classifier ? "real" : "local",
      evidence: finds.length > 0,
    });
  }

  // 3. Score it.
  if (d.risk) {
    const rules = d.risk.hard_rules_fired.map((r) => hardRuleInfo(String(r)).label.toLowerCase());
    steps.push({
      key: "risk",
      title: "Scored the payment",
      result: `Score ${d.risk.score} of 100, ${DECISIONS[d.risk.decision].toLowerCase()}${rules.length ? `. Hard rule: ${rules.join(", ")}` : ""}`,
      service: "Risk engine, our code",
      mode: "local",
    });
  }

  // 4. Check the vendor's identity (it only ran when the signal is on the assessment).
  const crsRan = d.risk?.signals.some((s) => s.name === "vendor_identity_check") && d.identity;
  if (crsRan && d.identity) {
    const live = d.identity.source === "crs-sandbox";
    const word = { verified: "Verified", unverified: "Not verified", flagged: "Flagged" }[d.identity.status];
    steps.push({
      key: "crs",
      title: "Checked the vendor's identity",
      result: `${word}, match ${d.identity.match_score.toFixed(2)}`,
      service: live ? "CRS sandbox" : "CRS",
      mode: live ? "real" : "simulated",
    });
  }

  // 5. Find a phone number that did not come from the email.
  const ic = d.independent_contact;
  if (ic) {
    const found = ic.status === "found";
    steps.push({
      key: "number",
      title: "Found a phone number that is not from the email",
      result: ic.simulated
        ? "Used the vendor website record already on file. No lookup ran."
        : found
          ? `From the vendor's own website, ${ic.confidence ? `${ic.confidence} confidence` : "confidence unknown"}`
          : (ic.hold_reasons[0]?.reason ?? "No usable number from the vendor's website, so the number on file was used"),
      service: ic.provider,
      mode: ic.simulated ? "simulated" : "real",
      link: !ic.simulated && ic.source_url ? { href: ic.source_url, label: ic.source_url.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "") } : undefined,
    });
  }

  // 6. Call the vendor.
  const call = d.calls.at(-1);
  if (call) {
    const simulated = callSimulated({ paymentId: d.payment.id, simulated: call.simulated }, modes);
    const r = call.outcome ? CALL_RESULT[call.outcome] : null;
    steps.push({
      key: "call",
      title: "Called the vendor",
      result: r ? r.text : "The call is in progress",
      service: simulated ? "Cartesia voice, Twilio call" : "Voice by Cartesia, call by Twilio",
      mode: simulated ? "simulated" : "real",
      status: r?.status,
      active: !call.outcome,
    });
  }

  // 7. What happened to the money.
  const s = d.payment.status;
  const money = formatUSD(d.payment.amount_usd);
  if (s === "paid") {
    const mode = d.payment.transfer_mode;
    steps.push({
      key: "outcome",
      title: "Paid",
      result: `${money}${d.payment.destination ? ` to the account ending ${d.payment.destination.account_last4}` : ""}${d.payment.nessie_transfer_id ? `, transfer ${d.payment.nessie_transfer_id}` : ""}`,
      service: mode === "nessie" ? "Capital One Nessie sandbox" : "Capital One Nessie",
      mode: mode === "nessie" ? "real" : "simulated",
      status: "paid",
    });
  } else if (s === "blocked") {
    steps.push({ key: "outcome", title: "Blocked", result: `${money} was not paid`, service: "Countersign", mode: "local", status: "blocked" });
  } else if (s === "held") {
    steps.push({ key: "outcome", title: "Held", result: `${money} waits for the controller`, service: "Countersign", mode: "local", status: "held" });
  }
  return steps;
}
