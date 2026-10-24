// HTTP client for the FastAPI backend. Routes mirror the API table in CLAUDE.md.
// With VITE_USE_MOCKS=true every call is answered by lib/mock instead of the network.

import { ApiError } from "@/lib/api-error";
import { mockRequest } from "@/lib/mock";
import type {
  AskAnswer,
  LeaderboardResponse,
  RedTeamResults,
  InboxMessage,
  InboxThreadDetail,
  InboxThreadSummary,
  LaunchAttackRequest,
  LaunchAttackResponse,
  UploadInvoiceResponse,
  PaymentDetail,
  PaymentRun,
  RunTotals,
  Payment,
  Invoice,
  Vendor,
  Message,
  VendorBankAccount,
  RiskAssessment,
  InjectionFinding,
  VerificationCall,
  VendorContact,
  AuditLogEntry,
  PaymentActions,
  IndependentContact,
  StartRunResponse,
  SystemComponentStatus,
  VendorSummary,
  VendorHistory,
} from "@/lib/types";

export const API_URL = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
export const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === "true";
/** The Rob Countersign bounty inbox, or "" until the organizers approve advertising it. */
export const BOUNTY_EMAIL = (import.meta.env.VITE_BOUNTY_EMAIL ?? "").trim();

type Method = "GET" | "POST";

async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  if (USE_MOCKS) return mockRequest<T>(method, path, body);

  const isForm = body instanceof FormData;
  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers: body && !isForm ? { "Content-Type": "application/json" } : undefined,
    body: body == null ? undefined : isForm ? body : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      // The backend sends either detail: "text" or detail: {error: "text", ...} (409 conflicts).
      if (typeof data?.detail === "string") detail = data.detail;
      else if (typeof data?.detail?.error === "string") detail = data.detail.error;
    } catch {
      // Non-JSON error body; keep the status text.
    }
    throw new ApiError(res.status, path, `${method} ${path} failed (${res.status}): ${detail}`, detail);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

const get = <T>(path: string) => request<T>("GET", path);
const post = <T>(path: string, body?: unknown) => request<T>("POST", path, body);

export { ApiError };

export const api = {
  resetDemo: (keepLeaderboard = false) => post<void>(`/api/demo/reset?keep_leaderboard=${keepLeaderboard}`),

  vendors: () => get<VendorSummary[]>("/api/vendors"),
  vendorHistory: (vendorId: string) => get<VendorHistory>(`/api/vendors/${vendorId}/history`),

  threads: () => get<InboxThreadSummary[]>("/api/inbox/threads"),
  thread: (threadId: string) => get<InboxThreadDetail>(`/api/inbox/threads/${encodeURIComponent(threadId)}`),
  /** Omit thread_id to start a new thread (it has no vendor). The vendor always comes from the thread, never the sender. */
  addMessage: (msg: { thread_id?: string; from_addr: string; reply_to?: string; subject: string; body: string }) =>
    post<InboxMessage>("/api/inbox/messages", msg),
  uploadInvoice: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return post<UploadInvoiceResponse>("/api/invoices/upload", form);
  },

  startRun: () => post<StartRunResponse>("/api/payment-runs"),
  run: async (runId: string): Promise<PaymentRun> => {
    const r = await get<BackendRun>(`/api/payment-runs/${runId}`);
    return { id: r.id, started_at: r.started_at, completed_at: r.completed_at, status: r.status, totals_json: r.totals };
  },

  payment: async (paymentId: string): Promise<PaymentDetail> =>
    USE_MOCKS ? get<PaymentDetail>(`/api/payments/${paymentId}`) : adaptPayment(await get<BackendPayment>(`/api/payments/${paymentId}`)),
  approve: (paymentId: string, reason: string, approver: string) => post<void>(`/api/payments/${paymentId}/approve`, { reason, approver }),
  reject: (paymentId: string, reason: string, approver: string) => post<void>(`/api/payments/${paymentId}/reject`, { reason, approver }),
  ask: (paymentId: string, question: string) => post<AskAnswer>(`/api/payments/${paymentId}/ask`, { question }),
  startCall: (paymentId: string) => post<void>(`/api/verifications/${paymentId}/call`),

  launchAttack: (req: LaunchAttackRequest) => post<LaunchAttackResponse>("/api/attacks", req),
  leaderboard: () => get<LeaderboardResponse>("/api/attacks/leaderboard"),

  runRedTeam: (n: number) => post<void>("/api/redteam/run", { n }),
  redTeamResults: () => get<RedTeamResults>("/api/redteam/results"),

  systemStatus: () => get<SystemComponentStatus[]>("/api/system/status"),
};

