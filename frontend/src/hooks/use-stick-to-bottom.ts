import { useEffect, useRef, type UIEvent } from "react";

/**
 * Keeps a scrolling list on its newest line while it grows, until the reader scrolls up; scrolling back to the bottom
 * re-pins it. Spread `onScroll` and attach `ref` to the scrolling element; pass anything that changes when a line lands.
 */
export function useStickToBottom<T extends HTMLElement>(dep: unknown) {
  const ref = useRef<T>(null);
  const pinned = useRef(true);
  const autoTop = useRef(0);

  useEffect(() => {
    const el = ref.current;
    if (!el || !pinned.current) return;
    el.scrollTop = el.scrollHeight;
    autoTop.current = el.scrollTop;
  }, [dep]);

  const onScroll = (e: UIEvent<T>) => {
    const el = e.currentTarget;
    // Our own scroll to the bottom can land after the next line arrived; only the reader unpins.
    if (Math.abs(el.scrollTop - autoTop.current) < 2) return;
    pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
  };

  return { ref, onScroll };
}
