import { FileCheck2 } from 'lucide-react'
import { Reveal } from './reveal'
import { SectionHeading } from './section-heading'

const CONTROLS = [
  { framework: 'SOX 404', control: 'Vendor master change review', evidence: 'Approver, timestamp, callback recording' },
  { framework: 'NACHA', control: 'Account validation before first ACH', evidence: 'Validation result per account' },
  { framework: 'Dual control', control: 'Separate requester and releaser', evidence: 'Two named identities per release' },
  { framework: 'Positive Pay', control: 'Issued-check file reconciliation', evidence: 'Daily file and exceptions' },
]

export function AuditEvidence() {
  return (
    <section aria-labelledby="audit-heading" className="border-t bg-surface">
      <div className="mx-auto grid max-w-6xl gap-12 px-6 py-24 lg:grid-cols-[1fr_1.4fr] lg:items-start">
        <Reveal className="flex flex-col gap-8">
          <div id="audit-heading">
            <SectionHeading
              eyebrow="Audit-ready"
              title="Evidence your auditors can sample in minutes."
              description="Each decision is mapped to the control it satisfies, so quarter-end testing is a filtered export instead of a scramble through inboxes."
            />
          </div>
          <div className="flex items-center gap-4 rounded-lg border bg-card p-4">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <FileCheck2 className="size-5" aria-hidden="true" />
            </span>
            <div className="flex flex-col text-sm">
              <span className="font-medium">Q3 FY26 control evidence.csv</span>
              <span className="text-muted-foreground tabular-nums">2,184 decisions · 4 controls · 0 exceptions</span>
            </div>
          </div>
        </Reveal>

        <Reveal delay={0.1}>
          <div className="overflow-x-auto rounded-xl border bg-card">
            <table className="w-full min-w-[36rem] text-sm">
              <caption className="sr-only">Controls mapped to evidence</caption>
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th scope="col" className="px-5 py-3 font-medium">Framework</th>
                  <th scope="col" className="px-3 py-3 font-medium">Control</th>
                  <th scope="col" className="px-5 py-3 font-medium">Evidence captured</th>
                </tr>
              </thead>
              <tbody>
                {CONTROLS.map((row) => (
                  <tr key={row.framework} className="border-b last:border-b-0">
                    <th scope="row" className="px-5 py-4 text-left">
                      <span className="rounded-md border bg-surface px-2 py-1 text-xs font-semibold">{row.framework}</span>
                    </th>
                    <td className="px-3 py-4 font-medium">{row.control}</td>
                    <td className="px-5 py-4 text-muted-foreground">{row.evidence}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
