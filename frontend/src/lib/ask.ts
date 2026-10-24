// Helpers for "Ask about this payment": suggested questions, and finding the drawer element each citation points at.

import type { AskClaim, PaymentDetail, PaymentStatus } from "@/lib/types";

/** The spec's budget for an answer. */
export const ASK_BUDGET_MS = 5000;

/** Suggested questions. The first one follows the payment's actual status. */
export function suggestedQuestions(status: PaymentStatus): string[] {
  const why = {
    blocked: "Why was this blocked?",
    held: "Why was this held?",
    paid: "Why was this paid?",
    pending: "Why is this still pending?",
  }[status];
  const second = status === "paid" ? "What did the risk check look at?" : "What would make this safe to pay?";
  return [why, second, "Has this vendor changed banks before?"];
}

const STOP = new Set(["that", "this", "with", "from", "were", "have", "been", "would", "which", "their", "there", "than", "then", "into", "only"]);

function words(text: string): Set<string> {
  return new Set(
    text
      .toLowerCase()
      .replace(/[^a-z0-9\s]/g, " ")
      .split(/\s+/)
      .filter((w) => (w.length > 3 || /^\d{4}$/.test(w)) && !STOP.has(w)),
  );
}

function overlap(a: Set<string>, b: Set<string>) {
  let n = 0;
  for (const w of a) if (b.has(w)) n++;
  return n;
}

/**
 * The drawer element a cited id lights up. Most ids are registered by the drawer as they are. Derived ids map to what
 * shows them: a hard rule to the risk assessment rows, the identity check to its signal, a call to the transcript line
 * that best matches the claim (`cal_x#2`) so the chip lands on the words that were said.
 */
export function drawerTarget(evidenceId: string, claim: AskClaim, detail: PaymentDetail): string {
  if (evidenceId.startsWith("rule:")) return detail.risk?.id ?? evidenceId;
  if (evidenceId.startsWith("identity:"))
    return detail.risk?.signals.find((s) => s.name === "vendor_identity_check")?.evidence_id ?? evidenceId;
  if (evidenceId.startsWith("cal_")) {
    const call = detail.calls.find((c) => c.id === evidenceId);
    const lines = call?.transcript ?? [];
    const bag = words(claim.text);
    let best = -1;
    let bestScore = 1; // at least two shared words, or the whole call
    lines.forEach((l, i) => {
      const score = overlap(words(l.text), bag) + (l.speaker === "vendor" ? 0.5 : 0);
      if (score > bestScore) [best, bestScore] = [i, score];
    });
    return best >= 0 ? `${evidenceId}#${best}` : evidenceId;
  }
  return evidenceId;
}
