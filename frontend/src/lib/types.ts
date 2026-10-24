// Wire types. Mirrors docs/models.md and docs/events.md (backend: app/models.py, app/events.py).
// When the backend changes a shape, change it here first; the compiler finds every screen that breaks.
// Text fields marked "untrusted" can hold attacker text: render as plain text, never as HTML.

export type ISODateTime = string;
export type ISODate = string;

// ---------- Enums ----------

export type VendorStatus = "active" | "inactive";
export type ContactSource = "on_file" | "website" | "listing";
export type RunStatus = "running" | "completed" | "failed";
export type PaymentStatus = "pending" | "paid" | "held" | "blocked";
export type Decision = "auto_pay" | "controller_review" | "hold" | "hold_and_verify";
export type CallOutcome = "confirmed" | "denied" | "no_answer" | "unclear";
export type AttackSource = "console" | "judge" | "bounty_email";
export type AttackResult = "caught" | "missed";
export type ModerationStatus = "pending" | "approved" | "hidden";
export type AuditActor = "agent" | "human" | "system";
export type Speaker = "agent" | "vendor";
// Card names from demo/attack-cards.md and run.py::_attack_for.
export type AttackCard = "classic_bank_change" | "poisoned_invoice" | "ceo_pressure" | "freestyle";
export type InjectionTechnique =
  | "white_text"
  | "tiny_font"
  | "off_page"
  | "zero_width"
  | "html_comment"
  | "instruction_classifier";

// ---------- Tables ----------

export interface Vendor {
  id: string;
  name: string;
  trade: string;
  email_domain: string;
  created_at: ISODateTime;
  status: VendorStatus;
}

export interface VendorBankAccount {
  id: string;
  vendor_id: string;
  routing_hash: string;
  account_last4: string;
  bank_name: string;
  valid_from: ISODateTime;
  valid_to: ISODateTime | null;
  verified_by_call_id: string | null;
}

export interface VendorContact {
  id: string;
  vendor_id: string;
  phone: string;
  source: ContactSource;
  source_url: string | null;
  first_seen: ISODateTime;
  last_verified: ISODateTime | null;
}

export interface Message {
  id: string;
  thread_id: string;
  vendor_id: string | null;
  from_addr: string;
  reply_to: string | null;
  subject: string; // untrusted
  body: string; // untrusted
  received_at: ISODateTime;
  is_attack: boolean;
}

// vendor_id, number, amount_usd and due_date are null for an uploaded PDF until extraction runs.
export interface Invoice {
  id: string;
  vendor_id: string | null;
  message_id: string | null;
  number: string | null;
  amount_usd: number | null;
  due_date: ISODate | null;
  remittance_json: Record<string, unknown> | null;
  pdf_path: string | null;
  extracted_json: Record<string, unknown> | null;
}

export interface RunTotals {
  paid: number;
  held: number;
  blocked: number;
  total_usd: number;
}

export interface PaymentRun {
  id: string;
  started_at: ISODateTime;
  completed_at: ISODateTime | null;
  status: RunStatus;
  totals_json: RunTotals | null;
}

export interface Payment {
  id: string;
  run_id: string;
  invoice_id: string;
  amount_usd: number;
  destination_account_id: string | null;
  status: PaymentStatus;
  nessie_transfer_id: string | null;
}

export interface Signal {
  name: string;
  weight: number;
  detail: string; // untrusted (may quote email text)
  evidence_id: string;
}

// Hard rules from risk.py. amount_over_max is the spec's "more than 50% above the 12-month max".
export type HardRule = "destination_changed" | "new_vendor" | "hidden_instructions" | "amount_over_max" | "contacts_differ";

export interface RiskAssessment {
  id: string;
  payment_id: string;
  score: number;
  decision: Decision;
  hard_rules_fired: (HardRule | string)[];
  signals_json: Signal[];
  model_version: string;
}

export interface InjectionFinding {
  id: string;
  invoice_id: string | null;
  message_id: string | null;
  technique: InjectionTechnique;
  snippet: string; // untrusted
  confidence: number;
}

export interface TranscriptLine {
  speaker: Speaker;
  text: string; // untrusted (vendor speech)
}

export interface VerificationCall {
  id: string;
  payment_id: string;
  contact_id: string | null;
  started_at: ISODateTime;
  outcome: CallOutcome | null;
  transcript: TranscriptLine[] | null;
  recording_url: string | null;
}

export interface Attack {
  id: string;
  attacker_name: string;
  source: AttackSource;
  card: AttackCard | string;
  payload_ref: string | null;
  result: AttackResult | null;
  created_at: ISODateTime;
  moderation_status: ModerationStatus;
}

