// Mock payment run. Reproduces what backend/app/services/run.py emits for this week's seed: same event order per
// invoice, same signal names and weights (risk.py), same call script (verify.py MockCaller), 5 invoices in flight at
// once, invoices taken in id order (so the three inv_atk_* rows come last). Result: 37 paid, 1 held, 2 blocked:
// the Summit call is denied, the poisoned PDF is quarantined, and the Northside (CEO pressure) call comes back
// unclear (verify.SEEDED_OUTCOMES), so that payment stays held for the controller.
//
// Timing is a deterministic jittered schedule per run id, scaled to about 25 seconds.

import { ApiError } from "@/lib/api-error";
import { createRng, hashSeed, type Rng } from "@/lib/mock/prng";
import {
  ATTACKER_ACCOUNTS,
  POISONED_HIDDEN_TEXT,
  accountByVendor,
  contacts,
  messages,
  openInvoices,
  vendorById,
  type OpenInvoice,
} from "@/lib/mock/seed";
import type {
  AttackLoggedEvent,
  AuditActor,
  AuditLogEntry,
  CallOutcome,
  Decision,
  HardRule,
  InjectionFinding,
  InjectionTechnique,
  Payment,
  PaymentDetail,
  PaymentRun,
  PaymentStatus,
  RiskAssessment,
  RunEvent,
  Signal,
  VerificationCall,
} from "@/lib/types";

// An event before the hub stamps id, at and run_id on it.
type Draft = DistributiveOmit<RunEvent, "id" | "at" | "run_id">;
type DistributiveOmit<T, K extends PropertyKey> = T extends unknown ? Omit<T, K> : never;

interface Step {
  t: number; // ms from run start
  event: Draft;
}

const CONCURRENCY = 5; // run.py CONCURRENCY
const DEFAULT_DURATION_MS = 25_000;
const DENIED_REASON = "Vendor denied the bank change on the verification call";
const UNCLEAR_NOTE = "verification unclear; waiting for the controller";
const QUARANTINE_REASON = "Hidden instructions detected in the document; quarantined";

// ---------- Per-invoice scripts ----------

const paymentId = (invoiceId: string) => "pay_" + invoiceId.split("_").slice(1).join("_");

function signal(rng: Rng, name: string, weight: number, detail: string): Signal {
  return { name, weight, detail, evidence_id: `evd_${rng.hex(12)}` };
}

function holdReasons(rule: string, signals: Signal[], identity: string) {
  const top = [...signals].sort((a, b) => b.weight - a.weight).slice(0, 4);
  return [`${rule}: Hold and place a verification call`, ...top.map((s) => `${s.name}: ${s.detail}`), identity];
}

/** The call verify.py's MockCaller places: agent question, then the vendor's answer and the agent's close. */
function verificationCall(
  rng: Rng,
  paymentId: string,
  vendorName: string,
  last4: string,
  outcome: "denied" | "unclear",
): { gap: number; event: Draft }[] {
  const reply =
    outcome === "denied"
      ? [
          { speaker: "vendor" as const, text: "No. We never changed banks." },
          { speaker: "agent" as const, text: "Thank you. I will not process that change and I am alerting the controller. Goodbye." },
        ]
      : [
          { speaker: "vendor" as const, text: "Sorry, who is this? I am not sure what you are asking." },
          { speaker: "agent" as const, text: "Thank you. I will pass this to a person. Goodbye." },
        ];
  const lines = [
    {
      speaker: "agent" as const,
      text:
        "Hello, this is an automated assistant calling for Ridgeline Builders accounts payable. This call is recorded. " +
        `We received a request to change where we send ${vendorName}'s payments, to an account ending ${last4}. Did your company make this change?`,
    },
    ...reply,
  ];
  // Each line arrives after roughly the time it takes to say the previous one.
  let speaking = rng.between(1100, 1600); // dialing and pickup
  return lines.map((line) => {
    const gap = speaking;
    speaking = 500 + line.text.length * rng.between(16, 21);
    return { gap, event: { type: "call.transcript", payment_id: paymentId, speaker: line.speaker, text: line.text } };
  });
}

