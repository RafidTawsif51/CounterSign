import type { ReactNode } from "react";

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3 border-b border-rule px-4 py-5 sm:px-6">
      <div className="min-w-0">
        <h1 className="text-lg font-semibold">{title}</h1>
        {description && <p className="mt-0.5 max-w-[72ch] text-sm text-ink-muted">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
