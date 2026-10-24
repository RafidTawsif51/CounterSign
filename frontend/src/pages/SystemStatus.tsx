import { EmptyState } from "@/components/shared/empty-state";
import { PageHeader } from "@/components/shared/page-header";

export function SystemStatus() {
  return (
    <>
      <PageHeader
        title="System status"
        description="What is real, what is simulated, and what is running on mocks right now."
      />
      <EmptyState title="Status not loaded">Each component's live or simulated state appears here.</EmptyState>
    </>
  );
}
