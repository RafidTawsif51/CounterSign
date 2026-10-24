export function DrawerSection({
  title,
  aside,
  id,
  children,
}: {
  title: string
  aside?: React.ReactNode
  id?: string
  children: React.ReactNode
}) {
  const headingId = id ? `${id}-heading` : undefined
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <h2 id={headingId} className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {title}
        </h2>
        {aside}
      </div>
      {children}
    </section>
  )
}
