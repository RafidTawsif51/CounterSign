import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { InlineError } from "@/components/shared/inline-error";
import { PageHeader } from "@/components/shared/page-header";
import { API_URL, api } from "@/lib/api";
import { useDataMode } from "@/lib/data-mode";
import { formatClock, formatRelativeTime } from "@/lib/format";
import { DOCUMENTED_STATUS, MODE_LABEL } from "@/lib/system-status";
import type { ComponentMode, HealthResponse, SystemComponentStatus } from "@/lib/types";

// What is real, what is sandboxed, what is simulated, and how we know. Reached from the "Sandbox" label in the top bar.
// The labels say what each component is in the product; health's mock flags say what this server is running right now,
// so a component labeled Real can never quietly be a mock in front of a judge.

const BADGE: Record<ComponentMode, "accent" | "neutral"> = { real: "accent", sandboxed: "neutral", simulated: "neutral", mock: "neutral", degraded: "neutral" };

export function SystemStatus() {
  const status = useQuery({ queryKey: ["system-status"], queryFn: api.systemStatus, retry: false });
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 15_000 });

  // Any failure here (an older server without the route, a 500) falls back to the documented list, never an empty page.
  const rows: SystemComponentStatus[] | null = status.data ?? (status.isError ? DOCUMENTED_STATUS : null);

  return (
    <>
      <PageHeader title="System status" description="What is real, what runs in a sandbox, what is simulated, and how we know." />
      <div className="max-w-[1120px] px-4 py-6 sm:px-6">
        <ServerLine health={health.data} error={health.error} onRetry={() => void health.refetch()} retrying={health.isFetching} updatedAt={health.dataUpdatedAt} />

        {rows ? (
          <ul className="mt-5 divide-y divide-rule overflow-hidden rounded-lg border border-rule bg-surface">
            {rows.map((r) => (
              <Row key={r.name} row={r} health={health.data} />
            ))}
          </ul>
        ) : (
          <ListSkeleton />
        )}

        <p className="mt-4 max-w-[80ch] text-sm text-ink-muted">
          {status.data
            ? "From the server's own status report."
            : "The server's status report did not load, so this is the documented list, with the server's mock switches checked live."}{" "}
          All money is sandbox money. Every vendor, person and company in the demo is fictional.
        </p>
      </div>
    </>
  );
}

function ServerLine({
  health,
  error,
  onRetry,
  retrying,
  updatedAt,
}: {
  health: HealthResponse | undefined;
  error: unknown;
  onRetry: () => void;
  retrying: boolean;
  updatedAt: number;
}) {
  const mode = useDataMode();
  if (error && !health) return <InlineError what="The server's health check" error={error} onRetry={onRetry} retrying={retrying} />;
  if (!health) return <Skeleton className="h-4 w-96" />;
  const where = mode === "mock" ? "Offline demo: built-in data in this browser" : `Connected to ${API_URL || window.location.origin}`;
  const mocks = Object.entries(health.mocks).filter(([, on]) => on).length;
  return (
    <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-muted">
      <span className="text-ink">{where}</span>
      <span>
        Database <span className="text-ink">{health.database === "postgres" ? "Postgres" : "SQLite"}</span>
      </span>
      <span>
        <span className="figure text-ink">{mocks}</span> of <span className="figure">{Object.keys(health.mocks).length}</span> components on their mock
      </span>
      <span>
        Checked <span className="figure">{formatClock(new Date(updatedAt).toISOString())}</span>
      </span>
    </p>
  );
}

function Row({ row, health }: { row: SystemComponentStatus; health: HealthResponse | undefined }) {
  const onMock = (row.mock_flags ?? []).filter((f) => health?.mocks[f]);
  return (
    <li className="grid gap-x-6 gap-y-1 px-4 py-3.5 sm:grid-cols-[220px_110px_120px_1fr]">
      <span className="font-medium">{row.name}</span>
      <span>
        <Badge variant={BADGE[row.mode]}>{MODE_LABEL[row.mode]}</Badge>
      </span>
      <span className="text-sm text-ink-muted" title="Last success">
        {row.last_success_at ? formatRelativeTime(row.last_success_at) : "None yet"}
      </span>
      <span className="text-sm">
        <span className="text-ink-muted">{row.detail}</span>
        {onMock.length > 0 && (
          <span className="mt-0.5 block text-ink">
            Running on its mock on this server ({onMock.map((f) => `MOCK_${f.toUpperCase()}`).join(", ")}).
          </span>
        )}
      </span>
    </li>
  );
}

function ListSkeleton() {
  return (
    <div aria-busy className="mt-5 space-y-3">
      {Array.from({ length: 8 }, (_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}
