import { ArrowUpRight } from 'lucide-react'
import { APP_NAV_ITEMS, type AppNavLabel } from '@/lib/nav'
import { cn } from '@/lib/utils'
import { Wordmark } from './wordmark'

export function AppNav({ current }: { current: AppNavLabel }) {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/90 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl flex-col gap-1 px-6 pt-3 sm:h-14 sm:flex-row sm:items-center sm:gap-8 sm:pt-0">
        <div className="flex items-center justify-between">
          <a href="/" className="rounded-md focus-visible:outline-2 focus-visible:outline-offset-4">
            <Wordmark />
          </a>
          <a href="/" className="text-sm text-muted-foreground hover:text-foreground sm:hidden">
            Site
          </a>
        </div>

        <nav aria-label="Demo" className="-mx-2 overflow-x-auto sm:mx-0 sm:h-full">
          <ul className="flex h-full items-stretch">
            {APP_NAV_ITEMS.map((item) => {
              const active = item.label === current
              return (
                <li key={item.label} className="flex">
                  <a
                    href={item.href}
                    aria-current={active ? 'page' : undefined}
                    className={cn(
                      'relative flex items-center whitespace-nowrap px-3 py-3 text-sm transition-colors sm:py-0',
                      'after:absolute after:inset-x-3 after:-bottom-px after:h-0.5 after:rounded-full',
                      active
                        ? 'font-medium text-foreground after:bg-foreground'
                        : 'text-muted-foreground hover:text-foreground',
                    )}
                  >
                    {item.label}
                  </a>
                </li>
              )
            })}
          </ul>
        </nav>

        <a
          href="/"
          className="ml-auto hidden items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground sm:flex"
        >
          Back to site
          <ArrowUpRight className="size-3.5" aria-hidden="true" />
        </a>
      </div>
    </header>
  )
}
