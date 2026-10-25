// "On this page" for long pages. Adapted from the Table of Contents component by inference-sh on 21st.dev
// (https://21st.dev/@inference-sh/components/table-of-contents): the IntersectionObserver scroll spy is theirs; the look follows
// DESIGN.md (hairline rail, accent edge on the current section, sentence case, no lowercase tracking label).

import { useCallback, useEffect, useState } from "react";
import { cn } from "@/lib/utils";

export interface TocItem {
  id: string;
  title: string;
}

/** The id of the section currently under the sticky header. `topOffset` is the header height in px. */
export function useActiveSection(ids: string[], topOffset = 120): string {
  const [active, setActive] = useState(ids[0] ?? "");
  const key = ids.join("|");

  useEffect(() => {
    if (!ids.length) return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) if (e.isIntersecting) setActive(e.target.id);
      },
      { rootMargin: `-${topOffset}px 0px -70% 0px`, threshold: 0 },
    );
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, topOffset]);

  return active;
}

/** Scroll to a section and keep the address bar in step. Smooth only when the reader has not asked for reduced motion. */
export function useScrollToSection() {
  return useCallback((id: string) => {
    const el = document.getElementById(id);
    if (!el) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    history.replaceState(null, "", `#${id}`);
  }, []);
}

export function TableOfContents({ items, active, className }: { items: TocItem[]; active: string; className?: string }) {
  const go = useScrollToSection();
  if (!items.length) return null;
  return (
    <nav aria-label="On this page" className={cn("text-sm", className)}>
      <p className="mb-2 text-ink-muted">On this page</p>
      <ul className="border-l border-rule">
        {items.map(({ id, title }) => {
          const current = active === id;
          return (
            <li key={id}>
              <a
                href={`#${id}`}
                aria-current={current ? "location" : undefined}
                onClick={(e) => {
                  e.preventDefault();
                  go(id);
                }}
                className={cn(
                  "-ml-px block border-l py-1 pl-3 transition-colors",
                  current ? "border-accent font-medium text-ink" : "border-transparent text-ink-muted hover:border-rule-strong hover:text-ink",
                )}
              >
                {title}
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
