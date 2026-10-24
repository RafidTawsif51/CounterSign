import type { ReactNode } from "react";

// Empty screens tell the user what to do next. Left-aligned, no illustration.
export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="px-4 py-10 sm:px-6">
      <p className="font-medium">{title}</p>
      {children && <div className="mt-1 max-w-[64ch] text-sm text-ink-muted">{children}</div>}
    </div>
  );
}
