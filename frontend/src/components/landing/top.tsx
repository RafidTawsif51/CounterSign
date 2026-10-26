// Project page, top of the page: the hero with its sample-run feed, and the sponsor strip.
// Hero feed: Animated List; badge: Animated Shiny Text; headline:
// Encrypted Text; background: a still grid after Animated Grid Pattern (dillionverma). Restyled to DESIGN.md.

import { BookCheck, Crosshair, Lock, PhoneCall, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { iconProps } from "@/components/shared/icon";
import { Money } from "@/components/shared/money";
import { StatusBadge } from "@/components/shared/status-badge";
import { HAS_APP } from "@/lib/landing";
import { cn } from "@/lib/utils";
import type { PaymentStatus } from "@/lib/types";
import { AppLink } from "./app-link";
import { AnimatedList, EncryptedText, Marquee, ShinyText } from "./primitives";

// The sample run, in the order the agent handles it. Amounts are the seeded week's real invoices.
type FeedItem = { id: string; status: PaymentStatus | null; title: string; detail: string; amount?: number };
const FEED: FeedItem[] = [
  { id: "paid-1", status: "paid", title: "Bedrock Excavation", detail: "BED-1120 paid to the verified account", amount: 35047.98 },
  { id: "change", status: null, title: "Bank change requested", detail: "Summit Concrete thread, from summit-concrete.co" },
  { id: "held", status: "held", title: "Summit Concrete held", detail: "New account •••• 7781, lookalike domain", amount: 20189.04 },
  { id: "call", status: "held", title: "Calling the number on file", detail: "(•••) •••-0100, from Summit's own website" },
  { id: "answer", status: null, title: "Vendor answered", detail: "\"We never changed banks.\"" },
  { id: "blocked", status: "blocked", title: "Payment blocked", detail: "Request marked as fraud, attack logged", amount: 20189.04 },
];

function FeedRow({ item }: { item: FeedItem }) {
  return (
    <div
      className={cn("row-flag flex items-start gap-3 rounded-md border border-rule bg-surface px-3 py-2.5")}
      data-status={item.status === "held" || item.status === "blocked" ? item.status : undefined}
    >
      <div className="w-18 shrink-0">
        {item.status ? <StatusBadge status={item.status} /> : <span className="text-xs text-ink-muted">Email</span>}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">{item.title}</p>
        <p className="truncate text-sm text-ink-muted">{item.detail}</p>
      </div>
      {item.amount != null && <Money amount={item.amount} className="shrink-0 text-sm" />}
    </div>
  );
}

const TRUST = [
  { icon: PhoneCall, text: "Calls the number on file, never the one in the email" },
  { icon: Lock, text: "Can't change bank details on its own" },
  { icon: BookCheck, text: "Every decision logged for audit" },
];

export function Hero() {
  return (
    <section className="relative overflow-hidden border-b border-rule">
      {/* A still ledger grid, faint, behind the hero only. */}
      <div aria-hidden className="pointer-events-none absolute inset-0 opacity-60 [background-image:linear-gradient(var(--rule)_1px,transparent_1px),linear-gradient(90deg,var(--rule)_1px,transparent_1px)] [background-size:48px_48px] [mask-image:linear-gradient(to_bottom,black,transparent_85%)]" />
      <div className="relative mx-auto grid max-w-[1120px] grid-cols-1 gap-10 px-4 pb-16 pt-12 sm:px-6 lg:grid-cols-[minmax(0,1fr)_440px] lg:pt-20">
        <div>
          {HAS_APP && (
            <AppLink to="/attack" className="mb-6 inline-flex items-center gap-2 rounded-sm border border-rule-strong bg-surface px-2 py-1 text-sm hover:bg-sunken">
              <Crosshair {...iconProps} className="text-ink-muted" />
              <ShinyText>Open challenge: try to get a payment past the agent</ShinyText>
            </AppLink>
          )}
          <h1 className="text-2xl font-semibold">
            <EncryptedText text="Every payment, countersigned." />
          </h1>
          <p className="mt-4 max-w-[600px] text-md text-ink-muted">
            Countersign is the AI accounts-payable agent that runs your weekly payment run and verifies every new bank detail with a real phone
            call before any money moves.
          </p>
          <div className="mt-6 flex flex-wrap gap-2">
            {HAS_APP ? (
              <>
                <Button asChild variant="primary"><AppLink to="/"><Play {...iconProps} />Start a live payment run</AppLink></Button>
                <Button asChild><AppLink to="/attack"><Crosshair {...iconProps} />Try to rob our AI</AppLink></Button>
              </>
            ) : (
              <Button asChild variant="primary"><a href="#journey"><Play {...iconProps} />See how it works</a></Button>
            )}
          </div>
          <ul className="mt-8 grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
            {TRUST.map((t) => (
              <li key={t.text} className="flex items-start gap-2 text-ink-muted">
                <t.icon {...iconProps} className="shrink-0 text-ink" />
                {t.text}
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-lg border border-rule bg-paper p-3">
          <div className="mb-2 flex items-baseline justify-between px-1">
            <p className="text-sm font-medium">Payment run activity</p>
            <p className="text-xs text-ink-muted">Sample run</p>
          </div>
          <AnimatedList items={FEED} keyOf={(i) => i.id} render={(i) => <FeedRow item={i} />} className="h-82" />
        </div>
      </div>
    </section>
  );
}

const SPONSORS: { name: string; role: string }[] = [
  { name: "Anthropic Claude", role: "reads and explains" },
  { name: "Apify", role: "finds the real number" },
  { name: "CRS", role: "checks identity" },
  { name: "Cartesia", role: "voices the call" },
  { name: "Twilio", role: "places the call" },
  { name: "Capital One Nessie", role: "moves the money" },
];

export function SponsorStrip() {
  return (
    <section aria-label="Built with" className="border-b border-rule py-6">
      <div className="mx-auto flex max-w-[1120px] flex-col gap-3 px-4 sm:px-6 md:flex-row md:items-center md:gap-8">
        <p className="shrink-0 text-sm text-ink-muted">Built with</p>
        <Marquee className="min-w-0 flex-1">
          {SPONSORS.map((s) => (
            <span key={s.name} className="flex items-baseline gap-2 whitespace-nowrap">
              <span className="text-md font-semibold">{s.name}</span>
              <span className="text-sm text-ink-muted">{s.role}</span>
            </span>
          ))}
        </Marquee>
      </div>
    </section>
  );
}
