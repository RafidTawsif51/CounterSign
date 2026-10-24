// Folds a run's event stream into board rows and the activity log. Pure, so the board re-derives everything from the
// events it has and a late connection (replay) lands on the same screen as a live one.

import { formatUSD } from "@/lib/format";
import { CONTACT_SOURCES, TECHNIQUES, signalInfo } from "@/lib/risk-catalog";
import type { CallOutcome, Decision, InjectionTechnique, PaymentStatus, RunEvent } from "@/lib/types";

/** Where a row is in the pipeline. Status says where the money is; stage says what the agent is doing. */
export type RowStage = "parsed" | "scored" | "calling" | "decided";

export interface BoardRow {
  paymentId: string;
  invoiceId: string;
  vendor: string;
  amount: number;
  status: PaymentStatus;
  stage: RowStage;
  score: number | null;
  decision: Decision | null;
  /** Requested last four, from the bank_details_changed signal. Null when the destination did not change. */
  changedTo: string | null;
  technique: InjectionTechnique | null;
  callOutcome: CallOutcome | null;
  updatedAt: string;
}

export type ActivityTone = "neutral" | PaymentStatus;

export interface ActivityEntry {
  id: string;
  at: string;
  text: string;
  tone: ActivityTone;
  paymentId: string | null;
  /** A vendor's words on the call. Untrusted text: render as plain text. */
  quote?: string;
}

export interface BoardState {
  /** Newest first: the order rows appear on the board. */
  rows: BoardRow[];
  activity: ActivityEntry[];
  startedAt: string | null;
  invoiceCount: number | null;
}

/** The short, evidence-first reason a payment was held: its two heaviest signals in plain words. */
function heldBecause(row: BoardRow, signals: { name: string; weight: number }[]) {
  const top = [...signals]
    .filter((s) => s.weight > 0)
    .sort((a, b) => b.weight - a.weight)
    .slice(0, 2)
    .map((s) => signalInfo(s.name).label.toLowerCase());
  if (row.changedTo) top[0] = `new bank account ending ${row.changedTo}`;
  return top.join(", ");
}

