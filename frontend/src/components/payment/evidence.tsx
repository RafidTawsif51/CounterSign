import * as React from "react";
import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

// Evidence links: a claim shows the id of the row that backs it (evd_ signal, cal_ call, inj_ finding, ras_ assessment,
// bac_ bank account, aud_ audit entry). Hovering or focusing the id highlights every element registered as its source.
// The "ask why" answer returns the same ids, so it can reuse EvidenceRef as is.

interface EvidenceState {
  active: string | null;
  setActive: (id: string | null) => void;
  /** Set by a click: the source stays lit for a moment after the scroll, when the pointer has left the chip. */
  pinned: string | null;
  pin: (id: string) => void;
}

const EvidenceContext = createContext<EvidenceState>({ active: null, setActive: () => {}, pinned: null, pin: () => {} });
const PIN_MS = 1600;

export function EvidenceProvider({ children }: { children: ReactNode }) {
  const [active, setActive] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);
  const timer = React.useRef<number | undefined>(undefined);
  const pin = React.useCallback((id: string) => {
    window.clearTimeout(timer.current);
    setPinned(id);
    timer.current = window.setTimeout(() => setPinned(null), PIN_MS);
  }, []);
  React.useEffect(() => () => window.clearTimeout(timer.current), []);
  const value = useMemo(() => ({ active, setActive, pinned, pin }), [active, pinned, pin]);
  return <EvidenceContext.Provider value={value}>{children}</EvidenceContext.Provider>;
}

/**
 * `evd_1a2b3c4d5e6f` shown as `evd_1a2b`. Readable ids (seeded `pay_atk_bank_change`, derived `rule:destination_changed`)
 * are cut at 14 characters instead, so they never end on a bare separator. The full id is in the title and the label.
 */
export function shortId(id: string) {
  const [prefix, rest = ""] = id.split(/_(.*)/s);
  if (/^[0-9a-f]{8,}$/.test(rest)) return `${prefix}_${rest.slice(0, 4)}`;
  return id.length <= 14 ? id : `${id.slice(0, 13).replace(/[_:]$/, "")}…`;
}

/**
 * An evidence chip. `target` is what it lights up and scrolls to when that differs from the id it shows (an /ask
 * citation of a call points at one transcript line, `cal_x#2`). Extra props pass through, so it can be a tooltip trigger.
 */
export function EvidenceRef({
  id,
  target,
  className,
  ...rest
}: { id: string | null | undefined; target?: string } & Omit<React.ComponentProps<"button">, "id">) {
  const { active, setActive, pin } = useContext(EvidenceContext);
  if (!id) return null;
  const goal = target ?? id;
  const on = active === goal || active === id;
  return (
    <button
      type="button"
      title={id}
      aria-label={`Evidence ${id}`}
      {...rest}
      onMouseEnter={() => setActive(goal)}
      onMouseLeave={() => setActive(null)}
      onFocus={() => setActive(goal)}
      onBlur={() => setActive(null)}
      onClick={() => {
        pin(goal);
        revealSource(goal);
      }}
      className={cn(
        "figure inline-flex h-[18px] shrink-0 items-center rounded-sm border px-1 align-middle text-xs leading-none transition-colors",
        on ? "border-accent bg-accent-tint text-accent" : "border-rule text-ink-muted hover:border-accent hover:text-accent",
        className,
      )}
    >
      {shortId(id)}
    </button>
  );
}

/** Scroll the first element backing this id into view, so a highlighted source is never off screen. */
function revealSource(id: string) {
  const el = [...document.querySelectorAll<HTMLElement>("[data-evidence]")].find((e) => e.dataset.evidence!.split(" ").includes(id));
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  el?.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
}

/** Props for an element that is the source of one or more evidence ids. */
export function useEvidenceSource(ids: (string | null | undefined)[]) {
  const { active, pinned } = useContext(EvidenceContext);
  const list = ids.filter(Boolean) as string[];
  const on = (active !== null && list.includes(active)) || (pinned !== null && list.includes(pinned));
  return {
    "data-evidence": list.join(" ") || undefined,
    className: cn(
      "rounded-md outline outline-1 -outline-offset-1 transition-[background-color,outline-color] duration-150",
      on ? "bg-accent-tint outline-accent" : "outline-transparent",
    ),
  };
}
