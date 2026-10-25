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
/** "seeded": the three planted attacks, logged on the run but never listed or counted on the leaderboard. */
export type AttackSource = "console" | "judge" | "bounty_email" | "seeded";
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

// Hard rules from risk.py. amount_over_max is "more than 30% above the 12-month max" (the spec says 50%; see risk.AMOUNT_OVER_MAX_FACTOR).
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
  /** PDF findings only: 1-based page, box [x0, top, x1, bottom] in PDF points from the top left, and the page size.
   *  Off-page text keeps its real coordinates, so the box can lie outside the page. Null for email findings. */
  page?: number | null;
  bbox?: [number, number, number, number] | null;
  page_width?: number | null;
  page_height?: number | null;
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
  /** The id its payment has (or will have). Never derive it from invoice_id. */
  payment_id: string;
  vendor: string;
  amount_usd: number;
}
export interface InjectionDetectedEvent extends EventBase {
  type: "injection.detected";
  invoice_id: string | null;
  /** Set when the finding is in an invoice. */
  payment_id: string | null;
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
  /** "mock_fallback": Nessie failed and the id is a mock. Missing on events from before the field existed. */
  transfer_mode?: TransferMode | null;
}
/** The controller approved or rejected a held payment; payment.paid or payment.blocked follows. */
export interface PaymentReviewedEvent extends EventBase {
  type: "payment.reviewed";
  payment_id: string;
  decision: "approved" | "rejected";
  approver: string;
  reason: string; // untrusted
}
/** A verification call finished after run.completed and moved a payment. Carries the run's new totals. */
export interface RunUpdatedEvent extends EventBase {
  type: "run.updated";
  payment_id: string;
  status: PaymentStatus;
  paid: number;
  held: number;
  blocked: number;
  total_usd: number;
  blocked_usd: number;
}
/** POST /api/demo/reset finished. Sent on the leaderboard channel. */
export interface DemoResetEvent extends EventBase {
  type: "demo.reset";
  kept_leaderboard: boolean;
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
  /** The page of the vendor's own website that shows the number: Apify Vendor Contact Verifier's proof. Null for an on-file number alone. */
  source_url?: string | null;
  confidence?: "high" | "medium" | "low" | null;
  agreement?: "consistent" | "conflicting" | "none_found" | null;
  /** The website's number and the number on file are the same number. Null when the website gave no usable number. */
  sources_agree?: boolean | null;
  /** Why the call went where it did, for example "contact sources disagree". They never release a hold. */
  hold_reasons?: string[];
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
  /** The controller report (services/report.py): plain text, Claude-written when it worked, else the summary again. Absent on older events. */
  report?: string | null;
  report_source?: "claude" | "basic" | null;
  /** paid, stopped, protected (strings) and needs_decision (list); null for a basic report. Built from structured fields only. */
  sections?: { paid: string; stopped: string; needs_decision: string[]; protected: string } | null;
  held_usd?: number | null;
  /** True when sent again after the run because a late call outcome changed it; the newest run.report wins. */
  updated?: boolean;
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

export interface AttackQueuedEvent extends EventBase {
  type: "attack.queued";
  attack_id: string;
  position: number;
  waiting_for: string | null;
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
  | AttackLoggedEvent
  | AttackQueuedEvent
  | PaymentReviewedEvent
  | RunUpdatedEvent
  | DemoResetEvent;

export type RunEventType = RunEvent["type"];

// ---------- API responses ----------
// Shapes below are taken from the backend's route code (docs/ does not cover them yet) and checked against a live run.

/** How a transfer went out (payments.py): "nessie" sandbox, "mock" adapter, or "mock_fallback" when Nessie failed. */
export type TransferMode = "nessie" | "mock" | "mock_fallback";

/** 200 from POST /api/payments/{id}/approve or /reject. */
export interface ReviewResult {
  payment_id: string;
  status: PaymentStatus;
  nessie_transfer_id?: string;
  transfer_mode?: TransferMode | null;
  paid_account_last4?: string;
  invoice_asked_for_a_different_account?: boolean;
}

/** A bank account as the payment detail shows it. `trusted` is false for an account that only came from a payment request. */
export interface AccountView {
  id: string;
  bank_name: string;
  account_last4: string;
  valid_from: ISODateTime;
  valid_to: ISODateTime | null;
  verified_by_call_id: string | null;
  trusted: boolean;
}

/** A verification call with the number dialed (masked to the last four) and where that number came from. */
export interface PaymentCall {
  id: string;
  payment_id: string;
  started_at: ISODateTime;
  outcome: CallOutcome | null;
  transcript: TranscriptLine[]; // untrusted (vendor speech)
  recording_url: string | null;
  contact: { id: string; source: ContactSource; source_url: string | null; phone: string } | null;
}

export interface AuditEntry {
  id: string;
  at: ISODateTime;
  entity: string;
  entity_id: string;
  actor: AuditActor;
  action: string;
  detail: Record<string, unknown> | null; // may quote untrusted text
}

/** GET /api/payments/{id}. Shape from backend/app/services/review.py. */
export interface PaymentDetail {
  payment: {
    id: string;
    run_id: string;
    status: PaymentStatus;
    amount_usd: number;
    nessie_transfer_id: string | null;
    transfer_mode: TransferMode | null;
    /** Where the payment points: the verified account, or the unverified one an invoice asked for. */
    destination: AccountView | null;
    /** The vendor's verified account (verify.open_verified_account). */
    last_verified_account: AccountView | null;
    /** Approving always pays this account, never the requested one. */
    approve_pays: AccountView | null;
  };
  /** Null only for a payment whose invoice row is gone. */
  invoice: {
    id: string;
    number: string | null;
    amount_usd: number | null;
    due_date: ISODate | null;
    has_pdf: boolean;
    /** The bank details the invoice or email asked for, hash and last four only. */
    requested_remittance: Partial<RemittanceDetails> | null;
    requested_account_differs_from_verified: boolean;
    quarantined: boolean;
    extraction_status: string | null;
  } | null;
  /** Null for an uploaded PDF that has no vendor yet. */
  vendor: (Vendor & { identity: IdentityResult | null }) | null;
  /** The email that carried the invoice. Untrusted text. */
  message: Pick<Message, "id" | "thread_id" | "from_addr" | "reply_to" | "subject" | "body" | "received_at" | "is_attack"> | null;
  risk: {
    id: string;
    score: number;
    decision: Decision;
    hard_rules_fired: (HardRule | string)[];
    hard_rule_actions: Record<string, string | null>;
    signals: Signal[];
    model_version: string;
    /** The hold reasons in one line each, hard rules first. */
    reasons: string[];
  } | null;
  injection_findings: InjectionFinding[];
  identity: IdentityResult | null;
  calls: PaymentCall[];
  audit: AuditEntry[];
  /** What the controller may do now, and why not. */
  actions: { can_approve: boolean; approve_blocked_reason: string | null; can_reject: boolean };
  /** What the independent number check (Apify Vendor Contact Verifier) found for the verification call. Null before a call is prepared. */
  independent_contact: IndependentContact | null;
}

export interface HoldReason {
  reason: string;
  detail: string;
  evidence_id: string;
}

export interface IndependentContact {
  provider: string;
  evidence_id: string;
  checked_at: ISODateTime;
  /** found: a usable number. not_usable: none, conflicting or low confidence. unavailable: Apify failed. no_website: nothing to check. */
  status: "found" | "not_usable" | "unavailable" | "no_website";
  /** The number the call used, masked. */
  number: string | null;
  number_source: ContactSource | null;
  source_url: string | null;
  confidence: "high" | "medium" | "low" | null;
  agreement: "consistent" | "conflicting" | "none_found" | null;
  confidence_reason: string | null;
  sources_agree: boolean | null;
  cached: boolean | null;
  actor_run_id: string | null;
  hold_reasons: HoldReason[];
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
  /** Invoice PDFs in the thread. */
  attachment_count: number;
}

export interface InboxMessage extends Message {
  is_html: boolean;
  invoice_ids: string[];
  /** The invoices attached to this message, with the payment id each has (or will have). */
  invoices: { id: string; payment_id: string; has_pdf: boolean }[];
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

/** 202 from POST /api/payment-runs (run.py start_run). */
export interface StartRunResponse {
  run_id: string;
  invoice_count: number;
  events_url: string;
}

/** GET /api/payment-runs/{id} (run.py get_run). Totals are computed from the payments, so they are live mid-run. */
export interface RunStatusResponse {
  id: string;
  status: RunStatus;
  started_at: ISODateTime;
  completed_at: ISODateTime | null;
  invoice_count: number | null;
  totals: { paid: number; held: number; blocked: number; pending: number; total_usd: number; blocked_usd: number };
  wall_seconds: number | null;
  timings_ms: Record<string, number> | null;
}

/** 201 from POST /api/invoices/upload (ingest.py). */
export interface UploadResult {
  invoice_id: string;
  payment_id: string;
  message_id: string | null;
  vendor_id: string | null;
  size_bytes: number;
}

/** GET /api/health (main.py). `mocks` is every MOCK_* flag, true when that component runs on its mock. */
export interface HealthResponse {
  status: "ok";
  database: "sqlite" | "postgres";
  mocks: Record<string, boolean>;
}

/** POST /api/attacks body (backend services/attacks.py AttackIn). The vendor always comes from thread_id. */
export interface LaunchAttackRequest {
  attacker_name: string;
  card: AttackCard;
  source?: "console" | "judge";
  payload: {
    thread_id?: string;
    from_addr: string;
    reply_to?: string;
    subject: string;
    body: string;
    /** A file name in backend/seed/invoices (poisoned_invoice and freestyle only). */
    pdf?: string;
    /** Or the PDF itself, base64, up to 5 MB. Not both. */
    pdf_base64?: string;
  };
}

/**
 * 201 from POST /api/attacks. Every attack runs as its own mini-run (run_id); while a full run is on it waits its turn
 * (queued, position 1 = next).
 */
export interface LaunchAttackResponse {
  attack_id: string;
  message_id: string;
  invoice_id: string;
  /** The id the attack's payment has once the mini-run reads the invoice. */
  payment_id: string;
  run_id: string;
  queued: boolean;
  position: number;
  waiting_for: string | null;
}

// ---------- Leaderboard ----------

/** One row of GET /api/attacks/leaderboard (backend attacks.leaderboard_row). Bounty handles arrive masked. */
export interface LeaderboardRow {
  id: string;
  handle: string;
  source: AttackSource;
  card: AttackCard | string;
  /** null while the attack is still being processed. */
  result: AttackResult | null;
  outcome: string;
  top_reasons: string[];
  amount_usd: number | null;
  /** Sandbox dollars the attack got paid out. */
  paid_usd: number;
  /** Null for a bounty email that is not approved yet. */
  payment_id: string | null;
  created_at: ISODateTime;
  moderation_status: ModerationStatus;
  /** The attack text, only once moderation approved it. Untrusted. */
  text: { subject: string | null; from_addr: string | null; body: string; has_pdf: boolean } | null;
}

export interface LeaderboardResponse {
  /** Newest first. Seeded attacks never appear. */
  attempts: LeaderboardRow[];
  totals: {
    attempts: number;
    unique_attackers: number;
    /** Paid out on missed attacks, sandbox money. */
    sandbox_usd_moved: number;
    caught: number;
    missed: number;
    pending_result: number;
    by_card: Record<string, number>;
  };
}

// ---------- Red team ----------

export type RedTeamFamily = "bank_change" | "poisoned_invoice" | "ceo_pressure" | "lookalike_domain" | "amount_padding";

/**
 * GET /api/redteam/results (backend/app/redteam/api.py). The backend returns exactly these keys and no others; the fuller
 * results (per-case rows, usage, method notes) are in demo/redteam-results.json. 404 until a measured run has finished.
 * Metrics follow CLAUDE.md "Red-team harness".
 */
export interface RedTeamResults {
  /** "mock" until a measured run exists, so the page can say the numbers are samples. */
  source: "mock" | "measured";
  generated_at: ISODateTime;
  families: {
    family: RedTeamFamily;
    attacks: number;
    caught_baseline: number;
    caught_countersign: number;
    /** Clean invoices mixed into this family's batch, and how many each agent held or blocked anyway. */
    clean_invoices: number;
    false_positives_baseline: number;
    false_positives_countersign: number;
    /** Paid to an account the attacker controls. A miss that pays the real vendor's verified account is not counted. */
    lost_to_scammers_usd_baseline: number;
    lost_to_scammers_usd_countersign: number;
  }[];
  legit_changes: { total: number; handled_countersign: number };
  median_run_seconds: { baseline: number; countersign: number };
}

/**
 * Real: runs live. Sandboxed: a provider's sandbox (sandbox money, test identities). Simulated: generated demo data, or a
 * provider sandbox as the server labels it. Mock: the server runs this component on its mock right now (its MOCK_* flag).
 * Degraded: the live provider is failing and the component is falling back (Apify lookups). The server sends all five;
 * the documented list uses sandboxed for Nessie and CRS.
 */
export type ComponentMode = "real" | "sandboxed" | "simulated" | "mock" | "degraded";

/**
 * One row of GET /api/system/status (backend/app/services/status.py). If the route fails, /status shows the documented
 * list (lib/system-status.ts) with GET /api/health's mock flags on top.
 */
export interface SystemComponentStatus {
  name: string;
  mode: ComponentMode;
  /** One line: what it does and how we know. */
  detail: string;
  /** The MOCK_* flags (health's keys) that put this component on its mock when true. Documented list only. */
  mock_flags?: string[];
  /** ISO time of the last successful call, when the component reports one. */
  last_success_at?: string | null;
}
