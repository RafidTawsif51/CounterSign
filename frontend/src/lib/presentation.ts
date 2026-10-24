// Presentation mode for the venue screen or projector: no sidebar, everything 1.15x (globals.css). F toggles it. Kept
// for this tab, and applied before first paint by the script in index.html, like the theme.

import { useSyncExternalStore } from "react";

const STORAGE_KEY = "countersign-presenting";

function read(): boolean {
  return document.documentElement.hasAttribute("data-presenting");
}

function subscribe(onChange: () => void) {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-presenting"] });
  return () => observer.disconnect();
}

export function usePresenting(): boolean {
  return useSyncExternalStore(subscribe, read, () => false);
}

export function setPresenting(on: boolean) {
  document.documentElement.toggleAttribute("data-presenting", on);
  try {
    if (on) sessionStorage.setItem(STORAGE_KEY, "1");
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Not kept across a reload; the mode still applies now.
  }
}
