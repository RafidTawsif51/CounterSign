import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { CallMark, CallProvenance, LimitLine, NumberFindingLine, OUTCOME, OUTCOME_TINT, PHASE_LABEL, useElapsed, useNumberTrust } from "@/components/call/call-parts";
import { api } from "@/lib/api";
import { CALL_LIMIT_S, type CallView } from "@/lib/calls";
import { formatDuration, formatPhoneMasked } from "@/lib/format";
import { cn } from "@/lib/utils";

// Compact verification call for the board's activity rail, so a call is visible without opening the drawer.
export function CallStrips({ calls }: { calls: CallView[] }) {
  if (calls.length === 0) return null;
  return (
    <section aria-label="Verification calls" className="shrink-0 border-b border-rule">
      <h2 className="flex h-9 items-center px-4 text-sm font-medium text-ink-muted">Verification calls</h2>
      <ul className="space-y-2 px-3 pb-3">
        {calls.map((call) => (
          <li key={call.paymentId}>
            <CallStrip call={call} />
          </li>
        ))}
      </ul>
    </section>
  );
}

export function CallStrip({ call }: { call: CallView }) {
  const elapsed = useElapsed(call.startedAt, call.endedAt);
  const trust = useNumberTrust(useVendorId(call.vendor), null, call.contactSource);
  // The vendor's own words are the evidence; fall back to the agent while the vendor has not spoken.
  const last = [...call.lines].reverse().find((l) => l.speaker === "vendor") ?? call.lines.at(-1);
  const o = call.outcome ? OUTCOME[call.outcome] : null;

  return (
    <Link
      to={`/app/payments/${call.paymentId}`}
      aria-live="polite"
      className="block rounded-md border border-rule bg-surface transition-colors hover:border-rule-strong"
    >
      <div className="px-3 pt-2.5 pb-2">
        <div className="flex items-center justify-between gap-3">
          <span className="flex min-w-0 items-center gap-2 font-medium">
            <CallMark phase={call.phase} className="size-2" />
            <span className="truncate">{call.vendor}</span>
          </span>
          {call.phase === "queued" ? (
            <span className="text-sm text-ink-muted">{PHASE_LABEL.queued}</span>
          ) : (
            <span className="figure shrink-0 text-sm">
              {formatDuration(elapsed)}
              <span className="text-ink-muted"> / {formatDuration(CALL_LIMIT_S)}</span>
            </span>
          )}
        </div>
        <p className="mt-0.5 truncate text-xs text-ink-muted">
          <span className="figure">{formatPhoneMasked(trust.phone)}</span>
          {trust.source === "on_file" && " on file"}, not from the email
        </p>
        <CallProvenance call={call} compact />
        <NumberFindingLine finding={call.finding} compact />
        {call.phase !== "queued" && <LimitLine elapsed={elapsed} className="mt-2" />}
        {last && (
          <p className="mt-2 line-clamp-2 text-sm">
            <span className="text-ink-muted">{last.speaker === "vendor" ? "Vendor" : "Countersign"}: </span>
            {last.text}
          </p>
        )}
        {call.phase === "dialing" && <p className="mt-2 text-sm text-ink-muted">Ringing</p>}
      </div>
      {o && (
        <p className={cn("rounded-b-md border-l-2 px-3 py-1.5 text-sm", OUTCOME_TINT[o.status])}>
          <span className="font-semibold">{o.title}:</span> {o.short}
        </p>
      )}
    </Link>
  );
}

function useVendorId(name: string): string | null {
  const { data } = useQuery({ queryKey: ["vendors"], queryFn: api.vendors, staleTime: Infinity });
  return data?.find((v) => v.name === name)?.id ?? null;
}
