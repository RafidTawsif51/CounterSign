import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Kbd({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <kbd
      className={cn(
        "figure inline-flex h-5 min-w-5 items-center justify-center rounded-sm border border-rule-strong bg-surface px-1 text-xs text-ink-muted",
        className,
      )}
    >
      {children}
    </kbd>
  );
}

export const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);
export const modKey = isMac ? "⌘" : "Ctrl";
