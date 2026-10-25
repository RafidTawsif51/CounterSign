import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useDataMode } from "@/lib/data-mode";
import { getRecording, leaveReplay } from "@/lib/replay";

const SERVICES: Record<string, string> = { twilio: "Twilio", cartesia: "Cartesia", apify: "Apify", crs: "CRS", nessie: "Nessie", claude: "Claude" };
const when = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

/**
 * Shown for the whole of a replay, on every screen. A replay is a real run played back from a recording, never live, and this
 * says so, says when it was recorded and says which services were simulated at that time.
 */
export function ReplayBanner() {
  const mode = useDataMode();
  const rec = getRecording();
  if (mode !== "replay" || !rec) return null;
  const simulated = Object.entries(rec.meta.services).filter(([, v]) => v !== "live").map(([k]) => SERVICES[k] ?? k);
  return (
    <div role="status" className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-ink bg-surface px-4 py-2 text-sm sm:px-6">
      <Badge variant="accent">Replay</Badge>
      <p className="min-w-0 flex-1">
        A recording of a payment run from {when.format(new Date(rec.meta.recorded_at))}. Nothing on this screen is live.{" "}
        <span className="text-ink-muted">
          {rec.meta.all_live ? "Every service was live when it was recorded." : `${simulated.join(", ")} ${simulated.length === 1 ? "was" : "were"} simulated when it was recorded.`}
        </span>
      </p>
      <Button size="sm" onClick={leaveReplay}>
        Exit replay
      </Button>
    </div>
  );
}
