// Project page, sections 4 to 9. Our builds of 21st.dev components, restyled to DESIGN.md:
//   Journey: Animated Beam (dillionverma) with a Multi Step Loader caption (Aceternity). The one signature moment.
//   ScamStory: Sticky Scroll Reveal (manuarora700). Security: Feature Section with Hover Effects (manuarora700), hover toned down.
//   Proof: Stats with Number Ticker (Aceternity) and Comparison (olewandowski1). Closing: CTA with Dashed Grid Lines (Aceternity)
//   with an Interactive Hover Button (dillionverma), without its arrow.
// Numbers are only ones we measured (docs/audit-report.md, the Oct 24 real calls). Red-team figures are not shown here.

import { useInView, useReducedMotion } from "framer-motion";
import {
  Banknote, Check, Crosshair, EyeOff, FileText, Fingerprint, Gauge, Globe, KeyRound, ListOrdered, Lock, Mail, MessageSquareText,
  Phone, ScanSearch, ShieldCheck, X,
} from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { CountersignMark } from "@/components/shared/countersign-mark";
import { iconProps } from "@/components/shared/icon";
import { Money } from "@/components/shared/money";
import { StatusBadge } from "@/components/shared/status-badge";
import { HAS_APP } from "@/lib/landing";
import { cn } from "@/lib/utils";
import { AppLink } from "./app-link";
import { BlurFade, NumberTicker } from "./primitives";

const REPO = "https://github.com/aayushswami123/Countersign";

function SectionHead({ title, lead }: { title: string; lead?: string }) {
  return (
    <div className="mb-8 max-w-[720px]">
      <h2 className="text-xl font-semibold">{title}</h2>
      {lead && <p className="mt-2 text-md text-ink-muted">{lead}</p>}
    </div>
  );
}

// ---------------------------------------------------------------- 4. the payment journey (the signature moment)

const NODES = [
  { icon: Mail, title: "Invoice or email arrives", by: "AP inbox", caption: "A vendor email with an invoice lands in the AP inbox." },
  { icon: FileText, title: "Claude reads it safely", by: "Claude", caption: "Claude fills one fixed form. Text in the document is data, never an instruction." },
  { icon: Gauge, title: "Risk engine checks history", by: "12 months", caption: "The payment is compared with 12 months of this vendor's invoices and bank accounts." },
  { icon: Globe, title: "Apify finds the real number", by: "Apify", caption: "For a new bank account, the vendor's phone number is read from the vendor's own website." },
  { icon: Fingerprint, title: "CRS checks identity", by: "CRS", caption: "CRS checks the vendor, and whoever asked for the change." },
  { icon: Phone, title: "Cartesia and Twilio call", by: "Cartesia, Twilio", caption: "An automated, disclosed call asks the vendor one question." },
  { icon: Banknote, title: "Nessie pays, or it is blocked", by: "Nessie", caption: "Verified payments are paid. A denied change is blocked before any money moves." },
];
const STEP_MS = 650;