export interface AuditLogEntry {
  id: string;
  at: ISODateTime;
  entity: string;
  entity_id: string;
  actor: AuditActor;
  action: string;
  detail_json: Record<string, unknown> | null;
}

// ---------- Events (SSE) ----------

interface EventBase {
  id: string;
  run_id: string | null;
  at: ISODateTime;
}

export interface RunStartedEvent extends EventBase {
  type: "run.started";
  invoice_count: number;
}
export interface InvoiceParsedEvent extends EventBase {
  type: "invoice.parsed";
  invoice_id: string;
  vendor: string;
  amount_usd: number;
}
export interface InjectionDetectedEvent extends EventBase {
  type: "injection.detected";
  invoice_id: string | null;
  message_id: string | null;
  technique: InjectionTechnique;
  snippet: string; // untrusted
}
export interface RiskScoredEvent extends EventBase {
  type: "risk.scored";
  payment_id: string;
  score: number;
  decision: Decision;
  top_signals: Signal[];
}
export interface PaymentPaidEvent extends EventBase {
  type: "payment.paid";
  payment_id: string;
  nessie_transfer_id: string;
}
export interface PaymentHeldEvent extends EventBase {
  type: "payment.held";
  payment_id: string;
  reasons: string[]; // untrusted
}
export interface CallStartedEvent extends EventBase {
  type: "call.started";
  payment_id: string;
  contact_source: ContactSource;
}
export interface CallTranscriptEvent extends EventBase {
  type: "call.transcript";
  payment_id: string;
  speaker: Speaker;
  text: string; // untrusted
}
export interface CallOutcomeEvent extends EventBase {
  type: "call.outcome";
  payment_id: string;
  outcome: CallOutcome;
}
export interface PaymentBlockedEvent extends EventBase {
  type: "payment.blocked";
  payment_id: string;
  reason: string; // untrusted
}
export interface RunCompletedEvent extends EventBase {
  type: "run.completed";
  paid: number;
  held: number;
  blocked: number;
  total_usd: number;
}
export interface RunReportEvent extends EventBase {
  type: "run.report";
  summary: string;
  paid: number;
  held: number;
  blocked: number;
  paid_usd: number;
  blocked_usd: number;
  findings: string[]; // untrusted
}
export interface AttackLoggedEvent extends EventBase {
  type: "attack.logged";
  attack_id: string;
  attacker_name: string;
  source: AttackSource;
  card: AttackCard | string;
  result: AttackResult | null;
  moderation_status: ModerationStatus;
}

export type RunEvent =
  | RunStartedEvent
  | InvoiceParsedEvent
  | InjectionDetectedEvent
  | RiskScoredEvent
  | PaymentPaidEvent
  | PaymentHeldEvent
  | CallStartedEvent
  | CallTranscriptEvent
  | CallOutcomeEvent
  | PaymentBlockedEvent
  | RunCompletedEvent
  | RunReportEvent
  | AttackLoggedEvent;

export type RunEventType = RunEvent["type"];

// ---------- API responses ----------
// Shapes below are not yet documented by the backend. Confirm with the backend lead before relying on extra fields.

/**
 * GET /api/payments/{id}. Proposed shape: the backend route does not exist yet (confirm with the backend lead).
 * The requested destination is invoice.remittance_json ({bank_name, routing_hash, account_last4}); the drawer compares it
 * with last_verified_account. Signals that were checked but did not fire are derived client-side from the signal list.
 */
export interface PaymentDetail {
  payment: Payment;
  invoice: Invoice;
  vendor: Vendor;
  /** The email that carried the invoice, for sender and Reply-To checks. Untrusted text. */
  message: Message | null;
  /** The vendor's current verified account (valid_to null). */
  last_verified_account: VendorBankAccount | null;
  risk: RiskAssessment | null;
  findings: InjectionFinding[];
  calls: (VerificationCall & { contact: VendorContact | null })[];
  audit: AuditLogEntry[];
}

export interface RemittanceDetails {
  bank_name: string;
  routing_hash: string;
  account_last4: string;
}

/**
 * GET /api/vendors row (backend services/vendors.py). Only the fields the frontend reads are typed; the route also returns
 * current_account, identity and risk_summary.
 */
export interface VendorSummary extends Vendor {
  /** Bank accounts a payment request asked for that no verification call has confirmed. Recorded when a run reads the invoice. */
  unverified_requested_accounts: number;
}

