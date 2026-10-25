// The verification call, as a phone-sized live view: who is calling, the 60 second limit, every line as it is spoken, and what it
// decided. It reads the payment record (callFromDetail), so it shows only what really happened on the call. It is our view of the
// call, not the vendor's own phone, and it says so. Used beside the board on a second screen and in the launch video.

import { useQuery } from "@tanstack/react-query";
import { PhoneCall, ShieldCheck } from "lucide-react";
import { useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { CallMark, LimitLine, OUTCOME, useElapsed } from "@/components/call/call-parts";
import { CountersignMark } from "@/components/shared/countersign-mark";
import { iconProps } from "@/components/shared/icon";
import { StatusBadge } from "@/components/shared/status-badge";
import { api } from "@/lib/api";
import { callFromDetail } from "@/lib/calls";
import { formatDuration, formatPhoneMasked } from "@/lib/format";
import { cn } from "@/lib/utils";

const PHASE_TEXT = { queued: "Waiting to call", dialing: "Calling", live: "On the call", ended: "Call ended" } as const;

export function CallView() {
  const [params] = useSearchParams();
  const paymentId = params.get("payment") ?? "";
  const detail = useQuery({
    queryKey: ["payment", paymentId, "call-view"],
    queryFn: () => api.payment(paymentId),
    enabled: !!paymentId,
    refetchInterval: (q) => (q.state.data?.calls.at(-1)?.outcome ? false : 600),
  });
  const d = detail.data;
  const call = d ? callFromDetail(d) : null;
  const elapsed = useElapsed(call?.startedAt ?? null, call?.endedAt ?? null);
  const dialed = d?.calls.at(-1)?.contact ?? null;
  const outcome = call?.outcome ? OUTCOME[call.outcome] : null;

  const end = useRef<HTMLLIElement>(null);
  useEffect(() => end.current?.scrollIntoView({ block: "end" }), [call?.lines.length]);

  return (
    <div className="flex min-h-screen items-start justify-center bg-paper p-4 text-ink">
      <section
        aria-label="Verification call, live view"
        className="flex h-[calc(100vh-32px)] max-h-[860px] w-full max-w-[400px] flex-col overflow-hidden rounded-lg border border-rule-strong bg-surface"
      >
        <header className="border-b border-rule px-5 pt-5 pb-4">
          <p className="flex items-center gap-2 text-sm text-ink-muted">
            <CountersignMark className="size-4" />
            Live view of the verification call
          </p>
          <div className="mt-4 flex items-center gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-md bg-accent text-accent-ink">
              <PhoneCall {...iconProps} />
            </span>
            <div className="min-w-0">
              <p className="text-md font-semibold">{d?.vendor?.name ?? "Vendor"}</p>
              <p className="figure text-sm text-ink-muted">{dialed ? formatPhoneMasked(dialed.phone) : "Number on file"}</p>
            </div>
          </div>
          <div className="mt-4 flex items-center justify-between">
            <span className="flex items-center gap-2 text-sm">
              {call && <CallMark phase={call.phase} />}
              {call ? PHASE_TEXT[call.phase] : paymentId ? "Waiting for the call" : "No call selected"}
            </span>
            <span className="figure text-md">{call?.startedAt ? formatDuration(elapsed) : "0:00"}</span>
          </div>
          {call?.startedAt && <LimitLine elapsed={elapsed} className="mt-2" />}
        </header>

        <ol className="flex-1 space-y-4 overflow-y-auto px-5 py-4" aria-live="polite">
          {(call?.lines ?? []).map((l, i) => (
            <li key={i} ref={i === (call?.lines.length ?? 0) - 1 ? end : undefined} className={cn("max-w-[88%]", l.speaker === "vendor" && "ml-auto text-right")}>
              <p className="text-xs text-ink-muted">{l.speaker === "agent" ? "Countersign (automated)" : d?.vendor?.name ?? "Vendor"}</p>
              <p className={cn("mt-1", l.speaker === "vendor" ? "text-md font-medium" : "text-ink")}>{l.text}</p>
            </li>
          ))}
          {call && call.lines.length === 0 && (
            <li className="text-sm text-ink-muted">
              {call.phase === "dialing" ? "Ringing. The agent speaks first, says it is automated and that the call is transcribed." : "Waiting."}
            </li>
          )}
        </ol>

        <footer className="border-t border-rule">
          {outcome && (
            <div className="row-flag px-5 py-3" data-status={outcome.status === "paid" ? undefined : outcome.status}>
              <div className="flex items-center justify-between gap-3">
                <span className="font-semibold">{outcome.title}</span>
                <StatusBadge status={d?.payment.status ?? outcome.status} />
              </div>
              <p className="mt-1 text-sm text-ink-muted">{outcome.text}</p>
            </div>
          )}
          <p className="flex items-center gap-2 px-5 py-3 text-xs text-ink-muted">
            <ShieldCheck {...iconProps} />
            {call?.simulated
              ? "Simulated call: no phone was dialed on this server."
              : "Number from the vendor's own website, never the email. Voice by Cartesia, call by Twilio."}
          </p>
        </footer>
      </section>
    </div>
  );
}