/** What the pipeline decides for one payment, fixed when the run is scheduled. Events reveal it over time. */
interface PaymentPlan {
  score: number;
  decision: Decision;
  hardRules: HardRule[];
  signals: Signal[]; // every signal that fired, including weight-0 ones (identity check passed)
  identity: string | null;
  finding: { technique: InjectionTechnique; snippet: string; confidence: number } | null;
  callOutcome: CallOutcome | null;
}

interface Script {
  plan: PaymentPlan;
  steps: { gap: number; event: Draft }[];
}

const CLEAN_PLAN: PaymentPlan = {
  score: 0,
  decision: "auto_pay",
  hardRules: [],
  signals: [],
  identity: null,
  finding: null,
  callOutcome: null,
};

function script(inv: OpenInvoice, rng: Rng, transferNo: () => string): Script {
  const vendor = vendorById.get(inv.vendor_id)!;
  const pid = paymentId(inv.id);
  const parsed: Draft = { type: "invoice.parsed", invoice_id: inv.id, vendor: vendor.name, amount_usd: inv.amount_usd };
  const extract = rng.between(700, 1500);

  if (inv.planted === null) {
    return {
      plan: CLEAN_PLAN,
      steps: [
        { gap: extract, event: parsed },
        { gap: rng.between(180, 420), event: { type: "risk.scored", payment_id: pid, score: 0, decision: "auto_pay", top_signals: [] } },
        { gap: rng.between(250, 650), event: { type: "payment.paid", payment_id: pid, nessie_transfer_id: transferNo() } },
      ],
    };
  }

  if (inv.planted === "poisoned_pdf") {
    const plan: PaymentPlan = {
      ...CLEAN_PLAN,
      decision: "hold",
      hardRules: ["hidden_instructions"],
      finding: { technique: "white_text", snippet: POISONED_HIDDEN_TEXT, confidence: 0.97 },
    };
    return { plan, steps: [
      { gap: extract, event: parsed },
      {
        gap: rng.between(500, 900),
        event: { type: "injection.detected", invoice_id: inv.id, message_id: null, technique: "white_text", snippet: POISONED_HIDDEN_TEXT },
      },
      { gap: rng.between(150, 300), event: { type: "risk.scored", payment_id: pid, score: 0, decision: "hold", top_signals: [] } },
      { gap: 40, event: { type: "payment.blocked", payment_id: pid, reason: QUARANTINE_REASON } },
      { gap: 20, event: attackLogged(rng, "poisoned_invoice") },
    ] };
  }

  // bank_change (Summit) and ceo_pressure (Northside): destination changed, hold_and_verify, then a call.
  // Summit's call is denied and blocked; Northside's is scripted unclear by the backend and stays held.
  const outcome = inv.planted === "bank_change" ? "denied" : "unclear";
  const current = accountByVendor.get(inv.vendor_id)!.account_last4;
  const requested = inv.planted === "bank_change" ? ATTACKER_ACCOUNTS.summit.account_last4 : ATTACKER_ACCOUNTS.northside.account_last4;
  const bankChanged = signal(rng, "bank_details_changed", 30, `New account ending ${requested}; last verified ending ${current}`);
  const signals =
    inv.planted === "bank_change"
      ? [
          bankChanged,
          signal(rng, "lookalike_domain", 25, "summit-concrete.co vs summitconcrete.com"),
          signal(rng, "reply_to_mismatch", 15, "Reply-To: billing@summit-concrete.co"),
          signal(rng, "urgency_language", 15, "matched 'today'"),
          signal(rng, "first_message_from_sender", 10, "ar@summit-concrete.co not seen in vendor history"),
        ]
      : [
          bankChanged,
          signal(rng, "urgency_language", 15, "matched 'today', 'ceo approved', 'the ceo'"),
          signal(rng, "first_message_from_sender", 10, "dana.whitfield@ridgeline-builders.co not seen in vendor history"),
          signal(rng, "outside_usual_hours", 5, "Sent at 06:00 UTC, outside the vendor's usual hours"),
        ];
  const score = Math.min(100, signals.reduce((sum, s) => sum + s.weight, 0)); // 95 and 60
  const identity = `CRS identity check: verified (match ${rng.between(0.9, 0.98).toFixed(2)})`;
  // risk.py adds the identity result as a weight-0 signal when the check passes on a changed destination.
  const plan: PaymentPlan = {
    score,
    decision: "hold_and_verify",
    hardRules: ["destination_changed"],
    signals: [...signals, signal(rng, "vendor_identity_check", 0, identity)],
    identity,
    finding: null,
    callOutcome: outcome,
  };

  return { plan, steps: [
    { gap: extract, event: parsed },
    {
      gap: rng.between(600, 1000),
      event: { type: "risk.scored", payment_id: pid, score, decision: "hold_and_verify", top_signals: signals.slice(0, 4) },
    },
    { gap: 40, event: { type: "payment.held", payment_id: pid, reasons: holdReasons("destination_changed", signals, identity) } },
    { gap: 20, event: attackLogged(rng, inv.planted === "bank_change" ? "classic_bank_change" : "ceo_pressure") },
    { gap: rng.between(300, 600), event: { type: "call.started", payment_id: pid, contact_source: "on_file" } },
    ...verificationCall(rng, pid, vendor.name, requested, outcome),
    { gap: rng.between(900, 1300), event: { type: "call.outcome", payment_id: pid, outcome } },
    // Denied blocks the payment. Unclear emits nothing more: the payment stays held for the controller.
    ...(outcome === "denied"
      ? [{ gap: rng.between(120, 250), event: { type: "payment.blocked", payment_id: pid, reason: DENIED_REASON } as Draft }]
      : []),
  ] };
}