/** The stored CRS identity result for a vendor (backend services/identity.py IdentityResult). */
export interface IdentityResult {
  vendor_id: string;
  status: "verified" | "unverified" | "flagged";
  match_score: number;
  test_identity_id: string;
  flags: string[];
  summary: string;
  checked_at: ISODateTime;
  source: "crs-sandbox" | "crs-sandbox-mock";
}

/** A contact as the history route returns it: the phone is masked to `+1***0142` (last four only). */
export interface HistoryContact {
  id: string;
  source: ContactSource;
  source_url: string | null;
  phone: string;
  first_seen: ISODateTime;
  last_verified: ISODateTime | null;
}

export interface HistoryInvoice {
  id: string;
  number: string | null;
  amount_usd: number | null;
  due_date: ISODate | null;
  has_pdf: boolean;
  remittance: Record<string, unknown> | null;
  payment_id: string | null;
  status: PaymentStatus | "open";
  score: number | null;
  decision: Decision | null;
  hard_rules_fired: string[];
}

export interface HistoryBankAccount {
  id: string;
  bank_name: string;
  account_last4: string;
  valid_from: ISODateTime;
  valid_to: ISODateTime | null;
  /** The vendor's verified account: the one money may go to. */
  trusted: boolean;
  current: boolean;
  verified_by_call_id: string | null;
  /** "onboarding", "phone call: confirmed", "requested, not verified". */
  verified_by: string;
}

/** GET /api/vendors/{id}/history. Shape from backend/app/services/vendors.py. */
export interface VendorHistory {
  vendor: Vendor;
  /** Null only if the check could not run; the route runs it once for a vendor with no result on file. */
  identity: IdentityResult | null;
  summary: { invoices: number; paid: number; average_paid_usd: number | null; max_paid_usd: number | null };
  /** Newest first. */
  invoices: HistoryInvoice[];
  bank_accounts: HistoryBankAccount[];
  contacts: HistoryContact[];
  calls: (Omit<VerificationCall, "contact_id"> & { contact: Omit<HistoryContact, "first_seen" | "last_verified"> | null })[];
}

/** GET /api/inbox/threads, newest activity first. Shape from backend/app/services/ingest.py. */
export interface InboxThreadSummary {
  thread_id: string;
  vendor: { id: string; name: string } | null;
  subject: string; // untrusted
  preview: string; // untrusted
  count: number;
  /** The seed's ground truth, not a detection. The inbox never shows it; attack markers come from what the run caught. */
  has_attack: boolean;
  last_received_at: ISODateTime;
  /** Invoice PDFs in the thread. Proposed: not returned by the backend yet, so the marker hides when it is missing. */
  attachment_count?: number;
}

export interface InboxMessage extends Message {
  is_html: boolean;
  invoice_ids: string[];
}

/** GET /api/inbox/threads/{thread_id}: the summary plus every message, oldest first. */
export interface InboxThreadDetail extends InboxThreadSummary {
  messages: InboxMessage[];
}

/** One sentence of an /ask answer and the stored record that backs it. */
export interface AskClaim {
  text: string;
  evidence_id: string;
}

/**
 * A record an /ask claim cites. ids are the stored ids (evd_, cal_, inj_, aud_, bac_, ras_, pay_, inv_, msg_, ven_) or
 * synthetic ones for derived facts: rule:<hard_rule>, identity:<vendor_id>, history:amounts:<vendor_id>.
 */
export interface AskEvidence {
  id: string;
  kind: string;
  label: string;
  text: string;
  untrusted_text?: string; // untrusted
}

/** POST /api/payments/{id}/ask. Shape from backend/app/services/ask.py (not in docs/ yet). */
export interface AskAnswer {
  payment_id: string;
  question: string;
  answer: string; // plain prose, no ids; masked
  claims: AskClaim[];
  evidence: AskEvidence[];
  /** claude, or template when MOCK_CLAUDE is on or the model missed the 4.5 s deadline. */
  source: "claude" | "template";
  model: string | null;
  cached: boolean;
  elapsed_ms: number;
}

export interface StartRunResponse {
  run_id: string;
  events_url?: string;
}

export interface LaunchAttackRequest {
  attacker_name: string;
  card: AttackCard;
  payload: Record<string, unknown>;
}

export interface LaunchAttackResponse {
  attack_id: string;
  message_id?: string;
  run_id?: string;
}

export type ComponentMode = "real" | "simulated" | "mock" | "down";

export interface SystemComponentStatus {
  name: string;
  mode: ComponentMode;
  detail?: string;
}
