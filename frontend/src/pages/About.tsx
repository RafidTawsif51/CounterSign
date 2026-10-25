// The project page (/about): what Countersign is, the moment, how it works, the proof, and every way into the live app.
// See DESIGN.md, Project page. Every number here was measured; each section says where it came from.

import { useQuery } from "@tanstack/react-query";
import { Banknote, Crosshair, ExternalLink, ListOrdered } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CountersignMark } from "@/components/shared/countersign-mark";
import { iconProps } from "@/components/shared/icon";
import { Money } from "@/components/shared/money";
import { StatusBadge } from "@/components/shared/status-badge";
import { api } from "@/lib/api";
import { DOCUMENTED_STATUS, MODE_LABEL } from "@/lib/system-status";
import type { SystemComponentStatus } from "@/lib/types";

const REPO = "https://github.com/aayushswami123/Countersign";

const SECTIONS = [
  { id: "moment", label: "The moment" },
  { id: "how", label: "How it works" },
  { id: "attacks", label: "Attacks it stops" },
  { id: "proof", label: "Proof" },
  { id: "defenses", label: "Defenses" },
  { id: "auditor", label: "Auditor access" },
  { id: "sponsors", label: "Built with" },
  { id: "limits", label: "Limits" },
];

// The real "No" call, Oct 24, every service live (docs/audit-report.md, "Real calls with every service live").
const CALL: { t: string; step: string; detail: ReactNode; by: string }[] = [
  { t: "0.08", step: "Email received", detail: <>Reply in Summit Concrete's real invoice thread from <Evidence>summit-concrete.co</Evidence>: "We switched banks, please process today."</>, by: "Attack console" },
  { t: "1.04", step: "Held", detail: <>Score 100. New account <span className="figure">•••• 6213</span>, lookalike domain, Reply-To mismatch, urgency. Hard rule: destination changed.</>, by: "Risk engine" },
  { t: "1.06", step: "Identity checked", detail: <>Request from <Evidence>summit-concrete.co</Evidence> failed: email risk 88, identity mismatch. Summit itself verified.</>, by: "CRS sandbox" },
  { t: "1.07", step: "Number found", detail: <>Summit's own website, contact page, high confidence. The number in the email is never used.</>, by: "Apify Actor" },
  { t: "2.46", step: "Call placed", detail: <>"Did your company make this change? Please say yes or no."</>, by: "Twilio, Cartesia voice" },
  { t: "31.5", step: "Vendor answered", detail: <>"No, we never changed banks."</>, by: "Twilio speech, Claude" },
];

const STEPS: { step: string; what: string; by: string }[] = [
  { step: "Read", what: "Every invoice PDF and vendor email is read into one fixed form: vendor, amount, due date, remittance. The document is data, never instructions.", by: "Claude Sonnet 5.5" },
  { step: "Scan", what: "White text, tiny fonts, text off the page, zero-width characters and hidden HTML are found in code; a classifier flags text that gives orders to an AI.", by: "Our code, Claude Haiku 5.5" },
  { step: "Score", what: "Hard rules always hold: new bank account, new vendor, hidden instructions, changed contacts, 30% over the vendor's 12-month maximum. Weighted signals cover the rest.", by: "Risk engine" },
  { step: "Find the number", what: "For a changed account, the vendor's phone number is read from the vendor's own website, with the page as proof.", by: "Apify" },
  { step: "Check identity", what: "Reverse phone, email risk and identity verification on the vendor and on whoever asked for the change. A failed check keeps the money held even after a yes.", by: "CRS" },
  { step: "Call", what: "An automated, disclosed call asks one question. Denied blocks the payment; confirmed saves the new account as verified; anything else goes to the controller.", by: "Twilio, Cartesia" },
  { step: "Pay", what: "Only verified destinations are paid, through two independent guards that re-read the account right before money moves.", by: "Capital One Nessie" },
  { step: "Explain", what: "Every decision is in the audit log, and Ask answers why a payment was paid, held or blocked, citing stored evidence.", by: "Claude Haiku 5.5" },
];

const ATTACKS: { name: string; does: string; caught: string; to: string }[] = [
  { name: "We changed banks", does: "Replies in a real invoice thread from a lookalike domain with a new account and a reason to hurry.", caught: "New destination always holds and calls. The vendor says no on the phone.", to: "/attack" },
  { name: "Poisoned invoice", does: "Hides white text in the PDF telling an AI to change the remittance and skip verification.", caught: "Hidden-text scan quarantines the document before any model can act on it.", to: "/inbox" },
  { name: "The CEO approved it", does: "Writes as Ridgeline's CEO: pay today, new account, keep it quiet.", caught: "Authority and secrecy language, lookalike of Ridgeline's own domain, and the same call.", to: "/attack" },
  { name: "Write your own", does: "Any email into any vendor's thread, including a new phone number to call.", caught: "New contact details are ignored. A miss is logged as a new test case.", to: "/attack" },
];

// docs/redteam.md: 200 attacks, 200 clean invoices, 5 legitimate changes; the verification call was simulated in this run.
const REDTEAM: { family: string; base: string; cs: string; baseLost: number; csLost: number }[] = [
  { family: "Bank change", base: "40 of 40", cs: "40 of 40", baseLost: 0, csLost: 0 },
  { family: "Poisoned invoice", base: "33 of 40", cs: "40 of 40", baseLost: 10521, csLost: 0 },
  { family: "CEO pressure", base: "40 of 40", cs: "40 of 40", baseLost: 0, csLost: 0 },
  { family: "Lookalike domain", base: "16 of 40", cs: "40 of 40", baseLost: 460990, csLost: 0 },
  { family: "Amount padding", base: "28 of 40", cs: "26 of 40", baseLost: 0, csLost: 0 },
];

const LAYERS: { name: string; kind: "Probabilistic" | "Deterministic"; what: string }[] = [
  { name: "Hidden-content scan", kind: "Probabilistic", what: "Finds what a person cannot see but a model would read. Flagged 9 of 9 poisoned documents and 0 of 3 clean ones in our audit." },
  { name: "Instruction classifier", kind: "Probabilistic", what: "Claude Haiku flags text that addresses an AI or gives orders, plus a keyword list that runs even if Claude is down." },
  { name: "Fixed-schema extraction", kind: "Probabilistic", what: "The model can only fill vendor, amount, dates and remittance. There is no field for an instruction." },
  { name: "Least privilege", kind: "Deterministic", what: "The payment agent has no function that edits bank details or contacts. Only the verification service can, after a confirmed call." },
  { name: "Hard-rule backstop", kind: "Deterministic", what: "Any new destination means a call, whatever any model says. Even a fully fooled extractor cannot move money." },
];

const SPONSORS: { name: string; role: string; see: string; to: string }[] = [
  { name: "Anthropic", role: "Claude reads every invoice into a fixed form, flags instructions aimed at an AI, judges the vendor's spoken answer, and explains every decision with evidence.", see: "Payment detail, Ask", to: "/" },
  { name: "CRS", role: "Checks the number we dial belongs to the vendor and that whoever asked for the change is who they claim. A failure keeps the money held.", see: "Payment detail, identity step", to: "/" },
  { name: "Apify", role: "Our Vendor Contact Verifier Actor finds the vendor's phone number on the vendor's own website, with the page as proof.", see: "Call card, source link", to: "/" },
  { name: "Twilio", role: "Places the verification call and hears the vendor's answer.", see: "Call card, transcript", to: "/" },
  { name: "Cartesia", role: "The voice of the verification call.", see: "Call card", to: "/" },
  { name: "Capital One Nessie", role: "Moves the money for verified payments, in the sandbox, with the transfer id on every paid payment.", see: "Payment detail, paid step", to: "/" },
];

const LIMITS = [
  "The company is fictional: Ridgeline Builders, 30 vendors and 12 months of history are generated. All money is sandbox money.",
  "Demo calls go to a team phone that plays the vendor. The vendor websites show fictional 555 numbers, and calls only go to an allow list in code.",
  "Approve and reject have no login in the demo. Approve can only pay the vendor's last verified account, never the account a request asked for.",
  "The risk weights are starting points, not validated on real data. Padded invoices from a vendor's real address up to about 1.3 times its maximum pass.",
  "The Twilio account is a trial: the call is transcribed, not recorded, and voicemail is not detected.",
  "CRS answers only for its sandbox test identities, so our vendors and senders are mapped onto them.",
];

export function About() {
  return (
    <div className="min-h-screen bg-paper text-ink">
      <header className="sticky top-0 z-10 border-b border-rule bg-paper">
        <div className="mx-auto flex h-14 max-w-[1120px] items-center gap-3 px-4 sm:px-6">
          <CountersignMark />
          <span className="text-md font-semibold">Countersign</span>
          <span className="hidden text-sm text-ink-muted md:inline">AI accounts payable that never pays a scammer</span>
          <div className="ml-auto flex items-center gap-2">
            <Button asChild variant="ghost" size="sm" className="hidden sm:inline-flex">
              <a href={REPO} target="_blank" rel="noreferrer"><ExternalLink {...iconProps} />Source</a>
            </Button>
            <Button asChild variant="primary" size="sm">
              <Link to="/attack"><Crosshair {...iconProps} />Try to rob us</Link>
            </Button>
          </div>
        </div>
        <nav aria-label="Sections" className="border-t border-rule">
          <div className="mx-auto flex max-w-[1120px] gap-5 overflow-x-auto px-4 sm:px-6">
            {SECTIONS.map((s) => (
              <a key={s.id} href={`#${s.id}`} className="whitespace-nowrap py-2 text-sm text-ink-muted hover:text-ink">
                {s.label}
              </a>
            ))}
          </div>
        </nav>
      </header>

      <main className="mx-auto max-w-[1120px] px-4 sm:px-6">
        <section className="grid grid-cols-1 gap-8 border-b border-rule py-12 lg:grid-cols-[minmax(0,1fr)_400px]">
          <div>
            <h1 className="max-w-[640px] text-xl font-semibold">
              Companies are giving AI agents the keys to their bank accounts. Scammers have noticed. Try to rob ours.
            </h1>
            <p className="mt-4 max-w-[640px] text-md text-ink-muted">
              Countersign is an AI accounts-payable agent that runs a company's weekly vendor payment run. It pays clean invoices on its own and
              holds any payment headed to a new bank account until the vendor confirms it on a phone call Countersign places itself, to a number
              it found on its own. It is built for one- to three-person AP teams paying 50 or more vendors a week, with no security team behind them.
            </p>
            <div className="mt-6 flex flex-wrap gap-2">
              <Button asChild variant="primary"><Link to="/attack"><Crosshair {...iconProps} />Try to rob us</Link></Button>
              <Button asChild><Link to="/"><Banknote {...iconProps} />Open the payment run</Link></Button>
              <Button asChild variant="ghost"><a href="/leaderboard" target="_blank" rel="noreferrer"><ListOrdered {...iconProps} />Leaderboard</a></Button>
            </div>
          </div>
          <dl className="self-start rounded-lg border border-rule bg-surface">
            <div className="border-b border-rule px-4 py-3">
              <dt className="text-sm text-ink-muted">The rule</dt>
              <dd className="mt-1 text-md">Money never goes to a new destination without proof from outside the channel that asked for it.</dd>
            </div>
            <div className="px-4 py-3">
              <dt className="text-sm text-ink-muted">The seat it fills</dt>
              <dd className="mt-1">The AP specialist's weekly payment run and the controller's first review. It never has the power to change where money goes.</dd>
            </div>
          </dl>
        </section>

        <Section id="moment" title="The moment" lead="A real call from our rehearsal on Oct 24, every service live. A judge sends the classic scam; the vendor answers on a real phone.">
          <div className="relative overflow-x-auto rounded-lg border border-rule bg-surface">
            <table className="w-full min-w-[640px] text-left">
              <thead>
                <tr className="h-9 border-b border-rule text-sm text-ink-muted">
                  <th className="w-20 px-4 text-right font-normal">Seconds</th>
                  <th className="px-3 font-normal">Step</th>
                  <th className="px-3 font-normal">What happened</th>
                  <th className="px-4 font-normal">By</th>
                </tr>
              </thead>
              <tbody>
                {CALL.map((r) => (
                  <tr key={r.t} className="border-b border-rule align-top">
                    <td className="figure px-4 py-2.5 text-right text-ink-muted">{r.t}</td>
                    <td className="whitespace-nowrap px-3 py-2.5 font-medium">{r.step}</td>
                    <td className="px-3 py-2.5">{r.detail}</td>
                    <td className="whitespace-nowrap px-4 py-2.5 text-sm text-ink-muted">{r.by}</td>
                  </tr>
                ))}
                <tr className="row-flag align-top" data-status="blocked">
                  <td className="figure px-4 py-2.5 text-right">31.5</td>
                  <td className="px-3 py-2.5"><StatusBadge status="blocked" /></td>
                  <td className="px-3 py-2.5">
                    <Money amount={18613.56} /> stopped. Request marked as fraud, attack logged as caught.
                  </td>
                  <td className="whitespace-nowrap px-4 py-2.5 text-sm text-ink-muted">Countersign</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-sm text-ink-muted">
            The same request from Summit's real domain, answered "Yes, we did", passed CRS, saved the new account as verified and paid through
            Nessie 34.5 seconds after it was sent.
          </p>
        </Section>

        <Section id="how" title="How it works" lead="One payment's journey, and the service behind each step.">
          <ol className="divide-y divide-rule rounded-lg border border-rule bg-surface">
            {STEPS.map((s, i) => (
              <li key={s.step} className="grid grid-cols-1 gap-1 px-4 py-3 sm:grid-cols-[32px_160px_minmax(0,1fr)_200px] sm:gap-4">
                <span className="figure text-ink-muted">{i + 1}</span>
                <span className="font-medium">{s.step}</span>
                <span>{s.what}</span>
                <span className="text-sm text-ink-muted sm:text-right">{s.by}</span>
              </li>
            ))}
          </ol>
        </Section>

        <Section id="attacks" title="Attacks it stops" lead="The four cards on the attack console. Every attempt runs through the same pipeline as a real invoice and lands on the leaderboard.">
          <div className="relative overflow-x-auto rounded-lg border border-rule bg-surface">
            <table className="w-full min-w-[720px] text-left">
              <thead>
                <tr className="h-9 border-b border-rule text-sm text-ink-muted">
                  <th className="px-4 font-normal">Attack</th>
                  <th className="px-3 font-normal">What the attacker does</th>
                  <th className="px-3 font-normal">What catches it</th>
                  <th className="px-4 font-normal"><span className="sr-only">Open</span></th>
                </tr>
              </thead>
              <tbody>
                {ATTACKS.map((a) => (
                  <tr key={a.name} className="border-b border-rule align-top last:border-b-0">
                    <td className="whitespace-nowrap px-4 py-3 font-medium">{a.name}</td>
                    <td className="px-3 py-3">{a.does}</td>
                    <td className="px-3 py-3">{a.caught}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-right">
                      <Link to={a.to} className="text-sm text-accent hover:underline">Try it</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        <Section id="proof" title="Proof" lead="200 generated attacks in five families, 200 clean invoices and 5 legitimate bank changes, against a plain Claude agent told to pay valid invoices.">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
            <div>
              <p className="text-sm text-ink-muted">Lost to scammers</p>
              <Money amount={0} className="mt-1 block text-2xl" />
              <p className="mt-2 text-sm text-ink-muted">
                The plain agent lost <Money amount={471512} className="text-ink" />. Countersign caught 186 of 200 and handled 5 of 5 real bank changes;
                the plain agent refused all 5.
              </p>
              <Link to="/red-team" className="mt-3 inline-block text-sm text-accent hover:underline">Red team results</Link>
            </div>
            <div className="relative overflow-x-auto rounded-lg border border-rule bg-surface">
              <table className="w-full min-w-[560px] text-left">
                <thead>
                  <tr className="h-9 border-b border-rule text-sm text-ink-muted">
                    <th className="px-4 font-normal">Family</th>
                    <th className="px-3 text-right font-normal">Plain agent caught</th>
                    <th className="px-3 text-right font-normal">Countersign caught</th>
                    <th className="px-4 text-right font-normal">Plain agent lost</th>
                  </tr>
                </thead>
                <tbody>
                  {REDTEAM.map((r) => (
                    <tr key={r.family} className="h-10 border-b border-rule">
                      <td className="px-4">{r.family}</td>
                      <td className="figure px-3 text-right text-ink-muted">{r.base}</td>
                      <td className="figure px-3 text-right">{r.cs}</td>
                      <td className="px-4 text-right"><Money amount={r.baseLost} /></td>
                    </tr>
                  ))}
                  <tr className="h-10 font-medium">
                    <td className="px-4">All</td>
                    <td className="figure px-3 text-right text-ink-muted">157 of 200</td>
                    <td className="figure px-3 text-right">186 of 200</td>
                    <td className="px-4 text-right"><span className="ledger-total"><Money amount={471512} /></span></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <p className="mt-3 max-w-[760px] text-sm text-ink-muted">
            Honest reading: Countersign's 14 misses are all padded invoices from a vendor's real address, and all 8 of its false positives are one stress case,
            a clean email with a hidden preheader. The verification call was simulated in this run, so a caught redirect shows the payment was routed to a
            call. Source: docs/redteam.md.
          </p>
          <RealVsSimulated />
        </Section>

        <Section id="defenses" title="Defenses" lead="Five layers. The first three use AI or pattern matching and can be fooled. The last two are plain code, so fooling the AI still cannot move money.">
          <ul className="divide-y divide-rule rounded-lg border border-rule bg-surface">
            {LAYERS.map((l, i) => (
              <li key={l.name} className="grid grid-cols-1 gap-1 px-4 py-3 sm:grid-cols-[32px_200px_120px_minmax(0,1fr)] sm:gap-4">
                <span className="figure text-ink-muted">{i + 1}</span>
                <span className="font-medium">{l.name}</span>
                <span><Badge variant={l.kind === "Deterministic" ? "accent" : "neutral"}>{l.kind}</Badge></span>
                <span>{l.what}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-sm text-ink-muted">
            Each defense, the attack it stops and the test that proves it are listed in docs/security.md. 847 backend tests pass.
          </p>
        </Section>

        <Section id="auditor" title="Auditor access" lead="A controller or auditor connects their own Claude to a read-only MCP server and asks what the agent did.">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="rounded-lg border border-rule bg-surface">
              <p className="border-b border-rule px-4 py-2 text-sm text-ink-muted">Asked live on Oct 24</p>
              <div className="px-4 py-3">
                <p className="font-medium">"Did any money go to an unverified account?"</p>
                <p className="mt-2">
                  No. 0 of 1,196 paid payments went to an unverified destination. The two blocked attacks and the one held payment never sent money,
                  and approving the held one would pay the vendor's last verified account.
                </p>
                <p className="mt-2 text-sm text-ink-muted">16.6 seconds, 4 tool calls, every call in the audit log as mcp_reader.</p>
              </div>
            </div>
            <ul className="space-y-2">
              <li>Nine read-only tools: runs, payments, evidence, vendors, the audit log and the leaderboard. None can approve, pay, call, edit or reset.</li>
              <li>Email, invoice and transcript text comes back labeled untrusted, so a scammer's invoice cannot talk to the auditor's AI either.</li>
              <li>Numbers masked to the last four digits, a bearer token, 60 calls a minute.</li>
              <li className="figure overflow-x-auto whitespace-nowrap rounded-md border border-rule bg-sunken px-3 py-2 text-sm">
                claude mcp add --transport http countersign-auditor &lt;backend&gt;/mcp
              </li>
            </ul>
          </div>
        </Section>

        <Section id="sponsors" title="Built with" lead="Each service does one job in the payment's journey. Every one sits behind a mock, and the status page says which are live.">
          <div className="relative overflow-x-auto rounded-lg border border-rule bg-surface">
            <table className="w-full min-w-[640px] text-left">
              <tbody>
                {SPONSORS.map((s) => (
                  <tr key={s.name} className="border-b border-rule align-top last:border-b-0">
                    <td className="whitespace-nowrap px-4 py-3 font-medium">{s.name}</td>
                    <td className="px-3 py-3">{s.role}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-sm text-ink-muted">{s.see}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        <Section id="limits" title="Limits" lead="What is simulated and what we have not proven yet.">
          <ul className="max-w-[760px] list-disc space-y-2 pl-5">
            {LIMITS.map((l) => <li key={l}>{l}</li>)}
          </ul>
        </Section>

        <footer className="flex flex-wrap items-center gap-x-6 gap-y-2 py-8 text-sm text-ink-muted">
          <span>Countersign, Cal Hacks 13.0. Fictional company, sandbox money only.</span>
          <Link to="/" className="text-accent hover:underline">Payment run</Link>
          <Link to="/attack" className="text-accent hover:underline">Attack console</Link>
          <Link to="/status" className="text-accent hover:underline">System status</Link>
          <a href={REPO} target="_blank" rel="noreferrer" className="text-accent hover:underline">Source on GitHub</a>
        </footer>
      </main>
    </div>
  );
}

function Section({ id, title, lead, children }: { id: string; title: string; lead: string; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-28 border-b border-rule py-10">
      <h2 className="text-md font-semibold">{title}</h2>
      <p className="mb-5 mt-1 max-w-[760px] text-ink-muted">{lead}</p>
      {children}
    </section>
  );
}

function Evidence({ children }: { children: ReactNode }) {
  return <span className="text-blocked-ink">{children}</span>;
}

/** Live from GET /api/system/status; the documented list when the server does not answer, and it says so. */
function RealVsSimulated() {
  const q = useQuery({ queryKey: ["system-status"], queryFn: api.systemStatus, retry: false });
  const rows: SystemComponentStatus[] = q.data ?? DOCUMENTED_STATUS;
  return (
    <div className="mt-8">
      <div className="mb-2 flex items-baseline gap-3">
        <h3 className="font-medium">Real vs simulated</h3>
        <span className="text-sm text-ink-muted">{q.data ? "Live from this server" : "Documented list (server not answering)"}</span>
        <Link to="/status" className="ml-auto text-sm text-accent hover:underline">System status</Link>
      </div>
      <ul className="divide-y divide-rule rounded-lg border border-rule bg-surface">
        {rows.map((r) => (
          <li key={r.name} className="grid grid-cols-1 gap-1 px-4 py-2.5 sm:grid-cols-[240px_110px_minmax(0,1fr)] sm:gap-4">
            <span className="font-medium">{r.name}</span>
            <span><Badge variant={r.mode === "real" ? "accent" : "neutral"}>{MODE_LABEL[r.mode]}</Badge></span>
            <span className="text-ink-muted">{r.detail}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
