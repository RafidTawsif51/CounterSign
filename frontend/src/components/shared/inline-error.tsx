import { RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { iconProps } from "@/components/shared/icon";
import { errorMessage } from "@/lib/api-error";
import { cn } from "@/lib/utils";

// What failed, in a sentence, and a way to try again. Never JSON, never a stack trace: ApiError messages are written for
// people (lib/api-error.ts). Status colors stay out of it; an error is not a payment state.
export function InlineError({
  what,
  error,
  onRetry,
  retrying = false,
  className,
}: {
  /** What did not load, e.g. "This thread". */
  what: string;
  error: unknown;
  onRetry?: () => void;
  retrying?: boolean;
  className?: string;
}) {
  return (
    <div role="alert" className={cn("flex flex-wrap items-center gap-x-3 gap-y-2 text-sm", className)}>
      <p>
        <span className="font-medium">{what} did not load.</span> <span className="text-ink-muted">{errorMessage(error)}.</span>
      </p>
      {onRetry && (
        <Button size="sm" onClick={onRetry} disabled={retrying}>
          <RotateCcw {...iconProps} />
          {retrying ? "Trying again" : "Try again"}
        </Button>
      )}
    </div>
  );
}
