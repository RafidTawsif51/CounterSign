import { BookUser, FileSignature, Globe } from 'lucide-react'
import type { ContactSourceKind } from '@/lib/api'
import { cn } from '@/lib/utils'

const SOURCES: Record<ContactSourceKind, { label: string; Icon: typeof Globe }> = {
  vendor_website: { label: 'From vendor website', Icon: Globe },
  vendor_master_file: { label: 'From vendor master file', Icon: BookUser },
  signed_contract: { label: 'From signed contract', Icon: FileSignature },
}

export function contactSourceLabel(kind: ContactSourceKind) {
  return SOURCES[kind].label
}

export function ContactSourceBadge({ kind, className }: { kind: ContactSourceKind; className?: string }) {
  const { label, Icon } = SOURCES[kind]
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border border-verified/25 bg-verified/10 px-2.5 py-0.5 text-sm font-medium text-verified',
        className,
      )}
    >
      <Icon className="size-3.5" aria-hidden="true" />
      {label}
    </span>
  )
}