export function Journey() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-25% 0px" });
  const reduce = useReducedMotion();
  const [step, setStep] = useState(reduce ? NODES.length : 0); // nodes reached so far
  useEffect(() => {
    if (!inView || reduce || step >= NODES.length) return;
    const t = setTimeout(() => setStep((s) => s + 1), step === 0 ? 150 : STEP_MS);
    return () => clearTimeout(t);
  }, [inView, step, reduce]);
  const current = Math.max(0, Math.min(step, NODES.length) - 1);
  const done = step >= NODES.length;

  return (
    <section id="journey" className="scroll-mt-20 border-b border-rule py-16">
      <div className="mx-auto max-w-[1120px] px-4 sm:px-6">
        <BlurFade>
          <SectionHead title="How it works: the payment journey" lead="Every payment takes the same path. A new bank account adds a phone call that the scammer cannot answer." />
          <div ref={ref}>
            {/* The rail: a row of seven on wide screens, a column on narrow ones. The beam fills each link once, node to node. */}
            <ol className="grid grid-cols-1 lg:grid-cols-7">
              {NODES.map((n, i) => {
                const reached = step > i;
                return (
                  <li key={n.title} className="relative flex gap-3 pb-6 lg:flex-col lg:gap-2 lg:pb-0 lg:pr-3">
                    {i < NODES.length - 1 && (
                      <span aria-hidden className="absolute left-4 top-9 h-[calc(100%-36px)] w-px bg-rule lg:left-9 lg:top-4 lg:h-px lg:w-[calc(100%-36px)]">
                        <span
                          className={cn("absolute inset-0 origin-top bg-accent transition-transform duration-500 lg:origin-left", step > i + 1 ? "scale-100" : "scale-y-0 lg:scale-y-100 lg:scale-x-0")}
                          style={{ transitionTimingFunction: "cubic-bezier(0.2, 0, 0, 1)" }}
                        />
                      </span>
                    )}
                    <span
                      className={cn(
                        "relative grid size-8 shrink-0 place-items-center rounded-md border transition-colors duration-200",
                        reached ? "border-accent bg-accent text-accent-ink" : "border-rule-strong bg-surface text-ink-muted",
                      )}
                    >
                      <n.icon {...iconProps} />
                    </span>
                    <div className="min-w-0">
                      <p className={cn("text-sm font-medium", reached ? "text-ink" : "text-ink-muted")}>{n.title}</p>
                      <p className="text-xs text-ink-muted">{n.by}</p>
                    </div>
                  </li>
                );
              })}
            </ol>

            <div className="mt-8 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
              {/* Caption in the style of a multi-step loader: steps done are ticked, the current one is in ink. */}
              <div className="rounded-lg border border-rule bg-surface p-4" aria-live="polite">
                <p className="mb-2 text-sm text-ink-muted">Step {Math.min(step, NODES.length) || 1} of {NODES.length}</p>
                <p className="min-h-12 text-md">{NODES[current].caption}</p>
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <Outcome status="paid" shown={done} title="A normal invoice" text="Same account as last month. Paid through Nessie." />
                <Outcome status="blocked" shown={done} title="The scam" text="New account, and the real vendor says no. Blocked." />
              </div>
            </div>
          </div>
        </BlurFade>
      </div>
    </section>
  );
}

function Outcome({ status, shown, title, text }: { status: "paid" | "blocked"; shown: boolean; title: string; text: string }) {
  return (
    <div
      className={cn("row-flag rounded-lg border border-rule bg-surface p-4 transition-opacity duration-200", shown ? "opacity-100" : "opacity-40")}
      data-status={status === "blocked" ? "blocked" : undefined}
    >
      <StatusBadge status={status} />
      <p className="mt-2 font-medium">{title}</p>
      <p className="text-sm text-ink-muted">{text}</p>
    </div>
  );
}

// ---------------------------------------------------------------- 5. the scam, step by step

const STORY: { title: string; text: string; visual: ReactNode }[] = [
  {
    title: "An email says: we changed banks, send this week's payment here.",
    text: "It arrives inside Summit Concrete's real invoice thread, from a lookalike domain, asking for $18,613.56 to go to a new account today.",
    visual: <EmailCard />,
  },
  {
    title: "Countersign holds the payment.",
    text: "A new bank account is a hard rule: the payment is held whatever the score says, with every reason on record.",
    visual: <HoldCard />,
  },
  {
    title: "It calls the number already on file, not the one in the email.",
    text: "Apify reads Summit's own website for the number, and it matches the one on file. Nothing in the email is used.",
    visual: <CallCard />,
  },
  {
    title: "The real vendor says: we never changed banks. Payment blocked.",
    text: "On our real call on Oct 24 the payment was blocked 31.5 seconds after the email arrived. No money moved.",
    visual: <BlockedCard />,
  },
];

