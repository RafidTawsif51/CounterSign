import { NAV_ITEMS } from '@/lib/nav'
import { Wordmark } from './wordmark'

export function SiteFooter() {
  return (
    <footer className="border-t border-border bg-surface">
      <div className="mx-auto flex max-w-6xl flex-col gap-10 px-6 py-12 md:flex-row md:items-start md:justify-between">
        <div className="flex max-w-xs flex-col gap-3">
          <Wordmark />
          <p className="text-sm leading-relaxed text-muted-foreground">
            The AI accounts-payable agent that verifies before it pays.
          </p>
        </div>
        <nav aria-label="Footer">
          <ul className="grid grid-cols-2 gap-x-12 gap-y-3 sm:grid-cols-3">
            {NAV_ITEMS.map((item) => (
              <li key={item.label}>
                <a href={item.href} className="text-sm text-muted-foreground transition-colors hover:text-foreground">
                  {item.label}
                </a>
              </li>
            ))}
            <li>
              <a href="/attack" className="text-sm text-muted-foreground transition-colors hover:text-foreground">
                Try to rob our AI
              </a>
            </li>
          </ul>
        </nav>
      </div>
      <div className="mx-auto max-w-6xl px-6 pb-10">
        <p className="text-sm text-muted-foreground">© 2026 Countersign, Inc.</p>
      </div>
    </footer>
  )
}
