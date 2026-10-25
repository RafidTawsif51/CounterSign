// Is the FastAPI server answering? Only the health probe decides. A failed request or a dropped event stream just asks
// for a probe now, so one bad endpoint cannot flap the offline banner. The shell runs the probe loop
// (useConnectionMonitor) in live mode, to notice the server going away, and in mock mode, to notice it coming back.

import { useEffect, useSyncExternalStore } from "react";
import { API_URL } from "@/lib/api-url";
import { BUILT_MOCK, useDataMode } from "@/lib/data-mode";

/** The server has to be silent this long before the offline demo is offered. */
export const UNREACHABLE_AFTER_MS = 5_000;
const PROBE_TIMEOUT_MS = 3_000;
const FAST_MS = 1_000; // live, while the server is not answering
const LIVE_MS = 2_000; // live heartbeat: an open event stream can outlive a server that refuses everything else
const OFFLINE_MS = 5_000; // offline demo: only to offer the way back

export interface ConnectionState {
  /** null until the first probe answers. */
  reachable: boolean | null;
  /** When the current silence began. */
  downSince: number | null;
  /** Silent for at least UNREACHABLE_AFTER_MS. */
  unreachable: boolean;
}

let state: ConnectionState = { reachable: null, downSince: null, unreachable: false };
const listeners = new Set<() => void>();
let wake: (() => void) | null = null;

function set(next: ConnectionState) {
  if (next.reachable === state.reachable && next.downSince === state.downSince && next.unreachable === state.unreachable) return;
  state = next;
  listeners.forEach((l) => l());
}

function record(ok: boolean) {
  if (ok) return set({ reachable: true, downSince: null, unreachable: false });
  const downSince = state.downSince ?? Date.now();
  set({ reachable: false, downSince, unreachable: Date.now() - downSince >= UNREACHABLE_AFTER_MS });
}

/** A request or the stream failed: probe now instead of waiting for the heartbeat. */
export function reportFailure() {
  wake?.();
}

export async function probeServer(): Promise<boolean> {
  try {
    const res = await fetch(`${API_URL}/api/health`, { cache: "no-store", signal: AbortSignal.timeout(PROBE_TIMEOUT_MS) });
    // Same-origin in dev, an SPA fallback answers /api/health with index.html and a 200; only JSON counts.
    return res.ok && (res.headers.get("content-type") ?? "").includes("json");
  } catch {
    return false;
  }
}

export function useConnection(): ConnectionState {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => state,
    () => state,
  );
}

/** Mount once, in the shell. */
export function useConnectionMonitor() {
  const mode = useDataMode();

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let probing = false;

    const tick = async () => {
      if (timer) clearTimeout(timer);
      timer = null;
      if (probing) return;
      probing = true;
      const ok = await probeServer();
      probing = false;
      if (stopped) return;
      record(ok);
      timer = setTimeout(tick, mode === "mock" ? OFFLINE_MS : ok ? LIVE_MS : FAST_MS);
    };

    // Each mode starts fresh: a silence measured while live says nothing about the offline demo, and back.
    set({ reachable: null, downSince: null, unreachable: false });
    // A mock build has no live mode to go back to, so it never probes (and never fills the console with refusals).
    if (mode === "replay" || (mode === "mock" && BUILT_MOCK)) return;
    wake = () => void tick();
    void tick();
    return () => {
      stopped = true;
      wake = null;
      if (timer) clearTimeout(timer);
    };
  }, [mode]);
}
