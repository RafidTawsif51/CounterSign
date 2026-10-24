// Live run events. Screens use useRunEvents(runId) and never learn whether events come from the mock run
// (VITE_USE_MOCKS=true) or from the server's SSE stream. Wire format: docs/events.md.

import { useEffect, useState } from "react";
import { USE_MOCKS, streamUrl } from "@/lib/api";
import { mockSubscribe } from "@/lib/mock";
import type { AttackLoggedEvent, RunEvent } from "@/lib/types";

export type Unsubscribe = () => void;

/**
 * connecting: first connection. live: events flowing. reconnecting: the stream dropped and is being reopened (backoff).
 * complete: run.report received, stream closed.
 */
export type StreamStatus = "idle" | "connecting" | "live" | "reconnecting" | "complete";

interface Transport {
  open(path: string, onEvent: (e: RunEvent) => void, onStatus: (s: StreamStatus) => void): Unsubscribe;
}

/** Backoff between reconnects: 1 s, 2 s, 4 s, 8 s, then every 10 s until the server is back. */
export const RECONNECT_MAX_MS = 10_000;
const backoff = (attempt: number) => Math.min(RECONNECT_MAX_MS, 1000 * 2 ** attempt);

const sseTransport: Transport = {
  open(path, onEvent, onStatus) {
    let source: EventSource | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;
    let closed = false;

    // EventSource retries on its own, but gives up for good on some failures (a 5xx, a proxy error page) and never backs
    // off. So every error closes it and this reopens on our schedule. The server replays a run's stored events on each
    // connection; useRunEvents drops the repeats by event id.
    const connect = () => {
      source = new EventSource(streamUrl(path));
      source.onopen = () => {
        attempt = 0;
        onStatus("live");
      };
      source.onmessage = (msg) => {
        try {
          onEvent(JSON.parse(msg.data) as RunEvent);
        } catch {
          // A malformed frame is dropped; the next one still arrives.
        }
      };
      source.onerror = () => {
        source?.close();
        if (closed) return;
        onStatus("reconnecting");
        timer = setTimeout(connect, backoff(attempt++));
      };
    };
    connect();
    return () => {
      closed = true;
      if (timer) clearTimeout(timer);
      source?.close();
    };
  },
};

const mockTransport: Transport = {
  open(path, onEvent, onStatus) {
    queueMicrotask(() => onStatus("live"));
    return mockSubscribe(path, onEvent);
  },
};

const transport = USE_MOCKS ? mockTransport : sseTransport;

const runPath = (runId: string) => `/api/payment-runs/${encodeURIComponent(runId)}/events`;

export interface RunEventsState {
  /** Every event of the run so far, in arrival order, without duplicates. */
  events: RunEvent[];
  status: StreamStatus;
}

/**
 * Every event of one run. Stored events replay first, so connecting late is fine. A reconnect replays the run from the
 * start; events are de-duplicated by id. The stream closes itself after run.report. Pass null for no run.
 */
export function useRunEvents(runId: string | null): RunEventsState {
  const [state, setState] = useState<RunEventsState>({ events: [], status: runId ? "connecting" : "idle" });

  useEffect(() => {
    if (!runId) {
      setState({ events: [], status: "idle" });
      return;
    }
    setState({ events: [], status: "connecting" });

    const seen = new Set<string>();
    let closed = false;
    const close = transport.open(
      runPath(runId),
      (event) => {
        if (closed || seen.has(event.id)) return;
        seen.add(event.id);
        const done = event.type === "run.report";
        setState((s) => ({ events: [...s.events, event], status: done ? "complete" : "live" }));
        if (done) {
          closed = true;
          queueMicrotask(close);
        }
      },
      (status) => !closed && setState((s) => (s.status === status ? s : { ...s, status })),
    );

    return () => {
      closed = true;
      close();
    };
  }, [runId]);

  return state;
}

/**
 * Live attack.logged events for the leaderboard. No replay: load history with api.leaderboard() first, and again after
 * a reconnect (onStatus reports "live" once the stream is back).
 */
export function subscribeLeaderboard(onEvent: (e: AttackLoggedEvent) => void, onStatus: (s: StreamStatus) => void = () => {}): Unsubscribe {
  return transport.open("/api/leaderboard/events", (e) => e.type === "attack.logged" && onEvent(e), onStatus);
}
