import { ArrowRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Reveal } from './reveal'

export function ClosingCta() {
  return (
    <section aria-labelledby="closing-cta" className="px-4 py-24 md:px-6 md:py-32">
      <Reveal className="relative mx-auto max-w-6xl overflow-hidden rounded-3xl border border-border bg-surface">
        <div className="bg-dot-grid pointer-events-none absolute inset-0" aria-hidden="true" />
        <div className="relative flex flex-col items-center gap-6 px-6 py-20 text-center md:py-24">
          <h2 id="closing-cta" className="max-w-3xl text-balance text-3xl font-semibold tracking-tight md:text-5xl">
            Watch it stop a fraudulent payment in under a minute.
          </h2>
          <p className="max-w-xl text-pretty text-lg leading-relaxed text-muted-foreground">
            Run a real payment run with 40 vendors and one attack hidden inside, or try to get a payment past the agent
            yourself.
          </p>
          <div className="mt-2 flex flex-wrap justify-center gap-3">
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
        </div>
      </Reveal>
    </section>
  )
}
