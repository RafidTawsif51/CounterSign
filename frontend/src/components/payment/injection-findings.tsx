import { EyeOff } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { iconProps } from "@/components/shared/icon";
import { EvidenceRef, useEvidenceSource } from "@/components/payment/evidence";
import { Section } from "@/components/payment/section";
import { TECHNIQUES } from "@/lib/risk-catalog";
import type { InjectionFinding } from "@/lib/types";
import { cn } from "@/lib/utils";

export function InjectionFindings({ findings }: { findings: InjectionFinding[] }) {
  if (findings.length === 0) return null;
  return (
    <Section title="Injection findings">
      <div className="space-y-4">
        {findings.map((f) => (
          <Finding key={f.id} finding={f} />
        ))}
      </div>
    </Section>
  );
}

function Finding({ finding }: { finding: InjectionFinding }) {
  const source = useEvidenceSource([finding.id]);
  return (
    <div {...source} className={cn(source.className, "-m-2 p-2")}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge>{TECHNIQUES[finding.technique] ?? finding.technique}</Badge>
        <span className="text-sm text-ink-muted">
          <span className="figure">{Math.round(finding.confidence * 100)}%</span> confidence
        </span>
        <span className="text-sm text-ink-muted">in the {finding.invoice_id ? "invoice PDF" : "email"}</span>
        <EvidenceRef id={finding.id} className="ml-auto" />
      </div>
      <div className="mt-3 flex items-center gap-1.5 text-xs text-ink-muted">
        <EyeOff {...iconProps} />
        Hidden text: invisible to humans
      </div>
      {/* Attacker-controlled text: rendered as plain text, never as HTML. */}
      <pre className="figure mt-1.5 rounded-md border border-rule bg-sunken p-3 text-sm whitespace-pre-wrap text-ink">
        {finding.snippet}
      </pre>
    </div>
  );
}
