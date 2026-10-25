// Where data comes from: the FastAPI server ("live"), lib/mock in this browser ("mock", the offline demo), or a recording of a
// real run ("replay", lib/replay.ts). VITE_USE_MOCKS=true starts in mock. The offline-demo switch flips it at runtime without a reload, and every open
// window follows, so the leaderboard on the second screen goes offline with the board.

import { useSyncExternalStore } from "react";

export type DataMode = "live" | "mock" | "replay";

const STORAGE_KEY = "countersign-data-mode";
/** Built with VITE_USE_MOCKS=true: offline on purpose, with no live server to go back to. */
export const BUILT_MOCK = import.meta.env.VITE_USE_MOCKS === "true";

// Per tab, so a reload keeps the offline demo going; a fresh visit starts from the build setting again.
function readStored(): DataMode | null {
  try {
    const v = sessionStorage.getItem(STORAGE_KEY);
    return v === "live" || v === "mock" || v === "replay" ? v : null;
  } catch {
    return null;
  }
}

let mode: DataMode = readStored() ?? (BUILT_MOCK ? "mock" : "live");
const listeners = new Set<() => void>();
const channel = typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel("countersign-data-mode");

function apply(next: DataMode) {
  if (next === mode) return;
  mode = next;
  try {
    sessionStorage.setItem(STORAGE_KEY, next);
  } catch {
    // Not kept across a reload; the switch still applies now.
  }
  listeners.forEach((l) => l());
}

channel?.addEventListener("message", (e: MessageEvent) => {
  if (e.data === "live" || e.data === "mock" || e.data === "replay") apply(e.data);
});

export const getDataMode = (): DataMode => mode;
export const isMock = () => mode === "mock";
export const isReplay = () => mode === "replay";

export function setDataMode(next: DataMode) {
  apply(next);
  channel?.postMessage(next);
}

export function subscribeDataMode(onChange: () => void) {
  listeners.add(onChange);
  return () => {
    listeners.delete(onChange);
  };
}

export function useDataMode(): DataMode {
  return useSyncExternalStore(subscribeDataMode, getDataMode, getDataMode);
}
