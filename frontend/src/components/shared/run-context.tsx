import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api-error";
import { getDataMode, isMock, useDataMode, type DataMode } from "@/lib/data-mode";
import { mergeEvents, useGlobalEvents, useRunEvents, type StreamStatus } from "@/lib/events";
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
  /** After a demo reset: forget the run and every cached record. */
  forgetAfterReset: () => void;
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
  if (isMock()) return null;
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function storeRun(runId: string | null) {
  if (isMock()) return;
  try {
    if (runId) sessionStorage.setItem(STORAGE_KEY, runId);
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage unavailable: the run is still followed for this visit.
  }
}

function readPinned(): PinnedAttack | null {
  if (isMock()) return null;
  try {
    const raw = sessionStorage.getItem(PIN_KEY);
    return raw ? (JSON.parse(raw) as PinnedAttack) : null;
  } catch {
    return null;
  }
}

function storePinned(p: PinnedAttack | null) {
  if (isMock()) return;
  try {
    if (p) sessionStorage.setItem(PIN_KEY, JSON.stringify(p));
    else sessionStorage.removeItem(PIN_KEY);
  } catch {
    // Storage unavailable: the pin lasts for this visit.
  }
}

interface Owned<T> {
  value: T;
  mode: DataMode;
}

const owned = <T,>(value: T | null): Owned<T> | null => (value === null ? null : { value, mode: getDataMode() });

export function RunProvider({ children }: { children: ReactNode }) {
  // A run id belongs to the server or to the mock. Each is tagged with the mode it started in and only followed in that
  // mode: on the offline-demo switch the stream hook re-subscribes before the switch effect below clears the run, and a
  // live id handed to the mock would start a mock run under it.
  const mode = useDataMode();
  const [run, setRun] = useState<Owned<string> | null>(() => owned(readStoredRun()));
  const runId = run && run.mode === mode ? run.value : null;
  const setRunId = useCallback((id: string | null) => setRun(owned(id)), []);
  const { events: runEvents, status } = useRunEvents(runId);
  const global = useGlobalEvents();
  const events = useMemo(() => mergeEvents(runEvents, global.events.filter((e) => e.run_id === runId)), [runEvents, global.events, runId]);
  const summary = useMemo(() => summarizeRun(events), [events]);
  const [pin, setPin] = useState<Owned<PinnedAttack> | null>(() => owned(readPinned()));
  const pinned = pin && pin.mode === mode ? pin.value : null;
  const setPinned = useCallback((p: PinnedAttack | null) => setPin(owned(p)), []);
  const { events: ownPinnedEvents } = useRunEvents(pinned?.runId ?? null);
  const pinnedEvents = useMemo(
    () => mergeEvents(ownPinnedEvents, global.events.filter((e) => e.run_id === (pinned?.runId ?? null))),
    [ownPinnedEvents, global.events, pinned?.runId],
  );
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

  // A late call outcome changes a payment's record, and the global channel has no replay: refetch every payment record
  // when one arrives and when the channel reconnects.
  const lateSettled = global.events.filter((e) => e.type !== "call.transcript" && e.type !== "call.started" && e.type !== "demo.reset").length;
  useEffect(() => {
    void queryClient.invalidateQueries({ queryKey: ["payment"] });
  }, [lateSettled, global.connections, queryClient]);

  const startRun = useCallback(async () => {
    const { run_id } = await api.startRun();
    storeRun(run_id);
    setRunId(run_id);
    return run_id;
  }, [setRunId]);

  // When the mode flips, drop the run and the pin, and if a run was underway, start one on the new side so the board
  // keeps moving (the offline demo's whole point).
  const lastMode = useRef(mode);
  const runRef = useRef(run);
  runRef.current = run;
  useEffect(() => {
    if (lastMode.current === mode) return;
    lastMode.current = mode;
    const hadRun = runRef.current !== null;
    try {
      sessionStorage.removeItem(STORAGE_KEY);
      sessionStorage.removeItem(PIN_KEY);
    } catch {
      // Nothing stored to clear.
    }
    setRunId(null);
    setPinned(null);
    setFailedRun(null);
    if (mode === "mock" && hadRun)
      void startRun().catch((err) => toast.error("Offline payment run not started", { description: errorMessage(err) }));
  }, [mode, startRun, setRunId, setPinned]);

  const pinAttack = useCallback((a: PinnedAttack) => {
    storePinned(a);
    setPinned(a);
  }, [setPinned]);

  const unpin = useCallback(() => {
    storePinned(null);
    setPinned(null);
  }, [setPinned]);

  const clearRun = useCallback(() => {
    storeRun(null);
    setRunId(null);
    unpin();
  }, [unpin, setRunId]);

  // After a reset the run and every cached record are gone. Payment records (the drawer's and the board rows') are
  // dropped, not refetched: the rows are still mounted at this point and would each ask for a deleted payment.
  const forgetAfterReset = useCallback(() => {
    clearRun();
    const isPayment = (key: readonly unknown[]) => key[0] === "payment" || key[0] === "payment-row";
    queryClient.removeQueries({ predicate: (q) => isPayment(q.queryKey) });
    void queryClient.invalidateQueries();
  }, [clearRun, queryClient]);

  // The demo was reset in another browser. A reset from this one arrives here too, after the dialog already forgot
  // everything; doing it twice only refetches what is cached.
  const resets = global.events.filter((e) => e.type === "demo.reset").length;
  useEffect(() => {
    if (resets > 0) forgetAfterReset();
  }, [resets, forgetAfterReset]);

  const value = useMemo(
    () => ({ runId, events, status, summary, startRun, clearRun, forgetAfterReset, runFailed, pinned, pinnedEvents, pinAttack, unpin, allEvents }),
    [runId, events, status, summary, startRun, clearRun, forgetAfterReset, runFailed, pinned, pinnedEvents, pinAttack, unpin, allEvents],
  );
  return <RunContext.Provider value={value}>{children}</RunContext.Provider>;
}

export function useCurrentRun(): CurrentRun {
  const ctx = useContext(RunContext);
  if (!ctx) throw new Error("useCurrentRun must be used inside RunProvider");
  return ctx;
}
