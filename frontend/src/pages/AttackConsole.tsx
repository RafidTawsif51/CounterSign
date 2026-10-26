import { useMemo, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Crosshair } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AttackCardPicker } from "@/components/attack/attack-card-picker";
import { EmailEditor } from "@/components/attack/email-editor";
import { PdfDropzone, type PdfChoice } from "@/components/attack/pdf-dropzone";
import { iconProps } from "@/components/shared/icon";
import { NotInReplay } from "@/components/shared/not-in-replay";
import { PageHeader } from "@/components/shared/page-header";
import { useCurrentRun } from "@/components/shared/run-context";
import { api } from "@/lib/api";
import { useDataMode } from "@/lib/data-mode";
import { errorMessage } from "@/lib/api-error";
import { CARDS, SAMPLE_PDFS, type AttackPayloadDraft } from "@/lib/attack-cards";
import type { AttackCard, LaunchAttackRequest } from "@/lib/types";

// The attack console. Judges arrive with no instructions: pick a card, edit if they like, launch. This page never says
// whether an attack worked; it sends the judge to their payment, where each step plays out live.

const NAME_KEY = "countersign-attacker-name";

function readName() {
  try {
    return localStorage.getItem(NAME_KEY) ?? "";
  } catch {
    return "";
  }
}

function AttackScreen() {
  const navigate = useNavigate();
  const mode = useDataMode();
  const { pinAttack } = useCurrentRun();
  const [name, setName] = useState(readName);
  const [card, setCard] = useState<AttackCard | null>(null);
  // Each card keeps its own edits, so switching cards and back loses nothing.
  const [drafts, setDrafts] = useState<Record<string, AttackPayloadDraft>>(() => Object.fromEntries(CARDS.map((c) => [c.id, c.payload])));
  const [pdf, setPdf] = useState<PdfChoice | null>({ kind: "sample", file: SAMPLE_PDFS[0].file, label: SAMPLE_PDFS[0].label });
  const [tried, setTried] = useState(false);

  const def = CARDS.find((c) => c.id === card) ?? null;
  const draft = card ? drafts[card] : null;

  const launch = useMutation({
    mutationFn: (req: LaunchAttackRequest) => api.launchAttack(req),
    onSuccess: (res, req) => {
      try {
        localStorage.setItem(NAME_KEY, req.attacker_name);
      } catch {
        // Not remembered; nothing else depends on it.
      }
      pinAttack({
        runId: res.run_id,
        paymentId: res.payment_id,
        attackId: res.attack_id,
        attackerName: req.attacker_name,
        card: req.card,
      });
      // Straight to the payment: its steps play out there, live. The board behind it keeps the attack pinned.
      if (res.queued) toast("Your attack is queued.", { description: "It goes right after the run in progress." });
      navigate(`/app/payments/${res.payment_id}`);
    },
  });

  const missing = !name.trim() ? "Add your name for the leaderboard." : def?.takesPdf && !pdf ? "Add an invoice PDF, or use our sample." : null;

  function submit(e: FormEvent) {
    e.preventDefault();
    setTried(true);
    if (!def || !draft || missing) return;
    launch.mutate({
      attacker_name: name.trim(),
      card: def.id,
      source: "console",
      payload: {
        thread_id: draft.thread_id,
        from_addr: draft.from_addr.trim(),
        ...(draft.reply_to.trim() ? { reply_to: draft.reply_to.trim() } : {}),
        subject: draft.subject.trim() || "(no subject)",
        body: draft.body,
        ...(def.takesPdf && pdf ? (pdf.kind === "sample" ? { pdf: pdf.file } : { pdf_base64: pdf.base64 }) : {}),
      },
    });
  }

  return (
    <>
      <PageHeader
        title="Try to rob us."
        description="Pick an attack or write your own. Countersign will process it in this week's payment run."
      />
      <div className="max-w-[1120px] px-4 py-6 sm:px-6">
        <form onSubmit={submit} className="space-y-8" noValidate>
          <div className="max-w-sm">
            <label htmlFor="attacker-name" className="mb-1 block text-sm font-medium">
              Your name for the leaderboard
            </label>
            <Input
              id="attacker-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={80}
              autoComplete="nickname"
              className="touch-target"
              placeholder="Judge Priya"
              aria-invalid={tried && !name.trim() ? true : undefined}
            />
          </div>

          <AttackCardPicker label="Attack" options={CARDS} value={card} onChange={setCard} />

          {def && draft && (
            <section aria-label="Your attack" className="rounded-lg border border-rule bg-surface p-5">
              <h2 className="text-md font-semibold">{def.takesPdf ? "Your email and invoice" : "Your email"}</h2>
              <p className="mb-4 text-sm text-ink-muted">Pre-filled from the card. Change anything.</p>
              <EmailEditor
                value={draft}
                onChange={(v) => setDrafts((d) => ({ ...d, [def.id]: v }))}
                thread={
                  def.id === "freestyle" ? (
                    <VendorThreadPicker
                      threadId={draft.thread_id}
                      fallbackVendor={def.vendor}
                      onChange={(thread_id) => setDrafts((d) => ({ ...d, freestyle: { ...d.freestyle, thread_id } }))}
                    />
                  ) : (
                    <>
                      Sent into the <span className="text-ink">{def.vendor}</span> invoice thread, as if it came from them.
                    </>
                  )
                }
              />
              {def.takesPdf && (
                <div className="mt-4">
                  <p className="mb-1 text-sm font-medium">Invoice PDF</p>
                  {/* The mock cannot scan an uploaded PDF, so only the sample is offered there. */}
                  <PdfDropzone value={pdf} onChange={setPdf} allowUpload={mode !== "mock"} />
                </div>
              )}
            </section>
          )}

          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <Button type="submit" variant="primary" className="touch-target" disabled={!def || launch.isPending}>
              <Crosshair {...iconProps} />
              {launch.isPending ? "Launching" : "Launch attack"}
            </Button>
            <p className="text-sm text-ink-muted" aria-live="polite">
              {!def
                ? "Pick an attack to start."
                : tried && missing
                  ? <span className="text-ink">{missing}</span>
                  : launch.isError
                    ? <span className="text-ink">The attack was not sent. {errorMessage(launch.error)}. Launch again to retry.</span>
                    : "It goes through the same checks as every invoice this week. Watch the result on the board."}
            </p>
          </div>
        </form>
      </div>
    </>
  );
}

