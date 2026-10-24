import { Link } from "react-router-dom";
import { FlaskRound, Search } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { iconProps } from "@/components/shared/icon";
import { Kbd, modKey } from "@/components/shared/kbd";
import { ResetDemoDialog } from "@/components/shared/reset-demo-dialog";
import { useCurrentRun } from "@/components/shared/run-context";
import { USE_MOCKS } from "@/lib/api";
import { cn } from "@/lib/utils";

export function TopBar({ onOpenPalette }: { onOpenPalette: () => void }) {
  return (
    <header className="sticky top-0 z-30 flex h-12 shrink-0 items-center gap-4 border-b border-rule bg-paper px-4 sm:px-6">
      {/* On a phone the live run line matters more than the company name, which the board already shows. */}
      <span className="hidden shrink-0 font-medium sm:inline">Ridgeline Builders</span>
      <span aria-hidden className="hidden h-4 w-px shrink-0 bg-rule-strong sm:block" />
      <RunStatus />

      <div className="ml-auto flex shrink-0 items-center gap-2">
        <button
          type="button"
          onClick={onOpenPalette}
          className="hidden h-7 items-center gap-2 rounded-md border border-rule-strong bg-surface pr-1 pl-2 text-sm text-ink-muted transition-colors hover:text-ink sm:inline-flex"
        >
          <Search {...iconProps} />
          <span className="pr-6">Search</span>
          <Kbd>{modKey}K</Kbd>
        </button>

        <Tooltip>
          <TooltipTrigger asChild>
            <Link
              to="/status"
              className="hidden h-7 items-center gap-1.5 rounded-md border border-rule-strong bg-surface px-2 text-sm text-ink-muted transition-colors hover:text-ink md:inline-flex"
            >
              <FlaskRound {...iconProps} />
              {USE_MOCKS ? "Sandbox, mock data" : "Sandbox"}
            </Link>
          </TooltipTrigger>
          <TooltipContent side="bottom">All money is sandbox money. See what is real and what is simulated.</TooltipContent>
        </Tooltip>

        <ResetDemoDialog />
      </div>
    </header>
  );
}

function RunStatus() {
  const { runId, status, summary, runFailed } = useCurrentRun();
  const total = summary.invoiceCount;

  let detail: React.ReactNode;
  if (!runId) detail = <span className="text-ink-muted">Not started</span>;
  else if (status === "reconnecting") detail = <span className="text-ink-muted">Reconnecting…</span>;
  else if (runFailed) detail = <span className="text-ink-muted">Stopped when the server restarted. Start a new run.</span>;
  else if (total == null) detail = <span className="text-ink-muted">Starting</span>;
  else
    detail = (
      <span className="text-ink-muted">
        <span className="figure text-ink">{summary.processed}</span> of <span className="figure text-ink">{total}</span> processed
      </span>
    );

  const live = runId && !summary.completed && !runFailed && status === "live";

  return (
    <div className="flex min-w-0 items-center gap-2 text-sm" aria-live="polite">
      <span
        aria-hidden
        className={cn("size-1.5 shrink-0 transition-colors", live ? "bg-accent" : "border border-ink-faint")}
      />
      <span className="shrink-0">Thursday run</span>
      <span className="truncate">{detail}</span>
      {summary.completed && (
        <span className="hidden shrink-0 items-center gap-3 pl-1 lg:flex">
          <span aria-hidden className="h-3.5 w-px bg-rule-strong" />
          <span className="text-paid-ink">
            <span className="figure">{summary.paid}</span> paid
          </span>
          {summary.held > 0 && (
            <span className="text-held-ink">
              <span className="figure">{summary.held}</span> held
            </span>
          )}
          {summary.blocked > 0 && (
            <span className="text-blocked-ink">
              <span className="figure">{summary.blocked}</span> blocked
            </span>
          )}
        </span>
      )}
    </div>
  );
}
