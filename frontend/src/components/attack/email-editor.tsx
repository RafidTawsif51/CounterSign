import { useId, type ReactNode } from "react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { AttackPayloadDraft } from "@/lib/attack-cards";

// The attack email, pre-filled from the card and fully editable. What is typed here is sent as is.
export function EmailEditor({
  value,
  onChange,
  thread,
}: {
  value: AttackPayloadDraft;
  onChange: (v: AttackPayloadDraft) => void;
  /** The "Sent into" line, or a vendor picker for freestyle. */
  thread: ReactNode;
}) {
  const set = (k: keyof AttackPayloadDraft) => (e: { target: { value: string } }) => onChange({ ...value, [k]: e.target.value });
  return (
    <div className="space-y-3">
      <div className="text-sm text-ink-muted">{thread}</div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="From">
          {(id) => <Input id={id} value={value.from_addr} onChange={set("from_addr")} className="figure" spellCheck={false} autoComplete="off" />}
        </Field>
        <Field label="Reply-To" hint="optional">
          {(id) => <Input id={id} value={value.reply_to} onChange={set("reply_to")} className="figure" spellCheck={false} autoComplete="off" placeholder="Same as From" />}
        </Field>
      </div>
      <Field label="Subject">{(id) => <Input id={id} value={value.subject} onChange={set("subject")} />}</Field>
      <Field label="Body">{(id) => <Textarea id={id} value={value.body} onChange={set("body")} rows={11} className="leading-[20px]" />}</Field>
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: (id: string) => ReactNode }) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium">
        {label}
        {hint && <span className="font-normal text-ink-muted"> {hint}</span>}
      </label>
      {children(id)}
    </div>
  );
}
