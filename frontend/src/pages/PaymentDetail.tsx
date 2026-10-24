import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { AskPanel } from "@/components/payment/ask-panel";
import { AuditTrail } from "@/components/payment/audit-trail";
import { CallSlot } from "@/components/payment/call-slot";
import { DecisionFooter } from "@/components/payment/decision-footer";
import { Destination } from "@/components/payment/destination";
import { EvidenceProvider } from "@/components/payment/evidence";
import { HardRules } from "@/components/payment/hard-rules";
import { InjectionFindings } from "@/components/payment/injection-findings";
import { PaymentHeader } from "@/components/payment/payment-header";
import { RiskBreakdown } from "@/components/payment/risk-breakdown";
import { useCurrentRun } from "@/components/shared/run-context";
import { ApiError, api } from "@/lib/api";

export function PaymentDetail() {
  const { paymentId = "" } = useParams<{ paymentId: string }>();
  const navigate = useNavigate();
  const query = useQuery({ queryKey: ["payment", paymentId], queryFn: () => api.payment(paymentId), retry: false });
  useLiveRefresh(paymentId);

  const detail = query.data;

  return (
    <Sheet open onOpenChange={(open) => !open && navigate("/")}>
      <SheetContent className="sm:max-w-[640px]">
        {detail ? (
          <EvidenceProvider>
            <div className="flex-1 overflow-y-auto">
              <PaymentHeader detail={detail} />
              <AskPanel key={detail.payment.id} detail={detail} />
              <HardRules risk={detail.risk} />
              <RiskBreakdown risk={detail.risk} />
              <Destination detail={detail} />
              <InjectionFindings findings={detail.findings} />
              <CallSlot detail={detail} />
              <AuditTrail entries={detail.audit} />
            </div>
            {detail.payment.status === "held" && <DecisionFooter paymentId={detail.payment.id} vendor={detail.vendor.name} />}
          </EvidenceProvider>
        ) : query.isError ? (
          <div className="px-5 pt-4">
            <SheetTitle>Payment not found</SheetTitle>
            <SheetDescription className="mt-1">
              {query.error instanceof ApiError && query.error.status === 404
                ? `${paymentId} is not part of a payment run yet. Start a payment run, then open the payment from the board.`
                : query.error.message}
            </SheetDescription>
          </div>
        ) : (
          <LoadingState />
        )}
      </SheetContent>
    </Sheet>
  );
}

/** While a run is live, refetch whenever an event about this payment arrives (call lines, outcome, decision). */
function useLiveRefresh(paymentId: string) {
  const { allEvents: events } = useCurrentRun();
  const queryClient = useQueryClient();
  const last = events.at(-1);
  const relevant = last && "payment_id" in last && last.payment_id === paymentId;

  useEffect(() => {
    if (relevant) void queryClient.invalidateQueries({ queryKey: ["payment", paymentId] });
  }, [relevant, last?.id, paymentId, queryClient]);
}

function LoadingState() {
  return (
    <div className="space-y-3 px-5 pt-4" aria-busy>
      <SheetTitle className="sr-only">Loading payment</SheetTitle>
      <SheetDescription className="sr-only">Loading payment detail</SheetDescription>
      <Skeleton className="h-6 w-48" />
      <Skeleton className="h-4 w-64" />
      <Skeleton className="mt-6 h-8 w-40" />
      <Skeleton className="mt-6 h-24 w-full" />
    </div>
  );
}
