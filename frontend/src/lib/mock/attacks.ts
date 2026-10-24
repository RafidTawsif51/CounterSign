// Mock POST /api/attacks, following backend/app/services/attacks.py: the attack becomes a message in its thread (the
// vendor comes from the thread, never the sender), a synthetic invoice (amount = first dollar figure in the body, bank
// details = the labeled Bank / Routing number / Account number lines, else the vendor's current account), and its own
// mini-run that waits behind a full run. What the mock pipeline "finds" is decided here from the same rules risk.py uses.
// Mock limits: an uploaded PDF cannot be read, so it is treated as a clean invoice; a sample PDF hides the instruction
// with the technique its name says.

import { ApiError } from "@/lib/api-error";
import { COMPANY_DOMAIN, lookalikeOf } from "@/lib/inbox";
import { domainOf } from "@/lib/domain-diff";
import { postMessage } from "@/lib/mock/inbox";
import { getMockPaymentDetail, startMockMiniRun } from "@/lib/mock/run";
import { POISONED_HIDDEN_TEXT, accountByVendor, messages, openInvoices, vendorById, vendorProfile, type AttackPlan } from "@/lib/mock/seed";
import type { LaunchAttackRequest, LaunchAttackResponse, LeaderboardResponse, LeaderboardRow, Message } from "@/lib/types";

const PATH = "/api/attacks";
const EMAIL = /^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$/;
const CARDS = ["classic_bank_change", "poisoned_invoice", "ceo_pressure", "freestyle"];
const SAMPLE_TECHNIQUE: Record<string, AttackPlan["technique"]> = {
  "poisoned_white_text.pdf": "white_text",
  "poisoned_tiny_font.pdf": "tiny_font",
  "poisoned_off_page.pdf": "off_page",
  "poisoned_zero_width.pdf": "zero_width",
};

const hex = (n: number) => crypto.randomUUID().replace(/-/g, "").slice(0, n);
const bad = (why: string) => new ApiError(422, PATH, `POST ${PATH} failed (422): ${why}`);

