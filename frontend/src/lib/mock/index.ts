// Mock backend for VITE_USE_MOCKS=true. Data is fictional and mirrors the backend seed (see seed.ts).
// Routes that are not mocked yet fail loudly so a screen never silently renders made-up shapes.

import {
  decideMockPayment,
  getMockPaymentDetail,
  getMockRun,
  resetMockRuns,
  startMockRun,
  subscribeMockLeaderboard,
  subscribeMockRun,
} from "@/lib/mock/run";
import { mockAsk } from "@/lib/mock/ask";
import { bankAccounts, contacts, openInvoices, vendors } from "@/lib/mock/seed";
import { ApiError } from "@/lib/api-error";
import type { AttackLoggedEvent, RunEvent, StartRunResponse, SystemComponentStatus, VendorHistory } from "@/lib/types";

export class MockNotImplementedError extends Error {
  constructor(method: string, path: string) {
    super(`No mock for ${method} ${path}. Add it in src/lib/mock/.`);
    this.name = "MockNotImplementedError";
  }
}

const systemStatus: SystemComponentStatus[] = [
  { name: "Claude extraction", mode: "mock" },
  { name: "Risk engine", mode: "mock" },
  { name: "Injection defense", mode: "mock" },
  { name: "Verification call (Twilio + Cartesia)", mode: "mock" },
  { name: "Bank payments (Nessie sandbox)", mode: "mock" },
  { name: "Vendor identity (CRS sandbox)", mode: "mock" },
  { name: "Independent phone lookup (Apify)", mode: "mock" },
];

type Handler = (params: Record<string, string>, body: unknown) => unknown;

// "METHOD /path/:param" patterns, matched in order.
const routes: [string, Handler][] = [
  ["GET /api/system/status", () => systemStatus],
  ["GET /api/vendors", () => vendors],
  ["GET /api/vendors/:vendorId/history", ({ vendorId }) => vendorHistory(vendorId) ?? notFound(`/api/vendors/${vendorId}/history`)],
  ["POST /api/demo/reset", () => resetMockRuns()],
  [
    "POST /api/payment-runs",
    (): StartRunResponse => {
      const run_id = startMockRun();
      return { run_id, events_url: `/api/payment-runs/${run_id}/events` };
    },
  ],
  ["GET /api/payments/:paymentId", ({ paymentId }) => getMockPaymentDetail(paymentId) ?? notFound(`/api/payments/${paymentId}`)],
  ["POST /api/payments/:paymentId/ask", ({ paymentId }, body) => mockAsk(paymentId, questionOf(body))],
  ["POST /api/payments/:paymentId/approve", ({ paymentId }, body) => decideMockPayment(paymentId, "approve", reasonOf(body))],
  ["POST /api/payments/:paymentId/reject", ({ paymentId }, body) => decideMockPayment(paymentId, "reject", reasonOf(body))],
  [
    "GET /api/payment-runs/:runId",
    ({ runId }) => getMockRun(runId) ?? notFound(`/api/payment-runs/${runId}`),
  ],
];

function match(pattern: string, method: string, path: string): Record<string, string> | null {
  const [pMethod, pPath] = pattern.split(" ");
  if (pMethod !== method) return null;
  const want = pPath.split("/");
  const got = path.split("/");
  if (want.length !== got.length) return null;
  const params: Record<string, string> = {};
  for (let i = 0; i < want.length; i++) {
    if (want[i].startsWith(":")) params[want[i].slice(1)] = decodeURIComponent(got[i]);
    else if (want[i] !== got[i]) return null;
  }
  return params;
}

/** The mock world has no past invoices or calls; this week's open invoices stand in for history. */
function vendorHistory(vendorId: string): VendorHistory | null {
  const vendor = vendors.find((v) => v.id === vendorId);
  if (!vendor) return null;
  return {
    vendor,
    invoices: openInvoices.filter((i) => i.vendor_id === vendorId).map(({ planted: _planted, ...invoice }) => invoice),
    bank_accounts: bankAccounts.filter((a) => a.vendor_id === vendorId),
    contacts: contacts.filter((c) => c.vendor_id === vendorId),
    calls: [],
  };
}

function questionOf(body: unknown): string {
  return typeof body === "object" && body && "question" in body ? String((body as { question: unknown }).question) : "";
}

function reasonOf(body: unknown): string {
  return typeof body === "object" && body && "reason" in body ? String((body as { reason: unknown }).reason) : "";
}

function notFound(path: string): never {
  throw new ApiError(404, path, `GET ${path} failed (404): not found`);
}

export async function mockRequest<T>(method: string, path: string, body?: unknown): Promise<T> {
  const bare = path.split("?")[0];
  for (const [pattern, handler] of routes) {
    const params = match(pattern, method, bare);
    if (params) return structuredClone(await handler(params, body)) as T;
  }
  throw new MockNotImplementedError(method, path);
}

/** Same paths as the real SSE endpoints. */
export function mockSubscribe(path: string, onEvent: (event: RunEvent) => void): () => void {
  const run = path.match(/^\/api\/payment-runs\/([^/]+)\/events$/);
  if (run) return subscribeMockRun(decodeURIComponent(run[1]), onEvent);
  if (path === "/api/leaderboard/events") return subscribeMockLeaderboard(onEvent as (e: AttackLoggedEvent) => void);
  throw new MockNotImplementedError("STREAM", path);
}
