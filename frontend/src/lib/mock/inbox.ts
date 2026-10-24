// Mock AP inbox and vendor history, in the shapes backend/app/services/ingest.py and vendors.py return. Threads come
// from the seed's messages plus anything posted to /api/inbox/messages (the attack console); demo reset clears those.
// History adds 12 months of paid invoices per vendor, deterministic per vendor, so the vendor card has a real shape.

import { ApiError } from "@/lib/api-error";
import { createRng, hashSeed } from "@/lib/mock/prng";
import { getMockPaymentDetail } from "@/lib/mock/run";
import { ATTACKER_ACCOUNTS, PLANTED, bankAccounts, contacts, messages, openInvoices, vendorById, vendorProfile, vendors } from "@/lib/mock/seed";
import type {
  HistoryBankAccount,
  HistoryInvoice,
  IdentityResult,
  InboxMessage,
  InboxThreadDetail,
  InboxThreadSummary,
  Message,
  VendorHistory,
  VendorSummary,
} from "@/lib/types";

const PREVIEW_CHARS = 140; // ingest.PREVIEW_CHARS
const EMAIL = /^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$/;

/** Ids of messages posted during this session (the console, attacks). They join the seed's list so payment records find
 * them; demo reset takes them out again. */
const posted = new Set<string>();

export function resetMockInbox() {
  for (let i = messages.length - 1; i >= 0; i--) if (posted.has(messages[i].id)) messages.splice(i, 1);
  posted.clear();
}

/** Add a message to the AP inbox (POST /api/inbox/messages, or an attack). */
export function postMessage(msg: Message) {
  messages.push(msg);
  posted.add(msg.id);
}

function allMessages(): Message[] {
  return [...messages].sort((a, b) => (a.received_at < b.received_at ? -1 : a.received_at > b.received_at ? 1 : a.id < b.id ? -1 : 1));
}

function invoicesOf(messageId: string) {
  // Only real PDFs are attachments; an email attack's invoice is synthetic and has none.
  return openInvoices.filter((i) => i.message_id === messageId && i.pdf_path).map((i) => i.id);
}

function preview(body: string) {
  const text = body.replace(/\s+/g, " ").trim();
  return text.length <= PREVIEW_CHARS ? text : text.slice(0, PREVIEW_CHARS - 3).trimEnd() + "...";
}

function summary(threadId: string, msgs: Message[]): InboxThreadSummary {
  const vendorId = msgs.find((m) => m.vendor_id)?.vendor_id ?? null;
  const vendor = vendorId ? vendorById.get(vendorId) : undefined;
  return {
    thread_id: threadId,
    vendor: vendor ? { id: vendor.id, name: vendor.name } : null,
    subject: msgs[0].subject,
    preview: preview(msgs.at(-1)!.body),
    count: msgs.length,
    has_attack: msgs.some((m) => m.is_attack),
    last_received_at: msgs.at(-1)!.received_at,
    attachment_count: msgs.reduce((n, m) => n + invoicesOf(m.id).length, 0),
  };
}

function grouped() {
  const by = new Map<string, Message[]>();
  for (const m of allMessages()) by.set(m.thread_id, [...(by.get(m.thread_id) ?? []), m]);
  return by;
}

export function mockThreads(): InboxThreadSummary[] {
  return [...grouped()].map(([id, msgs]) => summary(id, msgs)).sort((a, b) => (a.last_received_at < b.last_received_at ? 1 : -1));
}

export function mockThread(threadId: string): InboxThreadDetail {
  const msgs = grouped().get(threadId);
  if (!msgs) throw new ApiError(404, `/api/inbox/threads/${threadId}`, `Thread not found`);
  return { ...summary(threadId, msgs), messages: msgs.map((m) => ({ ...m, is_html: /<\s*(html|body|div|p|br|span|a|table)\b/i.test(m.body), invoice_ids: invoicesOf(m.id) })) };
}

/** POST /api/inbox/messages. The vendor comes from the thread, never from from_addr (a lookalike must not pick it). */
export function mockAddMessage(body: unknown): InboxMessage {
  const path = "/api/inbox/messages";
  const b = (body ?? {}) as Partial<Record<"thread_id" | "from_addr" | "reply_to" | "subject" | "body", string>>;
  const bad = (why: string) => new ApiError(422, path, `${why}`);
  if (!b.from_addr || !EMAIL.test(b.from_addr)) throw bad("from_addr is not a valid email address");
  if (b.reply_to && !EMAIL.test(b.reply_to)) throw bad("reply_to is not a valid email address");
  if (!b.subject?.trim()) throw bad("subject is required");
  const threadId = b.thread_id || `thr_${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`;
  const vendorId = allMessages().find((m) => m.thread_id === threadId && m.vendor_id)?.vendor_id ?? null;
  const msg: Message = {
    id: `msg_${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`,
    thread_id: threadId,
    vendor_id: vendorId,
    from_addr: b.from_addr,
    reply_to: b.reply_to || null,
    subject: b.subject.trim(),
    body: b.body ?? "",
    received_at: new Date().toISOString(),
    is_attack: false,
  };
  postMessage(msg);
  return { ...msg, is_html: false, invoice_ids: [] };
}

// ---------- Vendor history ----------

/** Construction slows in winter. A rough monthly factor for the mock history (Jan first). */
const SEASON = [0.7, 0.75, 0.9, 1, 1.05, 1.1, 1.1, 1.1, 1.05, 0.9, 0.8, 0.7];

