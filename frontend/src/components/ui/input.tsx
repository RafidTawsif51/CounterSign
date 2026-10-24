import * as React from "react";
import { cn } from "@/lib/utils";

// Shared field look for input, textarea and select trigger.
export const fieldClass =
  "w-full min-w-0 rounded-md border border-rule-strong bg-surface text-base text-ink transition-colors outline-none placeholder:text-ink-faint focus-visible:border-accent disabled:cursor-not-allowed disabled:opacity-45 aria-invalid:border-blocked";

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        fieldClass,
        "h-8 px-2.5 file:mr-2 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-ink",
        className,
      )}
      {...props}
    />
  );
}

export { Input };
