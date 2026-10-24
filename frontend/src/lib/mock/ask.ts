// Mock POST /api/payments/{id}/ask. Same response shape as backend/app/services/ask.py. The three planted attacks get
// written answers built from the payment's own records (so every cited id exists in the drawer); anything else gets the
// backend's template answer. Each claim is a full sentence: the drawer renders the answer from the claims, in order.
// Latency is simulated, deterministic per question, inside the 5 s budget.

import { ApiError } from "@/lib/api-error";
import { hashSeed } from "@/lib/mock/prng";
import { getMockPaymentDetail } from "@/lib/mock/run";
import { formatAccount, formatUSD } from "@/lib/format";
import { HARD_RULES, SIGNALS } from "@/lib/risk-catalog";
import type { AskAnswer, AskClaim, AskEvidence, HardRule, PaymentDetail } from "@/lib/types";

const NO_ANSWER = "The stored evidence for this payment does not answer that question.";

type Intent = "why" | "safe" | "history" | "action" | "none";

function intentOf(question: string): Intent {
  const q = question.toLowerCase();
  if (/\b(approve|release|ignore|override|pay it|unblock)\b/.test(q) && !/\bwhat would\b/.test(q)) return "action";
  if (/\b(changed banks|bank change|banks before|accounts? before|bank history|previous account)\b/.test(q)) return "history";
  if (/\b(safe|what would|how (do|can|could) (we|i)|make this)\b/.test(q)) return "safe";
  if (/\b(why|how come|reason|explain|held|hold|blocked|block|paid|score|risk|look at)\b/.test(q)) return "why";
  return "none";
}

/** Claim sentences in reading order. Null ids are dropped, like the backend drops claims whose evidence does not exist. */
type Draft = [string, string | null | undefined][];

const last4 = (v: string | null | undefined) => formatAccount(v).slice(-4);

/** What the drawer's records say, gathered once so every answer reads from the same facts. */
function facts(d: PaymentDetail) {
  const signal = (name: string) => d.risk?.signals_json.find((s) => s.name === name && s.weight > 0);
  const call = d.calls.at(-1);
  return {
    d,
    signal,
    call,
    audit: (action: string) => d.audit.find((a) => a.action === action),
    finding: d.findings[0],
    verified: d.last_verified_account,
    verified4: last4(d.last_verified_account?.account_last4),
    requested: (d.invoice.remittance_json as { account_last4?: string } | null)?.account_last4 ?? null,
    vendorLine: call?.transcript?.find((l) => l.speaker === "vendor")?.text ?? null,
  };
}

type Facts = ReturnType<typeof facts>;

function bankHistory(f: Facts): Draft {
  const { d, verified } = f;
  if (!verified) return [];
  const onFile: Draft[number] = [
    `No. ${d.vendor.name} has one account on file, ending ${f.verified4} at ${verified.bank_name}, verified at onboarding in January 2025.`,
    verified.id,
  ];
  const bank = f.signal("bank_details_changed");
  if (bank && f.requested)
    return [onFile, [`The account ending ${f.requested} on this invoice was requested only by the email and has never been verified by a call.`, bank.evidence_id]];
  if (f.finding)
    return [onFile, ["This invoice pays that same account; only the hidden text in the PDF tried to reroute it, and it was ignored.", f.finding.id]];
  return [onFile];
}

function attackAnswer(f: Facts, intent: Intent): Draft | null {
  const { d, call } = f;
  const kind = d.findings.length ? "poisoned" : call?.outcome === "denied" ? "denied" : call?.outcome === "unclear" ? "unclear" : null;
  if (!kind) return null;
  if (intent === "history") return bankHistory(f);
  const bank = f.signal("bank_details_changed");

  if (kind === "denied") {
    if (intent === "why")
      return [
        [`It was blocked because ${d.vendor.name} told our verification call: "${f.vendorLine}"`, call!.id],
        [`The invoice asked to pay a new account ending ${f.requested} instead of the verified account ending ${f.verified4}, so the payment was held and the vendor was called at the number on file, not a number from the email.`, bank?.evidence_id],
        ["The request also came from summit-concrete.co, a lookalike of the vendor's real domain summitconcrete.com.", f.signal("lookalike_domain")?.evidence_id],
        ["The payment was blocked right after the call and the controller was alerted.", f.audit("blocked_by_verification")?.id],
      ];
    return [
      ["Nothing can make the new account safe now: the vendor denied the change on the call, so the request is treated as fraud.", call!.id],
      [`The invoice itself is safe to pay only to the verified account ending ${f.verified4}, and only Dev can approve that.`, f.verified?.id],
    ];
  }

  if (kind === "poisoned") {
    const finding = f.finding!;
    if (intent === "why")
      return [
        ["It was blocked because the invoice PDF hides white text telling an AI assistant to change the remittance details and approve the payment.", finding.id],
        ["Hidden instructions trigger a hard rule, so the document was quarantined whatever the score.", "rule:hidden_instructions"],
        [`The score itself was ${d.risk?.score ?? 0}: the sender, amount and account all match ${d.vendor.name}'s history.`, d.risk?.id],
      ];
    return [
      [`A clean copy of the invoice, without hidden text, sent from ${d.vendor.name}'s usual address; the quarantined PDF itself is never paid.`, finding.id],
      [`The amount and the account ending ${f.verified4} match the vendor's history, so a clean resubmission would pass.`, f.verified?.id],
    ];
  }

  // unclear: the CEO-pressure payment
  const urgency = f.signal("urgency_language");
  if (intent === "why")
    return [
      [`It is held because the invoice would pay a new account ending ${f.requested} instead of the verified account ending ${f.verified4}.`, bank?.evidence_id],
      ['The email pushed for speed with "CEO approved" and "today".', urgency?.evidence_id],
      [`It came from an address ${d.vendor.name} has never used.`, f.signal("first_message_from_sender")?.evidence_id],
      [`On the verification call to the number on file the vendor said "${f.vendorLine}", so the payment waits for Dev.`, call!.id],
    ];
  return [
    ["The vendor would have to confirm the new account on a call to an independently found number; only then does the verification service record it.", call!.id],
    ["A CEO's approval in an email does not count, because proof has to come from outside the channel that asked.", urgency?.evidence_id],
    [`Until then Dev can release it only to the verified account ending ${f.verified4}.`, f.verified?.id],
  ];
}

