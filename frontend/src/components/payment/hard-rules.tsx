import { Lock } from "lucide-react";
import { iconProps } from "@/components/shared/icon";
import { EvidenceRef, useEvidenceSource } from "@/components/payment/evidence";
import { Section } from "@/components/payment/section";
import { hardRuleInfo } from "@/lib/risk-catalog";
import type { RiskAssessment } from "@/lib/types";

export function HardRules({ risk }: { risk: RiskAssessment | null }) {
  const rules = risk?.hard_rules_fired ?? [];
  return (
    <Section title="Hard rules fired">
      {rules.length === 0 ? (
        <p className="text-sm text-ink-muted">No hard rule fired.</p>
      ) : (
        <ul className="-mx-2 space-y-1">
          {rules.map((rule) => (
            <HardRuleRow key={rule} rule={rule} riskId={risk!.id} />
          ))}
        </ul>
      )}
    </Section>
  );
}

function HardRuleRow({ rule, riskId }: { rule: string; riskId: string }) {
  const info = hardRuleInfo(rule);
  const source = useEvidenceSource([riskId]);
  return (
    <li {...source} className={`${source.className} flex gap-3 px-2 py-1.5`}>
      <Lock {...iconProps} className="mt-0.5 text-ink" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-medium">{info.label}</span>
          <EvidenceRef id={riskId} />
        </div>
        <p className="text-sm text-ink-muted">Hard rule: cannot be overridden by AI. {info.action}.</p>
      </div>
    </li>
  );
}
