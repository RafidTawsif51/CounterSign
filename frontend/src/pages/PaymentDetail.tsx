import { useNavigate, useParams } from "react-router-dom";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";

export function PaymentDetail() {
  const { paymentId } = useParams<{ paymentId: string }>();
  const navigate = useNavigate();

  return (
    <Sheet open onOpenChange={(open) => !open && navigate("/")}>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>Payment</SheetTitle>
          <SheetDescription className="figure">{paymentId}</SheetDescription>
        </SheetHeader>
        <div className="px-5 py-4 text-sm text-ink-muted">
          Risk signals, injection findings, the verification call and the audit trail for this payment appear here.
        </div>
      </SheetContent>
    </Sheet>
  );
}
