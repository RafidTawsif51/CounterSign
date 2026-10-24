import { useEffect, useRef, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { EvidenceRef } from "@/components/payment/evidence";
import { Section } from "@/components/payment/section";
import { InlineError } from "@/components/shared/inline-error";
import { api } from "@/lib/api";
import { ASK_BUDGET_MS, drawerTarget, suggestedQuestions } from "@/lib/ask";
import { signalInfo } from "@/lib/risk-catalog";
import type { AskAnswer, AskClaim, AskEvidence, PaymentDetail } from "@/lib/types";
import { cn } from "@/lib/utils";

// "Ask about this payment": a question in, a plain answer out, every claim cited by the stored record that backs it.
// The answer is read-only explanation (POST /api/payments/{id}/ask cannot change anything). No avatar, no typing dots:
// a thin line runs against the 5-second budget while it waits.

/** Open the drawer at `/payments/:id?ask=1` (the ⌘K "Ask why…" command) and the question field takes focus. */
export const ASK_PARAM = "ask";

interface Exchange {
  /** What was asked. The response's question can be the cache's normalized form ("why was this blocked"). */
  question: string;
  answer: AskAnswer;
  ms: number;
}

export function AskPanel({ detail }: { detail: PaymentDetail }) {
  const [question, setQuestion] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const [params, setParams] = useSearchParams();

  const ask = useMutation({
    mutationFn: async (q: string): Promise<Exchange> => {
      const started = performance.now();
      const answer = await api.ask(detail.payment.id, q);
      return { question: q, answer, ms: performance.now() - started };
    },
  });

  // Arriving from ⌘K: wait out the drawer's slide-in, then take focus. The param is dropped so a reload does not repeat it.
  useEffect(() => {
    if (!params.has(ASK_PARAM)) return;
    const id = window.setTimeout(() => {
      input.current?.focus();
      setParams((p) => (p.delete(ASK_PARAM), p), { replace: true });
    }, 220);
    return () => window.clearTimeout(id);
  }, [params, setParams]);

  function submit(q: string) {
    const text = q.trim();
    if (text.length < 3 || ask.isPending) return;
    setQuestion(text);
    ask.mutate(text);
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    submit(question);
  }

  return (
    <Section title="Ask about this payment">
      <section aria-label="Ask about this payment">
        <form onSubmit={onSubmit} className="flex gap-2">
          <Input
            ref={input}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            maxLength={500}
            placeholder="Ask why it was paid, held or blocked"
            aria-label="Question about this payment"
          />
          <Button type="submit" disabled={ask.isPending || question.trim().length < 3}>
            Ask
          </Button>
        </form>

        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
          {suggestedQuestions(detail.payment.status).map((q) => (
            <Button key={q} variant="link" size="sm" className="h-6 text-sm" disabled={ask.isPending} onClick={() => submit(q)}>
              {q}
            </Button>
          ))}
        </div>

        <div aria-live="polite">
          {ask.isPending && <Waiting key={ask.submittedAt} question={ask.variables ?? ""} />}
          {ask.isError && !ask.isPending && (
            <InlineError what="The answer" error={ask.error} onRetry={() => ask.variables && ask.mutate(ask.variables)} className="mt-4" />
          )}
          {ask.data && !ask.isPending && <Answer exchange={ask.data} detail={detail} />}
        </div>
      </section>
    </Section>
  );
}

/** The question being asked and a line that fills over the 5-second budget. */
function Waiting({ question }: { question: string }) {
  const [started, setStarted] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setStarted(true));
    return () => cancelAnimationFrame(id);
  }, []);
  return (
    <div className="mt-4" aria-busy>
      <p className="text-sm text-ink-muted">{question}</p>
      <div className="mt-2 h-0.5 w-full bg-rule" role="progressbar" aria-label="Waiting for the answer">
        <div
          className="h-full bg-ink ease-linear"
          style={{ width: started ? "100%" : "0%", transitionProperty: "width", transitionDuration: `${ASK_BUDGET_MS}ms` }}
        />
      </div>
    </div>
  );
}

function Answer({ exchange, detail }: { exchange: Exchange; detail: PaymentDetail }) {
  const { question, answer, ms } = exchange;
  const records = new Map(answer.evidence.map((e) => [e.id, e]));
  const over = ms > ASK_BUDGET_MS;

  return (
    <div className="mt-4">
      <p className="text-sm text-ink-muted">{question}</p>
      {/* Model output built from untrusted evidence: plain text only. The claims are the answer, each followed by the id
          that backs it; the prose answer is shown only when no claim survived (the backend drops uncited claims). */}
      <p className="mt-1.5 max-w-[72ch] text-md">
        {answer.claims.length > 0
          ? answer.claims.map((c, i) => (
              <span key={i}>
                {i > 0 && " "}
                {head(c.text)}
                {/* The chip stays on the line of the claim's last word instead of wrapping alone. */}
                <span className="whitespace-nowrap">
                  {tail(c.text)}
                  <Citation claim={c} record={records.get(c.evidence_id)} detail={detail} />
                </span>
              </span>
            ))
          : answer.answer}
      </p>
      <p className="mt-2 flex flex-wrap gap-x-3 text-sm text-ink-muted">
        <span>
          answered in <span className={cn("figure", over ? "text-ink" : "text-ink-muted")}>{seconds(ms)}</span>
          {over && " (over the 5s target)"}
        </span>
        <span>{sourceNote(answer)}</span>
      </p>
    </div>
  );
}

/** `1.8s`; a cached answer comes back in milliseconds, which reads as `0.04s` rather than a broken-looking `0.0s`. */
const seconds = (ms: number) => (ms < 100 ? `${(ms / 1000).toFixed(2)}s` : `${(ms / 1000).toFixed(1)}s`);

const head = (text: string) => text.slice(0, text.lastIndexOf(" ") + 1);
const tail = (text: string) => text.slice(text.lastIndexOf(" ") + 1);

function sourceNote(a: AskAnswer) {
  if (a.claims.length === 0) return "No stored record backs an answer to this.";
  const n = new Set(a.claims.map((c) => c.evidence_id)).size;
  const from = `from ${n} stored record${n === 1 ? "" : "s"}`;
  if (a.source === "claude") return `${from}${a.model ? `, written by ${a.model}` : ""}${a.cached ? ", cached" : ""}`;
  return `${from}, template answer (no model call)`;
}

function Citation({ claim, record, detail }: { claim: AskClaim; record?: AskEvidence; detail: PaymentDetail }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <EvidenceRef id={claim.evidence_id} target={drawerTarget(claim.evidence_id, claim, detail)} className="ml-1" title={undefined} />
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-80">
        <p className="font-medium">{recordLabel(record)}</p>
        {record && <p className="mt-0.5">{record.text}</p>}
      </TooltipContent>
    </Tooltip>
  );
}

/** The record's label in the drawer's words, not the backend's internal names. */
function recordLabel(record?: AskEvidence) {
  if (!record) return "Stored record";
  if (record.kind === "signal") return signalInfo(record.label.replace(/^Signal: /, "")).label;
  if (record.kind === "hard_rule") return "Hard rule";
  if (record.kind === "call") return record.label;
  if (record.kind === "audit") return "Audit trail entry";
  if (record.kind === "injection_finding") return "Injection finding";
  if (record.kind === "bank_account") return "Bank account on file";
  return record.label;
}
