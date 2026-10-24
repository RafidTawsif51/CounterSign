import { cn } from '@/lib/utils'

export function SectionHeading({
  eyebrow,
  title,
  description,
  align = 'left',
  inverted = false,
}: {
  eyebrow?: string
  title: string
  description?: string
  align?: 'left' | 'center'
  inverted?: boolean
}) {
  return (
    <div className={cn('flex max-w-2xl flex-col gap-4', align === 'center' && 'mx-auto items-center text-center')}>
      {eyebrow && (
        <p
          className={cn(
            'inline-flex items-center gap-2 text-sm font-medium',
            inverted ? 'text-primary-foreground/70' : 'text-primary',
          )}
        >
          <span className={cn('h-px w-6', inverted ? 'bg-primary-foreground/40' : 'bg-primary/40')} aria-hidden="true" />
          {eyebrow}
        </p>
      )}
      <h2 className="text-balance text-3xl font-semibold leading-tight tracking-tight md:text-[2.75rem]">{title}</h2>
      {description && (
        <p
          className={cn(
            'text-pretty text-lg leading-relaxed',
            inverted ? 'text-primary-foreground/70' : 'text-muted-foreground',
          )}
        >
          {description}
        </p>
      )}
    </div>
  )
}
