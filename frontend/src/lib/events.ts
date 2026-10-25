// Live run events. Screens use useRunEvents(runId) and never learn whether events come from the mock run
// (mock mode) or from the server's SSE stream. Wire format: docs/events.md.

import { useEffect, useState } from "react";
import { streamUrl } from "@/lib/api";
import { reportFailure } from "@/lib/connection";
import { isMock, isReplay, useDataMode } from "@/lib/data-mode";
import { replayTransport } from "@/lib/replay";
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

/**
 * One EventSource per stream URL for the whole app. A browser allows about six connections per origin over HTTP/1.1 and every
 * open stream holds one, so two components (or two tabs) listening to the same URL must share a connection, or a later request
 * (an attack launch, a payment fetch) waits behind them. Listeners join and leave; the connection opens with the first and
 * closes with the last.
 *
 * A run's stored events are replayed by the server only when a connection opens, so each shared run stream keeps what it has
 * delivered and replays it to a listener that joins later. The global channel has no replay and no buffer. A run stream is
 * closed after run.report: the global channel carries everything that can still happen to that run (calls, approvals, final
 * statuses), and a listener that joins a finished run is served from the buffer without a new connection.
 */
const GLOBAL_PATH = "/api/leaderboard/events";

interface Listener {
  onEvent: (e: RunEvent) => void;
  onStatus: (s: StreamStatus) => void;
}

interface SharedStream {
  listeners: Set<Listener>;
  status: StreamStatus;
  /** Delivered events, for a late joiner; only for run streams. */
  buffer: RunEvent[];
  ids: Set<string>;
  finished: boolean;
  source: EventSource | null;
  timer: ReturnType<typeof setTimeout> | null;
  attempt: number;
  closed: boolean;
}

const streams = new Map<string, SharedStream>();

function startStream(path: string, s: SharedStream) {
  const broadcast = (status: StreamStatus) => {
    s.status = status;
    for (const l of [...s.listeners]) l.onStatus(status);
  };
  // EventSource retries on its own, but gives up for good on some failures (a 5xx, a proxy error page) and never backs
  // off. So every error closes it and this reopens on our schedule. The server replays a run's stored events on each
  // connection; the buffer and useRunEvents drop the repeats by event id.
  const connect = () => {
    if (s.closed || s.finished) return;
    const source = new EventSource(streamUrl(path));
    s.source = source;
    source.onopen = () => {
      s.attempt = 0;
      broadcast("live");
    };
    source.onmessage = (msg) => {
      let event: RunEvent;
      try {
        event = JSON.parse(msg.data) as RunEvent;
      } catch {
        return; // A malformed frame is dropped; the next one still arrives.
      }
      if (path !== GLOBAL_PATH) {
        if (s.ids.has(event.id)) return;
        s.ids.add(event.id);
        s.buffer.push(event);
      }
      for (const l of [...s.listeners]) l.onEvent(event);
      if (event.type === "run.report" && path !== GLOBAL_PATH) {
        s.finished = true;
        source.close();
        s.source = null;
      }
    };
    source.onerror = () => {
      source.close();
      if (s.closed || s.finished) return;
      reportFailure();
      broadcast("reconnecting");
      s.timer = setTimeout(connect, backoff(s.attempt++));
    };
  };
  connect();
}

const sseTransport: Transport = {
  open(path, onEvent, onStatus) {
    let s = streams.get(path);
    const listener: Listener = { onEvent, onStatus };
    if (!s) {
      s = { listeners: new Set([listener]), status: "connecting", buffer: [], ids: new Set(), finished: false, source: null, timer: null, attempt: 0, closed: false };
      streams.set(path, s);
      startStream(path, s);
    } else {
      s.listeners.add(listener);
      // Joined an existing stream: hand over what it has already delivered, then its state.
      for (const e of s.buffer) onEvent(e);
      if (s.status === "live" || s.finished) queueMicrotask(() => s!.listeners.has(listener) && onStatus("live"));
    }
    const joined = s;
    return () => {
      joined.listeners.delete(listener);
      if (joined.listeners.size > 0) return;
      joined.closed = true;
      if (joined.timer) clearTimeout(joined.timer);
      joined.source?.close();
      if (streams.get(path) === joined) streams.delete(path);
    };
  },
};

/** For tests and the connection indicator: how many real connections are open or being retried. */
export const openStreamCount = () => [...streams.values()].filter((s) => !s.finished).length;

