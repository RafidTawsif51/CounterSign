import { useState } from "react";
import { Outlet } from "react-router-dom";
import { Play } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/shared/empty-state";
import { iconProps } from "@/components/shared/icon";
import { PageHeader } from "@/components/shared/page-header";
import { useCurrentRun } from "@/components/shared/run-context";

export function Board() {
  const { runId, summary, startRun } = useCurrentRun();
  const [starting, setStarting] = useState(false);
  const running = Boolean(runId) && !summary.completed;

  async function start() {
    setStarting(true);
    try {
      await startRun();
      toast.success("Payment run started", { description: "40 open invoices for Ridgeline Builders." });
    } catch (err) {
      toast.error("Payment run not started", { description: err instanceof Error ? err.message : "The server did not respond." });
    } finally {
      setStarting(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Payment run"
        description="This week's open invoices. Clean payments go out automatically; anything paying a new destination is held for a call."
        actions={
          <Button variant="primary" onClick={start} disabled={starting || running}>
            <Play {...iconProps} />
            {running ? "Run in progress" : "Start payment run"}
          </Button>
        }
      />
      {runId ? (
        <EmptyState title="Payments for this run appear here">
          The ledger, hold reasons and verification calls are next. Follow the run in the top bar meanwhile.
        </EmptyState>
      ) : (
        <EmptyState title="No payment run yet">
          Start a payment run to process this week's 40 open invoices for Ridgeline Builders.
        </EmptyState>
      )}
      {/* Payment detail drawer renders here at /payments/:paymentId. */}
      <Outlet />
    </>
  );
}
