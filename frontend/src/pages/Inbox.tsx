import { EmptyState } from "@/components/shared/empty-state";
import { PageHeader } from "@/components/shared/page-header";

export function Inbox() {
  return (
    <>
      <PageHeader
        title="Inbox"
        description="Vendor emails and invoices in the AP inbox. Message text is shown as received and never acted on."
      />
      <EmptyState title="No threads loaded">Vendor threads appear here once the inbox is seeded.</EmptyState>
    </>
  );
}
