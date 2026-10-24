import { useState } from "react";
import { Check, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { iconProps } from "@/components/shared/icon";
import { api } from "@/lib/api";

type Mode = "approve" | "reject";

// The controller's decision on a held payment. A reason is required either way; it goes into the audit trail.
export function DecisionFooter({ paymentId, vendor }: { paymentId: string; vendor: string }) {
  const [mode, setMode] = useState<Mode | null>(null);
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const queryClient = useQueryClient();

  async function submit() {
    if (!mode || !reason.trim()) return;
    setPending(true);
    try {
      await (mode === "approve" ? api.approve : api.reject)(paymentId, reason.trim());
      toast.success(mode === "approve" ? "Payment approved" : "Payment rejected", { description: vendor });
      setMode(null);
      setReason("");
      await queryClient.invalidateQueries({ queryKey: ["payment", paymentId] });
    } catch (err) {
      toast.error(mode === "approve" ? "Payment not approved" : "Payment not rejected", {
        description: err instanceof Error ? err.message : "The server did not respond.",
      });
    } finally {
      setPending(false);
    }
  }

  if (!mode) {
    return (
      <div className="flex items-center gap-3 border-t border-rule bg-surface px-5 py-3">
        <p className="mr-auto text-sm text-ink-muted">Held for the controller. Your reason is recorded in the audit trail.</p>
        <Button variant="danger" onClick={() => setMode("reject")}>
          <X {...iconProps} />
          Reject
        </Button>
        <Button variant="primary" onClick={() => setMode("approve")}>
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
      <Textarea
        id="decision-reason"
        autoFocus
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        className="min-h-16 text-sm"
        placeholder={
          approving
            ? "Called the controller at Northside on the number on file; they confirmed the new account."
            : "Vendor did not confirm the new account; paying the verified account next week."
        }
      />
      <div className="flex justify-end gap-2">
        <Button size="sm" onClick={() => setMode(null)} disabled={pending}>
          Cancel
        </Button>
        <Button size="sm" type="submit" variant={approving ? "primary" : "danger"} disabled={pending || !reason.trim()}>
          {approving ? "Approve payment" : "Reject payment"}
        </Button>
      </div>
    </form>
  );
}
