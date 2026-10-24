import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { USE_MOCKS, api } from "@/lib/api";
import { useRunEvents, type StreamStatus } from "@/lib/events";
import { summarizeRun, type RunSummary } from "@/lib/run-summary";
import type { RunEvent } from "@/lib/types";

// The run the app is looking at. One stream subscription for the whole shell; the top bar, palette and board share it.
// A judge's attack runs as its own mini-run; the shell follows that too, so the board can pin it.

/** The attack launched from this browser, pinned on the board until dismissed. */
export interface PinnedAttack {
  runId: string;
  paymentId: string;
  attackId: string;
  attackerName: string;
  card: string;
}

interface CurrentRun {
  runId: string | null;
  events: RunEvent[];
  status: StreamStatus;
  summary: RunSummary;
  startRun: () => Promise<string>;
  clearRun: () => void;
  pinned: PinnedAttack | null;
  /** The pinned attack's mini-run, from attack.logged through run.report. */
  pinnedEvents: RunEvent[];
  /** The server marked this run failed (it restarted mid-run, run.mark_stale_runs). No more events will come. */
  runFailed: boolean;
  pinAttack: (a: PinnedAttack) => void;
  unpin: () => void;
  /** The run's events and the pinned attack's, for views keyed by payment (drawer, call panel, inbox markers). */
  allEvents: RunEvent[];
}

const RunContext = createContext<CurrentRun | null>(null);
const STORAGE_KEY = "countersign-run";
const PIN_KEY = "countersign-pinned-attack";

// A real run outlives a reload, so remember it. A mock run lives in memory and is gone after a reload.
function readStoredRun(): string | null {
  if (USE_MOCKS) return null;
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function storeRun(runId: string | null) {
  if (USE_MOCKS) return;
  try {
    if (runId) sessionStorage.setItem(STORAGE_KEY, runId);
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage unavailable: the run is still followed for this visit.
  }
}

function readPinned(): PinnedAttack | null {
  if (USE_MOCKS) return null;
  try {
    const raw = sessionStorage.getItem(PIN_KEY);
    return raw ? (JSON.parse(raw) as PinnedAttack) : null;
  } catch {
    return null;
  }
}

function storePinned(p: PinnedAttack | null) {
  if (USE_MOCKS) return;
  try {
    if (p) sessionStorage.setItem(PIN_KEY, JSON.stringify(p));
    else sessionStorage.removeItem(PIN_KEY);
  } catch {
    // Storage unavailable: the pin lasts for this visit.
  }
}

export function RunProvider({ children }: { children: ReactNode }) {
  const [runId, setRunId] = useState<string | null>(readStoredRun);
  const { events, status } = useRunEvents(runId);
  const summary = useMemo(() => summarizeRun(events), [events]);
  const [pinned, setPinned] = useState<PinnedAttack | null>(readPinned);
  const { events: pinnedEvents } = useRunEvents(pinned?.runId ?? null);
  const allEvents = useMemo(() => (pinnedEvents.length ? [...events, ...pinnedEvents] : events), [events, pinnedEvents]);
  const attackDone = pinnedEvents.some((e) => e.type === "run.completed");

  // A server that restarts mid-run marks the run failed without an event. Each time the stream (re)connects, ask.
  const [failedRun, setFailedRun] = useState<string | null>(null);
  useEffect(() => {
    if (!runId || status !== "live" || summary.completed) return;
    let stale = false;
    api
      .run(runId)
      .then((r) => !stale && setFailedRun(r.status === "failed" ? runId : null))
      .catch(() => {
        // The stream is live, so the server is up; a failed lookup is not worth surfacing.
      });
    return () => {
      stale = true;
    };
  }, [runId, status, summary.completed]);
  const runFailed = failedRun !== null && failedRun === runId;

  // A run records requested accounts and changes vendor history, so vendor data is stale once it completes.
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!summary.completed && !attackDone) return;
    void queryClient.invalidateQueries({ queryKey: ["vendors"] });
    void queryClient.invalidateQueries({ queryKey: ["vendor-history"] });
  }, [summary.completed, attackDone, runId, queryClient]);

  const startRun = useCallback(async () => {
    const { run_id } = await api.startRun();
    storeRun(run_id);
    setRunId(run_id);
    return run_id;
  }, []);

  const pinAttack = useCallback((a: PinnedAttack) => {
    storePinned(a);
    setPinned(a);
  }, []);

  const unpin = useCallback(() => {
    storePinned(null);
    setPinned(null);
  }, []);

  const clearRun = useCallback(() => {
    storeRun(null);
    setRunId(null);
    unpin();
  }, [unpin]);

  const value = useMemo(
    () => ({ runId, events, status, summary, startRun, clearRun, runFailed, pinned, pinnedEvents, pinAttack, unpin, allEvents }),
    [runId, events, status, summary, startRun, clearRun, runFailed, pinned, pinnedEvents, pinAttack, unpin, allEvents],
  );
  return <RunContext.Provider value={value}>{children}</RunContext.Provider>;
}

export function useCurrentRun(): CurrentRun {
  const ctx = useContext(RunContext);
  if (!ctx) throw new Error("useCurrentRun must be used inside RunProvider");
  return ctx;
}
