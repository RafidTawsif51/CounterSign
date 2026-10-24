import { Outlet } from "react-router-dom";
import { EmptyState } from "@/components/shared/empty-state";
import { PageHeader } from "@/components/shared/page-header";

export function Board() {
  return (
    <>
      <PageHeader
        title="Payment run"
        description="This week's open invoices. Clean payments go out automatically; anything paying a new destination is held for a call."
      />
      <EmptyState title="No payment run yet">
        Start a payment run to process this week's 40 open invoices for Ridgeline Builders.
      </EmptyState>
      {/* Payment detail drawer renders here at /payments/:paymentId. */}
      <Outlet />
    </>
  );
}
