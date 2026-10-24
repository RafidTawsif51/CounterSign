import { EmptyState } from "@/components/shared/empty-state";
import { PageHeader } from "@/components/shared/page-header";

export function RedTeam() {
  return (
    <>
      <PageHeader
        title="Red team"
        description="Generated attacks mixed with clean invoices, run against a baseline agent and against Countersign."
      />
      <EmptyState title="No red-team results yet">
        Catch rate, money that would have been lost and false positives per attack family appear here after a run.
      </EmptyState>
    </>
  );
}
