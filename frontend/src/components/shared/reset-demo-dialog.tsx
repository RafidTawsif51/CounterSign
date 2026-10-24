import { useState } from "react";
import { RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { errorMessage } from "@/lib/api-error";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { iconProps } from "@/components/shared/icon";
import { useCurrentRun } from "@/components/shared/run-context";
import { api } from "@/lib/api";

/** Controlled by the shell, so the R shortcut can open it too. */
export function ResetDemoDialog({ open, onOpenChange: setOpen }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [pending, setPending] = useState(false);
  const { forgetAfterReset } = useCurrentRun();

  async function reset() {
    setPending(true);
    try {
      await api.resetDemo(true);
      forgetAfterReset();
      setOpen(false);
      toast.success("Demo reset", { description: "40 open invoices, no payment runs. The leaderboard was kept." });
    } catch (err) {
      toast.error("Demo not reset", { description: errorMessage(err) });
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !pending && setOpen(o)}>
      <DialogTrigger asChild>
        <Button size="sm">
          <RotateCcw {...iconProps} />
          Reset demo
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Reset the demo?</DialogTitle>
          <DialogDescription>
            Restores the seeded week for Ridgeline Builders: 40 open invoices and no payment runs. Holds, calls and approvals
            from this session are cleared. The leaderboard is kept.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <DialogClose asChild>
            <Button size="sm" disabled={pending}>
              Cancel
            </Button>
          </DialogClose>
          <Button size="sm" variant="primary" onClick={reset} disabled={pending}>
            {pending ? "Resetting" : "Reset demo"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
