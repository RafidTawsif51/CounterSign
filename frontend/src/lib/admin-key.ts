// The admin key (ADMIN_KEY on the server) for the routes that wipe the demo or spend money: reset and the red-team run. It is asked
// for once, kept in sessionStorage for this tab only, and sent as the X-Admin-Key header. It is never read from the build or the
// environment, so it is never in the bundle.

import { useSyncExternalStore } from "react";

const STORAGE_KEY = "countersign-admin-key";

export function getAdminKey(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY) || null;
  } catch {
    return null;
  }
}

export function setAdminKey(key: string) {
  try {
    sessionStorage.setItem(STORAGE_KEY, key);
  } catch {
    // Storage blocked: the key is asked for again next time.
  }
}

export function clearAdminKey() {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing to clear.
  }
}

interface Prompt {
  /** True when the server refused the key that was just tried. */
  retry: boolean;
  resolve: (key: string | null) => void;
}

let prompt: Prompt | null = null;
let pendingAnswer: Promise<string | null> | null = null;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

/** Ask the person for the key. Resolves with it (already stored), or null if they cancel. One question at a time. */
export function askForAdminKey(retry = false): Promise<string | null> {
  if (pendingAnswer) return pendingAnswer;
  pendingAnswer = new Promise<string | null>((resolve) => {
    prompt = {
      retry,
      resolve: (key) => {
        prompt = null;
        pendingAnswer = null;
        emit();
        resolve(key);
      },
    };
    emit();
  });
  return pendingAnswer;
}

export function answerAdminKey(key: string | null) {
  const trimmed = key?.trim();
  if (trimmed) setAdminKey(trimmed);
  prompt?.resolve(trimmed || null);
}

/** The question being asked, or null. For the dialog in the app shell. */
export function useAdminKeyPrompt(): { retry: boolean } | null {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => prompt,
  );
}