// attacks.py parse_bank_details and parse_amount
const ROUTING = /routing(?:\s*(?:number|no\.?|#))?\s*[:-]?\s*(\d{9})/i;
const ACCOUNT = /account(?:\s*(?:number|no\.?|#))?\s*[:-]?\s*([\d*xX -]{4,})/i;
const BANK = /^\s*bank(?:\s+name)?\s*[:-]\s*(.+)$/im;
const MONEY = /\$\s?([\d]{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)/g;

function bankDetails(body: string) {
  const routing = body.match(ROUTING);
  const digits = (body.match(ACCOUNT)?.[1] ?? "").replace(/\D/g, "");
  if (!routing || digits.length < 4) return null;
  return { bank_name: body.match(BANK)?.[1].trim().slice(0, 80) ?? "Unknown bank", routing_hash: `h_${routing[1].slice(-4)}`, account_last4: digits.slice(-4) };
}

function firstAmount(body: string) {
  for (const m of body.matchAll(MONEY)) {
    const v = Number(m[1].replace(/,/g, ""));
    if (v > 0 && v < 10_000_000) return Math.round(v * 100) / 100;
  }
  return null;
}

/** The vendor of a thread. Seeded history threads (thr_redhawk_0928) are not in the mock inbox, so their key names the vendor. */
function vendorForThread(threadId: string): string | null {
  const known = messages.find((m) => m.thread_id === threadId && m.vendor_id)?.vendor_id;
  if (known) return known;
  const key = threadId.match(/^thr_([a-z]+)_/)?.[1];
  return key && vendorById.has(`ven_${key}`) ? `ven_${key}` : null;
}

const HIDDEN_HTML: [RegExp, AttackPlan["technique"]][] = [
  [/<!--[\s\S]*?-->/, "html_comment"],
  [/display\s*:\s*none/i, "instruction_classifier"],
  [/class\s*=\s*["'][^"']*["'][\s\S]*display\s*:\s*none|\.[\w-]+\s*\{[^}]*display\s*:\s*none/i, "instruction_classifier"],
  [/color\s*:\s*#f7f7f7/i, "instruction_classifier"],
];

export function mockLaunchAttack(raw: unknown): LaunchAttackResponse {
  const req = (raw ?? {}) as Partial<LaunchAttackRequest>;
  const name = req.attacker_name?.trim() ?? "";
  if (name.length < 1 || name.length > 80) throw bad("attacker_name is required (up to 80 characters)");
  if (!req.card || !CARDS.includes(req.card)) throw bad("card must be classic_bank_change, poisoned_invoice, ceo_pressure or freestyle");
  const p = req.payload;
  if (!p?.from_addr || !EMAIL.test(p.from_addr)) throw bad("from_addr is not a valid email address");
  if (p.reply_to && !EMAIL.test(p.reply_to)) throw bad("reply_to is not a valid email address");
  if ((p.pdf || p.pdf_base64) && req.card !== "poisoned_invoice" && req.card !== "freestyle") throw bad("only poisoned_invoice and freestyle attacks take a PDF");
  if (p.pdf && p.pdf_base64) throw bad("send either pdf or pdf_base64, not both");
  if (p.pdf && !SAMPLE_TECHNIQUE[p.pdf]) throw bad(`pdf must be the name of a file in backend/seed/invoices: '${p.pdf}'`);

  const threadId = p.thread_id || `thr_${hex(12)}`;
  const vendorId = vendorForThread(threadId);
  if (!vendorId) throw bad("in mock mode an attack must go into a vendor's thread");
  const vendor = vendorById.get(vendorId)!;
  const profile = vendorProfile.get(vendorId)!;
  const current = accountByVendor.get(vendorId)!;
  const body = p.body ?? "";
  const subject = (p.subject ?? "").trim() || "(no subject)";

  const msg: Message = {
    id: `msg_${hex(12)}`,
    thread_id: threadId,
    vendor_id: vendorId,
    from_addr: p.from_addr,
    reply_to: p.reply_to || null,
    subject,
    body,
    received_at: new Date().toISOString(),
    is_attack: true,
  };
  postMessage(msg);

  const amount = firstAmount(body) ?? Math.round(profile.base * 0.9 * 100) / 100;
  const hasPdf = Boolean(p.pdf || p.pdf_base64);
  const requested = hasPdf ? null : bankDetails(body);
  const remit = requested ?? { bank_name: current.bank_name, routing_hash: current.routing_hash, account_last4: current.account_last4 };

  // What the checks find: the same signals and hard rules risk.py and injection.py apply.
  const signals: AttackPlan["signals"] = [];
  const hardRules: AttackPlan["hardRules"] = [];
  const fromDomain = domainOf(p.from_addr);
  const imitated = lookalikeOf(fromDomain, [vendor.email_domain, COMPANY_DOMAIN]);
  const changed = requested !== null && requested.account_last4 !== current.account_last4;
  if (changed) signals.push({ name: "bank_details_changed", weight: 30, detail: `New account ending ${requested.account_last4}; last verified ending ${current.account_last4}` });
  if (imitated) signals.push({ name: "lookalike_domain", weight: 25, detail: `${fromDomain} vs ${imitated}` });
  if (p.reply_to && p.reply_to.toLowerCase() !== p.from_addr.toLowerCase()) signals.push({ name: "reply_to_mismatch", weight: 15, detail: `Reply-To: ${p.reply_to}` });
  const pressure = body.match(/\b(today|urgent|immediately|asap|confidential|keep (this|it) quiet|ceo approved)\b/gi);
  if (pressure) signals.push({ name: "urgency_language", weight: 15, detail: `matched ${[...new Set(pressure.map((w) => `'${w.toLowerCase()}'`))].join(", ")}` });
  const max = profile.base * 1.2 * 1.1;
  if (amount > 1.5 * max) {
    signals.push({ name: "amount_outlier", weight: 15, detail: `${amount.toFixed(2)} against a 12-month maximum near ${max.toFixed(2)}` });
    hardRules.push("amount_over_max");
  }
  if (!messages.some((m) => m.id !== msg.id && m.vendor_id === vendorId && m.from_addr.toLowerCase() === p.from_addr.toLowerCase()))
    signals.push({ name: "first_message_from_sender", weight: 10, detail: `${p.from_addr} not seen in vendor history` });
  if (/\+?1?[\s.-]?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}/.test(body)) hardRules.push("contacts_differ");

  const html = HIDDEN_HTML.find(([re]) => re.test(body));
  const kind: AttackPlan["kind"] = p.pdf ? "hidden" : html ? "hidden" : changed ? "new_bank" : hardRules.includes("amount_over_max") ? "amount" : "clean";
  if (changed) hardRules.unshift("destination_changed");

  const attackId = `atk_${hex(12)}`;
  const invoiceId = `inv_atk_${hex(10)}`;
  openInvoices.push({
    id: invoiceId,
    vendor_id: vendorId,
    message_id: msg.id,
    number: "ATK-" + msg.id.slice(4, 12).toUpperCase(),
    amount_usd: amount,
    due_date: new Date(Date.now() + 15 * 86_400_000).toISOString().slice(0, 10),
    remittance_json: remit,
    pdf_path: hasPdf ? `uploads/${invoiceId}.pdf` : null,
    extracted_json: null,
    planted: null,
    attack: {
      attackId,
      attackerName: name,
      source: req.source === "judge" ? "judge" : "console",
      card: req.card,
      kind,
      signals: kind === "hidden" ? [] : signals,
      hardRules,
      technique: p.pdf ? SAMPLE_TECHNIQUE[p.pdf] : html?.[1],
      snippet: p.pdf ? POISONED_HIDDEN_TEXT : html ? hiddenText(body) : undefined,
    },
  });

  const runId = `run_${hex(12)}`;
  const { queued, position, waitingFor } = startMockMiniRun(runId, invoiceId);
  return { attack_id: attackId, message_id: msg.id, invoice_id: invoiceId, payment_id: "pay_" + invoiceId.split("_").slice(1).join("_"), run_id: runId, queued, position, waiting_for: waitingFor };
}

/** The instruction an HTML email hides: the comment, or the hidden element's text. */
function hiddenText(body: string) {
  const comment = body.match(/<!--([\s\S]*?)-->/)?.[1];
  if (comment) return comment.trim();
  const doc = new DOMParser().parseFromString(body, "text/html");
  const el = [...doc.body.querySelectorAll("span, div")].find((e) => /ai assistant/i.test(e.textContent ?? ""));
  return (el?.textContent ?? "").trim();
}

/** demo reset: take attack invoices out of this week's list. Their messages go with resetMockInbox. */
export function resetMockAttacks() {
  for (let i = openInvoices.length - 1; i >= 0; i--) if (openInvoices[i].attack) openInvoices.splice(i, 1);
}

/**
 * GET /api/attacks/leaderboard: every attack launched this session, newest first, scored from its payment. Like the
 * backend: caught = held or blocked, missed = paid (and its amount counts as sandbox money moved).
 */
export function mockLeaderboard(): LeaderboardResponse {
  const rows: LeaderboardRow[] = openInvoices
    .filter((i) => i.attack)
    .map((i): LeaderboardRow => {
      const a = i.attack!;
      const status = getMockPaymentDetail("pay_" + i.id.slice("inv_".length))?.payment.status;
      const result: LeaderboardRow["result"] = status === "paid" ? "missed" : status === "held" || status === "blocked" ? "caught" : null;
      const msg = messages.find((m) => m.id === i.message_id);
      return {
        id: a.attackId,
        handle: a.attackerName,
        source: a.source,
        card: a.card,
        result,
        outcome: status ?? "processing",
        top_reasons: a.signals.slice(0, 3).map((s) => `${s.name}: ${s.detail}`),
        amount_usd: i.amount_usd,
        paid_usd: status === "paid" ? i.amount_usd : 0,
        payment_id: "pay_" + i.id.split("_").slice(1).join("_"),
        created_at: msg?.received_at ?? new Date().toISOString(),
        moderation_status: "approved",
        text: msg ? { subject: msg.subject, from_addr: msg.from_addr, body: msg.body.slice(0, 2000), has_pdf: Boolean(i.pdf_path) } : null,
      };
    })
    .sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
  return {
    attempts: rows,
    totals: {
      attempts: rows.length,
      unique_attackers: new Set(rows.map((r) => r.handle.toLowerCase())).size,
      sandbox_usd_moved: Math.round(rows.reduce((t, r) => t + (r.result === "missed" ? r.paid_usd : 0), 0) * 100) / 100,
      caught: rows.filter((r) => r.result === "caught").length,
      missed: rows.filter((r) => r.result === "missed").length,
      pending_result: rows.filter((r) => r.result === null).length,
      by_card: rows.reduce<Record<string, number>>((m, r) => ((m[r.card] = (m[r.card] ?? 0) + 1), m), {}),
    },
  };
}
