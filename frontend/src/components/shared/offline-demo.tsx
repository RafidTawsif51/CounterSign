import { useState } from "react";
import { Link } from "react-router-dom";
import { FlaskRound, WifiOff } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { iconProps } from "@/components/shared/icon";
import { useCurrentRun } from "@/components/shared/run-context";
import { API_URL } from "@/lib/api-url";
import { UNREACHABLE_AFTER_MS, useConnection } from "@/lib/connection";
import { setDataMode, useDataMode } from "@/lib/data-mode";
import { startReplay, useRecording } from "@/lib/replay";

// The backup path for the live demo. When the server stops answering, a quiet line under the top bar offers the
// offline demo: the same flow on lib/mock in this browser, no reload, works with Wi-Fi off. While offline the top bar
// says so, and offers the way back once the server answers again.

const serverName = () => {
  try {
    return new URL(API_URL || window.location.origin).host;
  } catch {
    return API_URL;
  }
};

export function OfflineBanner() {
  const mode = useDataMode();
  const { unreachable, downSince } = useConnection();
  const { runId } = useCurrentRun();
  const recording = useRecording();
  // "Keep waiting" lasts for this outage only; if the server comes back and drops again, the line returns.
  const [dismissedFor, setDismissedFor] = useState<number | null>(null);
  if (mode !== "live" || !unreachable || dismissedFor === downSince) return null;

  function goOffline() {
    const hadRun = runId !== null;
    setDataMode("mock");
    toast("Offline demo", {
      description: hadRun
        ? "Built-in data in this browser. The payment run restarted from the top."
        : "Built-in data in this browser. Nothing is sent to the server.",
    });
  }

  return (
    <div role="status" className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-rule bg-surface px-4 py-2 text-sm sm:px-6">
      <WifiOff {...iconProps} className="shrink-0 text-ink-muted" />
      <p className="min-w-0 flex-1">
        The server at <span className="figure">{serverName()}</span> has not answered for {UNREACHABLE_AFTER_MS / 1000} seconds.{" "}
        <span className="text-ink-muted">
          {recording ? "A recorded replay plays back a real run. The offline demo runs the same flow on built-in sample data." : "The offline demo runs the same flow on built-in data in this browser."}
        </span>
      </p>
      <div className="flex shrink-0 items-center gap-2">
        <Button size="sm" variant="ghost" onClick={() => setDismissedFor(downSince)}>
          Keep waiting
        </Button>
        {recording && (
          <Button size="sm" onClick={() => void startReplay()}>
            Show recorded replay
          </Button>
        )}
        <Button size="sm" onClick={goOffline}>
          <WifiOff {...iconProps} />
          Switch to offline demo
        </Button>
      </div>
    </div>
  );
}

/** Top bar: what the data is. Sandbox when live; Offline demo when on the mock, with the way back once it exists. */
export function DataModeIndicator() {
  const mode = useDataMode();
  const { reachable } = useConnection();

  if (mode === "replay")
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border border-ink bg-surface px-2 text-sm font-medium text-ink">
            <FlaskRound {...iconProps} />
            Replay
          </span>
        </TooltipTrigger>
        <TooltipContent side="bottom">A recording of a real run, played back. Nothing here is live and no money moves.</TooltipContent>
      </Tooltip>
    );

  if (mode === "live")
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <Link
            to="/status"
            className="hidden h-7 items-center gap-1.5 rounded-md border border-rule-strong bg-surface px-2 text-sm text-ink-muted transition-colors hover:text-ink md:inline-flex"
          >
            <FlaskRound {...iconProps} />
            Sandbox
          </Link>
        </TooltipTrigger>
        <TooltipContent side="bottom">All money is sandbox money. See what is real and what is simulated.</TooltipContent>
      </Tooltip>
    );

  function goLive() {
    setDataMode("live");
    toast("Back on the live server", { description: `Connected to ${serverName()}. Start a payment run to continue.` });
  }

  return (
    <>
      <Tooltip>
        <TooltipTrigger asChild>
          <Link
            to="/status"
            className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border border-ink bg-surface px-2 text-sm font-medium text-ink"
          >
            <WifiOff {...iconProps} />
            Offline demo
          </Link>
        </TooltipTrigger>
        <TooltipContent side="bottom">Built-in data in this browser. Nothing is sent to the server, and no money moves.</TooltipContent>
      </Tooltip>
      {reachable && (
        <Button size="sm" onClick={goLive}>
          Back to live
        </Button>
      )}
    </>
  );
}
