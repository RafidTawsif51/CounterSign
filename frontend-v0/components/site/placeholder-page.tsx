import { ArrowRight } from 'lucide-react'
import { Button } from '@/components/ui/button'

export function PlaceholderPage({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return (
    <main className="mx-auto flex w-full max-w-6xl flex-col px-6 py-24 md:py-32">
      <div className="flex max-w-2xl flex-col gap-5">
        <p className="text-sm text-muted-foreground">{eyebrow}</p>
        <h1 className="text-balance text-4xl font-semibold tracking-tight md:text-5xl">{title}</h1>
        <p className="text-pretty text-lg leading-relaxed text-muted-foreground">{description}</p>
        <div className="pt-3">
          <Button variant="outline" className="h-10 gap-2 px-4" render={<a href="/run" />} nativeButton={false}>
            Watch a live payment run
            <ArrowRight className="size-4" aria-hidden="true" />
          </Button>
        </div>
      </div>
    </main>
  )
}