export function ScamStory() {
  const [active, setActive] = useState(0);
  const refs = useRef<(HTMLLIElement | null)[]>([]);
  useEffect(() => {
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => e.isIntersecting && setActive(Number((e.target as HTMLElement).dataset.i))),
      { rootMargin: "-45% 0px -45% 0px" },
    );
    refs.current.forEach((el) => el && io.observe(el));
    return () => io.disconnect();
  }, []);
  return (
    <section id="scam" className="scroll-mt-20 border-b border-rule bg-surface py-16">
      <div className="mx-auto max-w-[1120px] px-4 sm:px-6">
        <BlurFade>
          <SectionHead title="The scam, step by step" lead="The most common payment fraud there is, played against Countersign with a real phone call." />
          <div className="grid grid-cols-1 gap-10 lg:grid-cols-[minmax(0,1fr)_440px]">
            <ol>
              {STORY.map((s, i) => (
                <li key={s.title} data-i={i} ref={(el) => { refs.current[i] = el; }} className="flex flex-col border-l-2 py-6 pl-5 lg:min-h-[50vh] lg:py-10" style={{ borderColor: active === i ? "var(--accent)" : "var(--rule)" }}>
                  <p className="figure text-sm text-ink-muted">{String(i + 1).padStart(2, "0")}</p>
                  <p className={cn("mt-1 text-lg font-semibold transition-colors", active === i ? "text-ink" : "text-ink-muted")}>{s.title}</p>
                  <p className="mt-2 max-w-[520px] text-ink-muted">{s.text}</p>
                  <div className="mt-4 lg:hidden">{s.visual}</div>
                </li>
              ))}
            </ol>
            <div className="hidden lg:block">
              <div className="sticky top-20">
                <div key={active} className="animate-fade-in">{STORY[active].visual}</div>
              </div>
            </div>
          </div>
        </BlurFade>
      </div>
    </section>
  );
}

function Panel({ children, status }: { children: ReactNode; status?: "held" | "blocked" }) {
  return <div className="row-flag rounded-lg border border-rule bg-paper p-4" data-status={status}>{children}</div>;
}

function EmailCard() {
  return (
    <Panel>
      <p className="text-sm text-ink-muted">Re: Invoice SUM-1253</p>
      <p className="mt-1 text-sm">From <span className="text-blocked-ink underline decoration-blocked/60 underline-offset-2">ar@summit-concrete.co</span></p>
      <p className="text-sm text-ink-muted">Usually from ar@summitconcrete.com</p>
      <div className="mt-3 border-t border-rule pt-3 text-sm">
        <p>We switched banks this month. Please send this week's payment to the account below.</p>
        <p className="mt-2">Harborline Bank, account <span className="figure">•••• 6213</span></p>
        <p className="mt-2">Please process today, our month-end close is tomorrow.</p>
      </div>
    </Panel>
  );
}

function HoldCard() {
  return (
    <Panel status="held">
      <div className="flex items-center justify-between"><StatusBadge status="held" /><Money amount={18613.56} /></div>
      <p className="mt-3 font-medium">Summit Concrete, held for a verification call</p>
      <ul className="mt-2 space-y-1 text-sm text-ink-muted">
        <li>Hard rule: destination differs from the last verified account</li>
        <li>New account <span className="figure">•••• 6213</span>, last verified <span className="figure">•••• 2204</span></li>
        <li>Lookalike domain: <span className="text-blocked-ink">summit-concrete.co</span></li>
        <li>Reply-To differs from the sender; "process today"</li>
      </ul>
    </Panel>
  );
}

function CallCard() {
  return (
    <Panel status="held">
      <p className="text-md font-medium">Calling Summit Concrete at <span className="figure">(•••) •••-0100</span></p>
      <p className="mt-1 text-sm text-ink-muted">Source: the vendor's own website, matched with the number on file</p>
      <p className="mt-3 flex items-center gap-2 text-sm"><ShieldCheck {...iconProps} />Not taken from the email</p>
      <p className="mt-1 text-sm text-ink-muted">Number found by Apify. Voice by Cartesia, call by Twilio.</p>
    </Panel>
  );
}

function BlockedCard() {
  return (
    <Panel status="blocked">
      <div className="flex items-center justify-between"><StatusBadge status="blocked" /><Money amount={18613.56} /></div>
      <div className="mt-3 space-y-2 text-sm">
        <p><span className="text-ink-muted">Countersign</span> Did your company make this change? Please say yes or no.</p>
        <p className="text-md font-medium">"No, we never changed banks."</p>
      </div>
      <p className="mt-3 text-sm text-ink-muted">Blocked 31.5 s after the email arrived. Request marked as fraud.</p>
    </Panel>
  );
}

