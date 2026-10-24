import { ArrowRight, Lock, PhoneCall, ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { HeroProduct } from './hero-product'

const ASSURANCES = [
  { Icon: PhoneCall, label: 'Calls the number on file, never the one in the email' },
  { Icon: Lock, label: 'Agent has read-only access to bank details' },
  { Icon: ShieldCheck, label: 'Every decision logged for audit' },
]

export function Hero() {
  return (
    <section id="product" className="relative scroll-mt-16 overflow-hidden">
      <div className="bg-dot-grid mask-fade-b pointer-events-none absolute inset-x-0 top-0 h-[560px]" aria-hidden="true" />

      <div className="relative mx-auto flex max-w-6xl flex-col items-center px-6 pt-16 text-center md:pt-24">
        <a
          href="/attack"
          className="group inline-flex items-center gap-2 rounded-full border border-border bg-background py-1 pl-1 pr-3 text-sm shadow-xs transition-colors hover:border-input"
        >
          <span className="rounded-full bg-primary px-2 py-0.5 text-xs font-medium text-primary-foreground">New</span>
          <span className="text-muted-foreground">Open challenge: try to get a payment past the agent</span>
          <ArrowRight
            className="size-3.5 text-muted-foreground transition-transform group-hover:translate-x-0.5"
            aria-hidden="true"
          />
        </a>

        <h1 className="mt-8 max-w-4xl text-balance text-5xl font-semibold leading-[1.02] tracking-tight md:text-7xl">
          Every payment, countersigned.
        </h1>
        <p className="mt-6 max-w-2xl text-pretty text-lg leading-relaxed text-muted-foreground md:text-xl">
          Countersign is the AI accounts-payable agent that runs your weekly payment run and verifies every new bank
          detail with a real phone call before any money moves.
        </p>

        <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
          <Button className="h-12 gap-2 px-6 text-[15px]" render={<a href="/run" />} nativeButton={false}>
            Start a live payment run
            <ArrowRight className="size-4" aria-hidden="true" />
          </Button>
          <Button
            variant="outline"
            className="h-12 bg-background px-6 text-[15px]"
            render={<a href="/attack" />}
            nativeButton={false}
          >
            Try to rob our AI
          </Button>
        </div>

        <ul className="mt-10 flex flex-wrap justify-center gap-x-8 gap-y-3">
          {ASSURANCES.map(({ Icon, label }) => (
            <li key={label} className="flex items-center gap-2 text-sm text-muted-foreground">
              <Icon className="size-4 text-primary" aria-hidden="true" />
              {label}
            </li>
          ))}
        </ul>
      </div>

      <div className="relative mx-auto mt-16 max-w-6xl px-4 pb-20 md:mt-20 md:px-6 md:pb-28">
        <HeroProduct />
      </div>
    </section>
  )
}