/** `attack`: the events are an attack's mini-run, whose run.started and run.completed lines would read as a second run. */
export function foldBoard(events: RunEvent[], opts: { attack?: boolean } = {}): BoardState {
  const rows = new Map<string, BoardRow>();
  const order: string[] = [];
  const activity: ActivityEntry[] = [];
  const signalsBy = new Map<string, { name: string; weight: number }[]>();
  let startedAt: string | null = null;
  let invoiceCount: number | null = null;

  const log = (e: RunEvent, text: string, tone: ActivityTone, paymentId: string | null, quote?: string) =>
    activity.push({ id: e.id, at: e.at, text, tone, paymentId, quote });
  const money = (row: BoardRow) => `${row.vendor} ${formatUSD(row.amount)}`;

  for (const e of events) {
    if (e.type === "run.started") {
      startedAt = e.at;
      invoiceCount = e.invoice_count;
      if (!opts.attack) log(e, `Started the payment run over ${e.invoice_count} open invoices`, "neutral", null);
      continue;
    }
    if (e.type === "attack.logged" && e.result === null) {
      log(e, `Received an attack from ${e.attacker_name}; it goes through the same checks as every invoice`, "neutral", null);
      continue;
    }
    if (e.type === "attack.queued") {
      log(e, `Queued the attack behind the run in progress (position ${e.position})`, "neutral", null);
      continue;
    }
    if (e.type === "run.completed") {
      if (!opts.attack) log(e, `Run complete: ${e.paid} paid (${formatUSD(e.total_usd)}), ${e.held} held, ${e.blocked} blocked`, "neutral", null);
      continue;
    }
    if (e.type === "invoice.parsed") {
      const pid = e.payment_id;
      if (!rows.has(pid)) order.push(pid);
      rows.set(pid, {
        paymentId: pid,
        invoiceId: e.invoice_id,
        vendor: e.vendor,
        amount: e.amount_usd,
        status: "pending",
        stage: "parsed",
        score: null,
        decision: null,
        changedTo: null,
        technique: null,
        callOutcome: null,
        updatedAt: e.at,
      });
      continue;
    }
    if (e.type === "injection.detected") {
      const row = e.payment_id ? rows.get(e.payment_id) : undefined;
      if (!row) continue;
      row.technique = e.technique;
      row.updatedAt = e.at;
      log(e, `Found hidden instructions in ${row.vendor}'s invoice (${TECHNIQUES[e.technique].toLowerCase()})`, "neutral", row.paymentId);
      continue;
    }
    if (!("payment_id" in e)) continue;
    const row = rows.get(e.payment_id);
    if (!row) continue;
    row.updatedAt = e.at;

    switch (e.type) {
      case "risk.scored": {
        row.score = e.score;
        row.decision = e.decision;
        row.stage = "scored";
        signalsBy.set(row.paymentId, e.top_signals);
        const bank = e.top_signals.find((s) => s.name === "bank_details_changed");
        row.changedTo = bank?.detail.match(/ending (\d{4})/)?.[1] ?? null;
        break;
      }
      case "payment.paid":
        row.status = "paid";
        row.stage = "decided";
        log(e, `Paid ${money(row)}`, "paid", row.paymentId);
        break;
      case "payment.held":
        row.status = "held";
        log(e, `Held ${money(row)}: ${heldBecause(row, signalsBy.get(row.paymentId) ?? [])}`, "held", row.paymentId);
        break;
      case "call.started":
        row.stage = "calling";
        log(e, `Calling ${row.vendor} at the ${CONTACT_SOURCES[e.contact_source]}, not the number in the email`, "neutral", row.paymentId);
        break;
      case "call.transcript":
        if (e.speaker === "vendor") log(e, `${row.vendor} on the call`, "neutral", row.paymentId, e.text);
        break;
      case "call.outcome":
        row.callOutcome = e.outcome;
        row.stage = "decided";
        if (e.outcome === "unclear")
          log(e, `Call to ${row.vendor} was unclear; kept on hold for Dev to review`, "held", row.paymentId);
        if (e.outcome === "no_answer") log(e, `${row.vendor} did not answer; kept on hold`, "held", row.paymentId);
        if (e.outcome === "confirmed") log(e, `${row.vendor} confirmed the bank change on the call`, "neutral", row.paymentId);
        break;
      case "payment.blocked":
        row.status = "blocked";
        row.stage = "decided";
        log(e, `Blocked ${money(row)}: ${blockedBecause(row, e.reason)}`, "blocked", row.paymentId);
        break;
    }
  }

  return {
    rows: order.map((id) => rows.get(id)!).reverse(),
    activity,
    startedAt,
    invoiceCount,
  };
}

function blockedBecause(row: BoardRow, reason: string) {
  if (row.callOutcome === "denied") return "vendor denied the bank change on the call";
  if (row.technique) return "hidden instructions in the invoice, document quarantined";
  return reason;
}

/** The decision column, in the agent's own words. */
export function decisionLabel(row: BoardRow): string {
  if (row.stage === "parsed") return row.technique ? "Quarantining" : "Scoring";
  if (row.stage === "calling") return "Calling vendor…";
  if (row.status === "paid") return row.decision === "auto_pay" || !row.decision ? "Auto-paid" : "Paid after review";
  if (row.status === "blocked") {
    if (row.callOutcome === "denied") return "Denied on call";
    if (row.technique) return "Quarantined";
    return "Blocked";
  }
  if (row.status === "held") {
    if (row.callOutcome === "unclear") return "Unclear call";
    if (row.callOutcome === "no_answer") return "No answer";
    if (row.decision === "hold_and_verify") return "Verifying by phone";
    return "Controller review";
  }
  return row.decision === "auto_pay" ? "Paying" : "Holding";
}
