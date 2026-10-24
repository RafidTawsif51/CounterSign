import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PaymentTable } from "@/components/board/payment-table";
import { iconProps } from "@/components/shared/icon";
import type { PinnedAttack as Pinned } from "@/components/shared/run-context";
import { CARDS } from "@/lib/attack-cards";
import type { BoardRow } from "@/lib/board";
import type { RunEvent } from "@/lib/types";

// A judge's attack, pinned above the ledger in the accent outline until dismissed. Its row reveals the outcome in place,
// the same way every other payment does: this is where the attack console's result is shown, never on the console.
export function PinnedAttack({ pinned, events, rows, onUnpin }: { pinned: Pinned; events: RunEvent[]; rows: BoardRow[]; onUnpin: () => void }) {
  const card = CARDS.find((c) => c.id === pinned.card);
  const queued = events.find((e) => e.type === "attack.queued");
  const started = events.some((e) => e.type === "run.started");
  const row = rows.find((r) => r.paymentId === pinned.paymentId) ?? rows[0];

  const state = !started && queued?.type === "attack.queued"
    ? `Waiting for the run in progress to finish (position ${queued.position})`
    : !row
      ? "Reading the email and invoice"
      : row.status === "pending"
        ? "In the run now"
        : null;

  return (
    <section aria-label="Your attack" className="mx-4 my-3 overflow-hidden rounded-lg border border-accent shadow-[inset_0_0_0_1px_var(--accent)] sm:mx-6">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 bg-accent-tint px-4 py-2">
        <span className="font-semibold">Your attack</span>
        <span className="text-sm text-ink-muted">
          {pinned.attackerName}
          {card ? `, ${card.kicker}: ${card.title}` : ""}
        </span>
        {state && <span className="text-sm">{state}</span>}
        <Button variant="ghost" size="icon-sm" className="ml-auto" aria-label="Unpin your attack" onClick={onUnpin}>
          <X {...iconProps} />
        </Button>
      </div>
      <div className="bg-surface">
        <PaymentTable rows={row ? [row] : []} loading={!row} skeletonRows={1} emptyText="" />
      </div>
    </section>
  );
}