const mockTransport: Transport = {
  open(path, onEvent, onStatus) {
    queueMicrotask(() => onStatus("live"));
    return mockSubscribe(path, onEvent);
  },
};

// Chosen per subscription: the offline-demo switch closes live streams and reopens them on the mock; a replay plays the recording.
const transport = () => (isReplay() ? (replayTransport as Transport) : isMock() ? mockTransport : sseTransport);

const runPath = (runId: string) => `/api/payment-runs/${encodeURIComponent(runId)}/events`;

export interface RunEventsState {
  /** Every event of the run so far, in arrival order, without duplicates. */
  events: RunEvent[];
  status: StreamStatus;
}

/**
 * Every event of one run. Stored events replay first, so connecting late is fine. A reconnect replays the run from the
 * start; events are de-duplicated by id. Pass null for no run. The stream stays open after run.report (the server keeps
 * it open too): a controller's approve or reject arrives later on the same run, as payment.reviewed then payment.paid
 * or payment.blocked. Status stays "complete" from run.report on, except while reconnecting.
 */
export function useRunEvents(runId: string | null): RunEventsState {
  const [state, setState] = useState<RunEventsState>({ events: [], status: runId ? "connecting" : "idle" });
  const mode = useDataMode();

  useEffect(() => {
    if (!runId) {
      setState({ events: [], status: "idle" });
      return;
    }
    setState({ events: [], status: "connecting" });

    const seen = new Set<string>();
    let closed = false;
    let done = false;
    const close = transport().open(
      runPath(runId),
      (event) => {
        if (closed || seen.has(event.id)) return;
        seen.add(event.id);
        if (event.type === "run.report") done = true;
        setState((s) => ({ events: [...s.events, event], status: done ? "complete" : "live" }));
      },
      (status) => {
        if (closed) return;
        const next = done && status === "live" ? "complete" : status;
        setState((s) => (s.status === next ? s : { ...s, status: next }));
      },
    );

    return () => {
      closed = true;
      close();
    };
  }, [runId, mode]);

  return state;
}

/** Events the board needs from the global channel: they can arrive after the run's own stream was closed. */
const LATE_TYPES = new Set<string>([
  "call.started",
  "call.transcript",
  "call.outcome",
  "payment.paid",
  "payment.held",
  "payment.blocked",
  "payment.reviewed",
  "run.updated",
  "demo.reset",
]);

export interface GlobalEventsState {
  events: RunEvent[];
  /** Counts every (re)connection of the stream. The channel has no replay, so a change means events may have been missed. */
  connections: number;
}

/**
 * The global channel (GET /api/leaderboard/events), kept open for the whole session. A verification call can finish
 * after the run stream closed (or while it was reconnecting); its events, and the payment's final status, arrive here.
 * No replay. Reopened on the offline-demo switch like every other stream.
 */
export function useGlobalEvents(): GlobalEventsState {
  const [state, setState] = useState<GlobalEventsState>({ events: [], connections: 0 });
  const mode = useDataMode();
  useEffect(() => {
    setState((s) => ({ ...s, events: [] }));
    const seen = new Set<string>();
    let wasLive = false;
    return transport().open(
      "/api/leaderboard/events",
      (event) => {
        if (!LATE_TYPES.has(event.type) || seen.has(event.id)) return;
        seen.add(event.id);
        setState((s) => ({ ...s, events: [...s.events.slice(-1999), event] }));
      },
      (status) => {
        if (status === "live" && !wasLive) {
          wasLive = true;
          setState((s) => ({ ...s, connections: s.connections + 1 }));
        } else if (status !== "live") wasLive = false;
      },
    );
  }, [mode]);
  return state;
}

/** A run's own events plus the global channel's events for the same run, de-duplicated by id and in time order. */
export function mergeEvents(own: RunEvent[], late: RunEvent[]): RunEvent[] {
  if (late.length === 0) return own;
  const ids = new Set(own.map((e) => e.id));
  const extra = late.filter((e) => !ids.has(e.id));
  if (extra.length === 0) return own;
  return [...own, ...extra].sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : 0)); // stable
}

/**
 * Live attack.logged events for the leaderboard. No replay: load history with api.leaderboard() first, and again after
 * a reconnect (onStatus reports "live" once the stream is back).
 */
export function subscribeLeaderboard(onEvent: (e: AttackLoggedEvent) => void, onStatus: (s: StreamStatus) => void = () => {}): Unsubscribe {
  return transport().open("/api/leaderboard/events", (e) => e.type === "attack.logged" && onEvent(e), onStatus);
}
