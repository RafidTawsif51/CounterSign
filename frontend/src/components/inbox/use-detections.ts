import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";
import { useCurrentRun } from "@/components/shared/run-context";
import { api } from "@/lib/api";
import { detectionFor, type Detection } from "@/lib/inbox";

/**
 * Threads the current run caught an attack in, by thread id. Only payments the run held or blocked (or whose invoice
 * had hidden instructions) are looked up, so this stays a handful of requests; each payment record names its email,
 * and the email names its thread. Before a run there is nothing here: the inbox never shows the seed's is_attack flag.
 */
export function useDetections(): Map<string, Detection & { threadId: string }> {
  const { allEvents: events } = useCurrentRun();
  const flagged = useMemo(() => {
    const ids = new Set<string>();
    for (const e of events) {
      if (e.type === "payment.held" || e.type === "payment.blocked") ids.add(e.payment_id);
      if (e.type === "injection.detected" && e.payment_id) ids.add(e.payment_id);
    }
    return [...ids].sort();
  }, [events]);
  // Refetch when a payment's state moves on: a call ending turns held into blocked, a controller's review decides it.
  const settled = events.filter((e) => e.type === "payment.blocked" || e.type === "call.outcome" || e.type === "payment.reviewed").length;

  const results = useQueries({
    queries: flagged.map((id) => ({
      queryKey: ["payment", id, "detection", settled],
      queryFn: () => api.payment(id),
      staleTime: Infinity,
      retry: false,
    })),
  });

  return useMemo(() => {
    const out = new Map<string, Detection & { threadId: string }>();
    for (const r of results) {
      const d = r.data;
      const det = d && detectionFor(d);
      if (det && d.message) out.set(d.message.thread_id, { ...det, threadId: d.message.thread_id });
    }
    return out;
  }, [results.map((r) => r.dataUpdatedAt).join("|")]); // results is a new array every render; its data is what matters
}
