import { useQuery } from "@tanstack/react-query";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CatchRateChart, type CatchRateDatum } from "@/components/redteam/catch-rate-chart";
import { Money } from "@/components/shared/money";
import { PageHeader } from "@/components/shared/page-header";
import { InlineError } from "@/components/shared/inline-error";
import { ApiError, api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { RedTeamFamily, RedTeamResults } from "@/lib/types";

// Red-team results: generated attacks mixed with clean invoices, run against a plain AI agent told to "pay valid
// invoices" and against Countersign. Weights are hackathon starting points; this page is how we show what they do.

const FAMILY: Record<RedTeamFamily, string> = {
  bank_change: "Bank change",
  poisoned_invoice: "Poisoned invoice",
  ceo_pressure: "CEO pressure",
  lookalike_domain: "Lookalike domain",
  amount_padding: "Amount padding",
};

export function RedTeam() {
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({ queryKey: ["redteam"], queryFn: api.redTeamResults, retry: false });
  const notBuilt = error instanceof ApiError && error.status === 404;

  return (
    <>
      <PageHeader
        title="Red team"
        description="Generated attacks mixed with clean invoices, run against a plain AI agent told to pay valid invoices, and against Countersign."
      />
      <div className="max-w-[1120px] space-y-8 px-4 py-6 sm:px-6">
        {isLoading ? (
          <Loading />
        ) : isError && notBuilt ? (
          <p className="text-sm text-ink-muted">
            No red-team results on the server yet. Catch rates, money that would have been lost and false positives per attack family
            appear here once the red-team harness has run.
          </p>
        ) : isError ? (
          <InlineError what="Red-team results" error={error} onRetry={() => void refetch()} retrying={isFetching} />
        ) : data ? (
          <Results data={data} />
        ) : null}
      </div>
    </>
  );
}

function Results({ data }: { data: RedTeamResults }) {
  const f = data.families;
  const sum = (k: keyof RedTeamResults["families"][number]) => f.reduce((t, r) => t + Number(r[k]), 0);
  const lostBaseline = sum("lost_to_scammers_usd_baseline");
  const lostCountersign = sum("lost_to_scammers_usd_countersign");
  const rate = (n: number, of: number) => (of ? (n / of) * 100 : 0);
  const chart: CatchRateDatum[] = f.map((r) => ({
    family: r.family,
    label: FAMILY[r.family],
    baseline: rate(r.caught_baseline, r.attacks),
    countersign: rate(r.caught_countersign, r.attacks),
    attacks: r.attacks,
    caughtBaseline: r.caught_baseline,
    caughtCountersign: r.caught_countersign,
  }));

  return (
    <>
      {data.source === "mock" && (
        <p className="text-sm text-ink-muted">
          Sample numbers: the red-team harness has not run yet, so these show the layout, not a measurement.
        </p>
      )}

      <section aria-label="Money sent to scammers" className="flex flex-wrap items-end gap-x-12 gap-y-4 border-b border-rule pb-6">
        <div>
          <p className="text-sm text-ink-muted">Money a plain AI agent would have sent to scammers</p>
          <Money amount={lostBaseline} className="mt-1 block text-xl font-medium" />
        </div>
        <div>
          <p className="text-sm text-ink-muted">Countersign</p>
          <Money amount={lostCountersign} className="mt-1 block text-xl font-medium" />
        </div>
        <p className="max-w-[44ch] text-sm text-ink-muted">
          Counted only when the money went to an account the attacker controls. A miss that pays the vendor's verified account
          moves no money to a scammer.
        </p>
      </section>

      <CatchRateChart data={chart} />

      <section aria-label="Results by attack family" className="overflow-hidden rounded-lg border border-rule bg-surface">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Attack family</TableHead>
              <TableHead className="text-right">Attacks</TableHead>
              <TableHead className="text-right">Caught by baseline</TableHead>
              <TableHead className="text-right">Caught by Countersign</TableHead>
              <TableHead className="text-right">False positives on clean invoices</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {f.map((r) => (
              <TableRow key={r.family}>
                <TableCell className="font-medium">{FAMILY[r.family]}</TableCell>
                <TableCell className="figure text-right">{r.attacks}</TableCell>
                <TableCell className="text-right">
                  <Count n={r.caught_baseline} of={r.attacks} />
                </TableCell>
                <TableCell className="text-right">
                  <Count n={r.caught_countersign} of={r.attacks} strong />
                </TableCell>
                <TableCell className="text-right">
                  <FalsePositives baseline={r.false_positives_baseline} countersign={r.false_positives_countersign} clean={r.clean_invoices} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
          <TableFooter>
            <TableRow className="hover:bg-transparent">
              <TableCell className="font-medium">All families</TableCell>
              <TableCell className="text-right">
                <span className="figure ledger-total inline-block py-0.5">{sum("attacks")}</span>
              </TableCell>
              <TableCell className="text-right">
                <span className="ledger-total inline-block py-0.5">
                  <Count n={sum("caught_baseline")} of={sum("attacks")} />
                </span>
              </TableCell>
              <TableCell className="text-right">
                <span className="ledger-total inline-block py-0.5">
                  <Count n={sum("caught_countersign")} of={sum("attacks")} strong />
                </span>
              </TableCell>
              <TableCell className="text-right">
                <span className="ledger-total inline-block py-0.5">
                  <FalsePositives baseline={sum("false_positives_baseline")} countersign={sum("false_positives_countersign")} clean={sum("clean_invoices")} />
                </span>
              </TableCell>
            </TableRow>
          </TableFooter>
        </Table>
      </section>

      <p className="text-sm text-ink-muted">
        Legitimate bank changes handled by Countersign:{" "}
        <span className="figure text-ink">{data.legit_changes.handled_countersign}</span> of{" "}
        <span className="figure text-ink">{data.legit_changes.total}</span>. Median time per run: baseline{" "}
        <span className="figure text-ink">{data.median_run_seconds.baseline}</span> s, Countersign{" "}
        <span className="figure text-ink">{data.median_run_seconds.countersign}</span> s. Run {formatDate(data.generated_at)}. Signal
        weights are hackathon starting points, not validated; these results are how we judge them.
      </p>
    </>
  );
}

function Count({ n, of, strong = false }: { n: number; of: number; strong?: boolean }) {
  return (
    <span className="whitespace-nowrap">
      <span className={`figure ${strong ? "font-medium text-ink" : ""}`}>{n}</span>
      <span className="figure ml-2 inline-block w-11 text-ink-muted">{of ? Math.round((n / of) * 100) : 0}%</span>
    </span>
  );
}

function FalsePositives({ baseline, countersign, clean }: { baseline: number; countersign: number; clean: number }) {
  return (
    <span className="whitespace-nowrap text-ink-muted">
      Countersign <span className="figure text-ink">{countersign}</span>, baseline <span className="figure text-ink">{baseline}</span>, of{" "}
      <span className="figure">{clean}</span>
    </span>
  );
}

function Loading() {
  return (
    <div aria-busy className="space-y-4">
      <Skeleton className="h-10 w-96" />
      <Skeleton className="h-72 w-full" />
      <Skeleton className="h-48 w-full" />
    </div>
  );
}