function attackLogged(rng: Rng, card: string): Draft {
  return {
    type: "attack.logged",
    attack_id: `atk_${rng.hex(12)}`,
    attacker_name: "Seeded attack",
    source: "console",
    card,
    result: "caught",
    moderation_status: "approved",
  };
}

// ---------- Schedule: 5 workers pull invoices in id order ----------

function buildSchedule(runId: string, durationMs: number): { steps: Step[]; plans: Map<string, PaymentPlan> } {
  const rng = createRng(hashSeed(runId));
  let transfers = 0;
  const transferNo = () => `nes_mock_${String(++transfers).padStart(4, "0")}`;

  const steps: Step[] = [{ t: 0, event: { type: "run.started", invoice_count: openInvoices.length } }];
  const workers = Array.from({ length: CONCURRENCY }, () => rng.between(200, 500));
  const outcome = new Map<string, PaymentStatus>();
  const plans = new Map<string, PaymentPlan>();

  for (const inv of openInvoices) {
    const w = workers.indexOf(Math.min(...workers));
    let t = workers[w];
    const { plan, steps: invoiceSteps } = script(inv, rng, transferNo);
    plans.set(paymentId(inv.id), plan);
    for (const { gap, event } of invoiceSteps) {
      t += gap;
      steps.push({ t, event });
      if (event.type === "payment.paid") outcome.set(inv.id, "paid");
      if (event.type === "payment.blocked") outcome.set(inv.id, "blocked");
      if (event.type === "payment.held") outcome.set(inv.id, "held");
    }
    workers[w] = t + rng.between(30, 120);
  }

  const end = Math.max(...steps.map((s) => s.t));
  const scale = (durationMs - 600) / end;
  for (const s of steps) s.t = Math.round(s.t * scale);

  // Totals and report, worded as run.py writes them.
  const noteFor = { bank_change: DENIED_REASON, ceo_pressure: UNCLEAR_NOTE, poisoned_pdf: QUARANTINE_REASON };
  const amountOf = (id: string) => openInvoices.find((i) => i.id === id)!.amount_usd;
  const ids = openInvoices.map((i) => i.id);
  const by = (st: PaymentStatus) => ids.filter((id) => outcome.get(id) === st);
  const paidUsd = round2(by("paid").reduce((sum, id) => sum + amountOf(id), 0));
  const blockedUsd = round2(by("blocked").reduce((sum, id) => sum + amountOf(id), 0));
  const notes = openInvoices
    .filter((i) => outcome.get(i.id) !== "paid")
    .sort((a, b) => (paymentId(a.id) < paymentId(b.id) ? -1 : 1))
    .map((i) => `${vendorById.get(i.vendor_id)!.name}: ${noteFor[i.planted ?? "bank_change"]}`);
  const totals = { paid: by("paid").length, held: by("held").length, blocked: by("blocked").length };

  steps.push(
    { t: durationMs - 300, event: { type: "run.completed", ...totals, total_usd: paidUsd } },
    {
      t: durationMs - 150,
      event: {
        type: "run.report",
        summary:
          `${ids.length} invoices processed: ${totals.paid} paid (${usd(paidUsd)}), ${totals.held} held for the controller, ` +
          `${totals.blocked} blocked (${usd(blockedUsd)} protected).`,
        ...totals,
        paid_usd: paidUsd,
        blocked_usd: blockedUsd,
        findings: notes,
      },
    },
  );
  return { steps: steps.sort((a, b) => a.t - b.t), plans };
}

