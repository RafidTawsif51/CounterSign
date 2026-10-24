import { useEffect, useState, type ReactNode } from "react";
import {
  Check,
  CircleSlash,
  FileText,
  Inbox,
  Landmark,
  Mail,
  MessageSquareText,
  Phone,
  Play,
  RotateCcw,
  ShieldAlert,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { CallStrip } from "@/components/call/call-strip";
import { VerificationCallPanel } from "@/components/call/verification-call-panel";
import type { CallView, NumberTrust } from "@/lib/calls";
import { iconProps } from "@/components/shared/icon";
import { Money } from "@/components/shared/money";
import { formatUSD } from "@/lib/format";
import { StatusBadge } from "@/components/shared/status-badge";
import type { PaymentStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

type Theme = "light" | "dark";

function readTheme(): Theme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

export function DesignCheck() {
  const [theme, setThemeState] = useState<Theme>(readTheme);

  // Set the attribute before re-rendering so swatches read the new theme's values.
  const setTheme = (t: Theme) => {
    document.documentElement.dataset.theme = t;
    try {
      localStorage.setItem("countersign-theme", t);
    } catch {
      // Storage can be unavailable; the toggle still works for this visit.
    }
    setThemeState(t);
  };

  return (
    <div className="min-h-screen bg-paper text-ink">
      <header className="border-b border-rule bg-paper">
        <div className="mx-auto flex h-12 max-w-[1120px] items-center justify-between gap-4 px-4 sm:px-6">
          <div className="flex items-baseline gap-3">
            <span className="font-semibold">Countersign</span>
            <span className="text-sm text-ink-muted">Design check</span>
          </div>
          <ThemeSwitch theme={theme} onChange={setTheme} />
        </div>
      </header>

      <main className="mx-auto max-w-[1120px] px-4 pb-24 sm:px-6">
        <p className="max-w-[64ch] py-6 text-ink-muted">
          Every token in frontend/DESIGN.md, rendered. This route is not linked from the app. If something here looks
          wrong, fix the token, not the page that uses it.
        </p>

        <Section title="Surfaces and ink" note="Paper is the page. Surface holds content. Hairlines separate it.">
          <TokenGrid
            tokens={[
              ["--paper", "Page background"],
              ["--surface", "Tables, panels, inputs"],
              ["--surface-sunken", "Hover rows, code, wells"],
              ["--ink", "Primary text, totals rules"],
              ["--ink-muted", "Secondary text, pending"],
              ["--ink-faint", "Placeholders, disabled"],
              ["--rule", "Hairline dividers"],
              ["--rule-strong", "Control borders"],
              ["--accent", "Primary action, focus, links"],
            ]}
            theme={theme}
          />
        </Section>

        <Section title="Payment status" note="Color means payment state and nothing else. Badges always carry the word.">
          <div className="grid gap-px overflow-hidden rounded-lg border border-rule bg-rule sm:grid-cols-4">
            {(["pending", "paid", "held", "blocked"] as const).map((s) => (
              <div key={s} className="bg-surface p-4">
                <StatusBadge status={s} />
                <div className="mt-4 grid grid-cols-3 gap-2">
                  <Swatch cssVar={`--status-${s}`} label="Solid" theme={theme} />
                  <Swatch cssVar={`--status-${s}-ink`} label="Text" theme={theme} />
                  <Swatch cssVar={`--status-${s}-tint`} label="Tint" theme={theme} />
                </div>
              </div>
            ))}
          </div>
        </Section>

        <Section title="Type" note="IBM Plex Sans for words. IBM Plex Mono for money, IDs, timestamps and scores.">
          <TypeScale />
        </Section>

        <Section title="Buttons" note="Radius 6. One primary per view. Danger is for reject and block only.">
          <ButtonMatrix />
        </Section>

        <Section
          wide
          title="Ledger table"
          note="Rows are 40px. Flagged rows get a 2px status rule and an 8% tint. Totals sit between a single and a double rule."
        >
          <SampleTable />
        </Section>

        <Section title="Panels and overlays" note="Panels use radius 8 and a hairline. Only overlays cast a shadow.">
          <PanelsAndOverlays />
        </Section>

        <Section
          title="Verification call"
          note="Fixtures for the two outcomes the mock run never produces. A confirmed call releases the payment; no answer keeps it held."
        >
          <CallFixtures />
        </Section>

        <Section title="Icons" note="lucide-react only, 16px, stroke 1.75. Never emoji.">
          <div className="flex flex-wrap gap-x-6 gap-y-3 text-ink">
            {[
              [Inbox, "Inbox"],
              [FileText, "Invoice"],
              [Mail, "Email"],
              [Landmark, "Bank account"],
              [Phone, "Verification call"],
              [ShieldAlert, "Attack detected"],
              [MessageSquareText, "Ask why"],
              [Check, "Approve"],
              [X, "Reject"],
              [CircleSlash, "Block"],
            ].map(([Icon, label]) => {
              const I = Icon as typeof Inbox;
              return (
                <span key={label as string} className="inline-flex items-center gap-2 text-sm">
                  <I {...iconProps} />
                  {label as string}
                </span>
              );
            })}
          </div>
        </Section>
      </main>
    </div>
  );
}

function Section({
  title,
  note,
  wide = false,
  children,
}: {
  title: string;
  note: string;
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <section className={cn("grid gap-4 border-t border-rule py-8", !wide && "lg:grid-cols-[220px_1fr] lg:gap-8")}>
      <div>
        <h2 className="text-md font-semibold">{title}</h2>
        <p className="mt-1 text-sm text-ink-muted">{note}</p>
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

function ThemeSwitch({ theme, onChange }: { theme: Theme; onChange: (t: Theme) => void }) {
  return (
    <div role="radiogroup" aria-label="Theme" className="inline-flex rounded-md border border-rule-strong bg-surface p-0.5">
      {(["light", "dark"] as const).map((t) => (
        <button
          key={t}
          role="radio"
          aria-checked={theme === t}
          onClick={() => onChange(t)}
          className={cn(
            "h-6 rounded-sm px-2.5 text-sm capitalize transition-colors duration-150",
            theme === t ? "bg-accent text-accent-ink" : "text-ink-muted hover:text-ink",
          )}
        >
          {t}
        </button>
      ))}
    </div>
  );
}

// Reads the resolved value so the page shows what the current theme actually renders.
function useCssColor(cssVar: string, theme: Theme) {
  const [value, setValue] = useState("");
  useEffect(() => {
    const probe = document.createElement("span");
    probe.style.color = `var(${cssVar})`;
    document.body.appendChild(probe);
    const rgb = getComputedStyle(probe).color;
    probe.remove();
    setValue(toHex(rgb));
  }, [cssVar, theme]);
  return value;
}

function toHex(color: string) {
  const m = color.match(/[\d.]+/g);
  if (!m || m.length < 3) return color;
  // color-mix resolves to color(srgb r g b) with 0..1 channels; rgb() uses 0..255.
  const scale = color.startsWith("color(") ? 255 : 1;
  return (
    "#" +
    m
      .slice(0, 3)
      .map((n) => Math.round(Number(n) * scale).toString(16).padStart(2, "0"))
      .join("")
  ).toUpperCase();
}

function TokenGrid({ tokens, theme }: { tokens: [string, string][]; theme: Theme }) {
  return (
    <div className="grid overflow-hidden rounded-lg border border-rule bg-surface sm:grid-cols-3">
      {tokens.map(([cssVar, use]) => (
        <TokenCell key={cssVar} cssVar={cssVar} use={use} theme={theme} />
      ))}
    </div>
  );
}

function TokenCell({ cssVar, use, theme }: { cssVar: string; use: string; theme: Theme }) {
  const hex = useCssColor(cssVar, theme);
  return (
    <div className="flex items-center gap-3 border-b border-rule p-3 sm:[&:nth-last-child(-n+3)]:border-b-0 sm:[&:not(:nth-child(3n))]:border-r">
      <span className="size-8 shrink-0 rounded-md border border-rule-strong" style={{ background: `var(${cssVar})` }} />
      <div className="min-w-0">
        <div className="figure text-sm">{cssVar}</div>
        <div className="text-xs text-ink-muted">
          <span className="figure">{hex}</span> <span className="text-ink-faint">/</span> {use}
        </div>
      </div>
    </div>
  );
}

function Swatch({ cssVar, label, theme }: { cssVar: string; label: string; theme: Theme }) {
  const hex = useCssColor(cssVar, theme);
  return (
    <div>
      <div className="h-8 rounded-sm border border-rule" style={{ background: `var(${cssVar})` }} />
      <div className="mt-1 text-xs text-ink-muted">{label}</div>
      <div className="figure text-xs">{hex}</div>
    </div>
  );
}

const typeScale = [
  ["text-2xl", "40/44", "$184,212.50"],
  ["text-xl", "28/34", "Thursday payment run"],
  ["text-lg", "20/28", "Summit Concrete changed bank details"],
  ["text-md", "16/24", "Held for a verification call to the number on file."],
  ["text-base", "14/20", "Body. Invoice 4471 matches 12 months of history except the destination account."],
  ["text-sm", "13/18", "Secondary. Received 09:14 from ar@summit-concrete.co, reply-to differs."],
  ["text-xs", "12/16", "Captions, badges, column notes."],
] as const;

function TypeScale() {
  return (
    <div className="overflow-hidden rounded-lg border border-rule bg-surface">
      {typeScale.map(([cls, metrics, sample], i) => (
        <div
          key={cls}
          className={cn("grid grid-cols-[88px_1fr] items-baseline gap-4 px-4 py-3", i > 0 && "border-t border-rule")}
        >
          <div className="text-xs text-ink-muted">
            <div className="figure text-ink">{metrics}</div>
            {cls}
          </div>
          <div className={cn(cls, "min-w-0 sm:truncate", i === 0 ? "figure font-medium" : i <= 2 && "font-semibold")}>{sample}</div>
        </div>
      ))}
      <div className="grid gap-x-8 gap-y-2 border-t border-rule bg-sunken px-4 py-3 text-sm sm:grid-cols-2">
        <MonoRow label="Amount" value={formatUSD(48_250)} />
        <MonoRow label="Account" value="•••• 4417" />
        <MonoRow label="Invoice" value="INV-2026-4471" />
        <MonoRow label="Payment" value="pay_8c21f0" />
        <MonoRow label="Received" value="2026-10-22 09:14:07" />
        <MonoRow label="Risk score" value="85 / 100" />
      </div>
    </div>
  );
}

function MonoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-ink-muted">{label}</span>
      <span className="figure">{value}</span>
    </div>
  );
}

function ButtonMatrix() {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary">
          <Play {...iconProps} />
          Start payment run
        </Button>
        <Button variant="secondary">
          <Check {...iconProps} />
          Approve payment
        </Button>
        <Button variant="danger">
          <X {...iconProps} />
          Reject payment
        </Button>
        <Button variant="ghost">
          <MessageSquareText {...iconProps} />
          Ask why
        </Button>
        <Button variant="secondary" size="icon" aria-label="Reset demo">
          <RotateCcw {...iconProps} />
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" size="sm">
          Call vendor
        </Button>
        <Button variant="secondary" size="sm">
          Open invoice
        </Button>
        <Button variant="danger" size="sm">
          Block
        </Button>
        <Button variant="ghost" size="sm">
          View audit log
        </Button>
        <Button variant="primary" disabled>
          Run in progress
        </Button>
      </div>
    </div>
  );
}

type Row = {
  vendor: string;
  invoice: string;
  due: string;
  account: string;
  score: number;
  status: PaymentStatus;
  amount: number;
  reason?: string;
};

const rows: Row[] = [
  { vendor: "Bayline Electric", invoice: "INV-88213", due: "Oct 24", account: "2093", score: 6, status: "paid", amount: 12_480 },
  { vendor: "Ortega Framing", invoice: "OF-1180", due: "Oct 24", account: "7715", score: 11, status: "paid", amount: 31_906.4 },
  {
    vendor: "Summit Concrete",
    invoice: "INV-2026-4471",
    due: "Oct 24",
    account: "4417",
    score: 85,
    status: "held",
    amount: 48_250,
    reason: "New bank account, lookalike domain",
  },
  {
    vendor: "Delta Rebar Supply",
    invoice: "DRS-0932",
    due: "Oct 23",
    account: "9051",
    score: 100,
    status: "blocked",
    amount: 22_740,
    reason: "Hidden instructions in PDF",
  },
  { vendor: "Coastline Rentals", invoice: "CR-55021", due: "Oct 25", account: "3368", score: 18, status: "pending", amount: 4_115.75 },
];

const flagged = (s: PaymentStatus) => s === "held" || s === "blocked";

const cycle: PaymentStatus[] = ["pending", "held", "blocked", "paid"];

function SampleTable() {
  const [demoStatus, setDemoStatus] = useState<PaymentStatus>("pending");
  const data = rows.map((r, i) => (i === rows.length - 1 ? { ...r, status: demoStatus } : r));
  const total = data.reduce((sum, r) => sum + r.amount, 0);

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded-lg border border-rule bg-surface">
        <table className="w-full min-w-[820px] border-collapse text-left whitespace-nowrap">
          <thead>
            <tr className="h-9 border-b border-rule text-sm text-ink-muted">
              <th className="px-4 font-medium">Vendor</th>
              <th className="px-3 font-medium">Invoice</th>
              <th className="px-3 font-medium">Due</th>
              <th className="px-3 font-medium">To account</th>
              <th className="px-3 text-right font-medium">Risk</th>
              <th className="px-3 font-medium">Status</th>
              <th className="px-4 text-right font-medium">Amount</th>
            </tr>
          </thead>
          <tbody>
            {data.map((r) => (
              <tr key={r.invoice} data-status={r.status} className={cn("row-flag h-10 border-b border-rule", !flagged(r.status) && "hover:bg-sunken")}>
                <td className="px-4">
                  <div className="font-medium">{r.vendor}</div>
                </td>
                <td className="figure px-3 text-sm text-ink-muted">{r.invoice}</td>
                <td className="px-3 text-sm text-ink-muted">{r.due}</td>
                <td className="figure px-3 text-sm">•••• {r.account}</td>
                <td className={cn("figure px-3 text-right text-sm", r.score >= 60 ? "text-ink" : "text-ink-muted")}>
                  {r.score}
                </td>
                <td className="px-3">
                  <div className="flex items-center gap-2">
                    <StatusBadge status={r.status} />
                    {r.reason && <span className="max-w-[200px] truncate text-xs text-ink-muted">{r.reason}</span>}
                  </div>
                </td>
                <td className="px-4 text-right">
                  <Money amount={r.amount} />
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="h-10">
              <td className="px-4 text-sm text-ink-muted" colSpan={6}>
                {data.length} payments in this run
              </td>
              <td className="px-4 text-right">
                <span className="ledger-total inline-block py-1 font-medium">
                  <Money amount={total} />
                </span>
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setDemoStatus((s) => cycle[(cycle.indexOf(s) + 1) % cycle.length])}
      >
        <RotateCcw {...iconProps} />
        Change Coastline Rentals status (motion check)
      </Button>
    </div>
  );
}

function PanelsAndOverlays() {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="rounded-lg border border-rule bg-surface">
        <div className="flex h-10 items-center border-b border-rule px-4 text-sm font-medium">Hold reasons</div>
        <ul className="divide-y divide-rule text-sm">
          <li className="flex justify-between gap-4 px-4 py-2.5">
            <span>Bank details changed</span>
            <span className="figure text-ink-muted">+30</span>
          </li>
          <li className="flex justify-between gap-4 px-4 py-2.5">
            <span>Lookalike sender domain</span>
            <span className="figure text-ink-muted">+25</span>
          </li>
          <li className="flex justify-between gap-4 px-4 py-2.5">
            <span>Reply-To differs from sender</span>
            <span className="figure text-ink-muted">+15</span>
          </li>
          <li className="flex justify-between gap-4 px-4 py-2.5">
            <span>Urgency language</span>
            <span className="figure text-ink-muted">+15</span>
          </li>
        </ul>
      </div>

      <div className="relative min-h-[200px] overflow-hidden rounded-lg border border-rule bg-sunken">
        <div className="absolute inset-0 bg-scrim" />
        <div className="absolute top-6 right-6 left-6 rounded-lg border border-rule bg-surface p-4 shadow-overlay">
          <div className="font-medium">Reject payment to Summit Concrete?</div>
          <p className="mt-1 text-sm text-ink-muted">
            <Money amount={48_250} /> will not be sent. The request is logged as fraud and added to the leaderboard.
          </p>
          <div className="mt-4 flex justify-end gap-2">
            <Button size="sm">Cancel</Button>
            <Button size="sm" variant="danger">
              Reject payment
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Numbers and sources match the mock seed for these vendors.
const FIXTURE_TRUST: Record<string, NumberTrust> = {
  pay_fixture_confirmed: {
    phone: "+14155550104",
    source: "on_file",
    since: "2025-01-06T17:00:00Z",
    crossCheck: { source: "website", url: "https://www.alderlumber.com/contact", matches: true },
  },
  pay_fixture_no_answer: {
    phone: "+14155550110",
    source: "on_file",
    since: "2025-01-06T17:00:00Z",
    crossCheck: { source: "listing", url: "https://listings.example.com/pacific", matches: true },
  },
};

const FIXTURE_CALLS: CallView[] = [
  {
    paymentId: "pay_fixture_confirmed",
    vendor: "Alder Lumber Co",
    phase: "ended",
    contactSource: "on_file",
    startedAt: "2026-10-22T17:04:10Z",
    endedAt: "2026-10-22T17:04:31Z",
    lines: [
      {
        speaker: "agent",
        text: "Hello, this is an automated assistant calling for Ridgeline Builders accounts payable. This call is recorded. We received a request to change where we send Alder Lumber Co's payments, to an account ending 6630. Did your company make this change?",
      },
      { speaker: "vendor", text: "Yes, we moved to Sutter Federal last month. That's ours." },
      { speaker: "agent", text: "Thank you. The change is confirmed and recorded. Goodbye." },
    ],
    outcome: "confirmed",
    finding: { found: true, sourceUrl: "https://aayushswami123.github.io/Countersign/summit-concrete/contact.html", confidence: "high", agreement: "consistent", sourcesAgree: true, holdReasons: [] },
  },
  {
    paymentId: "pay_fixture_no_answer",
    vendor: "Pacific Rebar",
    phase: "ended",
    contactSource: "on_file",
    startedAt: "2026-10-22T17:06:02Z",
    endedAt: "2026-10-22T17:06:47Z",
    lines: [],
    outcome: "no_answer",
    finding: null,
  },
];

function CallFixtures() {
  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_320px]">
      <div className="space-y-4">
        {FIXTURE_CALLS.map((call) => (
          <div key={call.paymentId} className="overflow-hidden rounded-lg border border-rule bg-surface px-5 py-4">
            <VerificationCallPanel call={call} trust={FIXTURE_TRUST[call.paymentId]} />
          </div>
        ))}
      </div>
      <div className="space-y-2">
        {FIXTURE_CALLS.map((call) => (
          <CallStrip key={call.paymentId} call={call} />
        ))}
      </div>
    </div>
  );
}
