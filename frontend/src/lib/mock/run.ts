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
  openInvoices,
  vendorById,
  type OpenInvoice,
} from "@/lib/mock/seed";
import type { AttackLoggedEvent, PaymentRun, PaymentStatus, RunEvent, Signal } from "@/lib/types";

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

function script(inv: OpenInvoice, rng: Rng, transferNo: () => string): { gap: number; event: Draft }[] {
  const vendor = vendorById.get(inv.vendor_id)!;
  const pid = paymentId(inv.id);
  const parsed: Draft = { type: "invoice.parsed", invoice_id: inv.id, vendor: vendor.name, amount_usd: inv.amount_usd };
  const extract = rng.between(700, 1500);

  if (inv.planted === null) {
    return [
      { gap: extract, event: parsed },
      { gap: rng.between(180, 420), event: { type: "risk.scored", payment_id: pid, score: 0, decision: "auto_pay", top_signals: [] } },
      { gap: rng.between(250, 650), event: { type: "payment.paid", payment_id: pid, nessie_transfer_id: transferNo() } },
    ];
  }

  if (inv.planted === "poisoned_pdf") {
    return [
      { gap: extract, event: parsed },
      {
        gap: rng.between(500, 900),
        event: { type: "injection.detected", invoice_id: inv.id, message_id: null, technique: "white_text", snippet: POISONED_HIDDEN_TEXT },
      },
      { gap: rng.between(150, 300), event: { type: "risk.scored", payment_id: pid, score: 0, decision: "hold", top_signals: [] } },
      { gap: 40, event: { type: "payment.blocked", payment_id: pid, reason: QUARANTINE_REASON } },
      { gap: 20, event: attackLogged(rng, "poisoned_invoice") },
    ];
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

  return [
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
  ];
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

function buildSchedule(runId: string, durationMs: number): Step[] {
  const rng = createRng(hashSeed(runId));
  let transfers = 0;
  const transferNo = () => `nes_mock_${String(++transfers).padStart(4, "0")}`;

  const steps: Step[] = [{ t: 0, event: { type: "run.started", invoice_count: openInvoices.length } }];
  const workers = Array.from({ length: CONCURRENCY }, () => rng.between(200, 500));
  const outcome = new Map<string, PaymentStatus>();

  for (const inv of openInvoices) {
    const w = workers.indexOf(Math.min(...workers));
    let t = workers[w];
    for (const { gap, event } of script(inv, rng, transferNo)) {
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
  return steps.sort((a, b) => a.t - b.t);
}

// ---------- Hub: one in-flight run at a time, replay for late subscribers, like the server ----------

interface MockRun {
  id: string;
  startedAt: string;
  completedAt: string | null;
  events: RunEvent[];
  listeners: Set<(e: RunEvent) => void>;
  timers: ReturnType<typeof setTimeout>[];
}

const runs = new Map<string, MockRun>();
const leaderboardListeners = new Set<(e: AttackLoggedEvent) => void>();
let active: string | null = null;

export function startMockRun(opts: { runId?: string; durationMs?: number } = {}): string {
  if (active) throw new ApiError(409, "/api/payment-runs", `A payment run is already in progress (${active})`);
  const id = opts.runId ?? `run_${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`;
  const run: MockRun = { id, startedAt: new Date().toISOString(), completedAt: null, events: [], listeners: new Set(), timers: [] };
  runs.set(id, run);
  active = id;

  const rng = createRng(hashSeed(`${id}:ids`));
  for (const step of buildSchedule(id, opts.durationMs ?? DEFAULT_DURATION_MS)) {
    const timer = setTimeout(() => {
      const event = { ...step.event, id: `evt_${rng.hex(12)}`, run_id: id, at: new Date().toISOString() } as RunEvent;
      run.events.push(event);
      run.listeners.forEach((fn) => fn(event));
      if (event.type === "attack.logged") leaderboardListeners.forEach((fn) => fn(event));
      if (event.type === "run.completed") {
        run.completedAt = event.at;
        active = null;
      }
    }, step.t);
    run.timers.push(timer);
  }
  return id;
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
