import { EmptyState } from "@/components/shared/empty-state";
import { PageHeader } from "@/components/shared/page-header";

export function AttackConsole() {
  return (
    <>
      <PageHeader
        title="Attack console"
        description="Try to get money sent to the wrong account. Every attempt goes through the same pipeline and lands on the leaderboard."
      />
      <EmptyState title="Pick an attack card">
        Bank change, AI hijack, CEO pressure or freestyle. Attack cards appear here.
      </EmptyState>
    </>
  );
}
