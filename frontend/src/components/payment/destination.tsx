import { EvidenceRef, useEvidenceSource } from "@/components/payment/evidence";
import { Section } from "@/components/payment/section";
import { diffDomains, domainOf, type DiffPart } from "@/lib/domain-diff";
import { formatAccount, formatDate } from "@/lib/format";
import type { PaymentDetail, Signal } from "@/lib/types";
import { cn } from "@/lib/utils";
import { destinationChanged, requestedAccount } from "@/lib/verdict";

export function Destination({ detail }: { detail: PaymentDetail }) {
  const last = detail.last_verified_account;
  const req = requestedAccount(detail);
  const changed = destinationChanged(detail);
  const signals = detail.risk?.signals_json ?? [];
  const find = (name: string) => signals.find((s) => s.name === name);
  const bank = find("bank_details_changed");
  const confirmedCall = detail.calls.find((c) => c.outcome === "confirmed");

  return (
    <Section title="Where the money would go">
      {!changed && last ? (
        <SameAccount detail={detail} />
      ) : (
        <div className="grid overflow-hidden rounded-lg border border-rule sm:grid-cols-2">
          <AccountCell
            label="Last verified account"
            last4={last?.account_last4}
            bank={last?.bank_name}
            sourceIds={[last?.id, last?.verified_by_call_id]}
            evidenceId={last?.id}
            note={
              !last
                ? "No verified account on file"
                : last.verified_by_call_id
                  ? `Verified by call, ${formatDate(last.valid_from)}`
                  : `Verified at onboarding, ${formatDate(last.valid_from)}`
            }
          />
          <AccountCell
            className="border-t border-rule sm:border-t-0 sm:border-l"
            label="Requested on this invoice"
            last4={req?.account_last4}
            bank={req?.bank_name}
            sourceIds={[bank?.evidence_id]}
            evidenceId={changed ? bank?.evidence_id : undefined}
            emphasis={changed}
            note={
              !req
                ? "No remittance details on the invoice"
                : !changed
                  ? "Same as the last verified account"
                  : confirmedCall
                    ? "Confirmed by the vendor on the verification call"
                    : "Never verified"
            }
          />
        </div>
      )}

      {detail.message && <SenderRows detail={detail} lookalike={find("lookalike_domain")} replyTo={find("reply_to_mismatch")} firstSender={find("first_message_from_sender")} />}
    </Section>
  );
}

/** The invoice pays the account already verified: one line instead of two identical cells. */
function SameAccount({ detail }: { detail: PaymentDetail }) {
  const last = detail.last_verified_account!;
  const source = useEvidenceSource([last.id, last.verified_by_call_id]);
  return (
    <div {...source} className={cn(source.className, "-mx-2 flex flex-wrap items-baseline gap-x-2 px-2 py-1 text-sm")}>
      <span className="text-ink-muted">Pays the last verified account</span>
      <span className="figure text-base font-medium">{formatAccount(last.account_last4)}</span>
      <span className="text-ink-muted">
        {last.bank_name}, {last.verified_by_call_id ? "verified by call" : "verified at onboarding"} {formatDate(last.valid_from)}
      </span>
      <EvidenceRef id={last.id} className="ml-auto" />
    </div>
  );
}

function AccountCell(props: {
  label: string;
  last4?: string;
  bank?: string;
  note: string;
  sourceIds: (string | null | undefined)[];
  evidenceId?: string | null;
  emphasis?: boolean;
  className?: string;
}) {
  const source = useEvidenceSource(props.sourceIds);
  return (
    <div className={cn("bg-surface p-3", props.className)}>
      <div {...source} className={cn(source.className, "-m-1.5 p-1.5")}>
        <div className="flex items-center justify-between gap-2 text-xs text-ink-muted">
          {props.label}
          <EvidenceRef id={props.evidenceId} />
        </div>
        <div className="figure mt-1 text-md font-medium">{props.last4 ? formatAccount(props.last4) : "–"}</div>
        <div className="text-sm text-ink-muted">{props.bank || "Bank not stated"}</div>
        <div className={cn("mt-1 text-sm", props.emphasis ? "font-medium text-ink" : "text-ink-muted")}>{props.note}</div>
      </div>
    </div>
  );
}

function SenderRows({
  detail,
  lookalike,
  replyTo,
  firstSender,
}: {
  detail: PaymentDetail;
  lookalike?: Signal;
  replyTo?: Signal;
  firstSender?: Signal;
}) {
  const msg = detail.message!;
  const known = detail.vendor.email_domain.toLowerCase();
  const sender = domainOf(msg.from_addr);
  const diff = lookalike ? diffDomains(known, sender) : null;
  const local = msg.from_addr.slice(0, msg.from_addr.length - sender.length);

  return (
    <dl className="mt-4 grid grid-cols-[112px_1fr] gap-x-4 gap-y-1.5 text-sm">
      <dt className="text-ink-muted">Vendor domain</dt>
      <dd className="figure min-w-0 break-all">{diff ? <Marked parts={diff.real} /> : known}</dd>

      <EvidenceRow label="Sent from" signal={lookalike ?? firstSender}>
        {local}
        {diff ? <Marked parts={diff.fake} /> : sender}
      </EvidenceRow>

      {msg.reply_to && msg.reply_to.toLowerCase() !== msg.from_addr.toLowerCase() && (
        <EvidenceRow label="Reply-To" signal={replyTo}>
          {msg.reply_to}
        </EvidenceRow>
      )}
    </dl>
  );
}

function EvidenceRow({ label, signal, children }: { label: string; signal?: Signal; children: React.ReactNode }) {
  const source = useEvidenceSource([signal?.evidence_id]);
  return (
    <>
      <dt className="text-ink-muted">{label}</dt>
      <dd {...source} className={cn(source.className, "-mx-1 flex min-w-0 items-center gap-2 px-1")}>
        <span className="figure min-w-0 break-all">{children}</span>
        <EvidenceRef id={signal?.evidence_id} />
      </dd>
    </>
  );
}

/** Characters that differ from the real domain are inverted so a lookalike is visible at a glance. */
function Marked({ parts }: { parts: DiffPart[] }) {
  return (
    <>
      {parts.map((p, i) =>
        p.changed ? (
          <mark key={i} className="rounded-[2px] bg-ink px-px text-paper">
            {p.text}
          </mark>
        ) : (
          <span key={i}>{p.text}</span>
        ),
      )}
    </>
  );
}
