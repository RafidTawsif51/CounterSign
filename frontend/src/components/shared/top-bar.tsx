import { NavLink, useNavigate } from "react-router-dom";
import { Keyboard, Monitor, Search } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { iconProps } from "@/components/shared/icon";
import { Kbd, modKey } from "@/components/shared/kbd";
import { DataModeIndicator } from "@/components/shared/offline-demo";
import { ResetDemoDialog } from "@/components/shared/reset-demo-dialog";
import { useVisibleNav } from "@/components/shared/nav";
import { useDataMode } from "@/lib/data-mode";
import { useCurrentRun } from "@/components/shared/run-context";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api-error";
import { setPresenting, usePresenting } from "@/lib/presentation";
import { cn } from "@/lib/utils";

export function TopBar({
  onOpenPalette,
  onOpenShortcuts,
  resetOpen,
  onResetOpenChange,
}: {
  onOpenPalette: () => void;
  onOpenShortcuts: () => void;
  resetOpen: boolean;
  onResetOpenChange: (open: boolean) => void;
}) {
  const presenting = usePresenting();
  const replay = useDataMode() === "replay";
  const navigate = useNavigate();
  const { forgetAfterReset } = useCurrentRun();

  // One click for the stage: reset to the seeded week (the leaderboard stays), open the board, hide the developer controls.
  async function present() {
    try {
      await api.resetDemo(true);
      forgetAfterReset();
      navigate("/app");
      setPresenting(true);
      toast.success("Demo reset", { description: "Presenting. The leaderboard was kept. Press F to leave presentation mode." });
    } catch (err) {
      toast.error("Demo not reset", { description: errorMessage(err) });
    }
  }

  return (
    <header className="sticky top-0 z-30 flex h-12 shrink-0 items-center gap-4 border-b border-rule bg-paper px-4 sm:px-6">
      {/* On a phone the live run line matters more than the company name, which the board already shows. */}
      <span className="hidden shrink-0 font-medium sm:inline">Ridgeline Builders</span>
      <span aria-hidden className="hidden h-4 w-px shrink-0 bg-rule-strong sm:block" />
      <RunStatus />

      {presenting && <PresentationNav />}

      <div className="ml-auto flex shrink-0 items-center gap-2">
        {!presenting && !replay && <button
          type="button"
          onClick={onOpenPalette}
          className="hidden h-7 items-center gap-2 rounded-md border border-rule-strong bg-surface pr-1 pl-2 text-sm text-ink-muted transition-colors hover:text-ink sm:inline-flex"
        >
          <Search {...iconProps} />
          <span className="pr-6">Search</span>
          <Kbd>{modKey}K</Kbd>
        </button>}

        <DataModeIndicator />

        {presenting ? (
          <Button size="sm" variant="ghost" onClick={() => setPresenting(false)} title="Leave presentation mode (F)">
            Exit presentation
          </Button>
        ) : replay ? null : (
          <>
            <Button size="icon-sm" variant="ghost" onClick={onOpenShortcuts} aria-label="Keyboard shortcuts" title="Keyboard shortcuts (?)" className="hidden sm:inline-flex">
              <Keyboard {...iconProps} />
            </Button>
            <Button size="sm" onClick={present} title="Reset the demo (the leaderboard is kept), open the board and hide the controls" className="hidden sm:inline-flex">
              <Monitor {...iconProps} />
              Present
            </Button>
            <ResetDemoDialog open={resetOpen} onOpenChange={onResetOpenChange} />
          </>
        )}
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

/** With the sidebar hidden, the screens a judge needs stay one click away. No developer controls here. */
function PresentationNav() {
  const nav = useVisibleNav();
  const items = nav.filter((n) => ["/app", "/app/attack", "/app/leaderboard", "/app/red-team", "/app/status"].includes(n.to));
  return (
    <nav aria-label="Screens" className="ml-4 hidden items-center gap-1 md:flex">
      {items.map((n) =>
        n.newTab ? (
          <a key={n.to} href={n.to} target="countersign-leaderboard" rel="noreferrer" className="rounded-md px-2 py-1 text-sm text-ink-muted transition-colors hover:bg-sunken hover:text-ink">
            {n.label}
          </a>
        ) : (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.end}
            className={({ isActive }) => cn("rounded-md px-2 py-1 text-sm transition-colors hover:bg-sunken", isActive ? "font-medium text-ink" : "text-ink-muted hover:text-ink")}
          >
            {n.label}
          </NavLink>
        ),
      )}
    </nav>
  );
}
