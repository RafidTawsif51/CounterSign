// Mock backend for VITE_USE_MOCKS=true. Data must stay fictional (Ridgeline Builders and its vendors).
// Routes that are not mocked yet fail loudly so a screen never silently renders made-up shapes.

import type { RunEvent, SystemComponentStatus } from "@/lib/types";

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

type Handler = (body: unknown) => unknown;

const routes: Record<string, Handler> = {
  "GET /api/system/status": () => systemStatus,
};

export async function mockRequest<T>(method: string, path: string, body?: unknown): Promise<T> {
  const key = `${method} ${path.split("?")[0]}`;
  const handler = routes[key];
  if (!handler) throw new MockNotImplementedError(method, path);
  return structuredClone(handler(body)) as T;
}

export function mockSubscribe(_path: string, _onEvent: (event: RunEvent) => void): () => void {
  // The mock event player lands with the board. Until then a mock stream is silent.
  return () => {};
}
