import { useState } from "react";
import { Check, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { iconProps } from "@/components/shared/icon";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api-error";
import { formatAccount } from "@/lib/format";
import type { PaymentDetail } from "@/lib/types";

type Mode = "approve" | "reject";

/** The controller persona who decides exceptions in the demo; the backend records it as the approver. */
const CONTROLLER = "Dev";

// The controller's decision on a held payment. A reason is required either way; it goes into the audit trail.
// The backend says what is allowed (actions) and which account approving pays: always the verified one.
export function DecisionFooter({ detail }: { detail: PaymentDetail }) {
  const paymentId = detail.payment.id;
  const vendor = detail.vendor?.name ?? "this payment";
  const { can_approve, approve_blocked_reason, can_reject } = detail.actions;
  const pays = detail.payment.approve_pays;
  const [mode, setMode] = useState<Mode | null>(null);
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const queryClient = useQueryClient();

  async function submit() {
    if (!mode || !reason.trim()) return;
    setPending(true);
    try {
      await (mode === "approve" ? api.approve : api.reject)(paymentId, reason.trim(), CONTROLLER);
      toast.success(mode === "approve" ? "Payment approved" : "Payment rejected", { description: vendor });
      setMode(null);
      setReason("");
      await queryClient.invalidateQueries({ queryKey: ["payment", paymentId] });
    } catch (err) {
      toast.error(mode === "approve" ? "Payment not approved" : "Payment not rejected", {
        description: errorMessage(err),
      });
    } finally {
      setPending(false);
    }
  }

  if (!mode) {
    return (
      <div className="flex items-center gap-3 border-t border-rule bg-surface px-5 py-3">
        <p className="mr-auto text-sm text-ink-muted">
          {can_approve || !approve_blocked_reason
            ? "Held for the controller. Your reason is recorded in the audit trail."
            : `Approve is unavailable: ${approve_blocked_reason}.`}
        </p>
        <Button variant="danger" onClick={() => setMode("reject")} disabled={!can_reject}>
          <X {...iconProps} />
          Reject
        </Button>
        <Button variant="primary" onClick={() => setMode("approve")} disabled={!can_approve}>
          <Check {...iconProps} />
          Approve
        </Button>
      </div>
    );
  }

  const approving = mode === "approve";
  return (
    <form
      className="space-y-2 border-t border-rule bg-surface px-5 py-3"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <label htmlFor="decision-reason" className="text-sm font-medium">
        {approving ? "Why is it safe to pay?" : "Why reject this payment?"}
      </label>
      {approving && pays && (
        <p className="text-sm text-ink-muted">
          Approving pays the verified account <span className="figure text-ink">{formatAccount(pays.account_last4)}</span> at {pays.bank_name}, never
          an account the invoice asked for.
        </p>
      )}
      <Textarea
        id="decision-reason"
        autoFocus
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        className="min-h-16 text-sm"
        placeholder={
          approving
            ? "The amount matches the rental agreement; paying the account we already verified."
            : "Vendor did not confirm the new account; paying the verified account next week."
        }
      />
      <div className="flex justify-end gap-2">
        <Button size="sm" onClick={() => setMode(null)} disabled={pending}>
          Cancel
        </Button>
        <Button size="sm" type="submit" variant={approving ? "primary" : "danger"} disabled={pending || reason.trim().length < 3}>
          {approving ? "Approve payment" : "Reject payment"}
        </Button>
      </div>
    </form>
  );
}
