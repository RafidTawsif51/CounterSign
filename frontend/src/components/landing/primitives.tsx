// Motion primitives for the project page (/) only. Each is our own build of a 21st.dev component, restyled to DESIGN.md and
// written for framer-motion (the app's one motion library). Credits:
//   EncryptedText (manuarora700), AnimatedShinyText, AnimatedList, Marquee, NumberTicker, BlurFade (dillionverma, Magic UI).
// Every one has a reduced-motion path that renders the final state with no movement. See DESIGN.md, Project page.

import { AnimatePresence, motion, useInView, useReducedMotion } from "framer-motion";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

const EASE = [0.2, 0, 0, 1] as const;

/** A headline that resolves from scrambled glyphs once, on load. The final text is laid out in flow from the start (invisible while
 *  scrambling), so nothing shifts. Screen readers get the final text only. */
export function EncryptedText({ text, className, durationMs = 900 }: { text: string; className?: string; durationMs?: number }) {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(reduce ? text : "");
  useEffect(() => {
    if (reduce) return;
    const glyphs = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz0123456789";
    const start = performance.now();
    let raf = 0;
    let stopped = false;
    const finish = () => {
      stopped = true;
      cancelAnimationFrame(raf);
      setShown(text);
    };
    const tick = () => {
      if (stopped) return;
      const now = performance.now();
      const done = Math.min(1, (now - start) / durationMs);
      if (done >= 1) return finish();
      const fixed = Math.floor(done * text.length);
      setShown(text.split("").map((ch, i) => (i < fixed || ch === " " || ch === "," || ch === "." ? ch : glyphs[(i * 7 + Math.floor(now / 40)) % glyphs.length])).join(""));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    // Frames can stall (a background tab, a slow device): the headline always settles, and nothing writes after it has.
    const settle = setTimeout(finish, durationMs + 300);
    return () => {
      stopped = true;
      cancelAnimationFrame(raf);
      clearTimeout(settle);
    };
  }, [text, durationMs, reduce]);
  const settled = shown === text;
  return (
    <span className={cn("relative block", className)} aria-label={text}>
      <span aria-hidden className={settled ? "" : "invisible"}>{text}</span>
      {!settled && <span aria-hidden className="absolute inset-0 overflow-hidden">{shown}</span>}
    </span>
  );
}

/** A light sheen that crosses the text once after load, then rests. */
export function ShinyText({ children, className }: { children: ReactNode; className?: string }) {
  const reduce = useReducedMotion();
  if (reduce) return <span className={className}>{children}</span>;
  return (
    <motion.span
      className={cn("bg-clip-text text-transparent", className)}
      style={{
        backgroundImage: "linear-gradient(110deg, var(--ink-muted) 40%, var(--ink) 50%, var(--ink-muted) 60%)",
        backgroundSize: "250% 100%",
      }}
      initial={{ backgroundPosition: "100% 0" }}
      animate={{ backgroundPosition: "0% 0" }}
      transition={{ duration: 1.6, delay: 0.6, ease: EASE }}
    >
      {children}
    </motion.span>
  );
}

/** A rolling feed: it starts full, then every interval a new item arrives at the top and the oldest leaves at the bottom, cycling
 *  through `items`. The box is never empty and never changes height. Reduced motion: the first `size` items, still. */
export function AnimatedList<T>({ items, render, keyOf, size = 5, intervalMs = 1800, className }: {
  items: T[]; render: (item: T) => ReactNode; keyOf: (item: T) => string; size?: number; intervalMs?: number; className?: string;
}) {
  const reduce = useReducedMotion();
  const [k, setK] = useState(size - 1); // index of the newest item shown, counting up forever
  useEffect(() => {
    if (reduce) return;
    const t = setInterval(() => setK((n) => n + 1), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs, reduce]);
  const visible = Array.from({ length: Math.min(size, items.length) }, (_, i) => {
    const n = k - i;
    return { n, item: items[((n % items.length) + items.length) % items.length] };
  });
  return (
    <ol className={cn("flex flex-col gap-2 overflow-hidden", className)}>
      <AnimatePresence initial={false} mode="popLayout">
        {visible.map(({ n, item }) => (
          <motion.li
            key={`${n}-${keyOf(item)}`}
            layout={!reduce}
            initial={reduce ? false : { opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2, ease: EASE }}
          >
            {render(item)}
          </motion.li>
        ))}
      </AnimatePresence>
    </ol>
  );
}

/** A slow row that loops, pauses on hover or focus, and stands still (wrapped) with reduced motion. */
export function Marquee({ children, className, seconds = 40 }: { children: ReactNode; className?: string; seconds?: number }) {
  const reduce = useReducedMotion();
  if (reduce) return <div className={cn("flex flex-wrap gap-x-10 gap-y-3", className)}>{children}</div>;
  return (
    <div className={cn("group overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_6%,black_94%,transparent)]", className)}>
      <div className="flex w-max animate-marquee gap-10 group-hover:[animation-play-state:paused] group-focus-within:[animation-play-state:paused]" style={{ animationDuration: `${seconds}s` }}>
        <div className="flex shrink-0 gap-10">{children}</div>
        <div className="flex shrink-0 gap-10" aria-hidden>{children}</div>
      </div>
    </div>
  );
}

/** Counts up once, the first time it scrolls into view. Tabular figures, so the width never changes. */
export function NumberTicker({ value, className, durationMs = 900 }: { value: number; className?: string; durationMs?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-10% 0px" });
  const reduce = useReducedMotion();
  const [n, setN] = useState(reduce ? value : 0);
  useEffect(() => {
    if (!inView || reduce) return;
    const start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / durationMs);
      setN(Math.round(value * (1 - Math.pow(1 - p, 3))));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [inView, value, durationMs, reduce]);
  return <span ref={ref} className={cn("figure", className)}>{n.toLocaleString("en-US")}</span>;
}

/** Fades a block in once as it enters the view (used on three sections only). */
export function BlurFade({ children, className }: { children: ReactNode; className?: string }) {
  const reduce = useReducedMotion();
  if (reduce) return <div className={className}>{children}</div>;
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 8, filter: "blur(4px)" }}
      whileInView={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      viewport={{ once: true, margin: "-15% 0px" }}
      transition={{ duration: 0.4, ease: EASE }}
    >
      {children}
    </motion.div>
  );
}