// ---------- Hub: one in-flight run at a time, replay for late subscribers, like the server ----------

/** The rows the backend would hold for one payment, built up as events fire. */
interface PaymentRecord {
  payment: Payment;
  plan: PaymentPlan;
  risk: RiskAssessment | null;
  findings: InjectionFinding[];
  calls: VerificationCall[];
  audit: AuditLogEntry[];
}

interface MockRun {
  id: string;
  startedAt: string;
  completedAt: string | null;
  events: RunEvent[];
  listeners: Set<(e: RunEvent) => void>;
  timers: ReturnType<typeof setTimeout>[];
  plans: Map<string, PaymentPlan>;
  records: Map<string, PaymentRecord>;
  rng: Rng; // ids for rows and events
}

const runs = new Map<string, MockRun>();
const leaderboardListeners = new Set<(e: AttackLoggedEvent) => void>();
let active: string | null = null;

export function startMockRun(opts: { runId?: string; durationMs?: number } = {}): string {
  if (active) throw new ApiError(409, "/api/payment-runs", `A payment run is already in progress (${active})`);
  const id = opts.runId ?? `run_${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`;
  const { steps, plans } = buildSchedule(id, opts.durationMs ?? DEFAULT_DURATION_MS);
  const run: MockRun = {
    id,
    startedAt: new Date().toISOString(),
    completedAt: null,
    events: [],
    listeners: new Set(),
    timers: [],
    plans,
    records: new Map(),
    rng: createRng(hashSeed(`${id}:ids`)),
  };
  runs.set(id, run);
  active = id;

  for (const step of steps) run.timers.push(setTimeout(() => emit(run, step.event), step.t));
  return id;
}

function emit(run: MockRun, draft: Draft) {
  const event = { ...draft, id: `evt_${run.rng.hex(12)}`, run_id: run.id, at: new Date().toISOString() } as RunEvent;
  record(run, event);
  run.events.push(event);
  run.listeners.forEach((fn) => fn(event));
  if (event.type === "attack.logged") leaderboardListeners.forEach((fn) => fn(event));
  if (event.type === "run.completed") {
    run.completedAt = event.at;
    if (active === run.id) active = null;
  }
}

