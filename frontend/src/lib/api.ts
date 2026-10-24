// HTTP client for the FastAPI backend. Routes mirror the API table in CLAUDE.md.
// In mock mode (VITE_USE_MOCKS=true, or the offline-demo switch) every call is answered by lib/mock instead.

import { ApiError, detailText, statusText } from "@/lib/api-error";
import { API_URL } from "@/lib/api-url";
import { reportFailure } from "@/lib/connection";
import { isMock } from "@/lib/data-mode";
import { mockRequest } from "@/lib/mock";
import type {
  AskAnswer,
  LeaderboardResponse,
  ReviewResult,
  RedTeamResults,
  InboxMessage,
  InboxThreadDetail,
  InboxThreadSummary,
  LaunchAttackRequest,
  LaunchAttackResponse,
  HealthResponse,
  PaymentDetail,
  RunStatusResponse,
  StartCallResult,
  StartRunResponse,
  UploadResult,
  SystemComponentStatus,
  VendorSummary,
  VendorHistory,
} from "@/lib/types";

export { API_URL };
/** The Rob Countersign bounty inbox, or "" until the organizers approve advertising it. */
export const BOUNTY_EMAIL = (import.meta.env.VITE_BOUNTY_EMAIL ?? "").trim();

type Method = "GET" | "POST";

async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  if (isMock()) return mockRequest<T>(method, path, body);

  const isForm = body instanceof FormData;
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method,
      headers: body && !isForm ? { "Content-Type": "application/json" } : undefined,
      body: body == null ? undefined : isForm ? body : JSON.stringify(body),
    });
  } catch {
    reportFailure();
    throw new ApiError(0, path, `${statusText(0)} at ${API_URL || window.location.origin}`);
  }
  // A proxy in front of a stopped server answers 502 to 504 instead of failing the request.
  if (res.status >= 502 && res.status <= 504) reportFailure();
  if (!res.ok) {
    let detail: string | null = null;
    try {
      detail = detailText(await res.json());
    } catch {
      // Not JSON (a proxy page, an HTML error): fall back to the status.
    }
    throw new ApiError(res.status, path, detail ? sentence(detail) : statusText(res.status));
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

/** Server details are lowercase fragments ("payment not found"); show them as a sentence. */
const sentence = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

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
    return post<UploadResult>("/api/invoices/upload", form);
  },

  /** 202; 409 while another full run is in progress. */
  startRun: () => post<StartRunResponse>("/api/payment-runs"),
  run: (runId: string) => get<RunStatusResponse>(`/api/payment-runs/${runId}`),

  payment: (paymentId: string) => get<PaymentDetail>(`/api/payments/${paymentId}`),
  /** Held payments only. Pays the vendor's last verified account, never the requested one. */
  approve: (paymentId: string, reason: string, approver: string) => post<ReviewResult>(`/api/payments/${paymentId}/approve`, { reason, approver }),
  reject: (paymentId: string, reason: string, approver: string) => post<ReviewResult>(`/api/payments/${paymentId}/reject`, { reason, approver }),
  ask: (paymentId: string, question: string) => post<AskAnswer>(`/api/payments/${paymentId}/ask`, { question }),
  /** 202; 409 unless the payment is held. Calls at an independent number, never one from the email. Live server only. */
  startCall: (paymentId: string) => post<StartCallResult>(`/api/verifications/${paymentId}/call`),

  launchAttack: (req: LaunchAttackRequest) => post<LaunchAttackResponse>("/api/attacks", req),
  leaderboard: () => get<LeaderboardResponse>("/api/attacks/leaderboard"),

  /** Not on the backend yet: backend/app/redteam is empty. The mock answers results; /red-team shows the error live. */
  runRedTeam: (n: number) => post<void>("/api/redteam/run", { n }),
  redTeamResults: () => get<RedTeamResults>("/api/redteam/results"),

  /** What is real, simulated or on its mock right now. /status falls back to the documented list if it fails. */
  systemStatus: () => get<SystemComponentStatus[]>("/api/system/status"),
  /** Database and every MOCK_* flag as the server reads them. */
  health: () => get<HealthResponse>("/api/health"),
};

/** The original stored PDF of an invoice (GET /api/invoices/{id}/pdf). */
export function invoicePdfUrl(invoiceId: string) {
  return `${API_URL}/api/invoices/${encodeURIComponent(invoiceId)}/pdf`;
}

/** Absolute URL for an SSE endpoint. */
export function streamUrl(path: string) {
  return `${API_URL}${path}`;
}
