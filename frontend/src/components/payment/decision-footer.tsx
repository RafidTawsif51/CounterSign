import { useRef, useState } from "react";
import { Check, Phone, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { iconProps } from "@/components/shared/icon";
import { ApiError, api } from "@/lib/api";
import { formatAccount, formatUSD } from "@/lib/format";
import type { PaymentDetail } from "@/lib/types";
import { destinationChanged, requestedAccount } from "@/lib/verdict";

type Mode = "approve" | "reject";

const DEFAULT_APPROVER = "Dev (Controller)";

/**
 * What Approve pays, in one sentence. The API says which account (approve_pays); approving never pays the requested one.
 * In mock mode the API fields are absent and the last verified account stands in.
 */
export function approveSentence(detail: PaymentDetail): string | null {
  const pays = detail.approve_pays ?? detail.last_verified_account;
  if (!pays) return null;
  const verified = `verified account ending ${formatAccount(pays.account_last4).slice(-4)}`;
  const req = requestedAccount(detail);
  return destinationChanged(detail) && req
    ? `Pays ${verified}, not the requested account ending ${formatAccount(req.account_last4).slice(-4)}.`
    : `Pays ${verified}.`;
}

// The controller's decision on a held payment. The API says what is allowed (actions); a reason is required either way
// and goes into the audit trail with the approver's name.
export function DecisionFooter({ detail }: { detail: PaymentDetail }) {
  const [mode, setMode] = useState<Mode | null>(null);
  const [calling, setCalling] = useState(false);
  const queryClient = useQueryClient();
  const { payment, vendor } = detail;
  const held = payment.status === "held";
  // Mock mode sends no actions: a held payment can be decided there.
  const canApprove = held && (detail.actions?.can_approve ?? true);
  const canReject = held && (detail.actions?.can_reject ?? true);
  const canCall = held && destinationChanged(detail);
  if (!canApprove && !canReject && !canCall) return null;
  const blockedReason = held && !canApprove ? detail.actions?.approve_blocked_reason : null;

  async function callAgain() {
    setCalling(true);
    try {
      await api.startCall(payment.id);
      toast.success("Calling the vendor", { description: `${vendor.name}, at an independent number, not the one in the email.` });
      void queryClient.invalidateQueries({ queryKey: ["payment", payment.id] });
    } catch (err) {
      toast.error("Call not started", { description: err instanceof ApiError ? err.detail : "The server did not respond." });
    } finally {
      setCalling(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-rule bg-surface px-5 py-3">
      <p className="mr-auto min-w-[16ch] text-sm text-ink-muted">
        {blockedReason ? `Approve unavailable: ${blockedReason}.` : "Held for the controller. Your reason is recorded in the audit trail."}
        {canApprove && approveSentence(detail) && (
          <span className="mt-0.5 block font-medium text-ink">Approve: {approveSentence(detail)}</span>
        )}
      </p>
      {canCall && (
        <Button onClick={() => void callAgain()} disabled={calling}>
          <Phone {...iconProps} />
          Call vendor again
        </Button>
      )}
      {canReject && (
        <Button variant="danger" onClick={() => setMode("reject")}>
          <X {...iconProps} />
          Reject
        </Button>
      )}
      {canApprove && (
        <Button variant="primary" onClick={() => setMode("approve")}>
          <Check {...iconProps} />
          Approve
        </Button>
      )}
      {mode && <DecisionDialog key={mode} mode={mode} detail={detail} onClose={() => setMode(null)} />}
    </div>
  );
}

function DecisionDialog({ mode, detail, onClose }: { mode: Mode; detail: PaymentDetail; onClose: () => void }) {
  const [approver, setApprover] = useState(DEFAULT_APPROVER);
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reasonRef = useRef<HTMLTextAreaElement>(null);
  const queryClient = useQueryClient();
  const approving = mode === "approve";
  const { payment, vendor } = detail;
  const sentence = approveSentence(detail);
  const ready = reason.trim().length >= 3 && approver.trim().length > 0;

  async function submit() {
    if (!ready || pending) return;
    setPending(true);
    setError(null);
    try {
      await (approving ? api.approve : api.reject)(payment.id, reason.trim(), approver.trim());
      toast.success(approving ? "Payment approved" : "Payment rejected", {
        description: approving && sentence ? `${vendor.name}. ${sentence}` : vendor.name,
      });
      onClose();
      await queryClient.invalidateQueries({ queryKey: ["payment", payment.id] });
    } catch (err) {
      // 409: the API's own reason (for example the verified account changed after the hold). The dialog stays open.
      setError(err instanceof ApiError ? err.detail : "The server did not respond.");
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && !pending && onClose()}>
      <DialogContent
        className="max-w-[480px]"
        onOpenAutoFocus={(e) => {
          e.preventDefault(); // the reason is what the controller writes; the approver name has a default
          reasonRef.current?.focus();
        }}
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
          className="space-y-4"
        >
          <DialogHeader>
            <DialogTitle>{approving ? "Approve payment" : "Reject payment"}</DialogTitle>
            <DialogDescription>
              {vendor.name}, {formatUSD(payment.amount_usd)}
            </DialogDescription>
          </DialogHeader>

          {approving ? (
            sentence && <p className="rounded-md border border-rule bg-sunken px-3 py-2 text-sm font-medium">{sentence}</p>
          ) : (
            <p className="text-sm text-ink-muted">Rejecting blocks this payment. Nothing is sent.</p>
          )}

          <div className="space-y-1">
            <label htmlFor="decision-approver" className="text-sm font-medium">
              Approver
            </label>
            <Input id="decision-approver" value={approver} onChange={(e) => setApprover(e.target.value)} maxLength={100} />
          </div>
          <div className="space-y-1">
            <label htmlFor="decision-reason" className="text-sm font-medium">
              {approving ? "Why is it safe to pay?" : "Why reject this payment?"}
            </label>
            <Textarea
              id="decision-reason"
              ref={reasonRef}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={1000}
              className="min-h-20 text-sm"
              placeholder={approving ? "Confirmed the invoice amount with the vendor's office." : "Vendor did not confirm the change."}
            />
          </div>

          {error && (
            <p role="alert" className="rounded-md border border-blocked bg-blocked-tint px-3 py-2 text-sm text-blocked-ink">
              {error}
            </p>
          )}

          <DialogFooter>
            <Button type="button" onClick={onClose} disabled={pending}>
              Cancel
            </Button>
            <Button type="submit" variant={approving ? "primary" : "danger"} disabled={pending || !ready}>
              {approving ? "Approve payment" : "Reject payment"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
