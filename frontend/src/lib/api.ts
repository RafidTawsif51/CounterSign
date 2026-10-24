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
  Invoice,
  PaymentDetail,
  PaymentRun,
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
      if (typeof data?.detail === "string") detail = data.detail;
    } catch {
      // Non-JSON error body; keep the status text.
    }
    throw new ApiError(res.status, path, `${method} ${path} failed (${res.status}): ${detail}`);
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
    return post<Invoice>("/api/invoices/upload", form);
  },

  startRun: () => post<StartRunResponse>("/api/payment-runs"),
  run: (runId: string) => get<PaymentRun>(`/api/payment-runs/${runId}`),

  payment: (paymentId: string) => get<PaymentDetail>(`/api/payments/${paymentId}`),
  approve: (paymentId: string, reason: string) => post<void>(`/api/payments/${paymentId}/approve`, { reason }),
  reject: (paymentId: string, reason: string) => post<void>(`/api/payments/${paymentId}/reject`, { reason }),
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
