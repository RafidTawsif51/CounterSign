import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { USE_MOCKS, api } from "@/lib/api";
import { useRunEvents, type StreamStatus } from "@/lib/events";
import { summarizeRun, type RunSummary } from "@/lib/run-summary";
import type { RunEvent } from "@/lib/types";

// The run the app is looking at. One stream subscription for the whole shell; the top bar, palette and board share it.

interface CurrentRun {
  runId: string | null;
  events: RunEvent[];
  status: StreamStatus;
  summary: RunSummary;
  startRun: () => Promise<string>;
  clearRun: () => void;
}

const RunContext = createContext<CurrentRun | null>(null);
const STORAGE_KEY = "countersign-run";

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

export function RunProvider({ children }: { children: ReactNode }) {
  const [runId, setRunId] = useState<string | null>(readStoredRun);
  const { events, status } = useRunEvents(runId);
  const summary = useMemo(() => summarizeRun(events), [events]);

  const startRun = useCallback(async () => {
    const { run_id } = await api.startRun();
    storeRun(run_id);
    setRunId(run_id);
    return run_id;
  }, []);

  const clearRun = useCallback(() => {
    storeRun(null);
    setRunId(null);
  }, []);

  const value = useMemo(
    () => ({ runId, events, status, summary, startRun, clearRun }),
    [runId, events, status, summary, startRun, clearRun],
  );
  return <RunContext.Provider value={value}>{children}</RunContext.Provider>;
}

export function useCurrentRun(): CurrentRun {
  const ctx = useContext(RunContext);
  if (!ctx) throw new Error("useCurrentRun must be used inside RunProvider");
  return ctx;
}
