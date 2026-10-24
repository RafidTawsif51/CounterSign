'use client'

import { useState } from 'react'
import { Menu } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet'
import { NAV_ITEMS, type NavLabel } from '@/lib/nav'
import { cn } from '@/lib/utils'
import { Wordmark } from './wordmark'

function signIn() {
  toast("Sign-in isn't open yet", { description: 'Countersign is in private pilot. Try the live demo meanwhile.' })
}

export function SiteNav({ current }: { current?: NavLabel }) {
  const [open, setOpen] = useState(false)

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/90 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-6 px-6">
        <a href="/" className="rounded-md focus-visible:outline-2 focus-visible:outline-offset-4">
          <Wordmark />
        </a>

        <nav aria-label="Main" className="hidden min-[880px]:block">
          <ul className="flex items-center gap-7">
            {NAV_ITEMS.map((item) => (
              <li key={item.label}>
                <a
                  href={item.href}
                  aria-current={current === item.label ? 'page' : undefined}
                  className={cn(
                    'text-sm text-muted-foreground transition-colors hover:text-foreground',
                    current === item.label && 'font-medium text-foreground',
                  )}
                >
                  {item.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="flex items-center gap-2">
          <Button variant="ghost" className="hidden h-9 px-3 lg:inline-flex" onClick={signIn}>
            Sign in
          </Button>
          <Button className="hidden h-9 px-4 sm:inline-flex" render={<a href="/attack" />} nativeButton={false}>
            Try to rob our AI
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="size-9 min-[880px]:hidden"
            aria-label="Open menu"
            onClick={() => setOpen(true)}
          >
            <Menu className="size-5" aria-hidden="true" />
          </Button>
        </div>
      </div>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="right" className="w-full gap-0 p-6 sm:max-w-xs">
          <SheetTitle className="sr-only">Menu</SheetTitle>
          <Wordmark />
          <nav aria-label="Mobile" className="mt-8">
            <ul className="flex flex-col">
              {NAV_ITEMS.map((item) => (
                <li key={item.label}>
                  <a
                    href={item.href}
                    onClick={() => setOpen(false)}
                    aria-current={current === item.label ? 'page' : undefined}
                    className="block border-b border-border py-3 text-base text-foreground"
                  >
                    {item.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
          <div className="mt-8 flex flex-col gap-2">
            <Button className="h-10" render={<a href="/attack" />} nativeButton={false}>
              Try to rob our AI
            </Button>
            <Button variant="outline" className="h-10" onClick={signIn}>
              Sign in
            </Button>
          </div>
        </SheetContent>
      </Sheet>
    </header>
  )
}
