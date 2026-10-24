// Folds a run's event stream into the numbers the shell and board show.

import type { PaymentStatus, RunEvent } from "@/lib/types";

export interface RunSummary {
  invoiceCount: number | null;
  /** Payments with a decision: paid, held or blocked. */
  processed: number;
  paid: number;
  held: number;
  blocked: number;
  paidUsd: number;
  completed: boolean;
}

export function summarizeRun(events: RunEvent[]): RunSummary {
  let invoiceCount: number | null = null;
  let completed = false;
  const status = new Map<string, PaymentStatus>();
  const amount = new Map<string, number>(); // by payment id, from invoice.parsed

  for (const e of events) {
    switch (e.type) {
      case "run.started":
        invoiceCount = e.invoice_count;
        break;
      case "invoice.parsed":
        amount.set(e.payment_id, e.amount_usd);
        break;
      case "payment.paid":
        status.set(e.payment_id, "paid");
        break;
      case "payment.held":
        status.set(e.payment_id, "held");
        break;
      case "payment.blocked":
        status.set(e.payment_id, "blocked");
        break;
      case "run.completed":
        completed = true;
        break;
    }
  }

  const count = (s: PaymentStatus) => [...status.values()].filter((v) => v === s).length;
  let paidUsd = 0;
  for (const [pid, s] of status) if (s === "paid") paidUsd += amount.get(pid) ?? 0;

  return {
    invoiceCount,
    processed: status.size,
    paid: count("paid"),
    held: count("held"),
    blocked: count("blocked"),
    paidUsd: Math.round(paidUsd * 100) / 100,
    completed,
  };
}
