import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { CALL_LIMIT_S, numberTrust, type CallPhase, type ContactLike, type NumberTrust } from "@/lib/calls";
import type { CallOutcome, ContactSource, PaymentStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

// Pieces shared by the drawer's call panel and the board's call strip.

/** Each outcome, in the payment status it leaves behind. */
export const OUTCOME: Record<CallOutcome, { status: PaymentStatus; title: string; text: string; short: string }> = {
  denied: {
    status: "blocked",
    title: "Denied",
    text: "Vendor confirmed they never changed banks. Payment blocked, controller alerted.",
    short: "payment blocked",
  },
  confirmed: {
    status: "paid",
    title: "Confirmed",
    text: "New account saved, verified by this call.",
    short: "new account saved",
  },
  unclear: {
    status: "held",
    title: "Unclear",
    text: "The vendor did not confirm the change. Payment stays held for Dev, with this transcript.",
    short: "held for Dev",
  },
  no_answer: {
    status: "held",
    title: "No answer",
    text: "Nobody picked up. Payment stays held; only Dev can release it, and only to the last verified account.",
    short: "held for Dev",
  },
};

export const OUTCOME_TINT: Record<PaymentStatus, string> = {
  pending: "border-pending bg-pending-tint text-pending-ink",
  paid: "border-paid bg-paid-tint text-paid-ink",
  held: "border-held bg-held-tint text-held-ink",
  blocked: "border-blocked bg-blocked-tint text-blocked-ink",
};

export const PHASE_LABEL: Record<CallPhase, string> = {
  queued: "Queued",
  dialing: "Dialing",
  live: "On the call",
  ended: "Call ended",
};

/** Seconds since the call started, ticking while it is live and frozen once it ends. */
export function useElapsed(startedAt: string | null, endedAt: string | null): number {
  const [now, setNow] = useState(() => Date.now());
  const running = Boolean(startedAt) && !endedAt;

  useEffect(() => {
    if (!running) return;
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, [running]);

  if (!startedAt) return 0;
  const end = endedAt ? Date.parse(endedAt) : now;
  return Math.max(0, (end - Date.parse(startedAt)) / 1000);
}

/** Square status mark. Pulses (slowly, opacity only) while the call is live; DESIGN.md allows this one loop. */
export function CallMark({ phase, className }: { phase: CallPhase; className?: string }) {
  const active = phase === "dialing" || phase === "live";
  return (
    <span
      aria-hidden
      className={cn(
        "shrink-0",
        active ? "animate-call-pulse bg-accent" : phase === "queued" ? "border border-ink-muted" : "bg-ink-faint",
        className,
      )}
    />
  );
}

/** The 60-second limit as a thin line that fills as the call runs. */
export function LimitLine({ elapsed, className }: { elapsed: number; className?: string }) {
  const pct = Math.min(100, (elapsed / CALL_LIMIT_S) * 100);
  return (
    <div
      role="progressbar"
      aria-label="Call time used of the 60 second limit"
      aria-valuemin={0}
      aria-valuemax={CALL_LIMIT_S}
      aria-valuenow={Math.round(elapsed)}
      className={cn("h-0.5 w-full bg-rule", className)}
    >
      <div className="h-full bg-ink transition-[width] duration-200 ease-linear" style={{ width: `${pct}%` }} />
    </div>
  );
}

/**
 * Where the dialed number came from and who else vouches for it. Before the call starts the record has no dialed
 * contact yet, so it falls back to the vendor's contact with the call's source (on file, which verify.py prefers).
 */
export function useNumberTrust(vendorId: string | null, dialed: ContactLike | null, source: ContactSource | null): NumberTrust {
  const { data } = useQuery({
    queryKey: ["vendor-history", vendorId],
    queryFn: () => api.vendorHistory(vendorId!),
    enabled: Boolean(vendorId),
    staleTime: Infinity,
  });
  const contacts = data?.contacts ?? [];
  // A call's contact carries no first_seen; the same contact in the vendor history does.
  const contact = (dialed && contacts.find((c) => c.id === dialed.id)) ?? dialed ?? contacts.find((c) => c.source === (source ?? "on_file")) ?? null;
  return numberTrust(contact, contacts);
}

/** `summitconcrete.com/contact` from `https://www.summitconcrete.com/contact`. */
export function shortUrl(url: string) {
  return url.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "");
}