/** Mirror of the rows run.py and verify.py write, including the audit actions they use. */
function record(run: MockRun, e: RunEvent) {
  const audit = (rec: PaymentRecord, entity: string, entityId: string, actor: AuditActor, action: string, detail: Record<string, unknown>) =>
    rec.audit.push({ id: `aud_${run.rng.hex(12)}`, at: e.at, entity, entity_id: entityId, actor, action, detail_json: detail });

  if (e.type === "invoice.parsed") {
    const inv = openInvoices.find((i) => i.id === e.invoice_id)!;
    const pid = paymentId(inv.id);
    run.records.set(pid, {
      payment: {
        id: pid,
        run_id: run.id,
        invoice_id: inv.id,
        amount_usd: inv.amount_usd,
        destination_account_id: accountByVendor.get(inv.vendor_id)!.id,
        status: "pending",
        nessie_transfer_id: null,
      },
      plan: run.plans.get(pid)!,
      risk: null,
      findings: [],
      calls: [],
      audit: [],
    });
    return;
  }
  if (e.type === "injection.detected") {
    const rec = run.records.get(paymentId(e.invoice_id ?? ""));
    if (!rec || !rec.plan.finding) return;
    const finding: InjectionFinding = { id: `inj_${run.rng.hex(12)}`, invoice_id: e.invoice_id, message_id: e.message_id, ...rec.plan.finding };
    rec.findings.push(finding);
    audit(rec, "invoice", e.invoice_id ?? "", "agent", "quarantined", { finding_id: finding.id, technique: finding.technique });
    return;
  }
  if (!("payment_id" in e)) return;
  const rec = run.records.get(e.payment_id);
  if (!rec) return;
  const pid = e.payment_id;

  switch (e.type) {
    case "risk.scored":
      if (rec.plan.identity) audit(rec, "vendor", `ven_${vendorKey(rec)}`, "agent", "identity_check", { summary: rec.plan.identity });
      rec.risk = {
        id: `ras_${run.rng.hex(12)}`,
        payment_id: pid,
        score: rec.plan.score,
        decision: rec.plan.decision,
        hard_rules_fired: rec.plan.hardRules,
        signals_json: rec.plan.signals,
        model_version: "mock-risk-1",
      };
      audit(rec, "payment", pid, "agent", "risk_assessed", { assessment_id: rec.risk.id, score: e.score, decision: e.decision });
      break;
    case "payment.paid":
      rec.payment.status = "paid";
      rec.payment.nessie_transfer_id = e.nessie_transfer_id;
      audit(rec, "payment", pid, "agent", "paid", { transfer_id: e.nessie_transfer_id });
      break;
    case "payment.held":
      rec.payment.status = "held";
      audit(rec, "payment", pid, "agent", "held", { reason: e.reasons[0] });
      break;
    case "payment.blocked": {
      const byCall = rec.calls.some((c) => c.outcome === "denied");
      rec.payment.status = "blocked";
      audit(rec, "payment", pid, "agent", byCall ? "blocked_by_verification" : "blocked", { reason: e.reason });
      break;
    }
    case "call.started": {
      const contact = contacts.find((c) => c.vendor_id === `ven_${vendorKey(rec)}` && c.source === e.contact_source) ?? null;
      rec.calls.push({
        id: `cal_${run.rng.hex(12)}`,
        payment_id: pid,
        contact_id: contact?.id ?? null,
        started_at: e.at,
        outcome: null,
        transcript: [],
        recording_url: null,
      });
      break;
    }
    case "call.transcript":
      rec.calls.at(-1)?.transcript?.push({ speaker: e.speaker, text: e.text });
      break;
    case "call.outcome": {
      const call = rec.calls.at(-1);
      if (!call) break;
      call.outcome = e.outcome;
      audit(rec, "payment", pid, "agent", "verification_call", { call_id: call.id, outcome: e.outcome, contact_source: "on_file" });
      if (e.outcome !== "denied" && e.outcome !== "confirmed")
        audit(rec, "payment", pid, "agent", `verification_${e.outcome}`, { call_id: call.id, attempts: 1 });
      break;
    }
  }
}

function vendorKey(rec: PaymentRecord) {
  return openInvoices.find((i) => i.id === rec.payment.invoice_id)!.vendor_id.slice("ven_".length);
}

