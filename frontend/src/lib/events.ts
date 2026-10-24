// Server-sent events. One flat JSON object per message, switch on `type` (docs/events.md).
// The server keeps the stream open after run.completed; callers close it with the returned function.

import { USE_MOCKS, streamUrl } from "@/lib/api";
import { mockSubscribe } from "@/lib/mock";
import type { AttackLoggedEvent, RunEvent } from "@/lib/types";

export type Unsubscribe = () => void;

interface StreamHandlers<E> {
  onEvent: (event: E) => void;
  onError?: (error: Event) => void;
}

function subscribe<E>(path: string, { onEvent, onError }: StreamHandlers<E>): Unsubscribe {
  if (USE_MOCKS) return mockSubscribe(path, onEvent as (e: RunEvent) => void);

  const source = new EventSource(streamUrl(path));
  source.onmessage = (msg) => {
    try {
      onEvent(JSON.parse(msg.data) as E);
    } catch {
      // A malformed frame is dropped; the next one still arrives.
    }
  };
  // EventSource reconnects on its own (server sends retry: 3000) and replays the run from the start.
  if (onError) source.onerror = onError;
  return () => source.close();
}

/** Every event of one run. Stored events replay first, so it is safe to connect late. */
export function subscribeRun(runId: string, handlers: StreamHandlers<RunEvent>): Unsubscribe {
  return subscribe(`/api/payment-runs/${runId}/events`, handlers);
}

/** Live attack.logged events for the leaderboard. No replay: load history with api.leaderboard() first. */
export function subscribeLeaderboard(handlers: StreamHandlers<AttackLoggedEvent>): Unsubscribe {
  return subscribe("/api/leaderboard/events", handlers);
}
