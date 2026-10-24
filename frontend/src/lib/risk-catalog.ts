// Plain-English labels for what the backend checks. Names and weights mirror backend/app/services/risk.py (WEIGHTS,
// HARD_RULE_ACTIONS). Weights are hackathon starting points, not validated; the drawer shows them as they are.

import type { AuditActor, ContactSource, Decision, HardRule, InjectionTechnique } from "@/lib/types";

export interface SignalInfo {
  label: string;
  weight: number;
  /** What the check looks at, shown for signals that did not fire. */
  checks: string;
}

export const SIGNALS: Record<string, SignalInfo> = {
  bank_details_changed: { label: "Bank details changed", weight: 30, checks: "Requested account against the last verified account" },
  lookalike_domain: { label: "Lookalike sender domain", weight: 25, checks: "Sender domain within 2 edits of the vendor's, or homoglyphs" },
  reply_to_mismatch: { label: "Reply-To differs from sender", weight: 15, checks: "Reply-To header against the From address" },
  urgency_language: { label: "Urgency, secrecy or authority language", weight: 15, checks: "Words like today, confidential, CEO approved" },
  amount_outlier: { label: "Amount outlier", weight: 15, checks: "More than 2 standard deviations above 12 months of invoices" },
  invoice_format_changed: { label: "Invoice format changed", weight: 10, checks: "Layout fingerprint against the vendor's past PDFs" },
  first_message_from_sender: { label: "First message from this sender", weight: 10, checks: "Sender address against the vendor's history" },
  outside_usual_hours: { label: "Sent outside usual hours", weight: 5, checks: "Send time against the vendor's usual window" },
  vendor_identity_check: { label: "Vendor identity (CRS)", weight: 15, checks: "Vendor identity in the CRS sandbox" },
};

export function signalInfo(name: string): SignalInfo {
  return SIGNALS[name] ?? { label: name.replace(/_/g, " "), weight: 0, checks: "" };
}

export const HARD_RULES: Record<HardRule, { label: string; action: string }> = {
  destination_changed: {
    label: "Destination differs from the last verified account",
    action: "Hold and place a verification call",
  },
  new_vendor: { label: "New vendor or first payment", action: "Hold for controller review" },
  hidden_instructions: { label: "Hidden instructions in the document", action: "Quarantine the document, hold, flag as attack" },
  amount_over_max: { label: "Amount over 1.5 times the 12-month maximum", action: "Hold for controller review" },
  contacts_differ: { label: "Contact details differ from verified contacts", action: "Ignore the new contacts; use only independent numbers" },
};

export function hardRuleInfo(rule: string) {
  return HARD_RULES[rule as HardRule] ?? { label: rule.replace(/_/g, " "), action: "Hold" };
}

export const DECISIONS: Record<Decision, string> = {
  auto_pay: "Auto-pay",
  controller_review: "Controller review",
  hold: "Hold",
  hold_and_verify: "Hold and verify by phone",
};

/** Score thresholds from CLAUDE.md: 30 and up goes to review, 60 and up is held. */
export const THRESHOLDS = [
  { at: 30, label: "Review" },
  { at: 60, label: "Hold" },
] as const;

export const TECHNIQUES: Record<InjectionTechnique, string> = {
  white_text: "White text",
  tiny_font: "Tiny font",
  off_page: "Text off the page",
  zero_width: "Zero-width characters",
  html_comment: "HTML comment",
  instruction_classifier: "Instructions to an AI",
};

export const CONTACT_SOURCES: Record<ContactSource, string> = {
  on_file: "number on file",
  website: "number on the vendor's website",
  listing: "number from a public listing",
};

export const AUDIT_ACTIONS: Record<string, string> = {
  risk_assessed: "Risk assessed",
  identity_check: "Vendor identity checked",
  quarantined: "Document quarantined",
  injection_findings: "Injection findings recorded",
  held: "Held",
  paid: "Paid",
  blocked: "Blocked",
  blocked_by_verification: "Blocked after the verification call",
  independent_contact_checked: "Vendor's number checked",
  verification_call_placed: "Verification call placed",
  voice_failover_to_web: "Phone call failed, rang the softphone",
  verification_in_progress: "Waiting on the verification call",
  verification_unavailable: "Verification call not placed",
  verification_call: "Verification call finished",
  verification_unclear: "Call unclear, sent to the controller",
  verification_no_answer: "No answer",
  verification_confirmed: "Vendor confirmed the change",
  held_after_verification: "Still held after the call",
  needs_controller_review: "Sent to the controller",
  request_marked_fraud: "Request marked as fraud",
  requested_destination_rejected: "Requested account rejected",
  cleared_for_payment: "Cleared for payment",
  payment_guard_refused: "Payment guard refused the transfer",
  nessie_failed: "Nessie transfer failed",
  transfer_failed: "Transfer failed",
  bank_account_verified: "Bank account verified",
  approved: "Approved by the controller",
  rejected: "Rejected by the controller",
  extraction_failed: "Extraction failed",
};

export const ACTORS: Record<AuditActor, string> = { agent: "Agent", human: "Person", system: "System" };
