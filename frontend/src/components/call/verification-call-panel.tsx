import { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { ShieldCheck } from "lucide-react";
import { CallMark, LimitLine, OUTCOME, OUTCOME_TINT, PHASE_LABEL, shortUrl, useElapsed } from "@/components/call/call-parts";
import { iconProps } from "@/components/shared/icon";
import { useEvidenceSource } from "@/components/payment/evidence";
import { useStickToBottom } from "@/hooks/use-stick-to-bottom";
import { CALL_LIMIT_S, type CallView, type NumberTrust } from "@/lib/calls";
import { formatDuration, formatMonthYear, formatPhoneMasked } from "@/lib/format";
import { CONTACT_SOURCES } from "@/lib/risk-catalog";
import type { ContactSource } from "@/lib/types";
import { cn } from "@/lib/utils";

// The verification call, as it happens. This is the demo's "phone rings on the table" moment, so it runs a type step
// larger than the rest of the drawer and leads with the pitch point: the number is trusted for reasons that have
// nothing to do with the email that asked for the change.

const SPEAKER = { agent: "Countersign", vendor: "Vendor" } as const;

/** `evidenceId` (the stored call id) registers each transcript line as `<id>#<n>`, so an /ask citation can point at it. */
export function VerificationCallPanel({ call, trust, evidenceId }: { call: CallView; trust: NumberTrust; evidenceId?: string }) {
  const elapsed = useElapsed(call.startedAt, call.endedAt);
  const root = useRef<HTMLDivElement>(null);
  const active = call.phase !== "ended";

  // The call sits low in the drawer. While it is queued or ringing, bring it into view: this is the moment people watch.
  useEffect(() => {
    if (!active) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    root.current?.scrollIntoView({ block: "start", behavior: reduce ? "auto" : "smooth" });
  }, [active, call.phase === "dialing"]);

  return (
    <div ref={root} className="scroll-mt-4 space-y-4">
      <TrustedNumber call={call} trust={trust} />
      <CallState call={call} elapsed={elapsed} />
      {call.phase !== "queued" && <Transcript call={call} evidenceId={evidenceId} />}
      {call.outcome && <OutcomeBar outcome={call.outcome} />}
    </div>
  );
}

function TrustedNumber({ call, trust }: { call: CallView; trust: NumberTrust }) {
  const verb = call.phase === "queued" ? "Will call" : call.phase === "ended" ? "Called" : "Calling";
  return (
    <div className="rounded-lg bg-sunken px-4 py-3.5">
      <p className="text-lg font-semibold">
        {verb} {call.vendor} at <span className="figure font-medium whitespace-nowrap">{formatPhoneMasked(trust.phone)}</span>
      </p>
      <p className="mt-1.5 text-base text-ink-muted">
        Source: <span className="text-ink">{sourceSentence(trust)}</span>
        {trust.crossCheck && (
          <>
            , {trust.crossCheck.matches ? "matches" : "differs from"} {crossCheckName(trust.crossCheck.source)}
            {trust.crossCheck.url && (
              <>
                {" "}
                (
                <a href={trust.crossCheck.url} target="_blank" rel="noreferrer" className="text-accent underline-offset-4 hover:underline">
                  {shortUrl(trust.crossCheck.url)}
                </a>
                )
              </>
            )}
          </>
        )}
        .
      </p>
      <p className="mt-2 flex items-center gap-1.5 text-base font-medium">
        <ShieldCheck {...iconProps} className="text-ink-muted" />
        Not taken from the email.
      </p>
      {trust.crossCheck && !trust.crossCheck.matches && (
        <p className="mt-1 text-sm text-ink-muted">The sources disagree, so the agent dials the number verified longest ago and flags it.</p>
      )}
    </div>
  );
}

function sourceSentence(trust: NumberTrust) {
  if (!trust.source) return "looking up the vendor's number";
  const where = trust.source === "on_file" ? "on file" : CONTACT_SOURCES[trust.source];
  return trust.since ? `${where} since ${formatMonthYear(trust.since)}` : where;
}

function crossCheckName(source: ContactSource) {
  return source === "website" ? "vendor website" : "public listing";
}

function CallState({ call, elapsed }: { call: CallView; elapsed: number }) {
  const timed = call.phase !== "queued";
  return (
    <div aria-live="polite">
      <div className="flex items-center justify-between gap-4">
        <span className="flex items-center gap-2.5 text-md font-medium">
          <CallMark phase={call.phase} className="size-2.5" />
          {call.phase === "queued" ? "Queued: the call starts once the hold is recorded" : PHASE_LABEL[call.phase]}
        </span>
        {timed && (
          <span className="shrink-0 text-sm text-ink-muted">
            <span className="figure text-lg text-ink">{formatDuration(elapsed)}</span>
            <span className="figure"> / {formatDuration(CALL_LIMIT_S)}</span>
          </span>
        )}
      </div>
      {timed && <LimitLine elapsed={elapsed} className="mt-2" />}
    </div>
  );
}

function Transcript({ call, evidenceId }: { call: CallView; evidenceId?: string }) {
  const scroll = useStickToBottom<HTMLOListElement>(call.lines.length);
  // Lines already there when the panel opened appear at once; only new ones fade in.
  const seen = useRef(call.lines.length);

  if (call.lines.length === 0)
    return call.phase === "ended" ? null : (
      <p className="text-base text-ink-muted">Ringing. The agent speaks first and says the call is automated and recorded.</p>
    );

  return (
    <ol
      ref={scroll.ref}
      onScroll={scroll.onScroll}
      aria-label="Call transcript"
      className="max-h-80 space-y-3 overflow-y-auto border-l border-rule pl-4"
    >
      {call.lines.map((line, i) => (
        <Line key={i} line={line} fadeIn={i >= seen.current} evidenceId={evidenceId ? `${evidenceId}#${i}` : undefined} />
      ))}
    </ol>
  );
}

function Line({ line, fadeIn, evidenceId }: { line: CallView["lines"][number]; fadeIn: boolean; evidenceId?: string }) {
  const source = useEvidenceSource([evidenceId]);
  return (
    <motion.li
      initial={fadeIn ? { opacity: 0 } : false}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
      {...source}
      className={cn(source.className, "-mx-2 grid grid-cols-[88px_1fr] gap-3 px-2 py-0.5")}
    >
      <span className="pt-0.5 text-sm font-medium text-ink-muted">{SPEAKER[line.speaker]}</span>
      {/* Vendor speech is untrusted text: plain text only. */}
      <span className={cn("text-md", line.speaker === "vendor" ? "font-medium text-ink" : "text-ink")}>{line.text}</span>
    </motion.li>
  );
}

function OutcomeBar({ outcome }: { outcome: keyof typeof OUTCOME }) {
  const o = OUTCOME[outcome];
  // Bleeds to the drawer edges with the same leading status rule a flagged row has.
  return (
    <div role="status" className={cn("-mx-5 border-l-2 px-5 py-3.5", OUTCOME_TINT[o.status])}>
      <p className="text-md">
        <span className="font-semibold">{o.title}.</span> {o.text}
      </p>
    </div>
  );
}
