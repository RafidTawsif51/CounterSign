import { Bot, Server, UserRound } from "lucide-react";
import { useEvidenceSource } from "@/components/payment/evidence";
import { Section } from "@/components/payment/section";
import { formatClock, formatScore } from "@/lib/format";
import { ACTORS, AUDIT_ACTIONS, CONTACT_SOURCES, DECISIONS, SIGNALS, hardRuleInfo } from "@/lib/risk-catalog";
import type { ContactSource } from "@/lib/types";
import type { AuditEntry, Decision } from "@/lib/types";
import { cn } from "@/lib/utils";

const ACTOR_ICON = { agent: Bot, human: UserRound, system: Server } as const;

export function AuditTrail({ entries }: { entries: AuditEntry[] }) {
  return (
    <Section title="Audit trail" aside={<span className="text-xs text-ink-muted">Append-only</span>}>
      {entries.length === 0 ? (
        <p className="text-sm text-ink-muted">Nothing recorded yet.</p>
      ) : (
        <ol className="relative">
          <span aria-hidden className="absolute top-2 bottom-2 left-[9px] w-px bg-rule" />
          {entries.map((e) => (
            <AuditRow key={e.id} entry={e} />
          ))}
        </ol>
      )}
    </Section>
  );
}

function AuditRow({ entry }: { entry: AuditEntry }) {
  const d = entry.detail ?? {};
  // A row is also a source for the ids it mentions, so hovering a call or assessment id lights up its history.
  const source = useEvidenceSource([entry.id, d.call_id as string, d.assessment_id as string, d.finding_id as string]);
  const Icon = ACTOR_ICON[entry.actor];

  return (
    <li className="relative grid grid-cols-[20px_1fr_auto] items-start gap-x-3 py-1">
      <span
        title={ACTORS[entry.actor]}
        className={cn(
          "relative mt-px flex size-5 items-center justify-center rounded-sm border bg-surface",
          entry.actor === "human" ? "border-accent text-accent" : "border-rule-strong text-ink-muted",
        )}
      >
        <Icon size={12} strokeWidth={1.75} aria-hidden />
        <span className="sr-only">{ACTORS[entry.actor]}</span>
      </span>
      <div {...source} className={cn(source.className, "-mx-1 min-w-0 px-1")}>
        <div className="text-sm font-medium">{AUDIT_ACTIONS[entry.action] ?? entry.action.replace(/_/g, " ")}</div>
        {describe(entry.action, d) && <div className="text-xs break-words text-ink-muted">{describe(entry.action, d)}</div>}
      </div>
      <time dateTime={entry.at} className="figure pt-0.5 text-xs text-ink-muted">
        {formatClock(entry.at)}
      </time>
    </li>
  );
}

function describe(action: string, d: Record<string, unknown>): string | null {
  switch (action) {
    case "risk_assessed":
      return `Score ${formatScore(d.score as number)}, ${DECISIONS[d.decision as Decision]?.toLowerCase() ?? d.decision}`;
    case "paid":
      return d.transfer_id ? `Nessie transfer ${d.transfer_id}` : null;
    case "verification_call":
      return `${OUTCOME[d.outcome as string] ?? d.outcome}. Called the ${CONTACT_SOURCES[d.contact_source as ContactSource] ?? "vendor"}.`;
    case "approved":
    case "rejected":
      return `${d.by ?? "Controller"}: ${d.reason ?? ""}`;
    case "quarantined":
      return d.technique ? `Technique ${String(d.technique).replace("_", " ")}` : null;
    default:
      return typeof d.summary === "string" ? d.summary : typeof d.reason === "string" ? humanReason(d.reason) : null;
  }
}

const OUTCOME: Record<string, string> = {
  confirmed: "Vendor confirmed",
  denied: "Vendor denied the change",
  unclear: "Unclear answer",
  no_answer: "No answer",
};

/** Backend reasons look like `destination_changed: Hold and place a verification call`. Name the rule in words. */
function humanReason(reason: string) {
  const m = reason.match(/^([a-z_]+): (.*)$/);
  if (!m) return reason;
  const [, key, rest] = m;
  if (key in SIGNALS) return `${SIGNALS[key].label}: ${rest}`;
  const rule = hardRuleInfo(key);
  return rule.label.toLowerCase() === key.replace(/_/g, " ") ? reason : `${rule.label}. ${rest}.`;
}