/** Absolute URL for an SSE endpoint. */
export function streamUrl(path: string) {
  return `${API_URL}${path}`;
}

// ---------- GET /api/payments/{id}: backend shape -> PaymentDetail ----------
// The backend names several fields differently from the table columns the screens were written against
// (requested_remittance, signals, injection_findings, detail). Mapping here keeps the screens and the mock unchanged.

interface BackendAccount {
  id: string;
  bank_name: string;
  account_last4: string;
  valid_from: string;
  valid_to: string | null;
  verified_by_call_id: string | null;
  trusted: boolean;
}

interface BackendRun {
  id: string;
  status: PaymentRun["status"];
  started_at: string;
  completed_at: string | null;
  totals: RunTotals | null;
}

interface BackendPayment {
  payment: Pick<Payment, "id" | "run_id" | "status" | "amount_usd" | "nessie_transfer_id"> & {
    destination: BackendAccount | null;
    last_verified_account: BackendAccount | null;
    /** Approving always pays this account: the vendor's verified one, never the one a request asked for. */
    approve_pays: BackendAccount | null;
  };
  actions: PaymentActions;
  independent_contact: IndependentContact | null;
  invoice: {
    id: string;
    number: string | null;
    amount_usd: number | null;
    due_date: string | null;
    has_pdf: boolean;
    requested_remittance: Record<string, unknown> | null;
    requested_account_differs_from_verified: boolean;
  } | null;
  vendor: (Vendor & { identity?: unknown }) | null;
  message: (Message & { is_attack: boolean }) | null;
  risk: (Omit<RiskAssessment, "payment_id" | "signals_json"> & { signals: RiskAssessment["signals_json"] }) | null;
  injection_findings: InjectionFinding[];
  calls: (Omit<VerificationCall, "contact_id"> & { contact: (Pick<VendorContact, "id" | "source" | "source_url" | "phone">) | null })[];
  audit: (Omit<AuditLogEntry, "detail_json"> & { detail: Record<string, unknown> | null })[];
}

function adaptPayment(b: BackendPayment): PaymentDetail {
  const p = b.payment;
  const vendorId = b.vendor?.id ?? "";
  const account = (a: BackendAccount | null): VendorBankAccount | null =>
    a && { ...a, vendor_id: vendorId, routing_hash: "" }; // the API never returns a routing hash
  const payment: Payment = {
    id: p.id,
    run_id: p.run_id,
    invoice_id: b.invoice?.id ?? "",
    amount_usd: p.amount_usd,
    destination_account_id: p.destination?.id ?? null,
    status: p.status,
    nessie_transfer_id: p.nessie_transfer_id,
  };
  const invoice: Invoice = {
    id: b.invoice?.id ?? "",
    vendor_id: b.vendor?.id ?? null,
    message_id: b.message?.id ?? null,
    number: b.invoice?.number ?? null,
    amount_usd: b.invoice?.amount_usd ?? null,
    due_date: b.invoice?.due_date ?? null,
    remittance_json: b.invoice?.requested_remittance ?? null,
    pdf_path: null,
    extracted_json: null,
    requested_account_differs: b.invoice?.requested_account_differs_from_verified,
  };
  return {
    payment,
    invoice,
    vendor: b.vendor as Vendor,
    message: b.message,
    last_verified_account: account(p.last_verified_account),
    risk: b.risk && { ...b.risk, payment_id: p.id, signals_json: b.risk.signals },
    findings: b.injection_findings,
    calls: b.calls.map((c) => ({ ...c, contact_id: c.contact?.id ?? null, contact: c.contact && ({ ...c.contact, vendor_id: vendorId, first_seen: "", last_verified: null } as VendorContact) })),
    audit: b.audit.map(({ detail, ...a }) => ({ ...a, detail_json: detail })),
    actions: b.actions,
    independent_contact: b.independent_contact,
    approve_pays: account(p.approve_pays),
  };
}

/** The original stored PDF of an invoice (GET /api/invoices/{id}/pdf). */
export function invoicePdfUrl(invoiceId: string) {
  return `${API_URL}/api/invoices/${encodeURIComponent(invoiceId)}/pdf`;
}