/** Freestyle goes into any vendor's thread: the newest thread per vendor, by vendor name. */
function VendorThreadPicker({ threadId, fallbackVendor, onChange }: { threadId: string; fallbackVendor: string; onChange: (threadId: string) => void }) {
  const { data } = useQuery({ queryKey: ["inbox", "threads"], queryFn: api.threads, staleTime: 30_000 });
  const options = useMemo(() => {
    const byVendor = new Map<string, { threadId: string; name: string }>();
    for (const t of data ?? []) if (t.vendor && !byVendor.has(t.vendor.id)) byVendor.set(t.vendor.id, { threadId: t.thread_id, name: t.vendor.name });
    return [...byVendor.values()].sort((a, b) => a.name.localeCompare(b.name));
  }, [data]);
  // The card's own thread may be a historical one the list does not reach; keep it selectable under its vendor's name.
  const current = options.find((o) => o.threadId === threadId) ?? { threadId, name: fallbackVendor };
  const all = options.some((o) => o.threadId === threadId) ? options : [current, ...options.filter((o) => o.name !== current.name)];

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span>Sent into the invoice thread of</span>
      <Select value={threadId} onValueChange={onChange}>
        <SelectTrigger size="sm" className="w-64" aria-label="Vendor thread">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {all.map((o) => (
            <SelectItem key={o.threadId} value={o.threadId}>
              {o.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

export function AttackConsole() {
  return useDataMode() === "replay" ? (
    <NotInReplay title="Try to rob us." what="Attacks run on the live system, and a replay cannot take one. Exit the replay to launch an attack." />
  ) : (
    <AttackScreen />
  );
}
