'use client'

import { useId, useState } from 'react'
import { formatUsdWhole } from '@/lib/format'
import { Reveal } from './reveal'
import { SectionHeading } from './section-heading'

const TARGETED_SHARE = 0.0015
const AUTOMATED_SHARE = 0.85
const LOADED_HOURLY_COST = 62

function compactUsd(value: number) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value)
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  display,
  onChange,
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  display: string
  onChange: (value: number) => void
}) {
  const id = useId()
  const percent = ((value - min) / (max - min)) * 100
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between gap-4">
        <label htmlFor={id} className="text-sm text-primary-foreground/75">
          {label}
        </label>
        <output htmlFor={id} className="text-lg font-semibold tabular-nums">
          {display}
        </output>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-1.5 w-full cursor-pointer appearance-none rounded-full accent-primary-foreground"
        style={{
          background: `linear-gradient(to right, var(--primary-foreground) ${percent}%, color-mix(in oklab, var(--primary-foreground) 20%, transparent) ${percent}%)`,
        }}
      />
    </div>
  )
}

export function RoiCalculator() {
  const [spendMillions, setSpendMillions] = useState(250)
  const [changesPerMonth, setChangesPerMonth] = useState(60)
  const [minutesPerCallback, setMinutesPerCallback] = useState(25)

  const annualSpend = spendMillions * 1_000_000
  const exposure = annualSpend * TARGETED_SHARE
  const manualHours = (changesPerMonth * 12 * minutesPerCallback) / 60
  const hoursReturned = manualHours * AUTOMATED_SHARE
  const remainingHours = manualHours - hoursReturned
  const laborSaved = hoursReturned * LOADED_HOURLY_COST

  return (
    <section id="calculator" aria-labelledby="calculator-heading" className="scroll-mt-20 bg-primary text-primary-foreground">
      <div className="mx-auto grid max-w-6xl gap-14 px-6 py-24 md:py-32 lg:grid-cols-[1fr_1.1fr] lg:items-center">
        <Reveal className="flex flex-col gap-10">
          <div id="calculator-heading">
            <SectionHeading
              inverted
              eyebrow="Exposure estimate"
              title="See what is riding on your next payment run."
              description="Move the sliders to match your payables. The estimate updates as you go."
            />
          </div>

          <div className="flex flex-col gap-8">
            <Slider
              label="Annual vendor spend"
              value={spendMillions}
              min={10}
              max={2000}
              step={10}
              display={compactUsd(annualSpend)}
              onChange={setSpendMillions}
            />
            <Slider
              label="Bank detail change requests per month"
              value={changesPerMonth}
              min={5}
              max={400}
              step={5}
              display={String(changesPerMonth)}
              onChange={setChangesPerMonth}
            />
            <Slider
              label="Minutes spent on each manual callback"
              value={minutesPerCallback}
              min={5}
              max={60}
              step={5}
              display={`${minutesPerCallback} min`}
              onChange={setMinutesPerCallback}
            />
          </div>
        </Reveal>

        <Reveal delay={0.1}>
          <div className="flex flex-col overflow-hidden rounded-xl bg-card text-card-foreground" aria-live="polite">
            <div className="flex flex-col gap-2 border-b p-6 md:p-8">
              <p className="text-sm text-muted-foreground">Spend that attackers could target each year</p>
              <p className="text-5xl font-semibold tabular-nums tracking-tight md:text-6xl">{compactUsd(exposure)}</p>
              <p className="text-sm text-muted-foreground">
                Every dollar of it is countersigned before release.
              </p>
            </div>

            <dl className="grid grid-cols-2 border-b">
              <div className="flex flex-col gap-1 border-r p-6">
                <dt className="text-xs text-muted-foreground">AP hours returned per year</dt>
                <dd className="text-2xl font-semibold tabular-nums">{Math.round(hoursReturned).toLocaleString('en-US')}</dd>
              </div>
              <div className="flex flex-col gap-1 p-6">
                <dt className="text-xs text-muted-foreground">Labor cost recovered</dt>
                <dd className="text-2xl font-semibold tabular-nums">{formatUsdWhole(laborSaved)}</dd>
              </div>
            </dl>

            <div className="flex flex-col gap-4 p-6 md:p-8">
              <p className="text-sm font-medium">Callback hours per year</p>
              <div className="flex flex-col gap-3 text-sm">
                <div className="flex flex-col gap-1.5">
                  <div className="flex justify-between text-muted-foreground">
                    <span>Manual today</span>
                    <span className="tabular-nums">{Math.round(manualHours).toLocaleString('en-US')} h</span>
                  </div>
                  <span className="h-2 rounded-full bg-held" aria-hidden="true" />
                </div>
                <div className="flex flex-col gap-1.5">
                  <div className="flex justify-between text-muted-foreground">
                    <span>With CounterSign</span>
                    <span className="tabular-nums">{Math.round(remainingHours).toLocaleString('en-US')} h</span>
                  </div>
                  <span className="h-2 overflow-hidden rounded-full bg-muted" aria-hidden="true">
                    <span
                      className="block h-full rounded-full bg-verified transition-[width] duration-500"
                      style={{ width: `${(1 - AUTOMATED_SHARE) * 100}%` }}
                    />
                  </span>
                </div>
              </div>
              <p className="text-pretty text-xs leading-relaxed text-muted-foreground">
                Illustrative estimate. Assumes {(TARGETED_SHARE * 100).toFixed(2)}% of spend is targeted, {AUTOMATED_SHARE * 100}% of
                callbacks run without a person, and ${LOADED_HOURLY_COST}/hour loaded AP cost.
              </p>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
