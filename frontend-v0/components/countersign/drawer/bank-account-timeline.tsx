import { CircleAlert, FileSignature, Landmark, Phone, PhoneOff } from 'lucide-react'
import type { BankAccount, BankVerificationMethod, CallOutcome } from '@/lib/api'
import { cn } from '@/lib/utils'
import { DrawerSection } from './drawer-section'

const METHOD: Record<BankVerificationMethod, { label: string; Icon: typeof Phone }> = {
  phone_callback: { label: 'Phone callback', Icon: Phone },
  signed_form: { label: 'Signed form', Icon: FileSignature },
  micro_deposit: { label: 'Micro-deposits', Icon: Landmark },
  unverified: { label: 'Not verified', Icon: CircleAlert },
}

const STATUS: Record<BankAccount['status'], { label: string; pill: string; dot: string }> = {
  requested: { label: 'Requested', pill: 'bg-blocked/10 text-blocked', dot: 'bg-blocked ring-blocked/20' },
  active: { label: 'Verified, on file', pill: 'bg-verified/10 text-verified', dot: 'bg-verified ring-verified/20' },
  retired: { label: 'Retired', pill: 'bg-muted text-muted-foreground', dot: 'bg-muted-foreground/50 ring-muted' },
}

function formatDate(iso: string) {
  return new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

export function BankAccountTimeline({
  accounts,
  callOutcome,
}: {
  accounts: BankAccount[]
  /** The live call result, which settles whether a requested account was real. */
  callOutcome?: CallOutcome
}) {
  return (
    <DrawerSection title="Bank accounts" id="accounts">
      <ol className="flex flex-col">
        {accounts.map((account, index) => {
          const status = STATUS[account.status]
          const method = METHOD[account.verification.method]
          const denied = account.status === 'requested' && callOutcome === 'denied'
          const isLast = index === accounts.length - 1
          return (
            <li key={account.id} className="relative flex gap-4 pb-5 last:pb-0">
              {!isLast && <span aria-hidden="true" className="absolute left-[5px] top-4 bottom-0 w-px bg-border" />}
              <span aria-hidden="true" className={cn('relative mt-1.5 size-[11px] shrink-0 rounded-full ring-4', status.dot)} />
              <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                  <p className="font-medium">
                    Account ending <span className="font-mono tabular-nums">{account.last4}</span>
                  </p>
                  <span className={cn('rounded-full px-2 py-0.5 text-xs font-medium', status.pill)}>
                    {denied ? 'Denied by vendor' : status.label}
                  </span>
                </div>
                <p className="text-muted-foreground">
                  {account.bank_name} ·{' '}
                  <span className="tabular-nums">
                    {account.status === 'requested'
                      ? `Requested ${formatDate(account.added_at)}`
                      : `${formatDate(account.added_at)} to ${account.retired_at ? formatDate(account.retired_at) : 'present'}`}
                  </span>
                </p>
                {account.requested_via && (
                  <p className="text-muted-foreground">
                    Came in by: <span className="text-foreground">{account.requested_via}</span>
                  </p>
                )}
                <p
                  className={cn(
                    'flex items-start gap-2 leading-relaxed',
                    account.verification.method === 'unverified' ? 'text-blocked' : 'text-foreground',
                  )}
                >
                  <method.Icon className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                  <span>
                    <span className="font-medium">{method.label}</span>
                    {account.verification.verified_at && (
                      <span className="tabular-nums text-muted-foreground"> · {formatDate(account.verification.verified_at)}</span>
                    )}
                    <span className="block text-muted-foreground">{account.verification.detail}</span>
                  </span>
                </p>
                {denied && (
                  <p className="flex items-start gap-2 leading-relaxed text-blocked">
                    <PhoneOff className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                    The vendor denied this change on the verification call.
                  </p>
                )}
              </div>
            </li>
          )
        })}
      </ol>
    </DrawerSection>
  )
}
