import { useEffect, useRef, useState } from "react";

const FRESH_MS = 1200;

/**
 * Ids that appeared after the first load, kept "fresh" briefly so their row can show an arrival highlight that then
 * fades (the fade is a CSS transition on the row). Pass null until the list has loaded so the first load is not news.
 * `scope` resets what counts as already seen (for example, switching threads).
 */
export function useArrivals(ids: string[] | null, scope?: string): Set<string> {
  const seen = useRef<Set<string> | null>(null);
  const seenScope = useRef(scope);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const timers = useRef<number[]>([]);
  const key = ids?.join("|") ?? null;

  // Each arrival fades on its own clock; a second arrival must not cancel the first one's fade.
  useEffect(() => () => timers.current.forEach(window.clearTimeout), []);

  useEffect(() => {
    if (!ids) return;
    if (seen.current === null || seenScope.current !== scope) {
      seen.current = new Set(ids);
      seenScope.current = scope;
      setFresh(new Set());
      return;
    }
    const arrived = ids.filter((id) => !seen.current!.has(id));
    if (arrived.length === 0) return;
    arrived.forEach((id) => seen.current!.add(id));
    setFresh((f) => new Set([...f, ...arrived]));
    timers.current.push(window.setTimeout(() => setFresh((f) => new Set([...f].filter((id) => !arrived.includes(id)))), FRESH_MS));
  }, [key, scope]); // key stands in for ids

  return fresh;
}
