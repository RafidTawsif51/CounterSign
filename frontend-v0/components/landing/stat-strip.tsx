import { Reveal } from './reveal'

const STATS = [
  {
    value: 74,
    label: 'of organizations were affected by business email compromise in 2025',
    bar: 'bg-blocked',
  },
  { value: 17, label: 'use AI to fight payments fraud', bar: 'bg-primary' },
]

export function StatStrip() {
  return (
    <section aria-label="Payments fraud in numbers" className="bg-surface">
      <div className="mx-auto flex max-w-6xl flex-col gap-12 px-6 py-20 md:flex-row md:items-end md:justify-between">
        <Reveal className="flex max-w-sm flex-col gap-3">
          <h2 className="text-balance text-2xl font-semibold tracking-tight md:text-3xl">
            The attack is common. The defense is not.
          </h2>
          <p className="text-sm text-muted-foreground">Source: AFP 2026 Payments Fraud and Control Survey</p>
        </Reveal>

        <dl className="grid flex-1 gap-10 sm:grid-cols-2 md:max-w-2xl">
          {STATS.map((stat, i) => (
            <Reveal key={stat.value} delay={i * 0.1} className="flex flex-col gap-4">
              <dt className="sr-only">{stat.label}</dt>
              <dd className="text-6xl font-semibold tracking-tight tabular-nums">
                {stat.value}
                <span className="text-4xl text-muted-foreground">%</span>
              </dd>
              <dd aria-hidden="true" className="h-1 w-full overflow-hidden rounded-full bg-border">
                <span className={`block h-full rounded-full ${stat.bar}`} style={{ width: `${stat.value}%` }} />
              </dd>
              <dd aria-hidden="true" className="text-pretty text-[15px] leading-relaxed text-muted-foreground">
                {stat.label}
              </dd>
            </Reveal>
          ))}
        </dl>
      </div>
    </section>
  )
}