/** GET /api/payments/{id}: the newest run that has this payment. */
export function getMockPaymentDetail(pid: string): PaymentDetail | null {
  const rec = [...runs.values()].reverse().map((r) => r.records.get(pid)).find(Boolean);
  if (!rec) return null;
  const { planted: _planted, ...invoice } = openInvoices.find((i) => i.id === rec.payment.invoice_id)!;
  return {
    payment: rec.payment,
    invoice,
    vendor: vendorById.get(invoice.vendor_id)!,
    message: messages.find((m) => m.id === invoice.message_id) ?? null,
    last_verified_account: accountByVendor.get(invoice.vendor_id) ?? null,
    risk: rec.risk,
    findings: rec.findings,
    calls: rec.calls.map((c) => ({ ...c, contact: contacts.find((x) => x.id === c.contact_id) ?? null })),
    audit: [...rec.audit],
  };
}

/** POST /api/payments/{id}/approve or /reject by the controller. Only a held payment can be decided. */
export function decideMockPayment(pid: string, decision: "approve" | "reject", reason: string) {
  const run = [...runs.values()].reverse().find((r) => r.records.has(pid));
  const rec = run?.records.get(pid);
  const path = `/api/payments/${pid}/${decision}`;
  if (!run || !rec) throw new ApiError(404, path, `POST ${path} failed (404): payment not found`);
  if (rec.payment.status !== "held") throw new ApiError(409, path, `POST ${path} failed (409): payment is ${rec.payment.status}, not held`);
  if (!reason.trim()) throw new ApiError(422, path, `POST ${path} failed (422): a reason is required`);

  rec.audit.push({
    id: `aud_${run.rng.hex(12)}`,
    at: new Date().toISOString(),
    entity: "payment",
    entity_id: pid,
    actor: "human",
    action: decision === "approve" ? "approved" : "rejected",
    detail_json: { reason, by: "Dev (controller)" },
  });
  if (decision === "approve") emit(run, { type: "payment.paid", payment_id: pid, nessie_transfer_id: `nes_mock_c${run.rng.hex(3)}` });
  else emit(run, { type: "payment.blocked", payment_id: pid, reason: `Rejected by the controller: ${reason}` });
}

/** POST /api/demo/reset in mock mode: stop any run and forget every run, back to the seeded week. */
export function resetMockRuns() {
  for (const run of runs.values()) {
    run.timers.forEach(clearTimeout);
    run.listeners.clear();
  }
  runs.clear();
  active = null;
}

/** Stored events replay first, then live ones. An unknown run id starts a run under that id (deep links keep working). */
export function subscribeMockRun(runId: string, onEvent: (e: RunEvent) => void): () => void {
  let run = runs.get(runId);
  if (!run) {
    startMockRun({ runId });
    run = runs.get(runId)!;
  }
  let open = true;
  const replay = [...run.events];
  queueMicrotask(() => open && replay.forEach(onEvent));
  const live = (e: RunEvent) => open && onEvent(e);
  run.listeners.add(live);
  return () => {
    open = false;
    run.listeners.delete(live);
  };
}

export function subscribeMockLeaderboard(onEvent: (e: AttackLoggedEvent) => void): () => void {
  leaderboardListeners.add(onEvent);
  return () => leaderboardListeners.delete(onEvent);
}

export function getMockRun(runId: string): PaymentRun | null {
  const run = runs.get(runId);
  if (!run) return null;
  const done = run.events.find((e) => e.type === "run.completed");
  return {
    id: run.id,
    started_at: run.startedAt,
    completed_at: run.completedAt,
    status: done ? "completed" : "running",
    totals_json: done && done.type === "run.completed" ? { paid: done.paid, held: done.held, blocked: done.blocked, total_usd: done.total_usd } : null,
  };
}

function round2(n: number) {
  return Math.round(n * 100) / 100;
}

function usd(n: number) {
  return n.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2 });
}