function pastInvoices(vendorId: string): HistoryInvoice[] {
  const profile = vendorProfile.get(vendorId);
  if (!profile) return [];
  const rng = createRng(hashSeed(`history:${vendorId}`));
  const out: HistoryInvoice[] = [];
  // Nov 2025 through Oct 2026, the 12 months before this week's run.
  for (let k = 0; k < 12; k++) {
    const year = k < 2 ? 2025 : 2026;
    const month = (10 + k) % 12; // 0-based: 10 = Nov
    const expected = profile.kind === "monthly" ? 1 : profile.rate * 4.3;
    const n = profile.kind === "monthly" ? 1 : Math.max(0, Math.round(expected + rng.between(-1, 1)));
    for (let j = 0; j < n; j++) {
      const day = Math.min(28, 3 + Math.floor(rng.between(0, 24)));
      out.push({
        id: `inv_h_${vendorId.slice(4)}_${k}_${j}`,
        number: null,
        amount_usd: Math.round(profile.base * SEASON[month] * rng.between(0.8, 1.2) * 100) / 100,
        due_date: `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`,
        has_pdf: true,
        remittance: null,
        payment_id: null,
        status: "paid",
        score: 0,
        decision: "auto_pay",
        hard_rules_fired: [],
      });
    }
  }
  return out;
}

const PLANTED_BY_VENDOR: Record<string, { invoice: string; requested?: { bank_name: string; account_last4: string } }> = {
  ven_summit: { invoice: PLANTED.bank_change.invoice, requested: ATTACKER_ACCOUNTS.summit },
  ven_northside: { invoice: PLANTED.ceo_pressure.invoice, requested: ATTACKER_ACCOUNTS.northside },
};

/**
 * Accounts a payment request asked for and no call has verified. Like run.py, they are recorded when a run reads the
 * planted invoice (verify.record_requested_destination), so before any run there are none.
 */
function requestedAccounts(vendorId: string): HistoryBankAccount[] {
  const planted = PLANTED_BY_VENDOR[vendorId];
  if (!planted?.requested || !getMockPaymentDetail("pay_" + planted.invoice.slice("inv_".length))) return [];
  return [
    {
      id: `bac_${vendorId.slice(4)}_requested`,
      bank_name: planted.requested.bank_name,
      account_last4: planted.requested.account_last4,
      valid_from: "2026-10-22T17:00:00Z",
      valid_to: null,
      trusted: false,
      current: false,
      verified_by_call_id: null,
      verified_by: "requested, not verified",
    },
  ];
}

/** GET /api/vendors, with the unverified request count. */
export function mockVendors(): VendorSummary[] {
  return vendors.map((v) => ({ ...v, unverified_requested_accounts: requestedAccounts(v.id).length }));
}

/** backend identity.MockIdentityChecker: verified, match 0.90 to 0.99, stable per vendor. */
export function identityFor(vendorId: string): IdentityResult {
  const score = 0.9 + (hashSeed(vendorId) % 10) / 100;
  return {
    vendor_id: vendorId,
    status: "verified",
    match_score: Math.round(score * 100) / 100,
    test_identity_id: `crs_test_${(hashSeed(`crs:${vendorId}`) >>> 0).toString(16).padStart(8, "0").slice(0, 8)}`,
    flags: [],
    summary: `CRS identity check: verified (match ${score.toFixed(2)})`,
    checked_at: "2026-10-22T17:00:00Z",
    source: "crs-sandbox-mock",
  };
}

const maskPhone = (phone: string) => (phone.length > 6 ? `${phone.slice(0, 2)}***${phone.slice(-4)}` : "***");

export function mockVendorHistory(vendorId: string): VendorHistory {
  const vendor = vendorById.get(vendorId);
  if (!vendor) throw new ApiError(404, `/api/vendors/${vendorId}/history`, `Vendor not found`);

  const current: HistoryInvoice[] = openInvoices
    .filter((i) => i.vendor_id === vendorId)
    .map((i) => {
      const pid = "pay_" + i.id.slice("inv_".length);
      const d = getMockPaymentDetail(pid);
      return {
        id: i.id,
        number: i.number,
        amount_usd: i.amount_usd,
        due_date: i.due_date,
        has_pdf: Boolean(i.pdf_path),
        remittance: i.remittance_json,
        payment_id: d ? pid : null,
        status: d?.payment.status ?? "open",
        score: d?.risk?.score ?? null,
        decision: d?.risk?.decision ?? null,
        hard_rules_fired: d?.risk?.hard_rules_fired ?? [],
      };
    });

  const accounts: HistoryBankAccount[] = bankAccounts
    .filter((a) => a.vendor_id === vendorId)
    .map((a) => ({ ...a, trusted: true, current: true, verified_by: "onboarding" }));
  accounts.push(...requestedAccounts(vendorId));

  const paid = pastInvoices(vendorId);
  const paidAmounts = paid.map((i) => i.amount_usd ?? 0);
  return {
    vendor,
    identity: identityFor(vendorId),
    summary: {
      invoices: paid.length + current.length,
      paid: paid.length,
      average_paid_usd: paidAmounts.length ? Math.round((paidAmounts.reduce((a, b) => a + b, 0) / paidAmounts.length) * 100) / 100 : null,
      max_paid_usd: paidAmounts.length ? Math.max(...paidAmounts) : null,
    },
    invoices: [...current, ...paid.reverse()],
    bank_accounts: accounts,
    contacts: contacts
      .filter((c) => c.vendor_id === vendorId)
      .map((c) => ({ id: c.id, source: c.source, source_url: c.source_url, phone: maskPhone(c.phone), first_seen: c.first_seen, last_verified: c.last_verified })),
    calls: [],
  };
}
