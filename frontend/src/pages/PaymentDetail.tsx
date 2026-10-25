import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { AskPanel } from "@/components/payment/ask-panel";
import { AuditTrail } from "@/components/payment/audit-trail";
import { CallSlot } from "@/components/payment/call-slot";
import { DecisionFooter } from "@/components/payment/decision-footer";
import { DecisionTimeline } from "@/components/payment/decision-timeline";
import { Destination } from "@/components/payment/destination";
import { EvidenceProvider } from "@/components/payment/evidence";
import { HardRules } from "@/components/payment/hard-rules";
import { InjectionFindings } from "@/components/payment/injection-findings";
import { LiveProcessing } from "@/components/payment/live-processing";
import { PaymentHeader } from "@/components/payment/payment-header";
import { RiskBreakdown } from "@/components/payment/risk-breakdown";
import { InlineError } from "@/components/shared/inline-error";
import { useCurrentRun } from "@/components/shared/run-context";
import { ApiError, api } from "@/lib/api";
import { CARDS } from "@/lib/attack-cards";

const CARD_LABEL: Record<string, string> = Object.fromEntries(CARDS.map((c) => [c.id, c.title]));

export function PaymentDetail() {
  const { paymentId = "" } = useParams<{ paymentId: string }>();
  const navigate = useNavigate();
  const { pinned } = useCurrentRun();
  // The judge's own attack: its payment row appears a moment after launch, so keep asking until it does.
  const processing = pinned?.paymentId === paymentId;
  const query = useQuery({
    queryKey: ["payment", paymentId],
    queryFn: () => api.payment(paymentId),
    retry: false,
    refetchInterval: (q) => (processing && q.state.error instanceof ApiError && q.state.error.status === 404 ? 700 : false),
  });
  useLiveRefresh(paymentId);
  // Closing navigates away and unmounts the drawer before Radix can restore focus, so a keyboard user would land on
  // the page body. Put them back on the row they opened, unless focus already went somewhere on purpose.
  useEffect(
    () => () => {
      requestAnimationFrame(() => {
        if (document.activeElement && document.activeElement !== document.body) return;
        document.querySelector<HTMLElement>(`[data-payment-id="${CSS.escape(paymentId)}"]`)?.focus();
      });
    },
    [paymentId],
  );

  const detail = query.data;
  const hasCall = Boolean(detail && (detail.calls.length > 0 || (detail.payment.status === "held" && detail.risk?.decision === "hold_and_verify")));

  return (
    <Sheet open onOpenChange={(open) => !open && navigate("/")}>
      <SheetContent className="sm:max-w-[640px]">
        {detail ? (
          <EvidenceProvider>
            <div className="flex-1 overflow-y-auto">
              <PaymentHeader detail={detail} />
              <DecisionTimeline detail={detail} />
              {/* A payment with a call: the call sits right under the steps, so the judge watches it without scrolling. */}
              {hasCall && <CallSlot detail={detail} />}
              <AskPanel key={detail.payment.id} detail={detail} />
              <HardRules risk={detail.risk} />
              <RiskBreakdown risk={detail.risk} />
              <Destination detail={detail} />
              <InjectionFindings findings={detail.injection_findings} />
              {!hasCall && <CallSlot detail={detail} />}
              <AuditTrail entries={detail.audit} />
            </div>
            <DecisionFooter detail={detail} />
          </EvidenceProvider>
        ) : query.isError && processing && query.error instanceof ApiError && query.error.status === 404 ? (
          <LiveProcessing who={`${pinned.attackerName}, ${CARD_LABEL[pinned.card] ?? pinned.card}`} />
        ) : query.isError ? (
          <div className="px-5 pt-4">
            {query.error instanceof ApiError && query.error.status === 404 ? (
              <>
                <SheetTitle>Payment not found</SheetTitle>
                <SheetDescription className="mt-1">
                  {paymentId} is not part of a payment run yet. Start a payment run, then open the payment from the board.
                </SheetDescription>
              </>
            ) : (
              <>
                <SheetTitle className="sr-only">Payment did not load</SheetTitle>
                <SheetDescription className="sr-only">The payment detail could not be loaded.</SheetDescription>
                <InlineError what="This payment" error={query.error} onRetry={() => void query.refetch()} retrying={query.isFetching} className="pr-10" />
              </>
            )}
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
