import { useEffect, useRef } from "react";
import { animate, motion, useMotionValue, useReducedMotion, useTransform } from "framer-motion";
import { cn } from "@/lib/utils";

// Adapted from 21st.dev "Number Ticker" (danielpetho/basic-number-ticker).
// Tweens from the previous value to the new one when the value changes. Never animates on mount (DESIGN.md: state
// changes only), never overshoots, and jumps straight to the value under reduced motion. Digits are tabular mono, so
// the width does not jitter while the number moves.

const EASE_OUT = [0.2, 0, 0, 1] as const;

export function NumberTicker({
  value,
  format = (n) => String(Math.round(n)),
  className,
}: {
  value: number;
  format?: (n: number) => string;
  className?: string;
}) {
  const count = useMotionValue(value);
  const text = useTransform(count, format);
  const reduce = useReducedMotion();
  const formatRef = useRef(format);
  formatRef.current = format;

  useEffect(() => {
    if (reduce) {
      count.set(value);
      return;
    }
    const controls = animate(count, value, { type: "tween", duration: 0.2, ease: EASE_OUT });
    return () => controls.stop();
  }, [value, reduce, count]);

  return (
    <motion.span className={cn("figure", className)} aria-label={formatRef.current(value)}>
      {text}
    </motion.span>
  );
}