// ---------------------------------------------------------------- 6. security

const DEFENSES = [
  { icon: EyeOff, title: "Hidden text scanner", text: "Finds white text, tiny fonts, text off the page, zero-width characters and hidden HTML before any model reads the document." },
  { icon: ScanSearch, title: "AI hijack detector", text: "Claude Haiku flags text that addresses an AI or gives orders, with a keyword list that keeps running if Claude is down." },
  { icon: FileText, title: "Reads, never obeys", text: "Document text is data, not commands. The model can only fill vendor, amount, dates and remittance; there is no field for an instruction." },
  { icon: Lock, title: "Two money locks", text: "Two independent guards re-read the destination right before money moves and refuse anything that is not a verified account." },
  { icon: KeyRound, title: "Least privilege", text: "The agent cannot change bank details. Only a confirmed verification call can, through one service that owns those writes." },
  { icon: MessageSquareText, title: "Ask why, and a full audit log", text: "Every decision is logged. Ask why a payment was held and the answer cites the stored evidence." },
];

export function Security() {
  return (
    <section id="security" className="scroll-mt-20 border-b border-rule py-16">
      <div className="mx-auto max-w-[1120px] px-4 sm:px-6">
        <SectionHead title="How it can't be tricked" lead="The first three layers use AI or pattern matching and could be fooled. The last three are plain code, so a fooled AI still cannot move money." />
        {/* Hairlines from 1px gaps over the rule color, so every divider is right at every width. */}
        <ul className="grid grid-cols-1 gap-px overflow-hidden rounded-lg border border-rule bg-rule sm:grid-cols-2 lg:grid-cols-3">
          {DEFENSES.map((d) => (
            <li key={d.title} className="bg-surface p-5 transition-colors hover:bg-sunken">
              <d.icon {...iconProps} className="text-ink-muted" />
              <p className="mt-3 font-medium">{d.title}</p>
              <p className="mt-1 text-sm text-ink-muted">{d.text}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- 7. proof

const COMPARE: { row: string; them: boolean; us: boolean }[] = [
  { row: "Can change where money goes on its own", them: true, us: false },
  { row: "Can act on instructions hidden in an invoice", them: true, us: false },
  { row: "Calls the vendor to verify a new bank account", them: false, us: true },
  { row: "Explains every decision with evidence", them: false, us: true },
  { row: "Logs everything for audit", them: false, us: true },
];

export function Proof() {
  return (
    <section id="proof" className="scroll-mt-20 border-b border-rule bg-surface py-16">
      <div className="mx-auto max-w-[1120px] px-4 sm:px-6">
        <BlurFade>
          <SectionHead title="Proof" lead="What we measured on our own system. The sources are listed under the table." />
          <dl className="grid grid-cols-1 divide-y divide-rule rounded-lg border border-rule bg-paper sm:grid-cols-3 sm:divide-x sm:divide-y-0">
            <Stat label="Poisoned documents caught" note="White text, tiny fonts, text off the page, zero-width characters and hidden HTML">
              <NumberTicker value={9} /> <span className="text-ink-muted">of</span> <span className="figure">9</span>
            </Stat>
            <Stat label="This week's demo run" note="40 invoices in 6.9 s with every service live">
              <span className="text-paid-ink"><NumberTicker value={37} /></span> <span className="text-sm text-ink-muted">paid</span>{" "}
              <span className="text-held-ink"><NumberTicker value={1} /></span> <span className="text-sm text-ink-muted">held</span>{" "}
              <span className="text-blocked-ink"><NumberTicker value={2} /></span> <span className="text-sm text-ink-muted">blocked</span>
            </Stat>
            <Stat label="Times hidden text tricked extraction" note="The classifier missed one zero-width attack; the hidden-text scanner caught it">
              <span className="figure">0</span>
            </Stat>
          </dl>
          <div className="mt-8 overflow-x-auto rounded-lg border border-rule bg-paper">
            <table className="w-full min-w-[520px] text-left">
              <thead>
                <tr className="h-9 border-b border-rule text-sm text-ink-muted">
                  <th className="px-4 font-normal">Countersign against a typical AI agent</th>
                  <th className="w-36 px-3 text-center font-normal">Typical AI agent</th>
                  <th className="w-36 px-4 text-center font-normal">Countersign</th>
                </tr>
              </thead>
              <tbody>
                {COMPARE.map((c) => (
                  <tr key={c.row} className="h-10 border-b border-rule last:border-b-0">
                    <td className="px-4">{c.row}</td>
                    <td className="px-3 text-center"><YesNo yes={c.them} /></td>
                    <td className="px-4 text-center"><YesNo yes={c.us} strong /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-sm text-ink-muted">
            Sources: docs/audit-report.md and docs/security.md in the repository.
            {HAS_APP && <> <AppLink to="/red-team" className="text-accent hover:underline">Red-team results</AppLink> are on their own page.</>}
          </p>
        </BlurFade>
      </div>
    </section>
  );
}

function Stat({ label, note, children }: { label: string; note: string; children: ReactNode }) {
  return (
    <div className="p-5">
      <dt className="text-sm text-ink-muted">{label}</dt>
      <dd className="mt-2 text-xl">{children}</dd>
      <dd className="mt-2 text-sm text-ink-muted">{note}</dd>
    </div>
  );
}

function YesNo({ yes, strong }: { yes: boolean; strong?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-1 text-sm", strong ? "text-ink" : "text-ink-muted")}>
      {yes ? <Check {...iconProps} /> : <X {...iconProps} />}
      {yes ? "Yes" : "No"}
    </span>
  );
}

// ---------------------------------------------------------------- 8. closing CTA and 9. footer

export function ClosingCta() {
  return (
    <section className="relative border-b border-rule py-20">
      {/* Dashed grid lines framing the call to action, after CTA with Dashed Grid Lines. */}
      <div aria-hidden className="pointer-events-none absolute inset-x-0 top-8 border-t border-dashed border-rule-strong" />
      <div aria-hidden className="pointer-events-none absolute inset-x-0 bottom-8 border-t border-dashed border-rule-strong" />
      <div className="relative mx-auto max-w-[1120px] px-4 sm:px-6">
        <div className="relative border-x border-dashed border-rule-strong px-6 py-10 sm:px-10">
          <h2 className="text-xl font-semibold">Think you can get a payment past it?</h2>
          <p className="mt-2 max-w-[560px] text-ink-muted">Send any email or invoice into the live system. Every attempt runs through the real pipeline and lands on the leaderboard.</p>
          <div className="mt-6 flex flex-wrap gap-2">
            <Button asChild variant="primary" className="group relative overflow-hidden">
              <AppLink to="/attack">
                {/* Interactive hover button: a darker fill sweeps in on hover. No arrow. */}
                <span aria-hidden className="absolute inset-0 origin-left scale-x-0 bg-accent-hover transition-transform duration-200 group-hover:scale-x-100" />
                <span className="relative inline-flex items-center gap-2"><Crosshair {...iconProps} />Try to rob our AI</span>
              </AppLink>
            </Button>
            <Button asChild><AppLink to="/leaderboard" newTab><ListOrdered {...iconProps} />See the leaderboard</AppLink></Button>
          </div>
        </div>
      </div>
    </section>
  );
}

export function Footer() {
  return (
    <footer className="mx-auto flex max-w-[1120px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-8 text-sm text-ink-muted sm:px-6">
      <span className="flex items-center gap-2 font-medium text-ink"><CountersignMark />Countersign</span>
      <span>Built at Cal Hacks 13.0. Fictional company, sandbox money only.</span>
      <span className="flex gap-4 sm:ml-auto">
        {HAS_APP && (
          <>
            <AppLink to="/" className="text-accent hover:underline">Live demo</AppLink>
            <AppLink to="/leaderboard" newTab className="text-accent hover:underline">Leaderboard</AppLink>
          </>
        )}
        <a href={REPO} target="_blank" rel="noreferrer" className="text-accent hover:underline">GitHub</a>
      </span>
    </footer>
  );
}
