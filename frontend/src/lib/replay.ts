// Recorded replay: the backup for a demo that cannot run live (no Wi-Fi, no server, a call that will not connect).
//
// A recording is a real finished payment run, saved by `python -m scripts.record_run` as public/replay/recorded-run.json: every
// event the server stored for the run, plus the answers the screens ask for while it plays (each payment's detail, the vendor
// list, and so on), and a note of which services were live or simulated when it was recorded. Replay plays those events back
// through the same hooks the live stream uses, and answers requests from the recording. It never talks to the server, and the
// screen says Replay the whole time (components/shared/replay-banner.tsx): a replay is never presented as live.

import { useQuery } from "@tanstack/react-query";
import { ApiError } from "@/lib/api-error";
import { getDataMode, setDataMode } from "@/lib/data-mode";
import type { RunEvent } from "@/lib/types";

export interface RecordingMeta {
  recorded_at: string;
  run_id: string;
  event_count: number;
  payments: number;
  /** "live" or "simulated", per service, when it was recorded. */
  services: Record<string, "live" | "simulated">;
  all_live: boolean;
}

export interface Recording {
  meta: RecordingMeta;
  events: RunEvent[];
  /** "GET /api/..." to the server's answer when it was recorded. */
  responses: Record<string, unknown>;
}

const URL = "/replay/recorded-run.json";
let loaded: Recording | null = null;
let loading: Promise<Recording> | null = null;

/** Fetched from this site's own files, so it works with the server down. Rejects when no recording was saved. */
export function loadRecording(): Promise<Recording> {
  if (loaded) return Promise.resolve(loaded);
  loading ??= fetch(URL, { cache: "no-store" })
    .then(async (res) => {
      // The dev server answers an unknown file with index.html; only JSON with events counts.
      const body = res.ok && (res.headers.get("content-type") ?? "").includes("json") ? ((await res.json()) as Recording) : null;
      if (!body || !Array.isArray(body.events) || body.events.length === 0) throw new Error("no recording");
      loaded = body;
      return body;
    })
    .finally(() => {
      loading = null;
    });
  return loading;
}

export const getRecording = () => loaded;

/** The recording, once loaded, or null when there is none. Components offer replay only when this is not null. */
export function useRecording(): Recording | null {
  const { data } = useQuery({ queryKey: ["recording"], queryFn: loadRecording, staleTime: Infinity, retry: false });
  return data ?? null;
}

/** Switch every window to the recording. Rejects when there is nothing to play. */
export async function startReplay(): Promise<void> {
  await loadRecording();
  setDataMode("replay");
}

export function leaveReplay() {
  setDataMode("live");
}

/**
 * When each event fires, in ms from the start. Real gaps are squeezed: a live run takes minutes, a replay should take about
 * half a minute. Call lines keep a readable pace so the transcript can be followed; the whole thing never exceeds 45 s.
 */
export function pace(events: RunEvent[]): number[] {
  const floor = (e: RunEvent) => (e.type === "call.transcript" ? 900 : e.type === "call.started" ? 700 : e.type === "call.outcome" ? 900 : 70);
  const cap = (e: RunEvent) => (e.type.startsWith("call.") ? 2500 : 700);
  let prev = Date.parse(events[0].at);
  const gaps = events.map((e, i) => {
    const t = Date.parse(e.at);
    const real = i === 0 || Number.isNaN(t) || Number.isNaN(prev) ? 0 : Math.max(0, t - prev);
    prev = t;
    return Math.min(Math.max(real, floor(e)), cap(e));
  });
  const total = gaps.reduce((a, b) => a + b, 0);
  const k = total > 45_000 ? 45_000 / total : 1;
  let at = 300;
  return gaps.map((g) => (at += g * k));
}

/** The event stream during a replay: the recorded run, played once from the top. Every other channel stays silent. */
export const replayTransport = {
  open(path: string, onEvent: (e: RunEvent) => void, onStatus: (s: "live" | "idle") => void): () => void {
    const rec = loaded;
    const wanted = path.match(/^\/api\/payment-runs\/([^/]+)\/events$/);
    queueMicrotask(() => onStatus(rec ? "live" : "idle"));
    if (!rec || !wanted || decodeURIComponent(wanted[1]) !== rec.meta.run_id) return () => {}; // nothing live is ever mixed in
    let closed = false;
    const times = pace(rec.events);
    const timers = rec.events.map((e, i) => setTimeout(() => !closed && onEvent(e), times[i]));
    return () => {
      closed = true;
      timers.forEach(clearTimeout);
    };
  },
};

/** The server's answer to a GET, as recorded. Anything else is not part of a replay. */
export function replayRequest<T>(method: string, path: string): T {
  if (method !== "GET") throw new ApiError(409, path, "This is a replay of a recorded run. Leave the replay to do that.");
  const hit = loaded?.responses[`GET ${path.split("?")[0]}`];
  if (hit === undefined) throw new ApiError(404, path, "That is not part of the recording.");
  return hit as T;
}

/** For labels: was this service live when it was recorded? */
export const recordedSimulated = (service: string): boolean => (loaded?.meta.services[service] ?? "simulated") !== "live";

export const inReplay = () => getDataMode() === "replay";
