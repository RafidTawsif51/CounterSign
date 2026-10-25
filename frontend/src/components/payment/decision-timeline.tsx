import { Badge } from "@/components/ui/badge";
import { Section } from "@/components/payment/section";
import { useServiceModes } from "@/lib/services";
import { buildTimeline, type TimelineStep } from "@/lib/timeline";
import type { PaymentDetail, PaymentStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

// How the decision was made, step by step, and which service did each step. Only steps that happened are listed. A step
// whose service was simulated says so in words; nothing here names Apify, CRS, Twilio, Cartesia, Nessie or Claude for work
// they did not do.

const MARK: Record<PaymentStatus, string> = { pending: "bg-pending", paid: "bg-paid", held: "bg-held", blocked: "bg-blocked" };

export function DecisionTimeline({ detail }: { detail: PaymentDetail }) {
  const modes = useServiceModes();
  const steps = buildTimeline(detail, modes);
  if (steps.length === 0) return null;
  return (
    <Section title="How this decision was made">
      <ol className="divide-y divide-rule border-y border-rule">
        {steps.map((s) => (
          <Step key={s.key} step={s} />
        ))}
      </ol>
    </Section>
  );
}

function Step({ step }: { step: TimelineStep }) {
  return (
    <li className="grid grid-cols-[10px_1fr] gap-x-3 py-2.5 sm:grid-cols-[10px_1fr_minmax(0,15rem)]">
      <span
        aria-hidden
        className={cn(
          "mt-1.5 size-2.5",
          step.active ? "animate-call-pulse bg-accent" : step.status ? MARK[step.status] : step.evidence ? "bg-blocked" : "bg-ink-faint",
        )}
      />
      <div className="min-w-0">
        <p className="text-sm font-medium">{step.title}</p>
        <p className={cn("text-sm", step.evidence ? "text-blocked-ink" : "text-ink-muted")}>
          {step.result}
          {step.link && (
            <>
              {". "}
              <a href={step.link.href} target="_blank" rel="noreferrer" className="figure break-all text-accent underline-offset-4 hover:underline">
                {step.link.label}
              </a>
            </>
          )}
        </p>
      </div>
      <p className="col-start-2 mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-muted sm:col-start-3 sm:mt-0 sm:justify-end sm:text-right">
        {step.mode === "simulated" && <Badge>Simulated</Badge>}
        <span>{step.service}</span>
      </p>
    </li>
  );
}
