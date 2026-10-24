import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

// Evidence links: a claim shows the id of the row that backs it (evd_ signal, cal_ call, inj_ finding, ras_ assessment,
// bac_ bank account, aud_ audit entry). Hovering or focusing the id highlights every element registered as its source.
// The "ask why" answer returns the same ids, so it can reuse EvidenceRef as is.

interface EvidenceState {
  active: string | null;
  setActive: (id: string | null) => void;
}

const EvidenceContext = createContext<EvidenceState>({ active: null, setActive: () => {} });

export function EvidenceProvider({ children }: { children: ReactNode }) {
  const [active, setActive] = useState<string | null>(null);
  const value = useMemo(() => ({ active, setActive }), [active]);
  return <EvidenceContext.Provider value={value}>{children}</EvidenceContext.Provider>;
}

/** `evd_1a2b3c4d5e6f` shown as `evd_1a2b`. The full id is in the title and the accessible name. */
export function shortId(id: string) {
  const [prefix, rest = ""] = id.split(/_(.*)/s);
  return `${prefix}_${rest.slice(0, 4)}`;
}

export function EvidenceRef({ id, className }: { id: string | null | undefined; className?: string }) {
  const { active, setActive } = useContext(EvidenceContext);
  if (!id) return null;
  const on = active === id;
  return (
    <button
      type="button"
      title={id}
      aria-label={`Evidence ${id}`}
      onMouseEnter={() => setActive(id)}
      onMouseLeave={() => setActive(null)}
      onFocus={() => setActive(id)}
      onBlur={() => setActive(null)}
      onClick={() => revealSource(id)}
      className={cn(
        "figure inline-flex h-[18px] shrink-0 items-center rounded-sm border px-1 align-middle text-[11px] leading-none transition-colors",
        on ? "border-accent bg-accent-tint text-accent" : "border-rule text-ink-faint hover:border-accent hover:text-accent",
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
  el?.scrollIntoView({ block: "nearest", behavior: reduce ? "auto" : "smooth" });
}

/** Props for an element that is the source of one or more evidence ids. */
export function useEvidenceSource(ids: (string | null | undefined)[]) {
  const { active } = useContext(EvidenceContext);
  const list = ids.filter(Boolean) as string[];
  const on = active !== null && list.includes(active);
  return {
    "data-evidence": list.join(" ") || undefined,
    className: cn(
      "rounded-md outline outline-1 -outline-offset-1 transition-[background-color,outline-color] duration-150",
      on ? "bg-accent-tint outline-accent" : "outline-transparent",
    ),
  };
}
