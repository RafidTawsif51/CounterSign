// The one-sentence verdict at the top of the payment drawer, with the evidence that backs it.

import { formatAccount } from "@/lib/format";
import { hardRuleInfo } from "@/lib/risk-catalog";
import type { PaymentDetail, RemittanceDetails } from "@/lib/types";

export interface Verdict {
  text: string;
  evidence: string[];
}

/** The bank details the invoice or email asked for, if it named an account. */
export function requestedAccount(d: PaymentDetail): RemittanceDetails | null {
  const r = d.invoice?.requested_remittance;
  return r?.account_last4 ? { bank_name: r.bank_name ?? "", routing_hash: r.routing_hash ?? "", account_last4: r.account_last4 } : null;
}

/** The backend compares routing hash and last four against the verified account (review.py). */
export function destinationChanged(d: PaymentDetail) {
  return Boolean(d.invoice?.requested_account_differs_from_verified);
}

export function verdictFor(d: PaymentDetail): Verdict | null {
  const { status } = d.payment;
  if (status !== "held" && status !== "blocked") return null;

  const call = d.calls.at(-1);
  const finding = d.injection_findings[0];
  const decided = [...d.audit].reverse().find((a) => a.actor === "human" && (a.action === "approved" || a.action === "rejected"));
  const bankSignal = d.risk?.signals.find((s) => s.name === "bank_details_changed");
  const req = requestedAccount(d);

  if (status === "blocked") {
    if (decided?.action === "rejected") {
      const reason = String(decided.detail?.reason ?? "");
      return { text: `Blocked: the controller rejected it.${reason ? ` "${reason}"` : ""}`, evidence: [decided.id] };
    }
    if (call?.outcome === "denied")
      return { text: "Blocked: the vendor confirmed by phone that they never changed banks.", evidence: [call.id] };
    if (finding)
      return {
        text: "Blocked: the invoice hides instructions telling an AI to reroute and approve this payment, so the document was quarantined.",
        evidence: [finding.id],
      };
    return { text: "Blocked by the risk checks below.", evidence: d.risk ? [d.risk.id] : [] };
  }

  // held
  if (call?.outcome === "unclear")
    return {
      text: "Held: the call to the vendor's number on file did not confirm the new account, so the controller decides.",
      evidence: [call.id],
    };
  if (call?.outcome === "no_answer")
    return { text: "Held: the vendor did not answer the verification call. The controller decides.", evidence: [call.id] };
  if (destinationChanged(d))
    return {
      text: `Held: it would pay a new account ending ${req ? formatAccount(req.account_last4).slice(-4) : ""}, so the vendor is being called at an independent number.`,
      evidence: [bankSignal?.evidence_id, call?.id].filter(Boolean) as string[],
    };
  const rule = d.risk?.hard_rules_fired[0];
  if (rule) return { text: `Held: ${hardRuleInfo(rule).label.toLowerCase()}. ${hardRuleInfo(rule).action}.`, evidence: [d.risk!.id] };
  return { text: `Held: risk score ${d.risk?.score ?? ""} is at or above the hold threshold of 60.`, evidence: d.risk ? [d.risk.id] : [] };
}
