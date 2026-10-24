import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

// One drawer section: hairline above, a quiet heading, no card around it.
export function Section({
  title,
  aside,
  children,
  className,
}: {
  title: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("border-t border-rule px-5 py-4", className)}>
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-medium text-ink-muted">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}
