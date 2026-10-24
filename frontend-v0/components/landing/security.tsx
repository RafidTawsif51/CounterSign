import { Check, LockKeyhole, Minus, ScrollText, ShieldCheck, UserRound } from 'lucide-react'
import { Reveal } from './reveal'
import { SectionHeading } from './section-heading'

const PRINCIPLES = [
  {
    Icon: ShieldCheck,
    title: 'Money never moves to a new destination without out-of-band proof.',
    body: 'A new or changed bank account is paid only after the vendor confirms it on a call to the number you already had on file.',
  },
  {
    Icon: LockKeyhole,
    title: "The AI can't change bank details.",
    body: 'Vendor master data is read-only to the agent. Changes need a person with the right role, and every change is logged.',
  },
  {
    Icon: ScrollText,
    title: 'Every decision is explained.',
    body: 'Each payment shows the signals it was scored on, what the agent did and why, written for an auditor to read.',
  },
]

type Access = 'agent' | 'person' | 'never'

const MATRIX: Array<{ action: string; access: Access }> = [
  { action: 'Read invoices and AP email', access: 'agent' },
  { action: 'Score payments and hold anomalies', access: 'agent' },
  { action: 'Call vendors on the number on file', access: 'agent' },
  { action: 'Approve held payments', access: 'person' },
  { action: 'Edit vendor bank details', access: 'person' },
  { action: 'Pay an account that failed verification', access: 'never' },
]

const ACCESS_LABEL: Record<Access, string> = {
  agent: 'Agent',
  person: 'Person with role',
  never: 'No one',
}

function AccessCell({ access }: { access: Access }) {
  const Icon = access === 'agent' ? Check : access === 'person' ? UserRound : Minus
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-sm text-primary-foreground/80">
      <Icon className="size-4" aria-hidden="true" />
      {ACCESS_LABEL[access]}
    </span>
  )
}

export function Security() {
  return (
    <section id="security" className="relative scroll-mt-16 overflow-hidden bg-primary text-primary-foreground">
      <div className="relative mx-auto flex max-w-6xl flex-col gap-14 px-6 py-24 md:py-32">
        <Reveal>
          <SectionHeading
            inverted
            eyebrow="Security"
            title="Rules the agent cannot talk its way around."
            description="However convincing the email, however urgent the invoice, these hold."
          />
        </Reveal>

        <div className="grid gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] lg:gap-16">
          <ul className="flex flex-col">
            {PRINCIPLES.map(({ Icon, title, body }, i) => (
              <Reveal key={title} delay={i * 0.06}>
                <li className="flex gap-5 border-t border-primary-foreground/15 py-7">
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-lg border border-primary-foreground/20 bg-primary-foreground/5">
                    <Icon className="size-4 text-primary-foreground" aria-hidden="true" />
                  </span>
                  <div className="flex flex-col gap-2">
                    <h3 className="text-balance text-lg font-semibold leading-snug tracking-tight">{title}</h3>
                    <p className="text-pretty text-[15px] leading-relaxed text-primary-foreground/70">{body}</p>
                  </div>
                </li>
              </Reveal>
            ))}
          </ul>

          <Reveal delay={0.1}>
            <div className="overflow-hidden rounded-2xl border border-primary-foreground/15 bg-primary-foreground/[0.04]">
              <div className="flex items-center justify-between gap-4 border-b border-primary-foreground/15 px-6 py-4">
                <p className="font-medium">Who can do what</p>
                <p className="text-sm text-primary-foreground/60">Enforced outside the model</p>
              </div>
              <table className="w-full text-left">
                <caption className="sr-only">Permissions for the Countersign agent and your team</caption>
                <thead>
                  <tr className="text-sm text-primary-foreground/60">
                    <th scope="col" className="px-6 py-3 font-normal">
                      Action
                    </th>
                    <th scope="col" className="px-6 py-3 font-normal">
                      Allowed for
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-primary-foreground/10">
                  {MATRIX.map((row) => (
                    <tr key={row.action}>
                      <td className="px-6 py-3.5 text-[15px]">{row.action}</td>
                      <td className="px-6 py-3.5">
                        <AccessCell access={row.access} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  )
}
