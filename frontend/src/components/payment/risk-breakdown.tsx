import { EvidenceRef, useEvidenceSource } from "@/components/payment/evidence";
import { Section } from "@/components/payment/section";
import { formatScore } from "@/lib/format";
import { SIGNALS, THRESHOLDS, signalInfo } from "@/lib/risk-catalog";
import type { PaymentDetail, Signal } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Placed extends Signal {
  offset: number; // where this signal's segment starts on the 0 to 100 track
  width: number; // its share of the track, clipped so the total never passes 100
}

export function RiskBreakdown({ risk }: { risk: PaymentDetail["risk"] }) {
  if (!risk) {
    return (
      <Section title="Risk score">
        <p className="text-sm text-ink-muted">Not scored yet.</p>
      </Section>
    );
  }

  // Positive signals, heaviest first, laid end to end. Weight-0 results (identity passed) count as checked.
  const fired = risk.signals.filter((s) => s.weight > 0).sort((a, b) => b.weight - a.weight);
  let cursor = 0;
  const placed: Placed[] = fired.map((s) => {
    const width = Math.max(0, Math.min(s.weight, 100 - cursor));
    const p = { ...s, offset: cursor, width };
    cursor += width;
    return p;
  });
  const passed = risk.signals.filter((s) => s.weight <= 0);
  const firedNames = new Set(risk.signals.map((s) => s.name));
  // The CRS identity check only runs on a changed destination or a first payment, so it is listed only when it ran.
  const unchecked = Object.keys(SIGNALS).filter((name) => !firedNames.has(name) && name !== "vendor_identity_check");

  return (
    <Section title="Risk score" aside={<EvidenceRef id={risk.id} />}>
      <div className="flex items-baseline gap-2">
        <span className="figure text-xl font-medium">{formatScore(risk.score)}</span>
        <span className="figure text-sm text-ink-muted">/ 100</span>
      </div>

      <ScoreTrack placed={placed} />

      {placed.length === 0 ? (
        <p className="mt-4 text-sm text-ink-muted">
          No signal fired: sender, amount, timing and format all match this vendor's history.
          {risk.hard_rules_fired.length > 0 && " The hard rule above held it anyway."}
        </p>
      ) : (
        <ul className="-mx-2 mt-4">
          {placed.map((s) => (
            <SignalRow key={s.evidence_id} signal={s} />
          ))}
        </ul>
      )}

      {(passed.length > 0 || unchecked.length > 0) && (
        <>
          <div className="mt-3 mb-1 flex items-center gap-3 text-xs text-ink-muted">
            Checked, did not fire
            <span className="h-px flex-1 bg-rule" />
          </div>
          <ul className="-mx-2 grid gap-x-6 sm:grid-cols-2">
            {passed.map((s) => (
              <QuietRow key={s.evidence_id} name={s.name} detail={s.detail} evidenceId={s.evidence_id} />
            ))}
            {unchecked.map((name) => (
              <QuietRow key={name} name={name} detail={signalInfo(name).checks} />
            ))}
          </ul>
        </>
      )}
    </Section>
  );
}

function ScoreTrack({ placed }: { placed: Placed[] }) {
  return (
    <div className="relative mt-3 mb-8">
      <div className="relative h-2 overflow-hidden rounded-sm bg-sunken">
        {placed.map((s) => (
          <span
            key={s.evidence_id}
            className="absolute inset-y-0 border-r border-surface bg-accent"
            style={{ left: `${s.offset}%`, width: `${s.width}%` }}
          />
        ))}
      </div>
      {THRESHOLDS.map((t) => (
        <div key={t.at} className="absolute top-[-3px] flex flex-col items-center" style={{ left: `${t.at}%` }}>
          <span className="h-3.5 w-px bg-ink-muted" />
          <span className="absolute top-4 text-[11px] whitespace-nowrap text-ink-muted">
            <span className="figure">{t.at}</span> {t.label}
          </span>
        </div>
      ))}
    </div>
  );
}

function SignalRow({ signal }: { signal: Placed }) {
  const source = useEvidenceSource([signal.evidence_id]);
  return (
    <li {...source} className={cn(source.className, "grid grid-cols-[1fr_auto] items-start gap-x-4 px-2 py-1.5")}>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium">{signalInfo(signal.name).label}</span>
          <EvidenceRef id={signal.evidence_id} />
        </div>
        <p className="text-sm break-words text-ink-muted">{signal.detail}</p>
      </div>
      <div className="flex w-[132px] flex-col items-end gap-1.5 pt-0.5">
        <span className="figure text-sm">+{signal.weight}</span>
        <span className="relative h-1.5 w-full rounded-sm bg-sunken">
          <span className="absolute inset-y-0 bg-accent" style={{ left: `${signal.offset}%`, width: `${signal.width}%` }} />
        </span>
      </div>
    </li>
  );
}

function QuietRow({ name, detail, evidenceId }: { name: string; detail: string; evidenceId?: string }) {
  const source = useEvidenceSource([evidenceId]);
  return (
    <li
      {...source}
      title={detail}
      className={cn(source.className, "flex min-w-0 items-center gap-2 px-2 py-1 text-sm text-ink-muted")}
    >
      <span className="truncate text-ink-muted">{signalInfo(name).label}</span>
      <EvidenceRef id={evidenceId} />
      <span className="ml-auto shrink-0">
        {evidenceId ? <span className="figure">+0</span> : <span className="figure">+{signalInfo(name).weight}</span>}
      </span>
    </li>
  );
}
