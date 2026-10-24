const SYSTEMS = [
  'NetSuite',
  'QuickBooks Online',
  'Sage Intacct',
  'Xero',
  'Microsoft Dynamics 365',
  'Bill.com',
  'Gmail',
  'Outlook',
  'Procore',
]

export function Integrations() {
  return (
    <section aria-label="Integrations" className="border-y border-border">
      <div className="mx-auto flex max-w-6xl flex-col items-center gap-6 px-6 py-10 md:flex-row md:gap-10">
        <p className="shrink-0 text-pretty text-center text-sm text-muted-foreground md:max-w-44 md:text-left">
          Works alongside the systems your AP team already runs
        </p>
        <div className="mask-fade-x relative w-full overflow-hidden">
          <ul className="animate-marquee flex w-max gap-12 motion-reduce:animate-none">
            {[...SYSTEMS, ...SYSTEMS].map((name, i) => (
              <li
                key={`${name}-${i}`}
                aria-hidden={i >= SYSTEMS.length}
                className="whitespace-nowrap text-lg font-semibold tracking-tight text-foreground/45"
              >
                {name}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}