/** backend ask.template_answer, for every payment that is not a planted attack. */
function templateAnswer(f: Facts, intent: Intent): Draft {
  const { d } = f;
  const status = d.payment.status;
  if (intent === "none") return [];
  const draft: Draft = [[`This payment of ${formatUSD(d.payment.amount_usd)} is ${status}.`, d.payment.id]];
  for (const r of (d.risk?.hard_rules_fired ?? []) as HardRule[])
    draft.push([`A hard rule applied: ${(HARD_RULES[r]?.label ?? r).toLowerCase()}.`, `rule:${r}`]);
  const fired = (d.risk?.signals_json ?? []).filter((s) => s.weight > 0).sort((a, b) => b.weight - a.weight).slice(0, 2);
  for (const s of fired) draft.push([`Risk signal: ${(SIGNALS[s.name]?.label ?? s.name).toLowerCase()} (${s.detail}).`, s.evidence_id]);
  if (!fired.length && !d.risk?.hard_rules_fired.length && status === "paid" && d.risk)
    draft.push(["No hard rule fired and no risk signal added to the score.", d.risk.id]);
  return draft;
}

function evidenceFor(d: PaymentDetail, id: string): AskEvidence | null {
  const signal = d.risk?.signals_json.find((s) => s.evidence_id === id);
  if (signal) return { id, kind: "signal", label: `Signal: ${signal.name}`, text: `Signal ${signal.name}, weight ${signal.weight}: ${signal.detail}` };
  if (id.startsWith("rule:")) return { id, kind: "hard_rule", label: `Hard rule: ${id.slice(5)}`, text: HARD_RULES[id.slice(5) as HardRule]?.label ?? id };
  if (d.risk?.id === id) return { id, kind: "risk_assessment", label: "The risk assessment", text: `Risk score ${d.risk.score} of 100, decision ${d.risk.decision}.` };
  const finding = d.findings.find((x) => x.id === id);
  if (finding) return { id, kind: "injection_finding", label: `Injection finding: ${finding.technique}`, text: `Detected ${finding.technique} with confidence ${finding.confidence.toFixed(2)}.`, untrusted_text: finding.snippet };
  const call = d.calls.find((c) => c.id === id);
  if (call)
    return {
      id,
      kind: "call",
      label: "Verification call for this payment",
      text: `Verification call, outcome ${call.outcome ?? "none yet"}.`,
      untrusted_text: (call.transcript ?? []).map((l) => `${l.speaker}: ${l.text}`).join("\n"),
    };
  const audit = d.audit.find((a) => a.id === id);
  if (audit) return { id, kind: "audit", label: `Audit: ${audit.action}`, text: `${audit.actor} did ${audit.action}.` };
  const acct = d.last_verified_account;
  if (acct?.id === id) return { id, kind: "bank_account", label: "A bank account of this vendor", text: `Account ending ${last4(acct.account_last4)} at ${acct.bank_name}, on file from onboarding.` };
  if (d.payment.id === id) return { id, kind: "payment", label: "The payment", text: `Payment ${d.payment.id} for ${formatUSD(d.payment.amount_usd)} is ${d.payment.status}.` };
  return null;
}

export async function mockAsk(paymentId: string, question: string): Promise<AskAnswer> {
  const path = `/api/payments/${paymentId}/ask`;
  const q = question.trim();
  if (q.length < 3) throw new ApiError(422, path, `POST ${path} failed (422): question is too short`);
  const d = getMockPaymentDetail(paymentId);
  if (!d) throw new ApiError(404, path, `POST ${path} failed (404): payment not found`);

  const f = facts(d);
  const intent = intentOf(q);
  const draft: Draft =
    intent === "action"
      ? [
          [
            d.payment.status === "paid"
              ? "I can only explain decisions, not make them. This payment was already released automatically; nothing needed approving."
              : `I can only explain decisions, not make them, and nothing was approved: the payment is still ${d.payment.status}. Dev makes that call from the drawer.`,
            d.payment.id,
          ],
        ]
      : (attackAnswer(f, intent) ?? templateAnswer(f, intent));

  const claims: AskClaim[] = draft.flatMap(([text, id]) => (id ? [{ text, evidence_id: id }] : []));
  const elapsed = 900 + (hashSeed(`${paymentId}:${q.toLowerCase()}`) % 1300);
  await new Promise((r) => setTimeout(r, elapsed));

  return {
    payment_id: paymentId,
    question: q,
    answer: claims.length ? claims.map((c) => c.text).join(" ") : NO_ANSWER,
    claims,
    evidence: [...new Set(claims.map((c) => c.evidence_id))].map((id) => evidenceFor(d, id)).filter((e): e is AskEvidence => e !== null),
    source: "template",
    model: null,
    cached: false,
    elapsed_ms: elapsed,
  };
}
